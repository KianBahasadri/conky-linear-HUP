#!/usr/bin/env python3
"""Render low-attention billing widget explorations with Pycairo.

Everything in this file is self-contained so these experiments cannot alter or
depend on the production renderer.  Percentages are illustrative design data.
"""

from __future__ import annotations

import math
from pathlib import Path

import cairo


OUT = Path(__file__).resolve().parent
W, H = 424, 300

COLORS = {
    "ink": "06111d",
    "ink2": "0a1524",
    "white": "f3f7ff",
    "muted": "78879c",
    "faint": "34455c",
    "cyan": "2de2e6",
    "green": "38f28d",
    "violet": "a78bfa",
    "amber": "ffad42",
    "azure": "31d8e8",
    "coral": "fb8b7a",
    "danger": "ff5d73",
    "warn": "ffc857",
}

PROVIDERS = (
    ("AWS", "amber"),
    ("AZURE", "azure"),
    ("ANTH", "coral"),
)

SAFE = {
    "name": "safe",
    "metered": ((0.336, 0.528), (0.214, 0.355), (0.302, 0.505)),
    "runway": 29,
    "days_left": 12,
    "status": "CALM",
    "summary": "NO PROJECTED BREACH",
}

ALERT = {
    "name": "alert",
    "metered": ((0.740, 1.140), (0.390, 0.660), (0.460, 0.820)),
    "runway": 9,
    "days_left": 12,
    "status": "2 SIGNALS",
    "summary": "AWS CAP AUG 29  ·  OR 3D SHORT",
}


def rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def source(cr, value: str, alpha: float = 1.0):
    cr.set_source_rgba(*rgb(COLORS.get(value, value)), alpha)


def text_width(cr, label: str) -> float:
    return cr.text_extents(label).width


def label(
    cr,
    value: str,
    x: float,
    y: float,
    size: float = 9,
    color: str = "white",
    alpha: float = 1.0,
    bold: bool = False,
    align: str = "left",
):
    cr.select_font_face(
        "Noto Sans Mono",
        cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
    )
    cr.set_font_size(size)
    width = text_width(cr, value)
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    source(cr, color, alpha)
    cr.move_to(x, y)
    cr.show_text(value)


def chamfer_path(cr, x, y, w, h, cut=13):
    cr.new_path()
    cr.move_to(x + cut, y)
    cr.line_to(x + w - cut, y)
    cr.line_to(x + w, y + cut)
    cr.line_to(x + w, y + h - cut)
    cr.line_to(x + w - cut, y + h)
    cr.line_to(x + cut, y + h)
    cr.line_to(x, y + h - cut)
    cr.line_to(x, y + cut)
    cr.close_path()


def wallpaper(cr):
    grad = cairo.LinearGradient(0, 0, W, H)
    grad.add_color_stop_rgb(0, *rgb("10182a"))
    grad.add_color_stop_rgb(0.52, *rgb("211b31"))
    grad.add_color_stop_rgb(1, *rgb("432e3e"))
    cr.set_source(grad)
    cr.paint()
    # Very faint wallpaper rays keep the translucency honest.
    source(cr, "9b7ac4", 0.035)
    for i in range(-2, 7):
        cr.move_to(-40 + i * 85, H)
        cr.line_to(135 + i * 55, 0)
    cr.set_line_width(22)
    cr.stroke()


