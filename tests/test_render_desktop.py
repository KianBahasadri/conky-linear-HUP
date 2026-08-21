import pytest

import render_desktop


# HDMI-3 in the developer's three-monitor layout, the head every rect below was
# measured on.
PRIMARY_MONITOR = {"index": 0, "name": "HDMI-3", "x": 1920, "y": 0,
                   "width": 1920, "height": 1080}


def config(**overrides):
    base = {"border_width": "0"}
    base.update({key: str(value) for key, value in overrides.items()})
    return base


# Every expectation here was read off the live X11 windows with
# `render_desktop.py --check`, so these lock in the geometry model against what
# Conky and the compositor actually produce.
@pytest.mark.parametrize(
    "overlay,settings,voffset,expected",
    [
        (
            "weather",
            dict(alignment="bottom_right", gap_x=6, gap_y=6,
                 minimum_width=456, maximum_width=456, minimum_height=276),
            -1,
            (3374, 794, 464, 284),
        ),
        (
            "resource-monitor",
            dict(alignment="top_right", gap_x=0, gap_y=34,
                 minimum_width=280, maximum_width=280, minimum_height=258),
            -1,
            (3556, 30, 288, 266),
        ),
        (
            "billing",
            dict(alignment="top_right", gap_x=6, gap_y=580,
                 minimum_width=456, maximum_width=456, minimum_height=300),
            -1,
            (3374, 576, 464, 308),
        ),
        (
            "minecraft",
            dict(alignment="bottom_left", gap_x=4, gap_y=6,
                 minimum_width=420, maximum_width=420, minimum_height=320),
            -1,
            (1920, 750, 428, 328),
        ),
        (
            "github",
            dict(alignment="top_left", gap_x=18, gap_y=32,
                 minimum_width=96, maximum_width=96, minimum_height=916),
            -1,
            (1934, 28, 104, 924),
        ),
        (
            # Self-sizing panel: the ${voffset} spacer opens the text area to
            # 320 and the line the spacer sits on adds one more line height.
            "rate-limit-panel",
            dict(alignment="bottom_left", gap_x=190, gap_y=6,
                 minimum_width=1540, maximum_width=1540, minimum_height=320),
            320,
            (2106, 731, 1548, 347),
        ),
        (
            "linear",
            dict(alignment="top_left", gap_x=190, gap_y=34,
                 minimum_width=1540, maximum_width=1540, minimum_height=398),
            398,
            (2106, 30, 1548, 425),
        ),
    ],
)
def test_window_rect_matches_live_geometry(overlay, settings, voffset, expected):
    settings = config(**settings)
    content_w, content_h = render_desktop.content_size(settings, voffset)
    assert render_desktop.window_rect(
        settings, PRIMARY_MONITOR, content_w, content_h
    ) == expected


def test_window_margin_uses_conky_defaults_for_unset_fields():
    # Only border_width is set in the overlay configs; the other two fall back
    # to Conky's defaults and the three together are the 4px the window extends
    # past its text area.
    assert render_desktop.window_margin({"border_width": "0"}) == 4
    assert render_desktop.window_margin({}) == 5
    assert render_desktop.window_margin(
        {"border_inner_margin": "10", "border_outer_margin": "2", "border_width": "1"}
    ) == 13


def test_content_size_ignores_a_spacer_shorter_than_the_minimum():
    settings = config(minimum_width=400, minimum_height=300)
    assert render_desktop.content_size(settings, -1) == (400, 300)
    assert render_desktop.content_size(settings, 100) == (400, 300)
    assert render_desktop.content_size(settings, 400) == (400, 419)


def test_content_size_clamps_width_to_maximum_width():
    settings = config(minimum_width=900, maximum_width=500, minimum_height=100)
    assert render_desktop.content_size(settings, -1) == (500, 100)


