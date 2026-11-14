# Whole-suite performance benchmarks

Run from the repository root:

```bash
uv run python scripts/benchmark_overlays.py --prove-regression
```

This command benchmarks the pinned reference commit and your current working
tree with the same fixtures, interpreter, native tools, hardware and settings.
It includes uncommitted source changes. It returns nonzero on a regression,
missing prerequisite, incomplete workload, inconsistent measurement or excessive
reference noise. It never changes your desktop's running overlays, production
timers, generated configs, caches, `.env`, credentials, or shell home directory.

## Prerequisites

Linux with cgroup v2 CPU and memory accounting, readable `/proc/*/smaps_rollup`,
Conky with Lua/Cairo and X11 support, Xvfb, fontconfig, uv, git, Bash, flock and
timeout. The Python plotting dependency is installed by `uv sync`.
On Debian/Ubuntu, install `conky-all xvfb fontconfig`. On Arch, install
`conky xorg-server-xvfb fontconfig`. Missing tools fail; no path silently skips.
An existing extracted Xvfb at `cache/benchmark-tools/usr/bin/Xvfb` is also
detected; the benchmark does not download executables automatically.

By default the command starts a temporary delegated systemd user service for
each measurement. On hosts without a systemd user manager, pass
`--cgroup-root /sys/fs/cgroup/your-delegated-empty-subtree` (or set
`CONKY_BENCH_CGROUP_ROOT`). The CI workflow shows the delegation setup for its
ephemeral Ubuntu runner. The subtree needs CPU and memory controllers enabled
and permission to create and migrate processes into child cgroups. Start the
benchmark supervisor inside that subtree as well: Linux requires write access
to the source and destination groups' common ancestor when migrating a process.
CI moves only its measurement-step shell into a `supervisor` child once with
sudo; sampling and measured workloads then live in separate sibling groups.

## Workload and measurement

The benchmark runs the real launcher, Conky windows, Lua renderers, uv, shell
fetch loops and subprocesses. Each run has all panels enabled: nine windows per
monitor, twelve data fetch loops and the desktop-theme watcher loop. Sessions
are merged into Git, as on the production desktop.

The profiles and measurement policy live in
[`benchmarks/policy.json`](../benchmarks/policy.json). `single` uses one
1920×1080 monitor; `dual` uses two adjacent 1920×1080 monitors. Each profile runs
the reference and candidate three times, alternating which runs first. Each
run waits for every fetcher and window to complete, then records a five-second
warm-up, twenty seconds of steady operation with production timers, and twelve
seconds of intensive refreshes. The warm-up is excluded from the comparisons.

Refresh bursts interrupt the actual fetch loops' sleeping children every six
seconds. They also invalidate repository discovery, Actions results, workout
analysis, and AWS's local daily cache. Long-interval fetchers therefore run
without waiting minutes or hours. GPU sampling continues through the actual
resource renderer and helper. Every fetcher and GPU sampling must complete in
the burst phase; every window must draw in both measured phases.

[`benchmarks/fixtures.py`](../benchmarks/fixtures.py) generates versioned fixed
data: sixteen Linear tasks, twelve real Git repositories with 48 files each
(four dirty), six tmux sessions, two Codex and two Cursor cloud accounts, Gemini
quota, 401 contribution days, weather and historical weather, Minecraft status,
AWS and OpenRouter observations, fourteen 900-point TCX runs, a real SQLite ZIP
containing ninety weigh-ins, and two simulated GPUs with 32 DRM clients.
Provider acquisition boundaries and desktop service commands use fixed
responses. Fetchers still parse, normalize, analyze, cache, discover repositories,
spawn helpers and render. Python network connections are rejected and fail the
run. This workload does not model live network latency, credential renewal,
every provider configuration, or the cost of actual GPU drivers.

All suite processes remain in one cgroup, including detached windows, shell
loops, uv, git, CLI stubs, and short-lived descendants. CPU comes from the
kernel's cumulative `cpu.stat`, so helpers that exit between samples are still
counted. Reports include total CPU seconds per phase, CPU as a percentage of
one logical core, and CPU divided by the recorded affinity CPU count. For
example, 100% of one core is 5% of capacity across twenty logical CPUs.

Memory is sampled every 100 ms. Steady memory is the median sample; peaks are
the highest observed samples. PSS apportions shared pages among processes;
summed RSS counts each process's shared pages again. The report also keeps
cgroup memory, which includes charged cache and kernel allocations. These
quantities have different meanings. Samples read processes sequentially and
can miss processes or spikes shorter than the sampling interval; peak RSS is
not an exact high-water mark.

Per-window timing measures Lua draw CPU milliseconds, with p95 comparisons
for each window and the whole suite. Waiting on subprocesses is excluded from
that draw CPU timer but their CPU is included in the cgroup total. Lightweight
supervision and timing instrumentation are included in both measured versions.
The sampler, Xvfb server, real compositor, GPU execution/VRAM, battery and
display-server costs are outside the cgroup. Use a separate live-desktop or
power measurement when changing those paths.

