import json
import stat
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import fetch_common as common


def test_escape_tsv():
    assert common.escape_tsv("a\\b\tc\nd") == "a\\\\b\\tc\\nd"


def test_atomic_write_json_preserves_unicode(tmp_path):
    path = tmp_path / "cards.json"
    common.atomic_write_json(
        path,
        {"title": "Consistency — scenario targets"},
    )
    raw = path.read_text(encoding="utf-8")
    assert "—" in raw
    assert "\\u2014" not in raw
    assert json.loads(raw)["title"] == "Consistency — scenario targets"


def test_atomic_write_json_applies_sensitive_mode_before_replace(tmp_path):
    path = tmp_path / "credentials.json"

    common.atomic_write_json(path, {"token": "secret"}, mode=0o600)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_atomic_write_json_preserves_symlink_chain_and_target_mode(tmp_path):
    target = tmp_path / "auth.json.kian"
    target.write_text('{"token": "old"}', encoding="utf-8")
    target.chmod(0o600)
    current = tmp_path / "current"
    current.symlink_to(target.name)
    auth = tmp_path / "auth.json"
    auth.symlink_to(current.name)

    common.atomic_write_json(auth, {"token": "new"})

    assert auth.is_symlink()
    assert current.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8")) == {"token": "new"}
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_write_rejects_dangling_and_cyclic_symlinks(tmp_path):
    dangling = tmp_path / "dangling"
    dangling.symlink_to("missing")
    with pytest.raises(FileNotFoundError):
        common.atomic_write_text(dangling, "payload")
    assert dangling.is_symlink()

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.symlink_to(second.name)
    second.symlink_to(first.name)
    with pytest.raises(RuntimeError):
        common.atomic_write_text(first, "payload")
    assert first.is_symlink()
    assert second.is_symlink()


def test_atomic_write_text_cleans_up_temporary_file_on_replace_failure(
    monkeypatch, tmp_path
):
    path = tmp_path / "status.json"
    monkeypatch.setattr(
        common.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        common.atomic_write_text(path, "payload")

    assert list(tmp_path.iterdir()) == []


def test_numeric_helpers_return_defaults_for_bad_input():
    assert common.as_float("bad", 1.5) == 1.5
    assert common.as_float(None, 2.5) == 2.5
    assert common.as_int("bad", 7) == 7
    assert common.as_int(None, 8) == 8
    assert common.as_int("3.9") == 3
    assert common.as_float("nan", 4.5) == 4.5
    assert common.as_float("inf", 4.5) == 4.5
    assert common.as_int("inf", 9) == 9


def test_parse_iso_epoch():
    assert common.parse_iso_epoch("2024-01-01T00:00:00Z") == 1704067200
    assert common.parse_iso_epoch("not-a-date") == 0
    assert common.parse_iso_epoch("") == 0


def test_usage_render_tsv_golden_string():
    output = {
        "ok": True,
        "updatedAt": "2026-06-03T12:00:00+00:00",
        "error": "none\nreally",
        "accounts": [
            {
                "label": "acct\\one",
                "planType": "pro",
                "isSelected": True,
                "ok": True,
                "error": "",
            }
        ],
        "bars": [
            {
                "account": "acct\\one",
                "planType": "pro",
                "isSelected": True,
                "window": "5h",
                "usedPercent": 12.3,
                "remainingPercent": 87.7,
                "resetsAt": "2026-06-03T17:00:00+00:00",
                "resetAtEpoch": 1780506000,
                "resetAfterSeconds": 18000,
                "windowSeconds": 18000,
            }
        ],
    }

    assert common.usage_render_tsv(output) == (
        "meta\tok\t1\tupdatedAt\t2026-06-03T12:00:00+00:00\terror\tnone\\nreally\n"
        "account\tacct\\\\one\tpro\t1\t1\t\t0\n"
        "bar\tacct\\\\one\tpro\t1\t5h\t12.3\t87.7\t2026-06-03T17:00:00+00:00\t1780506000\t18000\t18000\n"
    )


def test_load_env_strips_quotes_and_preserves_existing(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PLAIN=value",
                "DOUBLE=\"quoted value\"",
                "SINGLE='single quoted'",
                "EXISTING=from-file",
                "# COMMENT=ignored",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "from-env")

    common.load_env(Path(env_path))

    assert common.os.environ["PLAIN"] == "value"
    assert common.os.environ["DOUBLE"] == "quoted value"
    assert common.os.environ["SINGLE"] == "single quoted"
    assert common.os.environ["EXISTING"] == "from-env"


def test_local_day_start_is_five_am_and_rolls_back_before_it():
    tz = ZoneInfo("America/New_York")
    afternoon = datetime(2026, 10, 21, 17, 30, tzinfo=tz)
    assert common.local_day_start(afternoon) == datetime(2026, 10, 21, 5, 0, tzinfo=tz)
    early = datetime(2026, 10, 21, 4, 59, tzinfo=tz)
    assert common.local_day_start(early) == datetime(2026, 10, 20, 5, 0, tzinfo=tz)
    # 2026-03-08 is the US spring-forward; 04:30 is still before 05:00.
    dst = datetime(2026, 3, 8, 4, 30, tzinfo=tz)
    assert common.local_day_start(dst) == datetime(2026, 3, 7, 5, 0, tzinfo=tz)


def test_usage_history_keeps_pre_boundary_sample_when_later_polls_repeat(tmp_path):
    tz = ZoneInfo("America/New_York")
    render_path = tmp_path / "codex-usage-render.tsv"
    reset = 1_893_456_000
    before = datetime(2026, 10, 21, 4, 0, tzinfo=tz)
    output = {
        "accounts": [
            {
                "ok": True,
                "label": "ahmad",
                "windows": [{"label": "weekly", "usedPercent": 16, "resetAtEpoch": reset}],
            }
        ]
    }
    common.record_rate_limit_usage_history(render_path, output, now=before)
    same = datetime(2026, 10, 21, 18, 0, tzinfo=tz)
    common.record_rate_limit_usage_history(render_path, output, now=same)
    samples = common.load_usage_history(tmp_path / "rate-limit-usage-history.tsv")
    assert samples == [
        {
            "t": int(before.timestamp()),
            "provider": "codex",
            "account": "ahmad",
            "window": "weekly",
            "reset": reset,
            "used": 16.0,
        }
    ]

    output["accounts"][0]["windows"][0]["usedPercent"] = 31
    changed = datetime(2026, 10, 21, 19, 0, tzinfo=tz)
    common.record_rate_limit_usage_history(render_path, output, now=changed)
    samples = common.load_usage_history(tmp_path / "rate-limit-usage-history.tsv")
    assert [sample["t"] for sample in samples] == [
        int(before.timestamp()),
        int(changed.timestamp()),
    ]
    assert [sample["used"] for sample in samples] == [16.0, 31.0]


def test_usage_history_skips_stale_zero_and_finished_windows(tmp_path):
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 10, 21, 17, 0, tzinfo=tz)
    render_path = tmp_path / "cursor-usage-render.tsv"
    output = {
        "accounts": [
            {
                "ok": True,
                "staleCache": True,
                "label": "baba",
                "windows": [{"label": "weekly", "usedPercent": 20, "resetAtEpoch": 1_893_456_000}],
            },
            {
                "ok": True,
                "label": "kian",
                "windows": [
                    {"label": "auto", "usedPercent": 0, "resetAtEpoch": 1_893_456_000},
                    {"label": "api", "usedPercent": 12.5, "resetAtEpoch": 1_700_000_000},
                ],
            },
        ]
    }
    common.record_rate_limit_usage_history(render_path, output, now=now)
    assert common.load_usage_history(tmp_path / "rate-limit-usage-history.tsv") == []


