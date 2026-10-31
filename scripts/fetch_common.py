#!/usr/bin/env python3
import fcntl
import json
import math
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
ENV_PATH = ROOT / ".env"

FIVE_HOUR_WINDOW_SECONDS = 5 * 60 * 60
WEEKLY_WINDOW_SECONDS = 7 * 24 * 60 * 60


def load_env(path=ENV_PATH):
    if not Path(path).exists():
        return

    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def make_logger(log_path, source):
    """Return a log_event(message) bound to a log file and a source label."""

    def log_event(message):
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {source}: {message}\n")

    return log_event


def atomic_write_text(path, content, *, mode=None):
    path = Path(path)
    if path.is_symlink():
        # Auth profile selectors are symlink chains. Replacing the selector
        # itself would silently disable account switching; resolve strictly so
        # dangling and cyclic chains fail before a temporary file is created.
        path = path.resolve(strict=True)
        if not path.is_file():
            raise OSError(f"atomic write symlink target is not a regular file: {path}")
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        final_mode = mode
        if final_mode is None:
            with suppress(OSError):
                final_mode = stat.S_IMODE(path.stat().st_mode)
        if final_mode is not None:
            os.fchmod(fd, final_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            fd = -1
            tmp_file.write(content)
        os.replace(tmp_path, path)
    except Exception:
        if fd >= 0:
            os.close(fd)
        with suppress(FileNotFoundError):
            tmp_path.unlink()
        raise


def atomic_write_json(path, data, *, mode=None):
    # ensure_ascii=False keeps characters like em dashes as UTF-8 instead of \u2014,
    # which the Conky Lua JSON string unescaper must otherwise decode.
    atomic_write_text(
        path, json.dumps(data, indent=2, ensure_ascii=False), mode=mode
    )


def escape_tsv(value):
    return str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def unescape_tsv(value):
    output = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            if nxt == "t":
                output.append("\t")
            elif nxt == "n":
                output.append("\n")
            elif nxt == "\\":
                output.append("\\")
            else:
                output.append(nxt)
            index += 2
        else:
            output.append(value[index])
            index += 1
    return "".join(output)


def as_float(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def parse_iso_epoch(value):
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except (ValueError, OverflowError, OSError):
        return 0


def usage_render_tsv(output):
    """The meta/account/bar TSV shared by the Codex and Claude usage fetchers."""
    lines = [
        "\t".join(
            [
                "meta",
                "ok",
                "1" if output.get("ok") else "0",
                "updatedAt",
                escape_tsv(output.get("updatedAt", "")),
                "error",
                escape_tsv(output.get("error", "")),
            ]
        )
    ]

    for account in output.get("accounts", []):
        lines.append(
            "\t".join(
                [
                    "account",
                    escape_tsv(account.get("label", "")),
                    escape_tsv(account.get("planType", "")),
                    "1" if account.get("isSelected") else "0",
                    "1" if account.get("ok") else "0",
                    escape_tsv(account.get("error", "")),
                    "1" if account.get("staleCache") else "0",
                    *([
                        "1" if account.get("localAvailable") is True else "0",
                        escape_tsv(account["accountId"]),
                        str(account.get("availabilityGeneratedAt", 0)),
                        str(account.get("observedAt") or 0),
                        str(account.get("maxAgeSeconds", 300)),
                        escape_tsv(account.get("freshness", "unknown")),
                    ] if account.get("accountId") and "localAvailable" in account else []),
                ]
            )
        )

    for bar in output.get("bars", []):
        lines.append(
            "\t".join(
                [
                    "bar",
                    escape_tsv(bar.get("account", "")),
                    escape_tsv(bar.get("planType", "")),
                    "1" if bar.get("isSelected") else "0",
                    escape_tsv(bar.get("window", "")),
                    str(bar.get("usedPercent", 0)),
                    str(bar.get("remainingPercent", 0)),
                    escape_tsv(bar.get("resetsAt") or ""),
                    str(bar.get("resetAtEpoch", 0)),
                    str(bar.get("resetAfterSeconds", 0)),
                    str(bar.get("windowSeconds", 0)),
                    *([
                        escape_tsv(bar["accountId"]),
                        escape_tsv(bar.get("sourceName", "")),
                    ] if bar.get("accountId") else []),
                ]
            )
        )

    return "\n".join(lines) + "\n"


def flatten_bars(accounts):
    bars = []
    for account in accounts:
        for window in account.get("windows", []):
            bars.append(
                {
                    "account": account.get("label", ""),
                    "planType": account.get("planType", ""),
                    "isSelected": account.get("isSelected", False),
                    "window": window.get("label", ""),
                    "usedPercent": window.get("usedPercent", 0),
                    "remainingPercent": window.get("remainingPercent", 0),
                    "resetsAt": window.get("resetsAt"),
                    "resetAtEpoch": window.get("resetAtEpoch", 0),
                    "resetAfterSeconds": window.get("resetAfterSeconds", 0),
                    "windowSeconds": window.get("windowSeconds", 0),
                    "ok": account.get("ok", False),
                    **({"accountId": account["accountId"],
                        "sourceName": window.get("sourceName", "")}
                       if account.get("accountId") and "localAvailable" in account else {}),
                }
            )
    return bars


def write_usage_outputs(output_path, render_path, output):
    atomic_write_json(output_path, output)
    atomic_write_text(render_path, usage_render_tsv(output))
    try:
        record_rate_limit_usage_history(render_path, output)
    except Exception as error:
        print(f"rate-limit usage history: {error}", file=sys.stderr)


# Local day boundary for the rate-limit bar split. Must match
# conky/rate-limit-panel-renderer.lua.
RATE_LIMIT_DAY_START_HOUR = 5
RATE_LIMIT_USAGE_HISTORY_NAME = "rate-limit-usage-history.tsv"
RATE_LIMIT_USAGE_HISTORY_RETENTION_SECONDS = 40 * 86400
_CODEX_FINAL_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\] fetch_codex_usage: account=(?P<account>\S+) stage=final\b"
)
_CODEX_VALUES_RE = re.compile(r"\bvalues=(?P<values>\S+)")
_CODEX_WINDOW_RE = re.compile(
    r"(?P<label>[A-Za-z0-9_-]+)\(used=(?P<used>\d+(?:\.\d+)?)%,"
    r"(?:[^;]*?),reset=(?P<reset>[^,]*),[^;]*?window=(?P<window>\d+)s\)"
)


