#!/usr/bin/env python3
"""Render the Conky overlays to a PNG without screenshotting the desktop.

Reads the generated per-monitor Conky configs, works out where each overlay
window lands on the virtual desktop, then draws the real Lua renderers into
in-memory Cairo surfaces and composites them over a background. No X display,
no compositor, and no running Conky are required.

    ./scripts/render_desktop.py                    # whole desktop
    ./scripts/render_desktop.py --monitor 0        # one monitor
    ./scripts/render_desktop.py --overlay weather  # one overlay
    ./scripts/render_desktop.py --list             # window table, no render
    ./scripts/render_desktop.py --check            # model vs live X11 windows
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "conky" / "generated"
CACHE_DIR = ROOT / "cache"
LUA_WORKER = ROOT / "scripts" / "render_desktop.lua"
MONITOR_CACHE_PATH = CACHE_DIR / "monitor-layout.json"
DEFAULT_OUTPUT = CACHE_DIR / "desktop-render.png"

# Conky reserves this much space outside the text area on every side, so the
# window is always the content box grown by it. Defaults come from Conky's own
# config defaults; current overlay configs explicitly set all three to zero.
DEFAULT_BORDER_INNER_MARGIN = 3
DEFAULT_BORDER_OUTER_MARGIN = 1
DEFAULT_BORDER_WIDTH = 1

# Compatibility with legacy 'JetBrains Mono:size=10' spacer configs. Current
# templates use explicit bounded heights and empty text, so this is not applied.
TEXT_LINE_HEIGHT_PX = 19

# Launch order from scripts/start_conky_overlays.sh. Conky windows stack in map
# order, so later entries here are the ones drawn on top.
OVERLAY_Z_ORDER = [
    "linear",
    "rate-limit-panel",
    "minecraft",
    "github",
    "weather",
    "resource-monitor",
    "billing",
    "git",
    "sessions",
]

CONFIG_NAME_RE = re.compile(r"^(?P<key>.+)-overlay-(?P<head>\d+|fallback)\.conkyrc$")
CONFIG_FIELD_RE = re.compile(r"^\s*([a-z_]+)\s*=\s*(.+?),?\s*$")
LUA_PARSE_RE = re.compile(r"\$\{lua_parse\s+([A-Za-z0-9_]+)\s*\}")
MONITOR_LINE_RE = re.compile(
    r"^\s*(?P<index>\d+):\s*(?P<name>\S+)\s+"
    r"(?P<width>\d+)/\d+x(?P<height>\d+)/\d+"
    r"(?P<x>[+-]\d+)(?P<y>[+-]\d+)"
)
MONITOR_SPEC_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


class RenderError(Exception):
    """A failure the caller should see as a message, not a traceback."""


# --- Lua toolchain ---------------------------------------------------------


def conky_package_library_path():
    """Return Conky's module directory, which is where its Lua bindings live."""
    if not shutil.which("conky"):
        return None
    try:
        output = subprocess.run(
            ["conky", "--version"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None

    match = re.search(r"^Package library path:\s*(.+)$", output, re.MULTILINE)
    return match.group(1).strip() if match else None


def resolve_lua():
    """Find an interpreter that can load Conky's Cairo binding.

    The binding is a compiled Lua module linked against one specific Lua
    version, so the interpreter has to match it; that is usually not the
    system's default `lua`.
    """
    cpath_candidates = []
    library_path = conky_package_library_path()
    if library_path:
        cpath_candidates.append(f"{library_path}/lib?.so")
    cpath_candidates += [
        "/usr/lib/conky/lib?.so",
        "/usr/lib64/conky/lib?.so",
        "/usr/local/lib/conky/lib?.so",
    ]

    override = os.environ.get("CONKY_LUA_CPATH")
    if override:
        cpath_candidates = [override]

    interpreters = [
        interpreter
        for interpreter in ("lua5.4", "lua5.3", "lua", "luajit", "lua5.1")
        if shutil.which(interpreter)
    ]
    if not interpreters:
        raise RenderError("no Lua interpreter found; install lua (5.4 preferred)")

    tried = []
    for cpath in cpath_candidates:
        if not list(Path(cpath).parent.glob("*cairo*.so")):
            continue
        for interpreter in interpreters:
            probe = subprocess.run(
                [
                    interpreter,
                    "-e",
                    f"package.cpath={cpath!r}..';'..package.cpath; require('cairo')",
                ],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                return interpreter, cpath
            tried.append(f"{interpreter} + {cpath}")

    detail = "; ".join(tried) if tried else "no candidate module directory exists"
    raise RenderError(
        "cannot load Conky's Lua Cairo binding (tried: "
        f"{detail}). Set CONKY_LUA_CPATH to the directory pattern holding "
        "libcairo.so, e.g. /usr/lib/conky/lib?.so"
    )


def run_lua(lua, cpath, mode, spec_text, out_png=None):
    with tempfile.NamedTemporaryFile(
        "w", suffix=".tsv", prefix="render-desktop-", delete=False
    ) as spec_file:
        spec_file.write(spec_text)
        spec_path = spec_file.name

    command = [lua, str(LUA_WORKER), mode, spec_path]
    if out_png:
        command.append(str(out_png))

    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            env={**os.environ, "CONKY_LUA_CPATH": cpath},
        )
    finally:
        Path(spec_path).unlink(missing_ok=True)


# --- Conky config parsing --------------------------------------------------


def parse_conkyrc(path):
    """Pull the conky.config table and the conky.text block out of a config."""
    text = path.read_text(encoding="utf-8")
    config = {}

    in_config = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("conky.config"):
            in_config = True
            continue
        if in_config and stripped.startswith("}"):
            in_config = False
            continue
        if not in_config or stripped.startswith("--") or not stripped:
            continue

        match = CONFIG_FIELD_RE.match(line)
        if match:
            key, raw_value = match.group(1), match.group(2).strip()
            config[key] = raw_value.strip("'\"")

    body = ""
    text_match = re.search(r"conky\.text\s*=\s*\[\[(.*?)\]\]", text, re.DOTALL)
    if text_match:
        body = text_match.group(1)

    return config, body


def config_int(config, key, default=None):
    try:
        return int(config[key])
    except (KeyError, TypeError, ValueError):
        return default


def window_margin(config):
    """Pixels the window extends past its text area on each side."""
    return (
        config_int(config, "border_inner_margin", DEFAULT_BORDER_INNER_MARGIN)
        + config_int(config, "border_outer_margin", DEFAULT_BORDER_OUTER_MARGIN)
        + config_int(config, "border_width", DEFAULT_BORDER_WIDTH)
    )


def discover_overlays():
    """Return one record per generated config, in stacking order."""
    if not GENERATED_DIR.is_dir():
        raise RenderError(
            f"no generated configs in {GENERATED_DIR}. "
            "Run ./scripts/start_conky_overlays.sh --generate-only first."
        )

    overlays = []
    for path in sorted(GENERATED_DIR.glob("*.conkyrc")):
        name_match = CONFIG_NAME_RE.match(path.name)
        if not name_match:
            continue

        key = name_match.group("key")
        head_from_name = name_match.group("head")
        config, body = parse_conkyrc(path)

        spacer_match = LUA_PARSE_RE.search(body)
        overlays.append(
            {
                "key": key,
                "path": path,
                "head": config_int(
                    config,
                    "xinerama_head",
                    0 if head_from_name == "fallback" else int(head_from_name),
                ),
                "config": config,
                "entrypoint": config.get("lua_load", ""),
                "hook": config.get("lua_draw_hook_post", ""),
                "spacer": spacer_match.group(1) if spacer_match else "",
            }
        )

    def sort_key(overlay):
        try:
            depth = OVERLAY_Z_ORDER.index(overlay["key"])
        except ValueError:
            depth = len(OVERLAY_Z_ORDER)
        return (overlay["head"], depth, overlay["key"])

    return sorted(overlays, key=sort_key)


# --- Monitors --------------------------------------------------------------


def parse_monitor_spec(spec):
    monitors = []
    for index, part in enumerate(spec.split(",")):
        match = MONITOR_SPEC_RE.match(part.strip())
        if not match:
            raise RenderError(
                f"bad --monitors entry {part.strip()!r}; expected WxH+X+Y"
            )
        width, height, x, y = (int(value) for value in match.groups())
        if width <= 0 or height <= 0:
            raise RenderError(
                f"bad --monitors entry {part.strip()!r}; width and height must be positive"
            )
        monitors.append(
            {"index": index, "name": f"head-{index}", "x": x, "y": y,
             "width": width, "height": height}
        )
    return monitors


def validate_monitors(monitors, source):
    """Validate an external monitor-layout value before geometry uses it."""
    if not isinstance(monitors, list) or not monitors:
        raise RenderError(f"{source} monitor layout is not a non-empty list")

    required = ("index", "name", "x", "y", "width", "height")
    indexes = set()
    validated = []
    for position, monitor in enumerate(monitors):
        if not isinstance(monitor, dict):
            raise RenderError(f"{source} monitor {position} is not an object")
        missing = [field for field in required if field not in monitor]
        if missing:
            raise RenderError(
                f"{source} monitor {position} is missing {', '.join(missing)}"
            )

        numeric_fields = ("index", "x", "y", "width", "height")
        if any(
            isinstance(monitor[field], bool)
            or not isinstance(monitor[field], int)
            for field in numeric_fields
        ):
            raise RenderError(f"{source} monitor {position} has a non-integer geometry")
        if monitor["index"] < 0:
            raise RenderError(f"{source} monitor {position} has a negative index")
        if monitor["index"] in indexes:
            raise RenderError(
                f"{source} monitor layout repeats index {monitor['index']}"
            )
        if monitor["width"] <= 0 or monitor["height"] <= 0:
            raise RenderError(
                f"{source} monitor {position} has a non-positive width or height"
            )
        if not isinstance(monitor["name"], str) or not monitor["name"]:
            raise RenderError(f"{source} monitor {position} has no name")

        indexes.add(monitor["index"])
        validated.append({field: monitor[field] for field in required})

    return validated


def write_monitor_cache(monitors):
    """Atomically save the last live layout without risking a truncated cache."""
    MONITOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=MONITOR_CACHE_PATH.parent,
        prefix=f".{MONITOR_CACHE_PATH.name}.",
        suffix=".tmp",
        delete=False,
    ) as cache_file:
        json.dump(monitors, cache_file, indent=2)
        cache_file.write("\n")
        temporary_path = Path(cache_file.name)

    try:
        os.replace(temporary_path, MONITOR_CACHE_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


def monitors_from_xrandr():
    if not shutil.which("xrandr"):
        return None
    try:
        result = subprocess.run(
            ["xrandr", "--listmonitors"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    monitors = []
    for line in result.stdout.splitlines():
        match = MONITOR_LINE_RE.match(line)
        if not match:
            continue
        monitors.append(
            {
                "index": int(match.group("index")),
                "name": match.group("name").lstrip("+*"),
                "x": int(match.group("x")),
                "y": int(match.group("y")),
                "width": int(match.group("width")),
                "height": int(match.group("height")),
            }
        )
    return monitors or None


def detect_monitors(spec=None):
    """Live layout when a display is reachable, otherwise the last one seen.

    The cache is what makes a headless run possible: an agent on a machine with
    no X server still gets the real desktop dimensions.
    """
    if spec is not None:
        return validate_monitors(parse_monitor_spec(spec), "--monitors"), "--monitors"

    monitors = monitors_from_xrandr()
    if monitors:
        monitors = validate_monitors(monitors, "xrandr")
        try:
            write_monitor_cache(monitors)
        except OSError as error:
            print(
                f"render_desktop: could not update {MONITOR_CACHE_PATH}: {error}",
                file=sys.stderr,
            )
        return monitors, "xrandr"

    if MONITOR_CACHE_PATH.is_file():
        try:
            cached = json.loads(MONITOR_CACHE_PATH.read_text(encoding="utf-8"))
            cached = validate_monitors(cached, "cached")
        except (OSError, ValueError, RenderError) as error:
            raise RenderError(
                f"no live monitor layout and cached layout "
                f"{MONITOR_CACHE_PATH} is unusable: {error}"
            ) from error
        return cached, f"cache ({MONITOR_CACHE_PATH.name})"

    raise RenderError(
        "no monitor layout available: xrandr returned nothing and "
        f"{MONITOR_CACHE_PATH} does not exist. Pass --monitors WxH+X+Y[,...]"
    )


# --- Geometry --------------------------------------------------------------


def content_size(config, voffset):
    """Text-area size, before the border margins are added around it."""
    width = config_int(config, "minimum_width", 0)
    maximum_width = config_int(config, "maximum_width")
    if maximum_width:
        width = min(width, maximum_width)

    height = config_int(config, "minimum_height", 0)
    if voffset >= 0:
        # A ${voffset} spacer pushes the text area open to the requested height
        # plus the line the spacer itself occupies.
        height = max(height, voffset + TEXT_LINE_HEIGHT_PX)

    return width, height


def window_rect(config, monitor, content_w, content_h):
    """Place a Conky window on the virtual desktop.

    gap_x/gap_y are measured from the monitor edge to the text area, and the
    window then extends `margin` further out on every side.
    """
    alignment = config.get("alignment", "top_left")
    gap_x = config_int(config, "gap_x", 0)
    gap_y = config_int(config, "gap_y", 0)
    margin = window_margin(config)

    if alignment.endswith("_right"):
        x = monitor["x"] + monitor["width"] - gap_x - content_w
    elif alignment.endswith("_middle"):
        x = monitor["x"] + (monitor["width"] - content_w) // 2 + gap_x
    else:
        x = monitor["x"] + gap_x

    if alignment.startswith("bottom_"):
        y = monitor["y"] + monitor["height"] - gap_y - content_h
    elif alignment.startswith("middle_"):
        y = monitor["y"] + (monitor["height"] - content_h) // 2 + gap_y
    else:
        y = monitor["y"] + gap_y

    return x - margin, y - margin, content_w + 2 * margin, content_h + 2 * margin


def plan_windows(overlays, monitors, lua, cpath):
    """Resolve every overlay to a placed window, dropping the ones that cannot draw.

    The Lua pass reports whether each draw hook exists (stale configs left over
    from removed overlays do not have one) and evaluates the height spacers,
    which decide how tall the self-sizing panels actually are.
    """
    spec_lines = []
    for index, overlay in enumerate(overlays):
        # Measure the spacers against the window Conky starts with, before any
        # ${voffset} has grown it.
        base_w, base_h = content_size(overlay["config"], -1)
        margin = window_margin(overlay["config"])
        spec_lines.append(
            "\t".join(
                [
                    str(index),
                    overlay["entrypoint"],
                    overlay["hook"],
                    overlay["spacer"],
                    str(base_w + 2 * margin),
                    str(base_h + 2 * margin),
                ]
            )
        )
    result = run_lua(lua, cpath, "plan", "\n".join(spec_lines) + "\n")
    if result.returncode != 0:
        raise RenderError(
            f"the Lua planning pass failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )

    plans = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == 3:
            plans[int(fields[0])] = (fields[1] == "1", int(fields[2]))

    by_index = {monitor["index"]: monitor for monitor in monitors}
    windows, skipped = [], []

    for index, overlay in enumerate(overlays):
        hook_present, voffset = plans.get(index, (False, -1))
        if not hook_present:
            skipped.append((overlay, f"no conky_{overlay['hook']} in the entrypoint"))
            continue

        monitor = by_index.get(overlay["head"])
        if monitor is None:
            skipped.append((overlay, f"xinerama_head {overlay['head']} has no monitor"))
            continue

        content_w, content_h = content_size(overlay["config"], voffset)
        if content_w <= 0 or content_h <= 0:
            skipped.append((overlay, "config has no minimum_width/minimum_height"))
            continue

        x, y, width, height = window_rect(
            overlay["config"], monitor, content_w, content_h
        )
        windows.append({**overlay, "monitor": monitor, "x": x, "y": y,
                        "width": width, "height": height})

    return windows, skipped


def desktop_bounds(monitors):
    left = min(monitor["x"] for monitor in monitors)
    top = min(monitor["y"] for monitor in monitors)
    right = max(monitor["x"] + monitor["width"] for monitor in monitors)
    bottom = max(monitor["y"] + monitor["height"] for monitor in monitors)
    return left, top, right - left, bottom - top


def geometry_text(width, height, x, y):
    """Format dimensions and signed offsets in standard X geometry form."""
    return f"{width}x{height}{x:+d}{y:+d}"


def parse_background(value):
    text = value.lstrip("#")
    if len(text) == 6:
        text += "ff"
    if len(text) != 8 or not re.fullmatch(r"[0-9a-fA-F]{8}", text):
        raise RenderError(f"bad --background {value!r}; expected RRGGBB or RRGGBBAA")
    return [int(text[i:i + 2], 16) / 255 for i in (0, 2, 4, 6)]


def complete_png(path):
    """Whether Cairo appears to have finished writing a PNG at *path*."""
    try:
        with Path(path).open("rb") as png_file:
            if png_file.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            png_file.seek(-12, os.SEEK_END)
            return png_file.read() == b"\x00\x00\x00\x00IEND\xaeB`\x82"
    except (OSError, ValueError):
        return False


def render_to_png(lua, cpath, spec_text, output_path):
    """Render through a staged file, preserving the last good output on failure."""
    output_path = Path(output_path)
    if output_path.is_symlink():
        try:
            output_path = output_path.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise RenderError(f"output symlink is unusable: {error}") from error
        if not output_path.is_file():
            raise RenderError(
                f"output symlink target is not a regular file: {output_path}"
            )
    output_mode = None
    try:
        output_mode = output_path.stat().st_mode & 0o7777
    except FileNotFoundError:
        pass
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_path.parent, prefix=f".{output_path.name}."
    ) as staging_dir:
        staged_output = Path(staging_dir) / output_path.name
        result = run_lua(lua, cpath, "render", spec_text, staged_output)
        if not complete_png(staged_output):
            detail = result.stderr.strip() or result.stdout.strip()
            message = "the Lua render pass did not produce a complete PNG"
            if detail:
                message += f":\n{detail}"
            raise RenderError(message)
        if output_mode is not None:
            staged_output.chmod(output_mode)
        os.replace(staged_output, output_path)
    return result


# --- Live window probe (for --check) ---------------------------------------


def probe_x11_windows():
    """Geometry of the mapped Conky windows on the running X display.

    Only used by --check, to confirm the geometry model still matches what
    Conky and the window manager actually do.
    """
    import ctypes
    import ctypes.util

    library = ctypes.util.find_library("X11")
    if not library:
        raise RenderError("libX11 not found; --check needs a running X display")
    xlib = ctypes.CDLL(library)

    xlib.XOpenDisplay.restype = ctypes.c_void_p
    display = xlib.XOpenDisplay(None)
    if not display:
        raise RenderError("cannot open the X display; --check needs DISPLAY set")

    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    root = xlib.XDefaultRootWindow(display)

    class XWindowAttributes(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_int), ("y", ctypes.c_int),
            ("width", ctypes.c_int), ("height", ctypes.c_int),
            ("border_width", ctypes.c_int), ("depth", ctypes.c_int),
            ("visual", ctypes.c_void_p), ("root", ctypes.c_ulong),
            ("class_", ctypes.c_int), ("bit_gravity", ctypes.c_int),
            ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
            ("backing_planes", ctypes.c_ulong), ("backing_pixel", ctypes.c_ulong),
            ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong),
            ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int),
            ("all_event_masks", ctypes.c_long), ("your_event_mask", ctypes.c_long),
            ("do_not_propagate_mask", ctypes.c_long),
            ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p),
        ]

    class XClassHint(ctypes.Structure):
        _fields_ = [("res_name", ctypes.c_void_p), ("res_class", ctypes.c_void_p)]

    found = []

    def visit(window):
        root_out = ctypes.c_ulong()
        parent_out = ctypes.c_ulong()
        children = ctypes.POINTER(ctypes.c_ulong)()
        count = ctypes.c_uint()
        if not xlib.XQueryTree(
            ctypes.c_void_p(display), ctypes.c_ulong(window),
            ctypes.byref(root_out), ctypes.byref(parent_out),
            ctypes.byref(children), ctypes.byref(count),
        ):
            return

        for position in range(count.value):
            child = children[position]
            hint = XClassHint()
            if xlib.XGetClassHint(
                ctypes.c_void_p(display), ctypes.c_ulong(child), ctypes.byref(hint)
            ):
                class_name = ctypes.cast(
                    hint.res_class, ctypes.c_char_p
                ).value or b""
                if hint.res_name:
                    xlib.XFree(ctypes.c_void_p(hint.res_name))
                if hint.res_class:
                    xlib.XFree(ctypes.c_void_p(hint.res_class))

                if class_name.decode(errors="replace").lower() == "conky":
                    attributes = XWindowAttributes()
                    xlib.XGetWindowAttributes(
                        ctypes.c_void_p(display), ctypes.c_ulong(child),
                        ctypes.byref(attributes),
                    )
                    absolute_x = ctypes.c_int()
                    absolute_y = ctypes.c_int()
                    ignored = ctypes.c_ulong()
                    xlib.XTranslateCoordinates(
                        ctypes.c_void_p(display), ctypes.c_ulong(child),
                        ctypes.c_ulong(root), 0, 0,
                        ctypes.byref(absolute_x), ctypes.byref(absolute_y),
                        ctypes.byref(ignored),
                    )
                    found.append(
                        {
                            "x": absolute_x.value, "y": absolute_y.value,
                            "width": attributes.width, "height": attributes.height,
                        }
                    )
            visit(child)

        xlib.XFree(children)

    visit(root)
    return found


