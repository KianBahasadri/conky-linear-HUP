import copy
import json
import sys

import pytest

import benchmark_overlays as benchmark

sys.path.insert(0, str(benchmark.BENCH))
from verify_report import verify

POLICY = json.loads((benchmark.BENCH / "policy.json").read_text())


def measurements():
    runs = []
    for role in ("baseline", "candidate"):
        for repeat in range(1, 4):
            runs.append({"role": role, "profile": "single", "repetition": repeat,
                         "steady": {"cpu_core_percent": 12.0, "pss_mib": 100.0, "peak_rss_mib": 400.0},
                         "burst": {"cpu_core_percent": 25.0, "pss_mib": 120.0, "peak_rss_mib": 500.0},
                         "render_p95_cpu_ms": 3.0,
                         "render_windows": {"git-overlay-0": {"p95_cpu_ms": 2.0, "frames": 10}}})
    return runs


def complete_report():
    runs = measurements()
    for result in runs:
        result.update(windows=9, fetch_loops=13)
        result["render_windows"] = {f"overlay-{i}": {"p95_cpu_ms": 2.0, "frames": 10} for i in range(9)}
        for phase in ("warmup", "steady", "burst"):
            duration = POLICY["settings"][phase+"_seconds"]
            result.setdefault(phase, {})
            result[phase].update(wall_seconds=duration, cpu_seconds=2.0,
                samples=[{"time": 100.0, "cpu_seconds": 10.0, "pss_mib": 100, "rss_mib": 400,
                          "cgroup_memory_mib": 110, "processes": 50},
                         {"time": 100.0+duration, "cpu_seconds": 12.0, "pss_mib": 100, "rss_mib": 400,
                          "cgroup_memory_mib": 110, "processes": 50}])
    rows, _ = benchmark.compare(runs, POLICY, ["single"], 3)
    proof = copy.deepcopy(runs[3])
    proof.update(repetition="regression-proof", injected_regression=True)
    proof["steady"]["cpu_core_percent"] = 100.0
    runs.append(proof)
    limit = next(row["limit"] for row in rows if row["metric"] == "steady.cpu_core_percent")
    return {"status": "pass", "smoke": False, "failures": [], "runs": runs, "comparisons": rows,
            "profiles": {"single": POLICY["profiles"]["single"]}, "settings": POLICY["settings"],
            "fixture_version": POLICY["fixture_version"], "baseline_commit": POLICY["baseline_commit"],
            "changes": {"draw": {}, "env": {}},
            "regression_proof": {"rejected": True, "observed_cpu_core_percent": 100.0, "limit": limit}}


def test_regression_budget_rejects_cpu_memory_and_individual_slow_panel():
    runs = measurements()
    for result in runs[3:]:
        result["steady"]["cpu_core_percent"] = 90.0
        result["injected_regression"] = True
        result["burst"]["peak_rss_mib"] = 900.0
        result["render_windows"]["git-overlay-0"]["p95_cpu_ms"] = 30.0
    _, failures = benchmark.compare(runs, POLICY, ["single"], 3)
    assert any("steady.cpu_core_percent" in error for error in failures)
    assert any("burst.peak_rss_mib" in error for error in failures)
    assert any("window:git-overlay-0" in error for error in failures)


def test_one_outlier_does_not_turn_noise_into_a_regression():
    runs = measurements()
    runs[-1]["steady"]["cpu_core_percent"] = 100.0
    _, failures = benchmark.compare(runs, POLICY, ["single"], 3)
    assert failures == []


def test_noisy_baseline_is_inconclusive_and_fails():
    runs = measurements()
    runs[0]["steady"]["cpu_core_percent"] = 100.0
    _, failures = benchmark.compare(runs, POLICY, ["single"], 3)
    assert any("baseline too noisy" in error for error in failures)


@pytest.mark.parametrize("fault", ["missing_repeat", "missing_panel", "nan", "infinity", "zero"])
def test_missing_or_invalid_measurements_fail(fault):
    runs = measurements()
    if fault == "missing_repeat":
        runs.pop()
    elif fault == "missing_panel":
        runs[-1]["render_windows"].clear()
    else:
        runs[-1]["steady"]["cpu_core_percent"] = {"nan": float("nan"), "infinity": float("inf"), "zero": 0.0}[fault]
    with pytest.raises((ValueError, KeyError)):
        benchmark.compare(runs, POLICY, ["single"], 3)


@pytest.mark.parametrize("field,value", [("status", "skipped"), ("smoke", True), ("failures", ["incomplete"]),
                                        ("regression_proof", {"rejected": False}), ("comparisons", []),
                                        ("settings", {}), ("baseline_commit", "other")])
def test_ci_gate_refuses_skipped_missing_or_modified_results(field, value):
    report = complete_report()
    verify(report, POLICY)
    broken = copy.deepcopy(report)
    broken[field] = value
    with pytest.raises((ValueError, KeyError)):
        verify(broken, POLICY)


@pytest.mark.parametrize("fault", ["empty_profile", "wrong_monitors", "duplicate_repetition", "missing_samples", "truncated_phase", "no_processes", "invalid_cpu_total", "nonmonotonic"])
def test_ci_gate_refuses_partial_raw_measurements(fault):
    report = complete_report()
    first = report["runs"][0]
    if fault == "empty_profile":
        report["profiles"] = {}
    elif fault == "wrong_monitors":
        report["profiles"]["single"] = [[1, 1, 0, 0]]
    elif fault == "duplicate_repetition":
        report["runs"][1]["repetition"] = 1
    elif fault == "missing_samples":
        first["steady"]["samples"] = []
    elif fault == "truncated_phase":
        first["steady"]["wall_seconds"] = 1
    elif fault == "no_processes":
        first["steady"]["samples"][0]["processes"] = 0
    elif fault == "invalid_cpu_total":
        first["steady"]["cpu_seconds"] = 999
    else:
        first["steady"]["samples"][1]["time"] = 1
    with pytest.raises((ValueError, KeyError)):
        verify(report, POLICY)


def test_interval_overrides_reject_unrelated_environment_and_nonfinite_values():
    for raw in ("HOME=3", "GIT_REFRESH_SECONDS=nan", "GIT_REFRESH_SECONDS=0", "GIT_REFRESH_SECONDS=1.5"):
        with pytest.raises(ValueError):
            benchmark.assignments([raw], benchmark.ENV_INTERVALS)
    assert benchmark.assignments(["GIT_REFRESH_SECONDS=5"], benchmark.ENV_INTERVALS) == {"GIT_REFRESH_SECONDS": "5"}
    assert benchmark.assignments(["resource-monitor=0.5"]) == {"resource-monitor": 0.5}