def local_day_start(now=None, tz=None):
    """Most recent local 05:00 at or before `now`.

    "Today" for the rate-limit bars starts at 05:00 in the machine timezone.
    """
    if now is not None and tz is None and now.tzinfo is not None:
        tz = now.tzinfo
    if tz is None:
        tz = datetime.now().astimezone().tzinfo
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    start = now.replace(
        hour=RATE_LIMIT_DAY_START_HOUR, minute=0, second=0, microsecond=0
    )
    if now < start:
        # Subtracting a day can land off 05:00 across a DST transition.
        yesterday = (start - timedelta(hours=12)).date()
        start = datetime(
            yesterday.year,
            yesterday.month,
            yesterday.day,
            RATE_LIMIT_DAY_START_HOUR,
            0,
            tzinfo=tz,
        )
    return start


def provider_from_render_path(render_path):
    name = Path(render_path).name
    marker = "-usage-render.tsv"
    if not name.endswith(marker):
        return ""
    return name[: -len(marker)]


def _history_key(sample):
    return (sample["provider"], sample["account"], sample["window"], sample["reset"])


def collapse_usage_history(samples, now):
    """Keep the latest pre-05:00 sample and the latest later sample per window.

    Finished windows are dropped. An unchanged used percent keeps its original
    timestamp, so a flat reading from before 05:00 is still the baseline after
    later polls.
    """
    day_start = int(local_day_start(now).timestamp())
    now_epoch = int(now.timestamp())
    grouped = {}
    for sample in samples:
        grouped.setdefault(_history_key(sample), []).append(sample)

    kept = []
    for key, group in grouped.items():
        reset = key[3]
        if reset > 0 and reset < now_epoch - 3600:
            continue
        before = [sample for sample in group if sample["t"] <= day_start]
        after = [sample for sample in group if sample["t"] > day_start]
        chosen = []
        if before:
            chosen.append(max(before, key=lambda sample: sample["t"]))
        if after:
            chosen.append(max(after, key=lambda sample: sample["t"]))
        if not chosen:
            continue
        if chosen[-1]["t"] < now_epoch - RATE_LIMIT_USAGE_HISTORY_RETENTION_SECONDS:
            continue
        kept.extend(chosen)
    kept.sort(key=lambda sample: (*_history_key(sample), sample["t"]))
    return kept


