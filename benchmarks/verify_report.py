"""Fail the CI gate on missing, partial, smoke-only or inconsistent results."""
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_overlays import BENCH, compare


def expected_fetch_loops(result, policy):
    """Loop count for this measured revision.

    Thirteen is the pre-optimization suite. The shared GPU producer adds one.
    The candidate adds the OpenCode loop the pinned baseline does not start.
    """
    extra = policy["candidate_extra_fetch_loops"] if result["role"] == "candidate" else 0
    return 13 + int(result["shared_gpu_sampler"]) + extra


def verify_run(result, monitors, policy):
    if (type(result["shared_gpu_sampler"]) is not bool
            or result["windows"] != len(monitors)*9
            or len(result["render_windows"]) != result["windows"]
            or result["fetch_loops"] != expected_fetch_loops(result, policy)):
        raise ValueError("incomplete window or fetch-loop coverage")
    for phase in ("warmup", "steady", "burst"):
        measured = result[phase]
        samples = measured["samples"]
        if len(samples) < 2 or measured["wall_seconds"]+policy["settings"]["sample_seconds"] < policy["settings"][phase+"_seconds"]:
            raise ValueError("missing or truncated measurement phase")
        for sample in samples:
            for key in ("time", "cpu_seconds", "pss_mib", "rss_mib", "cgroup_memory_mib", "processes"):
                if not math.isfinite(sample[key]) or sample[key] <= 0:
                    raise ValueError("missing or invalid raw resource sample")
        for before, after in zip(samples, samples[1:]):
            if after["time"] <= before["time"] or after["cpu_seconds"] < before["cpu_seconds"]:
                raise ValueError("resource samples are not monotonic")
        if not math.isclose(measured["cpu_seconds"], samples[-1]["cpu_seconds"]-samples[0]["cpu_seconds"]):
            raise ValueError("CPU total differs from raw counters")
        if not math.isclose(measured["wall_seconds"], samples[-1]["time"]-samples[0]["time"]):
            raise ValueError("phase duration differs from raw timestamps")
        if not math.isclose(measured["cpu_core_percent"], measured["cpu_seconds"]/measured["wall_seconds"]*100):
            raise ValueError("CPU percentage differs from raw counters")


def verify(report, policy):
    if report["status"] != "pass" or report["smoke"] or report["failures"]:
        raise ValueError("a complete passing benchmark is required")
    if report["settings"] != policy["settings"] or report["baseline_commit"] != policy["baseline_commit"]:
        raise ValueError("benchmark settings or baseline differ from the reviewed policy")
    if report["regression_commit"] != policy["regression_commit"]:
        raise ValueError("pre-optimization reference differs from the reviewed policy")
    if (not report["profiles"] or report["fixture_version"] != policy["fixture_version"]
            or any(policy["profiles"].get(name) != monitors for name, monitors in report["profiles"].items())):
        raise ValueError("missing or unsupported monitor/fixture configuration")
    if report["changes"] != {"draw": {}, "env": {}}:
        raise ValueError("exploratory interval overrides cannot satisfy CI")
    if not report["regression_proof"]["rejected"]:
        raise ValueError("missing intentional-regression rejection proof")
    for profile, monitors in report["profiles"].items():
        for role in ("baseline", "candidate"):
            runs = [r for r in report["runs"] if r["profile"] == profile and r["role"] == role and r["repetition"] != "regression-proof"]
            if sorted(r["repetition"] for r in runs) != list(range(1, policy["settings"]["repeats"]+1)):
                raise ValueError("missing or duplicate repetitions")
            for result in runs:
                verify_run(result, monitors, policy)
                revision = policy["baseline_commit"] if role == "baseline" else None
                if result["source_revision"] != revision:
                    raise ValueError("measured source revision differs from the reviewed policy")
    rows, failures = compare(report["runs"], policy, list(report["profiles"]), policy["settings"]["repeats"])
    if failures or rows != report["comparisons"]:
        raise ValueError("comparison is failing or inconsistent with raw measurements")
    proofs = [r for r in report["runs"] if r.get("injected_regression")]
    if len(proofs) != 1 or proofs[0]["role"] != "candidate":
        raise ValueError("missing measured regression workload")
    proof = proofs[0]
    verify_run(proof, report["profiles"][proof["profile"]], policy)
    expected_limit = next(row["limit"] for row in rows if row["profile"] == proof["profile"] and row["metric"] == "steady.cpu_core_percent")
    observed = report["regression_proof"]["observed_cpu_core_percent"]
    if (not math.isclose(observed, proof["steady"]["cpu_core_percent"])
            or not math.isclose(expected_limit, report["regression_proof"]["limit"]) or observed <= expected_limit):
        raise ValueError("measured intentional regression did not exceed the actual policy limit")
    legacy_runs = [r for r in report["runs"] if r["role"] == "legacy"]
    legacy_proofs = report["legacy_regression_proofs"]
    profiles = sorted(report["profiles"])
    if (sorted(r["profile"] for r in legacy_runs) != profiles
            or sorted(p["profile"] for p in legacy_proofs) != profiles):
        raise ValueError("missing or duplicate pre-optimization regression proof")
    for legacy in legacy_runs:
        profile = legacy["profile"]
        verify_run(legacy, report["profiles"][profile], policy)
        evidence = next(p for p in legacy_proofs if p["profile"] == profile)
        limit = next(row["limit"] for row in rows
                     if row["profile"] == profile and row["metric"] == "steady.cpu_core_percent")
        observed = legacy["steady"]["cpu_core_percent"]
        if (legacy["source_revision"] != policy["regression_commit"]
                or evidence["commit"] != policy["regression_commit"]
                or legacy["injected_regression"] or evidence["rejected"] is not True
                or not math.isclose(evidence["observed_cpu_core_percent"], observed)
                or not math.isclose(evidence["limit"], limit) or observed <= limit):
            raise ValueError("pre-optimization regression did not exceed the actual policy limit")


if __name__ == "__main__":
    verify(json.loads(Path(sys.argv[1]).read_text()), json.loads((BENCH / "policy.json").read_text()))
    print("Verified complete passing performance measurements and regression rejection")