def panel(cr):
    chamfer_path(cr, 9, 12, 408, 280)
    source(cr, "02050b", 0.50)
    cr.fill()

    chamfer_path(cr, 7, 8, 408, 280)
    source(cr, "cyan", 0.10)
    cr.set_line_width(7)
    cr.stroke()

    chamfer_path(cr, 8, 8, 408, 280)
    fill = cairo.LinearGradient(8, 8, 416, 288)
    fill.add_color_stop_rgba(0, *rgb(COLORS["ink2"]), 0.95)
    fill.add_color_stop_rgba(0.60, *rgb(COLORS["ink"]), 0.92)
    fill.add_color_stop_rgba(1, *rgb("090b18"), 0.91)
    cr.set_source(fill)
    cr.fill_preserve()
    border = cairo.LinearGradient(8, 8, 416, 288)
    border.add_color_stop_rgba(0, *rgb(COLORS["cyan"]), 0.88)
    border.add_color_stop_rgba(0.52, *rgb(COLORS["violet"]), 0.34)
    border.add_color_stop_rgba(1, *rgb(COLORS["cyan"]), 0.68)
    cr.set_source(border)
    cr.set_line_width(1.35)
    cr.stroke()

    # A broken top glint avoids the rounded, full-neon frame language used by
    # the existing panels.
    source(cr, "cyan", 0.75)
    cr.set_line_width(2)
    cr.move_to(21, 8)
    cr.line_to(132, 8)
    cr.move_to(336, 8)
    cr.line_to(402, 8)
    cr.stroke()


def header(cr, concept: str, state):
    label(cr, "BILLING / AUG 19", 24, 29, 7.5, "muted", 0.82, bold=True)
    label(cr, concept, 24, 48, 12.5, "white", 0.96, bold=True)
    is_alert = state["name"] == "alert"
    status_color = "danger" if is_alert else "green"
    label(cr, state["status"], 397, 31, 8, status_color, 0.96, bold=True, align="right")
    source(cr, status_color, 0.75)
    cr.rectangle(402, 21, 3, 11)
    cr.fill()


def footer(cr, state):
    is_alert = state["name"] == "alert"
    color = "danger" if is_alert else "green"
    source(cr, color, 0.15)
    cr.rectangle(24, 266, 376, 1)
    cr.fill()
    label(cr, state["summary"], 24, 280, 7.5, color, 0.95, bold=True)
    label(cr, "MTD → EOM", 399, 280, 7, "muted", 0.72, align="right")


def diamond(cr, x, y, r, color, fill_alpha=0.88, outline_alpha=1.0):
    cr.new_path()
    cr.move_to(x, y - r)
    cr.line_to(x + r, y)
    cr.line_to(x, y + r)
    cr.line_to(x - r, y)
    cr.close_path()
    source(cr, color, fill_alpha)
    cr.fill_preserve()
    source(cr, "white", outline_alpha * 0.62)
    cr.set_line_width(0.8)
    cr.stroke()


def square(cr, x, y, r, color, alpha=0.9):
    source(cr, color, alpha)
    cr.rectangle(x - r, y - r, r * 2, r * 2)
    cr.fill()


def dashed_line(cr, x1, y1, x2, y2, color="faint", alpha=0.6, width=1, dash=(3, 4)):
    source(cr, color, alpha)
    cr.set_line_width(width)
    cr.set_dash(dash)
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()
    cr.set_dash(())


def runway(cr, x, top, bottom, state, compact=False):
    """A day axis: unlike metered providers, height means days, not money."""
    runway_days = state["runway"]
    days_left = state["days_left"]
    max_days = 35
    y_for = lambda d: bottom - min(d, max_days) / max_days * (bottom - top)
    low = runway_days < days_left
    line_color = "danger" if low else "violet"

    label(cr, "OPENROUTER", x, top - 11, 6.8, "muted", 0.86, bold=True, align="center")
    # The angular path reads as time receding rather than a fill gauge.
    source(cr, line_color, 0.73)
    cr.set_line_width(1.35)
    cr.move_to(x - 10, bottom)
    cr.line_to(x, bottom - 8)
    cr.line_to(x - 5, bottom - 17)
    cr.line_to(x + 3, bottom - 27)
    cr.line_to(x - 2, y_for(runway_days))
    cr.stroke()
    y_eom = y_for(days_left)
    source(cr, "warn", 0.78)
    cr.set_line_width(1)
    cr.move_to(x - 15, y_eom)
    cr.line_to(x + 15, y_eom)
    cr.stroke()
    diamond(cr, x - 2, y_for(runway_days), 4.5, line_color, 0.9)
    label(cr, "EOM", x + 18, y_eom + 2, 6.5, "warn", 0.86)
    label(cr, f"{runway_days}D", x, bottom + 16, 10.5, line_color, 1, bold=True, align="center")
    if not compact:
        label(cr, "RUNWAY", x, bottom + 27, 6.4, "muted", 0.76, align="center")