def test_codex_log_line_backfills_nonzero_windows():
    line = (
        "[2026-10-20T20:00:32-04:00] fetch_codex_usage: account=ahmad stage=final "
        "ok=1 endpoint_fresh=1 selected=0 plan=plus source=api windows=2 "
        "values=5h(used=0.0%,remaining=100.0%,reset=2026-10-21T00:22:19+00:00,"
        "reset_after=1310s,window=18000s);weekly(used=16.0%,remaining=84.0%,"
        "reset=2026-10-27T19:22:19+00:00,reset_after=588110s,window=604800s)"
    )
    samples = common.parse_codex_history_line(line)
    assert len(samples) == 1
    assert samples[0]["provider"] == "codex"
    assert samples[0]["account"] == "ahmad"
    assert samples[0]["window"] == "weekly"
    assert samples[0]["used"] == 16.0
    assert samples[0]["reset"] == common.parse_iso_epoch("2026-10-27T19:22:19+00:00")
    assert common.parse_codex_history_line(line.replace(" source=api ", " source=local ")) is None


def test_write_usage_outputs_records_history_beside_the_render_file(tmp_path):
    render_path = tmp_path / "cursor-usage-render.tsv"
    common.write_usage_outputs(
        tmp_path / "cursor-usage.json",
        render_path,
        {
            "ok": True,
            "updatedAt": "2026-10-21T21:00:00+00:00",
            "error": "",
            "accounts": [
                {
                    "ok": True,
                    "label": "sepehr",
                    "planType": "pro",
                    "isSelected": True,
                    "windows": [
                        {
                            "label": "auto",
                            "usedPercent": 31.9,
                            "remainingPercent": 68.1,
                            "resetsAt": "2030-01-01T00:00:00+00:00",
                            "resetAtEpoch": 1893456000,
                            "resetAfterSeconds": 1000,
                            "windowSeconds": 2592000,
                        }
                    ],
                }
            ],
            "bars": [],
        },
    )
    history = (tmp_path / "rate-limit-usage-history.tsv").read_text(encoding="utf-8")
    assert "cursor\tsepehr\tauto\t1893456000\t31.9\n" in history


def test_rate_limit_panel_window_height_grows_with_accounts():
    assert common.rate_limit_panel_window_height(0) == 112
    assert common.rate_limit_panel_window_height(1) == 112
    assert common.rate_limit_panel_window_height(14) == 400
    assert common.rate_limit_panel_window_height(15) == 424
    assert common.rate_limit_panel_window_height(16) == 448
    assert common.rate_limit_panel_window_height(17) == 472
    assert common.rate_limit_panel_window_height(18) == 496
    assert common.rate_limit_panel_window_height(20) == 544


def test_rate_limit_account_count_from_cache_skips_removed_providers(tmp_path):
    (tmp_path / "codex-usage-render.tsv").write_text(
        "account\tkian\tfree\t1\t1\t\t0\naccount\tsepehr\tplus\t0\t1\t\t0\n",
        encoding="utf-8",
    )
    (tmp_path / "cursor-usage-render.tsv").write_text(
        "account\tida\tPro\t1\t1\t\t0\n",
        encoding="utf-8",
    )
    for name in ("pioneer", "claude", "grok", "opencode", "commandcode"):
        (tmp_path / f"{name}-usage-render.tsv").write_text(
            f"account\t{name}\t\t1\t1\t\t0\n",
            encoding="utf-8",
        )
    (tmp_path / "not-a-render.txt").write_text("account\tignored\n", encoding="utf-8")
    assert common.rate_limit_account_count_from_cache(tmp_path) == 3