def run_check(windows):
    """Match modelled windows to live ones by size, then report the offsets.

    Normal windows are placed by the window manager, so only their modelled
    size and presence are checkable. Conky-positioned windows must also land at
    the exact modelled coordinates.
    """
    live = probe_x11_windows()
    if not live:
        raise RenderError(
            "no Conky windows found on the display; start the overlays first"
        )

    remaining = list(live)
    rows, mismatches, exact = [], 0, 0
    window_manager_total = sum(
        window["config"].get("own_window_type") == "normal" for window in windows
    )

    for window in windows:
        window_manager_positions = window["config"].get("own_window_type") == "normal"
        candidates = [
            candidate
            for candidate in remaining
            if candidate["width"] == window["width"]
            and candidate["height"] == window["height"]
        ]
        if not candidates:
            rows.append((window, None, None, None, window_manager_positions))
            mismatches += 1
            continue

        best = min(
            candidates,
            key=lambda candidate: abs(candidate["x"] - window["x"])
            + abs(candidate["y"] - window["y"]),
        )
        remaining.remove(best)
        delta_x = best["x"] - window["x"]
        delta_y = best["y"] - window["y"]
        rows.append((window, best, delta_x, delta_y, window_manager_positions))
        if window_manager_positions:
            continue
        if delta_x or delta_y:
            mismatches += 1
        else:
            exact += 1

    print(f"{'overlay':<20} {'head':>4}  {'modelled':>20}  {'live':>20}  delta")
    for window, best, delta_x, delta_y, window_manager_positions in rows:
        modelled = geometry_text(
            window["width"], window["height"], window["x"], window["y"]
        )
        if best is None:
            print(f"{window['key']:<20} {window['head']:>4}  {modelled:>20}  "
                  f"{'(no size match)':>20}  -")
            continue
        live_text = geometry_text(
            best["width"], best["height"], best["x"], best["y"]
        )
        if window_manager_positions:
            delta = f"wm {delta_x:+d}{delta_y:+d}"
        else:
            delta = "exact" if not (delta_x or delta_y) else f"{delta_x:+d}{delta_y:+d}"
        print(f"{window['key']:<20} {window['head']:>4}  {modelled:>20}  "
              f"{live_text:>20}  {delta}")

    unmatched = len(remaining)
    conky_positioned_total = len(windows) - window_manager_total
    print(
        f"\n{exact}/{conky_positioned_total} Conky-positioned window(s) match "
        f"exactly; {window_manager_total} window-manager-positioned; "
        f"{unmatched} live window(s) unaccounted for"
    )
    return 0 if mismatches == 0 and unmatched == 0 else 1