def format_usage_history(samples):
    lines = []
    for sample in samples:
        used = round(float(sample["used"]), 1)
        lines.append(
            "\t".join(
                [
                    str(int(sample["t"])),
                    escape_tsv(sample["provider"]),
                    escape_tsv(sample["account"]),
                    escape_tsv(sample["window"]),
                    str(int(sample["reset"])),
                    f"{used:.1f}",
                ]
            )
        )
    return ("\n".join(lines) + "\n") if lines else ""


def load_usage_history(path):
    path = Path(path)
    if not path.is_file():
        return []
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 6:
            continue
        samples.append(
            {
                "t": as_int(fields[0]),
                "provider": unescape_tsv(fields[1]),
                "account": unescape_tsv(fields[2]),
                "window": unescape_tsv(fields[3]),
                "reset": as_int(fields[4]),
                "used": round(as_float(fields[5]), 1),
            }
        )
    return samples


def _usage_observations(provider, output, observed_at, existing):
    latest = {}
    for sample in existing:
        key = _history_key(sample)
        current = latest.get(key)
        if current is None or sample["t"] >= current["t"]:
            latest[key] = sample

    observations = []
    for account in output.get("accounts") or []:
        if not account.get("ok") or account.get("staleCache"):
            continue
        label = str((account.get("accountId") if "localAvailable" in account else None)
                    or account.get("label") or "")
        if not label:
            continue
        for window in account.get("windows") or []:
            window_label = str(window.get("sourceName") or window.get("label") or "")
            if not window_label:
                continue
            reset = as_int(window.get("resetAtEpoch"))
            used = round(as_float(window.get("usedPercent")), 1)
            sample = {
                "t": as_int(account.get("observedAt"), observed_at),
                "provider": provider,
                "account": label,
                "window": window_label,
                "reset": reset,
                "used": used,
            }
            key = _history_key(sample)
            current = latest.get(key)
            if used == 0 and (current is None or current["used"] == 0):
                continue
            if current is not None and current["used"] == used:
                continue
            observations.append(sample)
            latest[key] = sample
    return observations


def parse_codex_history_line(line):
    """One Codex stage=final log line, or None when it is not a fresh API sample."""
    if " stage=final " not in line or " ok=1 " not in line:
        return None
    if " endpoint_fresh=1 " not in line or " source=api " not in line:
        return None
    header = _CODEX_FINAL_RE.match(line)
    values = _CODEX_VALUES_RE.search(line)
    if not header or not values:
        return None
    try:
        observed_at = int(datetime.fromisoformat(header.group("ts")).timestamp())
    except ValueError:
        return None
    samples = []
    for window in _CODEX_WINDOW_RE.finditer(values.group("values")):
        used = round(as_float(window.group("used")), 1)
        if used == 0:
            continue
        reset = parse_iso_epoch(window.group("reset"))
        if reset <= 0:
            continue
        samples.append(
            {
                "t": observed_at,
                "provider": "codex",
                "account": header.group("account"),
                "window": window.group("label"),
                "reset": reset,
                "used": used,
            }
        )
    return samples


def backfill_codex_usage_history(log_paths):
    samples = []
    for path in log_paths:
        try:
            lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            parsed = parse_codex_history_line(line)
            if parsed:
                samples.extend(parsed)
    return samples


def rate_limit_log_paths(cache_dir=CACHE_DIR):
    paths = []
    cache_dir = Path(cache_dir)
    for name in (
        "conky-rate-limit-panel.log",
        "conky-rate-limit-panel.log.1",
        "conky-rate-limit-panel.log.2",
    ):
        path = cache_dir / name
        if path.is_file():
            paths.append(path)
    return paths