def scale_y(ratio, top=84, bottom=213):
    return bottom - ratio * (bottom - top)


def draw_canopy(cr, state):
    panel(cr)
    header(cr, "CAP CANOPY", state)
    top, bottom = 84, 211
    source(cr, "danger", 0.45)
    cr.set_line_width(1)
    cr.move_to(33, top)
    cr.line_to(287, top)
    cr.stroke()
    label(cr, "CAP", 31, top + 3, 6.5, "danger", 0.82, bold=True, align="right")
    source(cr, "muted", 0.18)
    cr.move_to(42, bottom)
    cr.line_to(279, bottom)
    cr.stroke()

    xs = (77, 163, 249)
    for (name, color), (actual, forecast), x in zip(PROVIDERS, state["metered"], xs):
        ya, yf = scale_y(actual, top, bottom), scale_y(forecast, top, bottom)
        dashed_line(cr, x, top, x, yf, color, 0.34, 0.9, (2, 4))
        source(cr, color, 0.62)
        cr.set_line_width(1.25)
        cr.move_to(x, yf)
        cr.line_to(x, ya)
        cr.stroke()
        square(cr, x, ya, 2.2, color, 0.75)
        if forecast > 1:
            source(cr, "danger", 0.18)
            cr.arc(x, yf, 12, 0, math.tau)
            cr.fill()
            diamond(cr, x, yf, 6, "danger")
        else:
            diamond(cr, x, yf, 5, color)
        label(cr, name, x, 231, 7.3, color, 0.95, bold=True, align="center")
        label(cr, f"{actual*100:.0f}→{forecast*100:.0f}", x, 244, 7, "white", 0.82, align="center")

    source(cr, "faint", 0.45)
    cr.rectangle(299, 70, 1, 181)
    cr.fill()
    runway(cr, 350, 91, 211, state)
    footer(cr, state)


def mound_path(cr, cx, base, peak, width):
    cr.new_path()
    cr.move_to(cx - width / 2, base)
    cr.curve_to(cx - width * 0.32, base, cx - width * 0.27, peak + 14, cx, peak)
    cr.curve_to(cx + width * 0.27, peak + 14, cx + width * 0.32, base, cx + width / 2, base)
    cr.close_path()


def draw_tide(cr, state):
    panel(cr)
    header(cr, "THRESHOLD TIDE", state)
    top, bottom = 84, 211
    source(cr, "danger", 0.40)
    cr.set_line_width(1)
    cr.move_to(32, top)
    cr.line_to(294, top)
    cr.stroke()
    label(cr, "100", 31, top + 3, 6.5, "danger", 0.78, bold=True, align="right")
    source(cr, "muted", 0.18)
    cr.move_to(37, bottom)
    cr.line_to(289, bottom)
    cr.stroke()

    xs = (76, 162, 248)
    for (name, color), (actual, forecast), x in zip(PROVIDERS, state["metered"], xs):
        ya, yf = scale_y(actual, top, bottom), scale_y(forecast, top, bottom)
        # Forecast is only an outline; the area fill stops at measured spend.
        mound_path(cr, x, bottom, yf, 67)
        source(cr, color, 0.58)
        cr.set_line_width(1.1)
        cr.set_dash((4, 3))
        cr.stroke()
        cr.set_dash(())
        mound_path(cr, x, bottom, ya, 54)
        grad = cairo.LinearGradient(x, ya, x, bottom)
        grad.add_color_stop_rgba(0, *rgb(COLORS[color]), 0.55)
        grad.add_color_stop_rgba(1, *rgb(COLORS[color]), 0.025)
        cr.set_source(grad)
        cr.fill()
        if forecast > 1:
            # The only sharp shape in the landscape appears on a breach.
            source(cr, "danger", 0.82)
            cr.move_to(x, yf)
            cr.line_to(x + 7, top)
            cr.line_to(x - 7, top)
            cr.close_path()
            cr.fill()
        diamond(cr, x, yf, 3.7, "danger" if forecast > 1 else color, 0.85)
        label(cr, name, x, 230, 7.2, color, 0.92, bold=True, align="center")
        label(cr, f"{forecast*100:.0f}%", x, 243, 7, "white", 0.80, align="center")

    source(cr, "faint", 0.45)
    cr.rectangle(301, 70, 1, 181)
    cr.fill()
    runway(cr, 351, 91, 211, state)
    footer(cr, state)