def test_parse_conkyrc_reads_config_fields_and_text_block(tmp_path):
    path = tmp_path / "demo-overlay-2.conkyrc"
    path.write_text(
        "conky.config = {\n"
        "  alignment = 'bottom_left',\n"
        "  xinerama_head = 2,\n"
        "  -- a comment that is not a field\n"
        "  gap_x = 190,\n"
        "  minimum_height = 320,\n"
        "  lua_load = '/repo/conky/overlay-entrypoint.lua',\n"
        "  lua_draw_hook_post = 'draw_demo',\n"
        "}\n"
        "\n"
        "conky.text = [[\n"
        "${lua_parse demo_height_spacer}\n"
        "]]\n",
        encoding="utf-8",
    )

    settings, body = render_desktop.parse_conkyrc(path)
    assert settings["alignment"] == "bottom_left"
    assert settings["xinerama_head"] == "2"
    assert settings["lua_draw_hook_post"] == "draw_demo"
    assert "a comment" not in settings
    assert render_desktop.LUA_PARSE_RE.search(body).group(1) == "demo_height_spacer"


def test_discover_overlays_orders_by_head_then_stacking(tmp_path, monkeypatch):
    monkeypatch.setattr(render_desktop, "GENERATED_DIR", tmp_path)
    for name in (
        "git-overlay-1.conkyrc",
        "linear-overlay-1.conkyrc",
        "git-overlay-0.conkyrc",
        "weather-overlay-0.conkyrc",
        "linear-overlay-0.conkyrc",
        "not-a-config.txt",
    ):
        (tmp_path / name).write_text(
            "conky.config = {\n  alignment = 'top_left',\n}\n", encoding="utf-8"
        )

    found = [
        (overlay["key"], overlay["head"])
        for overlay in render_desktop.discover_overlays()
    ]
    assert found == [
        ("linear", 0),
        ("weather", 0),
        ("git", 0),
        ("linear", 1),
        ("git", 1),
    ]


def test_discover_overlays_reports_a_missing_generated_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(render_desktop, "GENERATED_DIR", tmp_path / "absent")
    with pytest.raises(render_desktop.RenderError, match="start_conky_overlays"):
        render_desktop.discover_overlays()


def test_parse_monitor_spec_reads_a_layout_override():
    monitors = render_desktop.parse_monitor_spec("1920x1080+0+0, 2560x1440+1920+0")
    assert monitors[0]["x"] == 0 and monitors[0]["width"] == 1920
    assert monitors[1] == {"index": 1, "name": "head-1", "x": 1920, "y": 0,
                           "width": 2560, "height": 1440}


def test_parse_monitor_spec_rejects_junk():
    with pytest.raises(render_desktop.RenderError, match="expected WxH"):
        render_desktop.parse_monitor_spec("1920x1080")


def test_monitor_line_re_reads_xrandr_listmonitors():
    match = render_desktop.MONITOR_LINE_RE.match(
        " 0: +*HDMI-3 1920/600x1080/340+1920+0  HDMI-3"
    )
    assert match.group("index") == "0"
    assert match.group("name") == "+*HDMI-3"
    assert (match.group("width"), match.group("height")) == ("1920", "1080")
    assert (match.group("x"), match.group("y")) == ("1920", "0")


def test_desktop_bounds_covers_every_monitor():
    monitors = [
        {"x": 1920, "y": 0, "width": 1920, "height": 1080},
        {"x": 0, "y": 0, "width": 1920, "height": 1080},
        {"x": 3840, "y": -200, "width": 1920, "height": 1080},
    ]
    assert render_desktop.desktop_bounds(monitors) == (0, -200, 5760, 1280)


def test_parse_background_accepts_rgb_and_rgba():
    assert render_desktop.parse_background("000000") == [0.0, 0.0, 0.0, 1.0]
    assert render_desktop.parse_background("#ffffff00") == [1.0, 1.0, 1.0, 0.0]


def test_parse_background_rejects_junk():
    with pytest.raises(render_desktop.RenderError, match="expected RRGGBB"):
        render_desktop.parse_background("nope")