@contextmanager
def _exclusive_file_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with open(lock_path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def record_rate_limit_usage_history(render_path, output, now=None, cache_dir=CACHE_DIR):
    """Append changed window samples and fold them to the 05:00 baseline.

    The first history file under the live cache is seeded from Codex
    `stage=final` lines so the current day can split before the next morning.
    """
    provider = provider_from_render_path(render_path)
    if not provider:
        return
    history_path = Path(render_path).parent / RATE_LIMIT_USAGE_HISTORY_NAME
    now = now or datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.now().astimezone().tzinfo)
    observed_at = int(now.timestamp())

    with _exclusive_file_lock(history_path):
        if history_path.is_file():
            samples = load_usage_history(history_path)
        elif history_path.parent.resolve() == Path(cache_dir).resolve():
            try:
                samples = backfill_codex_usage_history(rate_limit_log_paths(cache_dir))
            except Exception as error:
                print(f"rate-limit usage history backfill: {error}", file=sys.stderr)
                samples = []
        else:
            samples = []
        samples.extend(_usage_observations(provider, output, observed_at, samples))
        atomic_write_text(history_path, format_usage_history(collapse_usage_history(samples, now)))


# Must match conky/rate-limit-panel-renderer.lua.
RATE_LIMIT_PANEL_MIN_HEIGHT = 112
RATE_LIMIT_PANEL_ROW_GAP = 24
RATE_LIMIT_PANEL_DYNAMIC_PADDING = 64
RATE_LIMIT_PANEL_TOP_INSET = 0
RATE_LIMIT_PANEL_BOTTOM_INSET = 0
RATE_LIMIT_PANEL_WINDOW_FLOOR = 112
RATE_LIMIT_PANEL_RENDER_TSVS = (
    "codex-usage-render.tsv",
    "cursor-usage-render.tsv",
    "gemini-usage-render.tsv",
)


def rate_limit_account_count_from_cache(cache_dir=CACHE_DIR):
    count = 0
    for name in RATE_LIMIT_PANEL_RENDER_TSVS:
        path = Path(cache_dir) / name
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith("account\t"):
                count += 1
    return count


# Legacy CLI measurements describe the natural content size. The launcher
# bounds each window with overlay_layout.py and excess rows rotate in place.
RATE_LIMIT_PANEL_FRAME_WIDTH = 1136
RATE_LIMIT_PANEL_FRAME_SIDE_CLEARANCE = 0


def rate_limit_panel_frame_height(account_count):
    """Height of the panel's drawn frame, before the window insets.

    Must match the layout math in conky/rate-limit-panel-renderer.lua.
    """
    count = max(1, int(account_count or 0))
    return max(
        RATE_LIMIT_PANEL_MIN_HEIGHT,
        RATE_LIMIT_PANEL_DYNAMIC_PADDING + count * RATE_LIMIT_PANEL_ROW_GAP,
    )


def rate_limit_panel_frame_width(window_width):
    """Width of the panel's drawn frame inside a window this wide."""
    return min(
        RATE_LIMIT_PANEL_FRAME_WIDTH,
        int(window_width) - RATE_LIMIT_PANEL_FRAME_SIDE_CLEARANCE,
    )


def rate_limit_panel_window_height(account_count):
    """Return the Conky minimum_height needed for the account list.

    Must match the layout math in conky/rate-limit-panel-renderer.lua.
    """
    count = max(1, int(account_count or 0))
    panel = max(
        RATE_LIMIT_PANEL_MIN_HEIGHT,
        RATE_LIMIT_PANEL_DYNAMIC_PADDING + count * RATE_LIMIT_PANEL_ROW_GAP,
    )
    return max(
        RATE_LIMIT_PANEL_WINDOW_FLOOR,
        RATE_LIMIT_PANEL_TOP_INSET + panel + RATE_LIMIT_PANEL_BOTTOM_INSET,
    )


if __name__ == "__main__":
    flag = sys.argv[1] if len(sys.argv) > 1 else ""
    if flag == "--print-rate-limit-panel-height":
        print(rate_limit_panel_window_height(rate_limit_account_count_from_cache()))
    elif flag == "--print-rate-limit-panel-frame-height":
        print(rate_limit_panel_frame_height(rate_limit_account_count_from_cache()))
    elif flag == "--print-rate-limit-panel-frame-width":
        print(rate_limit_panel_frame_width(sys.argv[2]))
    else:
        print(
            "usage: fetch_common.py --print-rate-limit-panel-height"
            " | --print-rate-limit-panel-frame-height"
            " | --print-rate-limit-panel-frame-width WINDOW_WIDTH",
            file=sys.stderr,
        )
        sys.exit(1)