def lens_path(cr, x, y1, y2, width):
    if y1 > y2:
        y1, y2 = y2, y1
    mid = (y1 + y2) / 2
    cr.new_path()
    cr.move_to(x, y1)
    cr.curve_to(x + width, y1 + (mid - y1) * 0.55, x + width, y2 - (y2 - mid) * 0.55, x, y2)
    cr.curve_to(x - width, y2 - (y2 - mid) * 0.55, x - width, y1 + (mid - y1) * 0.55, x, y1)
    cr.close_path()


def draw_lenses(cr, state):
    panel(cr)
    header(cr, "DELTA LENSES", state)
    top, bottom = 84, 211
    source(cr, "danger", 0.40)
    cr.set_line_width(1)
    cr.move_to(32, top)
    cr.line_to(290, top)
    cr.stroke()
    label(cr, "CAP", 31, top + 3, 6.5, "danger", 0.78, bold=True, align="right")

    xs = (77, 163, 249)
    for (name, color), (actual, forecast), x in zip(PROVIDERS, state["metered"], xs):
        ya, yf = scale_y(actual, top, bottom), scale_y(forecast, top, bottom)
        dashed_line(cr, x, top, x, min(yf, ya), color, 0.28, 0.8, (2, 4))
        lens_path(cr, x, yf, ya, 10)
        grad = cairo.LinearGradient(x - 9, 0, x + 9, 0)
        grad.add_color_stop_rgba(0, *rgb(COLORS[color]), 0.08)
        grad.add_color_stop_rgba(0.5, *rgb(COLORS[color]), 0.68)
        grad.add_color_stop_rgba(1, *rgb(COLORS[color]), 0.08)
        cr.set_source(grad)
        cr.fill_preserve()
        source(cr, color, 0.84)
        cr.set_line_width(0.9)
        cr.stroke()
        square(cr, x, ya, 2.1, color, 0.85)
        diamond(cr, x, yf, 3.6, "danger" if forecast > 1 else color)
        if forecast > 1:
            source(cr, "danger", 0.78)
            cr.set_line_width(2)
            cr.move_to(x - 10, top)
            cr.line_to(x + 10, top)
            cr.stroke()
        label(cr, name, x, 230, 7.2, color, 0.94, bold=True, align="center")
        label(cr, f"+{(forecast-actual)*100:.0f} · {forecast*100:.0f}", x, 243, 6.7, "white", 0.80, align="center")

    source(cr, "faint", 0.45)
    cr.rectangle(300, 70, 1, 181)
    cr.fill()
    runway(cr, 350, 91, 211, state)
    footer(cr, state)


def point_on_ray(t, x0=42, y0=220, x1=291, y1=84):
    return x0 + (x1 - x0) * t, y0 + (y1 - y0) * t


