import json
from pathlib import Path

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


def test_numeric_helpers_return_defaults_for_bad_input():
    assert common.as_float("bad", 1.5) == 1.5
    assert common.as_float(None, 2.5) == 2.5
    assert common.as_int("bad", 7) == 7
    assert common.as_int(None, 8) == 8
    assert common.as_int("3.9") == 3


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


def test_rate_limit_panel_window_height_grows_with_accounts():
    assert common.rate_limit_panel_window_height(0) == 320
    assert common.rate_limit_panel_window_height(1) == 320
    assert common.rate_limit_panel_window_height(14) == 320
    assert common.rate_limit_panel_window_height(15) == 320
    assert common.rate_limit_panel_window_height(16) == 320
    assert common.rate_limit_panel_window_height(17) == 320
    assert common.rate_limit_panel_window_height(18) == 336
    assert common.rate_limit_panel_window_height(20) == 368


def test_rate_limit_account_count_from_cache_skips_removed_providers(tmp_path):
    (tmp_path / "codex-usage-render.tsv").write_text(
        "account\tkian\tfree\t1\t1\t\t0\naccount\tsepehr\tplus\t0\t1\t\t0\n",
        encoding="utf-8",
    )
    (tmp_path / "cursor-usage-render.tsv").write_text(
        "account\tida\tPro\t1\t1\t\t0\n",
        encoding="utf-8",
    )
    (tmp_path / "pioneer-usage-render.tsv").write_text(
        "account\tpioneer\t\t1\t1\t\t0\n",
        encoding="utf-8",
    )
    (tmp_path / "not-a-render.txt").write_text("account\tignored\n", encoding="utf-8")
    assert common.rate_limit_account_count_from_cache(tmp_path) == 3