# --- Entry point -----------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The render uses whatever is in cache/ right now, so it shows the "
            "same data the live overlays show."
        ),
    )
    parser.add_argument(
        "-o", "--out", type=Path, default=DEFAULT_OUTPUT,
        help=f"output PNG (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--monitor", type=int, metavar="N",
        help="render only monitor N, cropped to that monitor",
    )
    parser.add_argument(
        "--overlay", action="append", metavar="KEY",
        help="render only this overlay (repeatable), e.g. weather",
    )
    parser.add_argument(
        "--scale", type=float, default=1.0,
        help="scale the output, e.g. 0.5 for half size (default: 1.0)",
    )
    parser.add_argument(
        "--background", default="000000",
        help="background as RRGGBB or RRGGBBAA (default: 000000, opaque black)",
    )
    parser.add_argument(
        "--monitors", metavar="SPEC",
        help="override the monitor layout, e.g. 1920x1080+0+0,1920x1080+1920+0",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="print the resolved window table and exit without rendering",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="compare the geometry model against the live X11 windows",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not math.isfinite(args.scale) or args.scale <= 0:
        raise RenderError("--scale must be a finite number greater than 0")

    background = parse_background(args.background)
    monitors, monitor_source = detect_monitors(args.monitors)
    lua, cpath = resolve_lua()

    overlays = discover_overlays()

    if args.check:
        # --check validates the geometry model against every live window, so it
        # deliberately ignores the rendering filters.
        windows, skipped = plan_windows(overlays, monitors, lua, cpath)
        for overlay, reason in skipped:
            print(f"skipped {overlay['path'].name}: {reason}", file=sys.stderr)
        return run_check(windows)

    if args.overlay:
        wanted = set(args.overlay)
        unknown = wanted - {overlay["key"] for overlay in overlays}
        if unknown:
            available = sorted({overlay["key"] for overlay in overlays})
            raise RenderError(
                f"unknown overlay(s): {', '.join(sorted(unknown))}. "
                f"Available: {', '.join(available)}"
            )
        overlays = [overlay for overlay in overlays if overlay["key"] in wanted]

    if args.monitor is not None:
        overlays = [overlay for overlay in overlays if overlay["head"] == args.monitor]

    if not overlays:
        raise RenderError("no overlay configs matched the given filters")

    windows, skipped = plan_windows(overlays, monitors, lua, cpath)
    for overlay, reason in skipped:
        print(f"skipped {overlay['path'].name}: {reason}", file=sys.stderr)

    if not windows:
        raise RenderError("nothing left to render after skips")

    if args.monitor is not None:
        matching = [
            monitor for monitor in monitors if monitor["index"] == args.monitor
        ]
        if not matching:
            raise RenderError(f"no monitor with index {args.monitor}")
        monitor = matching[0]
        origin_x, origin_y = monitor["x"], monitor["y"]
        canvas_w, canvas_h = monitor["width"], monitor["height"]
    else:
        origin_x, origin_y, canvas_w, canvas_h = desktop_bounds(monitors)

    if args.list:
        print(f"monitors ({monitor_source}):")
        for monitor in monitors:
            print(
                f"  head {monitor['index']} {monitor['name']}: "
                f"{geometry_text(monitor['width'], monitor['height'], monitor['x'], monitor['y'])}"
            )
        print(
            f"\ncanvas: {geometry_text(canvas_w, canvas_h, origin_x, origin_y)}"
        )
        print(f"\n{'overlay':<20} {'head':>4}  {'window':>22}  hook")
        for window in windows:
            rect = geometry_text(
                window["width"],
                window["height"],
                window["x"] - origin_x,
                window["y"] - origin_y,
            )
            print(f"{window['key']:<20} {window['head']:>4}  {rect:>22}  "
                  f"{window['hook']}")
        return 0

    spec_lines = [
        "\t".join(
            ["canvas", str(canvas_w), str(canvas_h)]
            + [f"{channel:.6f}" for channel in background]
            + [str(args.scale)]
        )
    ]
    for window in windows:
        spec_lines.append(
            "\t".join(
                [
                    "window",
                    window["entrypoint"],
                    window["hook"],
                    str(window["x"] - origin_x),
                    str(window["y"] - origin_y),
                    str(window["width"]),
                    str(window["height"]),
                ]
            )
        )

    result = render_to_png(
        lua, cpath, "\n".join(spec_lines) + "\n", args.out
    )

    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    # The worker reports what it actually drew, so a partial render is not
    # summarised as a complete one.
    composited = len(windows)
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == 2 and fields[0] == "composited":
            composited = int(fields[1])

    output_w = max(1, round(canvas_w * args.scale))
    output_h = max(1, round(canvas_h * args.scale))
    drawn = f"{composited} overlay window(s)"
    if composited != len(windows):
        drawn += f" ({len(windows) - composited} failed to draw)"
    print(
        f"{args.out}: {output_w}x{output_h}, {drawn} "
        f"from {len(monitors)} monitor(s) via {monitor_source}"
    )
    return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RenderError as error:
        print(f"render_desktop: {error}", file=sys.stderr)
        sys.exit(2)