def draw_ray(cr, state):
    panel(cr)
    header(cr, "THRESHOLD RAY", state)
    x0, y0, x1, y1 = 42, 218, 288, 84
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    # Extend slightly past cap so an overrun has somewhere truthful to land.
    source(cr, "danger", 0.28)
    cr.set_line_width(1.2)
    cr.move_to(x1, y1)
    cr.line_to(x0 + dx * 1.18, y0 + dy * 1.18)
    cr.stroke()
    source(cr, "cyan", 0.25)
    cr.move_to(x0, y0)
    cr.line_to(x1, y1)
    cr.stroke()
    for t in (0.25, 0.5, 0.75):
        px, py = x0 + dx * t, y0 + dy * t
        source(cr, "muted", 0.38)
        cr.set_line_width(0.8)
        cr.move_to(px - nx * 4, py - ny * 4)
        cr.line_to(px + nx * 4, py + ny * 4)
        cr.stroke()
        label(cr, f"{int(t*100)}", px - nx * 11, py - ny * 11 + 2, 6, "muted", 0.62, align="center")
    diamond(cr, x1, y1, 5.2, "danger", 0.68)
    label(cr, "CAP", x1 + 13, y1 - 2, 7, "danger", 0.9, bold=True)
    label(cr, "0", x0 - 2, y0 + 15, 6.5, "muted", 0.7, align="center")

    offsets = (-9, 0, 9)
    for (name, color), (actual, forecast), off in zip(PROVIDERS, state["metered"], offsets):
        ax, ay = x0 + dx * actual + nx * off, y0 + dy * actual + ny * off
        fx, fy = x0 + dx * forecast + nx * off, y0 + dy * forecast + ny * off
        source(cr, color, 0.55)
        cr.set_line_width(1.1)
        cr.move_to(ax, ay)
        cr.line_to(fx, fy)
        cr.stroke()
        square(cr, ax, ay, 1.9, color, 0.72)
        diamond(cr, fx, fy, 4.2, "danger" if forecast > 1 else color)

    # Three-value legend occupies less attention than labels scattered across the ray.
    legend_x = (51, 135, 219)
    for ((name, color), (_, forecast), lx) in zip(PROVIDERS, state["metered"], legend_x):
        square(cr, lx, 239, 2.3, color)
        label(cr, name, lx + 7, 242, 6.8, color, 0.9, bold=True)
        label(cr, f"{forecast*100:.0f}%", lx + 7, 254, 7, "white", 0.84)

    source(cr, "faint", 0.45)
    cr.rectangle(304, 70, 1, 188)
    cr.fill()
    runway(cr, 354, 92, 216, state, compact=True)
    footer(cr, state)


DRAWERS = (
    ("01-cap-canopy", draw_canopy),
    ("02-threshold-tide", draw_tide),
    ("03-delta-lenses", draw_lenses),
    ("04-threshold-ray", draw_ray),
)


def render_one(path: Path, drawer, state):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surface)
    wallpaper(cr)
    drawer(cr, state)
    surface.write_to_png(path)


def render_contact():
    margin, gutter = 28, 20
    label_h, row_gap = 28, 26
    cw = margin * 2 + W * 2 + gutter
    ch = 48 + len(DRAWERS) * (label_h + H + row_gap) + 12
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
    cr = cairo.Context(surface)
    bg = cairo.LinearGradient(0, 0, cw, ch)
    bg.add_color_stop_rgb(0, *rgb("111827"))
    bg.add_color_stop_rgb(1, *rgb("3b2b3c"))
    cr.set_source(bg)
    cr.paint()
    label(cr, "AMBIENT BILLING SIGNALS", margin, 28, 13, "white", 0.96, bold=True)
    label(cr, "CALM", margin + W - 2, 28, 8, "green", 0.92, bold=True, align="right")
    label(cr, "FORECAST BREACH", margin + W + gutter + W - 2, 28, 8, "danger", 0.92, bold=True, align="right")

    y = 48
    for index, (slug, _drawer) in enumerate(DRAWERS, 1):
        pretty = slug.split("-", 1)[1].replace("-", " ").upper()
        label(cr, f"0{index}  {pretty}", margin, y + 16, 8.5, "cyan", 0.90, bold=True)
        label(cr, "same geometry · changed state", cw - margin, y + 16, 7, "muted", 0.68, align="right")
        y += label_h
        for col, state in enumerate((SAFE, ALERT)):
            path = OUT / f"{slug}-{state['name']}.png"
            img = cairo.ImageSurface.create_from_png(path)
            x = margin + col * (W + gutter)
            cr.set_source_surface(img, x, y)
            cr.paint()
        y += H + row_gap
    surface.write_to_png(OUT / "ambient-contact-sheet.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, drawer in DRAWERS:
        for state in (SAFE, ALERT):
            render_one(OUT / f"{slug}-{state['name']}.png", drawer, state)
    render_contact()
    print(f"rendered {len(DRAWERS) * 2 + 1} PNGs in {OUT}")


if __name__ == "__main__":
    main()