## Results and graphs

Each invocation creates a new dated directory under `cache/benchmarks/`, or
use `--output PATH` to choose a new directory. It retains:

- `report.json`: raw time samples, operation start/end events, all repeated
  measurements, per-window timings, comparison limits, commit and working-tree
  diff fingerprint, copied-source/fixture/harness/policy fingerprints, CPU/core counts,
  interpreter/native-tool versions, monitor geometry, and measurement settings.
- `comparison.md`: readable comparison of the repeated-run medians and limits.
- `usage-single.png` / `.svg` and `usage-dual.png` / `.svg`: candidate timeline
  from the first repetition, with warm-up, steady/idle, and intensive intervals
  shaded. CPU uses a one-second trailing average; memory shows PSS and summed
  RSS. Activity lanes mark actual GPU sampling, repository scans, workout
  processing and billing refreshes.

Raw results preserve every repetition; the chart is an annotated representative
run, not an average across runs. Failed workloads remain in the output directory
for diagnostics. Successful runs remove their isolated working copies.

## Try shorter intervals

Evaluate proposed settings without changing the live desktop:

```bash
uv run python scripts/benchmark_overlays.py --profile single \
  --draw-interval resource-monitor=1 --draw-interval git=2 \
  --env GIT_REFRESH_SECONDS=10 --env SESSIONS_REFRESH_SECONDS=10
```

Draw overrides apply only to copied candidate templates. `--env` accepts only
the production refresh-interval variables listed by the benchmark; all must be
positive integers. You can also edit normal source/configuration first and run
the command with no overrides. Production `.env` values are intentionally not
imported: supply proposed timer values explicitly for the fixed benchmark.

`--smoke --profile single` runs a short harness diagnostic without a performance
comparison. A smoke report cannot satisfy the CI gate or establish a baseline.
`--inject-regression` deliberately
adds a busy CPU process to candidate runs and should return nonzero.

## Baseline review and noise

The baseline commit is explicitly pinned in the policy. Every invocation
re-measures it on the same machine as the candidate; old desktop observations
are not acceptance thresholds. Limits combine a relative margin with an
absolute floor, and compare medians from three runs. A single outlier does not
decide acceptance. The reference noise limit is the larger of 60% of its median
and twice the metric's absolute floor, explicitly set in the policy. A wider
reference range fails as inconclusive. Rerun on a quiet, comparable environment and inspect the raw
ranges; do not widen thresholds to make a candidate pass.

The initial three-run calibration for each monitor profile is preserved in
[`benchmarks/calibration.json`](../benchmarks/calibration.json), including the
environment, observed ranges, comparisons and measured regression rejection.
On that twenty-logical-CPU host, candidate medians were 14.9% of one core and
106 MiB PSS at steady state for one monitor, and 30.7% / 170 MiB for two.
Forced refreshes averaged 59.7% and 75.4% of one core respectively. These are
fixed-fixture observations with all panels enabled; the complete time samples
and annotated graphs remain in the corresponding local reports.

To change a baseline deliberately, make a separate reviewable policy change.
Keep reports for both reference commits and the candidate on the same host,
document why the new workload or cost is acceptable, inspect the graphs and
per-panel comparisons, and rerun the measured intentional-regression proof.
Fixture changes require a fixture-version bump and the same review. The
benchmark never rewrites the policy or baseline automatically.

## CI and acceptance

[CI](../.github/workflows/ci.yml) runs both profiles on standard public-repository
Ubuntu runners on every pull request, push and merge-group event. It uses the
same command with `--profile` per matrix entry, then independently verifies
the report. A further measured run adds a CPU hog and must exceed the policy's
CPU limit, demonstrating rejection of a real resource regression. Correctness
tests also exercise missing/invalid measurements and skipped-result rejection.

The repository's existing active `clusterfork-remote-development:main` ruleset
requires the `test` status context with strict up-to-date checks and no bypass
actors. The workflow preserves that context as an unconditional final gate
depending on correctness and the complete benchmark matrix. It explicitly
requires both results to be `success`; failed, missing, cancelled or skipped
benchmark jobs cannot satisfy it. Remote acceptance workflows that already
wait for `test` inherit the same gate. GitHub accepts skipped required jobs in
general, so this final gate uses `if: always()` and performs explicit result
checks; see [GitHub's status-check guidance](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).

Reports, comparisons and PNG/SVG timelines are uploaded for each profile, even
on failure, with ninety-day retention. Inspect them under the run's Artifacts
and summary on the repository's Actions page; commit-named artifacts provide
the performance history. Local history remains under `cache/benchmarks/` until
you delete it. Changing the policy is a deliberate code review, never an
automatic response to a red benchmark.
