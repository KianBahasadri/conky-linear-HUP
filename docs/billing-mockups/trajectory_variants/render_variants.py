#!/usr/bin/env python3
"""Deterministic Cairo sketches for a trajectory-based Conky billing panel."""

import math
import os

import cairo


HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "JetBrains Mono"
PANEL_W = 424
DAY = 19
DAYS = 31
ELAPSED = DAY / DAYS
DAYS_LEFT = DAYS - DAY

SERIES = [
    {
        "name": "AWS",
        "code": "AWS",
        "color": "ffb454",
        "spend": 8.41,
        "budget": 25.00,
        "forecast": 13.20,
    },
    {
        "name": "AZURE",
        "code": "AZR",
        "color": "38bdf8",
        "spend": 4.27,
        "budget": 20.00,
        "forecast": 7.10,
    },
    {
        "name": "ANTHROPIC",
        "code": "ANT",
        "color": "ff8f73",
        "spend": 6.04,
        "budget": 20.00,
        "forecast": 10.10,
    },
]
for item in SERIES:
    item["s"] = item["spend"] / item["budget"]
    item["f"] = item["forecast"] / item["budget"]

RESERVE = {
    "name": "OPENROUTER",
    "color": "a78bfa",
    "balance": 12.44,
    "burn": 0.43,
    "runway": 12.44 / 0.43,
}


def rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def shaded(value, shade=0):
    red, green, blue = rgb(value)
    if shade > 0:
        return (
            red + (1 - red) * shade,
            green + (1 - green) * shade,
            blue + (1 - blue) * shade,
        )
    if shade < 0:
        return red * (1 + shade), green * (1 + shade), blue * (1 + shade)
    return red, green, blue


def set_hex(cr, value, alpha=1, shade=0):
    cr.set_source_rgba(*shaded(value, shade), alpha)


def gradient(x0, y0, x1, y1, stops):
    pattern = cairo.LinearGradient(x0, y0, x1, y1)
    for offset, color, alpha, *shade in stops:
        pattern.add_color_stop_rgba(
            offset, *shaded(color, shade[0] if shade else 0), alpha
        )
    return pattern


def rounded_rect(cr, x, y, width, height, radius):
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


def wallpaper(cr, width, height):
    base = cairo.LinearGradient(0, 0, width, height)
    base.add_color_stop_rgb(0, 0.105, 0.085, 0.145)
    base.add_color_stop_rgb(0.48, 0.205, 0.165, 0.235)
    base.add_color_stop_rgb(1, 0.305, 0.245, 0.265)
    cr.set_source(base)
    cr.paint()

    glow = cairo.RadialGradient(
        width * 0.70, height * 0.32, 10,
        width * 0.70, height * 0.32, width * 0.62,
    )
    glow.add_color_stop_rgba(0, 0.30, 0.16, 0.42, 0.22)
    glow.add_color_stop_rgba(0.56, 0.08, 0.28, 0.35, 0.08)
    glow.add_color_stop_rgba(1, 0, 0, 0, 0)
    cr.set_source(glow)
    cr.paint()

    cr.set_line_width(1)
    for gx in range(0, width, 64):
        cr.set_source_rgba(0.65, 0.75, 0.95, 0.018)
        cr.move_to(gx + 0.5, 0)
        cr.line_to(gx + 0.5, height)
        cr.stroke()
    for gy in range(0, height, 64):
        cr.set_source_rgba(0.65, 0.75, 0.95, 0.014)
        cr.move_to(0, gy + 0.5)
        cr.line_to(width, gy + 0.5)
        cr.stroke()


def text_width(cr, label, size, weight=cairo.FONT_WEIGHT_BOLD):
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    return cr.text_extents(label).x_advance


def flat_text(
    cr, label, x, baseline, size, color="f8fafc", alpha=1,
    weight=cairo.FONT_WEIGHT_BOLD, align="left",
):
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    advance = cr.text_extents(label).x_advance
    if align == "right":
        x -= advance
    elif align == "center":
        x -= advance / 2
    set_hex(cr, color, alpha)
    cr.move_to(x, baseline)
    cr.show_text(label)


def lit_text(
    cr, label, x, baseline, size, color="f8fafc", alpha=1,
    weight=cairo.FONT_WEIGHT_BOLD, align="left",
):
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    advance = cr.text_extents(label).x_advance
    if align == "right":
        x -= advance
    elif align == "center":
        x -= advance / 2
    set_hex(cr, "000000", 0.44)
    cr.move_to(x, baseline + 1.5)
    cr.show_text(label)
    cr.set_source(gradient(x, baseline - size * 0.72, x, baseline + size * 0.06, [
        (0.00, color, alpha, 0.52),
        (0.30, color, alpha, 0.24),
        (0.64, color, alpha, 0.02),
        (1.00, color, alpha, -0.26),
    ]))
    cr.move_to(x, baseline)
    cr.show_text(label)


def panel_frame(cr, x, y, width, height, accent="00e5ff", secondary="8b5cf6"):
    rounded_rect(cr, x + 4, y + 7, width, height, 18)
    set_hex(cr, accent, 0.10)
    cr.fill()

    rounded_rect(cr, x + 2, y + 3, width, height, 18)
    set_hex(cr, accent, 0.15)
    cr.set_line_width(8)
    cr.stroke()

    rounded_rect(cr, x + 1, y + 2, width, height, 18)
    set_hex(cr, secondary, 0.22)
    cr.set_line_width(4)
    cr.stroke()

    rounded_rect(cr, x, y, width, height, 18)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, "0d1a30", 0.88),
        (0.06, "050d1c", 0.82),
        (0.80, "020617", 0.80),
        (1.00, "08111f", 0.85),
    ]))
    cr.fill_preserve()
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, accent, 1.00, 0.40),
        (0.40, accent, 0.80),
        (1.00, accent, 0.95, 0.08),
    ]))
    cr.set_line_width(2)
    cr.stroke()

    rounded_rect(cr, x + 8, y + 8, width - 16, height - 16, 12)
    cr.set_source(gradient(x, y + 8, x, y + height - 8, [
        (0.00, "c4b5fd", 0.42),
        (0.35, secondary, 0.24),
        (1.00, secondary, 0.10),
    ]))
    cr.set_line_width(1)
    cr.stroke()


def chip_width(cr, label, size=11, padding=18):
    return text_width(cr, label, size) + padding


def chip(cr, label, color, x, y, size=11, height=20, padding=18):
    width = chip_width(cr, label, size, padding)
    rounded_rect(cr, x + 0.5, y + 2, width, height, 6)
    set_hex(cr, "000000", 0.36)
    cr.fill()
    rounded_rect(cr, x, y, width, height, 6)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, color, 0.94, -0.58),
        (0.20, color, 0.95, -0.86),
        (0.66, "020617", 0.95),
        (1.00, color, 0.94, -0.76),
    ]))
    cr.fill_preserve()
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, color, 0.95, 0.45),
        (0.50, color, 0.74),
        (1.00, color, 0.88, 0.12),
    ]))
    cr.set_line_width(1.5)
    cr.stroke()
    lit_text(cr, label, x + padding / 2, y + height * 0.74, size, color)
    return width


def title_chips(cr, specs, x, y, width):
    gap = 7
    widths = [chip_width(cr, label, size) for label, color, size in specs]
    cursor = x + (width - sum(widths) - gap * (len(widths) - 1)) / 2
    for (label, color, size), item_width in zip(specs, widths):
        chip(cr, label, color, cursor, y - 9, size=size)
        cursor += item_width + gap


def divider(cr, x1, x2, y, color="8b5cf6", alpha=0.20):
    cr.set_source(gradient(x1, y, x2, y, [
        (0.00, color, 0.00),
        (0.12, color, alpha),
        (0.88, color, alpha),
        (1.00, color, 0.00),
    ]))
    cr.set_line_width(1)
    cr.move_to(x1, y + 0.5)
    cr.line_to(x2, y + 0.5)
    cr.stroke()


def bead(cr, x, y, radius, color, hollow=False, alpha=1.0):
    if not hollow:
        glow = cairo.RadialGradient(
            x - radius * 0.30, y - radius * 0.38, radius * 0.08,
            x, y, radius,
        )
        glow.add_color_stop_rgba(0, *shaded(color, 0.72), alpha)
        glow.add_color_stop_rgba(0.34, *shaded(color, 0.20), alpha)
        glow.add_color_stop_rgba(1, *shaded(color, -0.46), alpha)
        cr.set_source(glow)
        cr.arc(x, y, radius, 0, math.tau)
        cr.fill()
    set_hex(cr, color, 0.95 * alpha, 0.28)
    cr.set_line_width(1.1)
    cr.arc(x, y, radius, 0, math.tau)
    cr.stroke()


def diamond(cr, x, y, radius, color, hollow=True, alpha=1.0):
    cr.move_to(x, y - radius)
    cr.line_to(x + radius, y)
    cr.line_to(x, y + radius)
    cr.line_to(x - radius, y)
    cr.close_path()
    if not hollow:
        set_hex(cr, color, 0.82 * alpha, -0.08)
        cr.fill_preserve()
    set_hex(cr, color, 0.95 * alpha, 0.32)
    cr.set_line_width(1.3)
    cr.stroke()


def arrowhead(cr, x, y, angle, color, size=5, filled=True):
    cr.save()
    cr.translate(x, y)
    cr.rotate(angle)
    cr.move_to(size, 0)
    cr.line_to(-size * 0.72, -size * 0.66)
    cr.line_to(-size * 0.72, size * 0.66)
    cr.close_path()
    set_hex(cr, color, 0.95, 0.18)
    if filled:
        cr.fill_preserve()
    cr.set_line_width(1.1)
    cr.stroke()
    cr.restore()


def glow_line(cr, x1, y1, x2, y2, color, width=1.6, alpha=0.86, dash=None):
    set_hex(cr, color, 0.12 * alpha)
    cr.set_line_width(width + 3.0)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    if dash:
        cr.set_dash(dash)
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()
    cr.set_dash([])
    cr.set_source(gradient(x1, y1, x2, y2, [
        (0.00, color, alpha * 0.62, -0.12),
        (1.00, color, alpha, 0.30),
    ]))
    cr.set_line_width(width)
    if dash:
        cr.set_dash(dash)
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()
    cr.set_dash([])
    cr.set_line_cap(cairo.LINE_CAP_BUTT)


def panel_header(cr, x, y, title, subtitle, right="DAY 19 → 31"):
    flat_text(cr, title, x + 22, y + 36, 10, "dbeafe", 0.82)
    flat_text(
        cr, subtitle, x + 22, y + 50, 7.5, "94a3b8", 0.56,
        weight=cairo.FONT_WEIGHT_NORMAL,
    )
    flat_text(cr, right, x + PANEL_W - 22, y + 42, 8, "facc15", 0.76, align="right")


def common_footer(cr, x, y, height, right="WORST AWS · 53%"):
    divider(cr, x + 18, x + PANEL_W - 18, y + height - 32)
    flat_text(cr, "4/4 LIVE", x + 22, y + height - 14, 7, "39ff88", 0.78)
    flat_text(
        cr, right, x + PANEL_W - 22, y + height - 14, 7,
        "ffb454", 0.78, align="right",
    )


def reserve_tower(cr, x, y_top, y_bottom, max_days=40, compact=False):
    """Vertical runway position; gate and bead are both literal day values."""
    color = RESERVE["color"]
    runway = RESERVE["runway"]
    scale = lambda days: y_bottom - (y_bottom - y_top) * min(max_days, days) / max_days
    gate_y = scale(DAYS_LEFT)
    runway_y = scale(runway)

    set_hex(cr, "f8fafc", 0.08)
    cr.set_line_width(1)
    cr.move_to(x, y_top)
    cr.line_to(x, y_bottom)
    cr.stroke()
    for days in (0, 20, 40):
        yy = scale(days)
        set_hex(cr, "f8fafc", 0.12)
        cr.move_to(x - 4, yy)
        cr.line_to(x + 4, yy)
        cr.stroke()
        if not compact:
            flat_text(cr, str(days), x - 8, yy + 3, 6.5, "94a3b8", 0.38, align="right")

    set_hex(cr, "facc15", 0.70)
    cr.set_line_width(1.3)
    cr.move_to(x - 11, gate_y)
    cr.line_to(x + 11, gate_y)
    cr.stroke()
    flat_text(cr, "12D", x + 14, gate_y + 3, 7, "facc15", 0.78)

    glow_line(cr, x, y_bottom, x, runway_y, color, width=1.4, alpha=0.55)
    bead(cr, x, runway_y, 4.6, color)
    flat_text(cr, "29D", x + 10, runway_y + 3, 8, color, 0.92)
    return runway_y, gate_y


def reserve_slant(cr, x0, y0, x1, y1, max_days=40):
    """A literal oblique 0–40 day number line, not a filled progress bar."""
    color = RESERVE["color"]

    def point(days):
        amount = min(max_days, days) / max_days
        return x0 + (x1 - x0) * amount, y0 + (y1 - y0) * amount

    set_hex(cr, color, 0.22)
    cr.set_line_width(1)
    cr.move_to(x0, y0)
    cr.line_to(x1, y1)
    cr.stroke()
    gx, gy = point(DAYS_LEFT)
    rx, ry = point(RESERVE["runway"])
    bead(cr, gx, gy, 3.4, "facc15", hollow=True)
    bead(cr, rx, ry, 4.6, color)
    flat_text(cr, "NEED 12D", gx - 5, gy + 13, 7, "facc15", 0.74, align="center")
    flat_text(cr, "29D RUN", rx + 7, ry - 7, 7, color, 0.90)


def draw_landing_field(cr, x, y):
    height = 342
    panel_frame(cr, x, y, PANEL_W, height)
    title_chips(cr, [("SPEND WATCH", "00e5ff", 11), ("SAFE", "39ff88", 11)], x, y, PANEL_W)
    panel_header(cr, x, y, "LANDING FIELD", "NOW → EOM · NORMALIZED TO EACH CAP")

    plot_x0, plot_x1 = x + 32, x + 316
    plot_top, plot_bottom = y + 64, y + 235
    pmax = 1.15
    map_x = lambda day: plot_x0 + (plot_x1 - plot_x0) * day / DAYS
    map_y = lambda pressure: plot_bottom - (plot_bottom - plot_top) * pressure / pmax
    now_x = map_x(DAY)
    cap_y = map_y(1)

    cr.rectangle(plot_x0, plot_top, plot_x1 - plot_x0, cap_y - plot_top)
    cr.set_source(gradient(plot_x0, plot_top, plot_x0, cap_y, [
        (0, "f87171", 0.08), (1, "f87171", 0.015)
    ]))
    cr.fill()

    for day in (7, 14, 21, 28):
        gx = map_x(day)
        set_hex(cr, "f8fafc", 0.05)
        cr.set_line_width(1)
        cr.move_to(gx, plot_top)
        cr.line_to(gx, plot_bottom)
        cr.stroke()

    for pressure in (0.25, 0.50, 0.75):
        gy = map_y(pressure)
        set_hex(cr, "f8fafc", 0.045)
        cr.move_to(plot_x0, gy)
        cr.line_to(plot_x1, gy)
        cr.stroke()

    set_hex(cr, "f8fafc", 0.15)
    cr.set_dash([3, 3])
    cr.move_to(plot_x0, plot_bottom)
    cr.line_to(plot_x1, cap_y)
    cr.stroke()
    cr.set_dash([])
    flat_text(cr, "ON PACE", plot_x0 + 48, plot_bottom - 16, 6.5, "94a3b8", 0.36)

    set_hex(cr, "f87171", 0.50)
    cr.set_line_width(1.2)
    cr.move_to(plot_x0, cap_y)
    cr.line_to(plot_x1, cap_y)
    cr.stroke()
    flat_text(cr, "CAP", plot_x1 - 3, cap_y - 5, 7, "f87171", 0.72, align="right")

    set_hex(cr, "facc15", 0.42)
    cr.set_line_width(1)
    cr.move_to(now_x, plot_top)
    cr.line_to(now_x, plot_bottom)
    cr.stroke()
    flat_text(cr, "NOW", now_x + 4, plot_top + 10, 7, "facc15", 0.82)

    for item in sorted(SERIES, key=lambda it: it["f"]):
        cy, fy = map_y(item["s"]), map_y(item["f"])
        glow_line(cr, now_x, cy, plot_x1, fy, item["color"], width=1.6, alpha=0.88)
        bead(cr, now_x, cy, 4.2, item["color"])
        arrowhead(cr, plot_x1, fy, math.atan2(fy - cy, plot_x1 - now_x), item["color"], 4.5, filled=False)

    flat_text(cr, "1", plot_x0, plot_bottom + 13, 7, "94a3b8", 0.46)
    flat_text(cr, "19", now_x, plot_bottom + 13, 7, "facc15", 0.68, align="center")
    flat_text(cr, "31", plot_x1, plot_bottom + 13, 7, "94a3b8", 0.46, align="right")

    flat_text(cr, "RESERVE", x + 348, y + 73, 7, "a78bfa", 0.70, align="center")
    flat_text(cr, "$12.44", x + 348, y + 91, 11, "f8fafc", 0.90, align="center")
    reserve_tower(cr, x + 348, y + 102, y + 224)

    divider(cr, x + 18, x + PANEL_W - 18, y + 255)
    columns = [x + 24, x + 154, x + 284]
    for px, item in zip(columns, SERIES):
        bead(cr, px + 2, y + 274, 2.8, item["color"])
        lit_text(cr, item["code"], px + 11, y + 278, 8.5, item["color"])
        flat_text(cr, f"{item['s'] * 100:.0f}% → {item['f'] * 100:.0f}%", px, y + 294, 8, "f8fafc", 0.78)
        flat_text(cr, f"EOM ${item['forecast']:.2f}", px, y + 308, 7, item["color"], 0.72)
    common_footer(cr, x, y, height)
    return PANEL_W, height


def draw_forecast_rain(cr, x, y):
    height = 338
    panel_frame(cr, x, y, PANEL_W, height, accent="a78bfa", secondary="00e5ff")
    title_chips(cr, [("FORECAST RAIN", "a78bfa", 11), ("SAFE", "39ff88", 11)], x, y, PANEL_W)
    panel_header(cr, x, y, "VERTICAL TIME", "PRESSURE MOVES LEFT → RIGHT", right="CAP = 100%")

    plot_left, plot_right = x + 30, x + 354
    now_y, eom_y = y + 86, y + 221
    pmax = 1.14
    map_p = lambda p: plot_left + (plot_right - plot_left) * p / pmax
    cap_x = map_p(1)
    pace_x_now = map_p(ELAPSED)

    cr.rectangle(cap_x, y + 62, plot_right - cap_x, y + 238 - (y + 62))
    cr.set_source(gradient(cap_x, y, plot_right, y, [
        (0, "f87171", 0.015), (1, "f87171", 0.09)
    ]))
    cr.fill()

    for pressure, label in ((0.25, "25"), (0.50, "50"), (0.75, "75")):
        gx = map_p(pressure)
        set_hex(cr, "f8fafc", 0.05)
        cr.move_to(gx, y + 62)
        cr.line_to(gx, y + 238)
        cr.stroke()
        flat_text(cr, label, gx, y + 70, 6.5, "94a3b8", 0.34, align="center")

    set_hex(cr, "f87171", 0.52)
    cr.set_line_width(1.2)
    cr.move_to(cap_x, y + 60)
    cr.line_to(cap_x, y + 240)
    cr.stroke()
    flat_text(cr, "CAP", cap_x, y + 69, 7, "f87171", 0.76, align="center")

    set_hex(cr, "facc15", 0.21)
    cr.set_dash([3, 3])
    cr.move_to(pace_x_now, now_y)
    cr.line_to(cap_x, eom_y)
    cr.stroke()
    cr.set_dash([])
    bead(cr, pace_x_now, now_y, 3.0, "facc15", hollow=True)

    for gy, label, color in ((now_y, "NOW · DAY 19", "facc15"), (eom_y, "EOM · DAY 31", "94a3b8")):
        set_hex(cr, color, 0.18)
        cr.move_to(plot_left, gy)
        cr.line_to(plot_right, gy)
        cr.stroke()
        flat_text(cr, label, plot_left, gy - 6, 7, color, 0.64)

    for item in sorted(SERIES, key=lambda it: it["f"]):
        sx, fx = map_p(item["s"]), map_p(item["f"])
        glow_line(cr, sx, now_y, fx, eom_y, item["color"], width=1.7, alpha=0.90)
        bead(cr, sx, now_y, 4.1, item["color"])
        diamond(cr, fx, eom_y, 5, item["color"], hollow=True)

    legend_y = y + 243
    columns = [x + 24, x + 150, x + 276]
    for px, item in zip(columns, SERIES):
        diamond(cr, px + 3, legend_y + 4, 3, item["color"], hollow=False)
        lit_text(cr, item["code"], px + 12, legend_y + 8, 8.5, item["color"])
        flat_text(cr, f"${item['spend']:.2f} → ${item['forecast']:.2f}", px, legend_y + 23, 7.5, "f8fafc", 0.74)

    flat_text(cr, "OR  $12.44 · $0.43/D", x + 24, y + 286, 8, "a78bfa", 0.86)
    reserve_slant(cr, x + 135, y + 302, x + 384, y + 286)
    common_footer(cr, x, y, height, right="○ NOW  ◇ EOM")
    return PANEL_W, height


def draw_diamond_map(cr, x, y):
    height = 352
    panel_frame(cr, x, y, PANEL_W, height, accent="8b5cf6", secondary="00e5ff")
    title_chips(cr, [("CAP MAP", "8b5cf6", 11), ("SAFE", "39ff88", 11)], x, y, PANEL_W)
    panel_header(cr, x, y, "AFFINE MONTH MAP", "TIME NE · CAP PRESSURE NW", right="NO BREACH")

    base_x, base_y = x + 194, y + 246
    tv = (155, -92)
    pv = (-138, -92)
    pmax = 1.12

    def point(t, p):
        return (
            base_x + tv[0] * t + pv[0] * p / pmax,
            base_y + tv[1] * t + pv[1] * p / pmax,
        )

    domain = [point(0, 0), point(1, 0), point(1, pmax), point(0, pmax)]
    cr.move_to(*domain[0])
    for pt in domain[1:]:
        cr.line_to(*pt)
    cr.close_path()
    cr.set_source(gradient(x + 80, y + 90, x + 320, y + 250, [
        (0, "07111f", 0.70), (1, "01040c", 0.42)
    ]))
    cr.fill_preserve()
    set_hex(cr, "c4b5fd", 0.18)
    cr.set_line_width(1)
    cr.stroke()

    cap_a, cap_b = point(0, 1), point(1, 1)
    top_a, top_b = point(0, pmax), point(1, pmax)
    cr.move_to(*cap_a)
    cr.line_to(*cap_b)
    cr.line_to(*top_b)
    cr.line_to(*top_a)
    cr.close_path()
    set_hex(cr, "f87171", 0.07)
    cr.fill()

    for t in (7 / DAYS, 14 / DAYS, 21 / DAYS, 28 / DAYS):
        a, b = point(t, 0), point(t, pmax)
        set_hex(cr, "f8fafc", 0.045)
        cr.move_to(*a)
        cr.line_to(*b)
        cr.stroke()
    for p in (0.25, 0.50, 0.75):
        a, b = point(0, p), point(1, p)
        set_hex(cr, "f8fafc", 0.045)
        cr.move_to(*a)
        cr.line_to(*b)
        cr.stroke()

    now_a, now_b = point(ELAPSED, 0), point(ELAPSED, pmax)
    set_hex(cr, "facc15", 0.40)
    cr.move_to(*now_a)
    cr.line_to(*now_b)
    cr.stroke()
    eom_a, eom_b = point(1, 0), point(1, pmax)
    set_hex(cr, "c4b5fd", 0.26)
    cr.move_to(*eom_a)
    cr.line_to(*eom_b)
    cr.stroke()
    set_hex(cr, "f87171", 0.54)
    cr.set_line_width(1.3)
    cr.move_to(*cap_a)
    cr.line_to(*cap_b)
    cr.stroke()

    pace_start, pace_end = point(0, 0), point(1, 1)
    set_hex(cr, "f8fafc", 0.15)
    cr.set_dash([3, 3])
    cr.move_to(*pace_start)
    cr.line_to(*pace_end)
    cr.stroke()
    cr.set_dash([])

    flat_text(cr, "DAY 1", domain[0][0] - 4, domain[0][1] + 13, 7, "94a3b8", 0.48, align="center")
    flat_text(cr, "EOM", eom_a[0] + 3, eom_a[1] + 13, 7, "c4b5fd", 0.64, align="center")
    flat_text(cr, "NOW", now_a[0] + 4, now_a[1] + 13, 7, "facc15", 0.72, align="center")
    flat_text(cr, "CAP", cap_a[0] - 7, cap_a[1] - 3, 7, "f87171", 0.72, align="right")

    for item in sorted(SERIES, key=lambda it: it["f"]):
        current = point(ELAPSED, item["s"])
        forecast = point(1, item["f"])
        glow_line(cr, *current, *forecast, item["color"], width=1.7, alpha=0.90)
        bead(cr, *current, 4.2, item["color"])
        diamond(cr, *forecast, 4.8, item["color"], hollow=True)

    # A second affine ray, clearly labelled in days, keeps prepaid units separate.
    flat_text(cr, "OPENROUTER RESERVE", x + 24, y + 271, 7.5, "a78bfa", 0.78)
    flat_text(cr, "$12.44 · $0.43/D", x + 24, y + 287, 8, "f8fafc", 0.72)
    reserve_slant(cr, x + 170, y + 303, x + 388, y + 269)

    divider(cr, x + 18, x + PANEL_W - 18, y + 310)
    cursor = x + 24
    for item in SERIES:
        bead(cr, cursor + 2, y + 328, 2.5, item["color"])
        flat_text(cr, f"{item['code']} {item['f'] * 100:.0f}%", cursor + 10, y + 331, 7.5, item["color"], 0.84)
        cursor += 92
    flat_text(cr, "4/4 LIVE", x + PANEL_W - 22, y + 331, 7, "39ff88", 0.76, align="right")
    return PANEL_W, height


def draw_runway_deck(cr, x, y):
    height = 360
    panel_frame(cr, x, y, PANEL_W, height, accent="00e5ff", secondary="a78bfa")
    title_chips(cr, [("RUNWAY DECK", "00e5ff", 11), ("SAFE", "39ff88", 11)], x, y, PANEL_W)
    panel_header(cr, x, y, "ISOMETRIC FORECAST", "LANE = PROVIDER · HEIGHT = CAP PRESSURE", right="19 → 31")

    lane_xs = [x + 54, x + 157, x + 260]
    ground_y = y + 248
    time_v = (42, -38)
    pressure_v = (0, -132)

    def point(lane_x, t, p):
        return lane_x + time_v[0] * t, ground_y + time_v[1] * t + pressure_v[1] * p

    # Ground and cap planes are the stable reference geometry.
    for p, fill, alpha in ((0, "38bdf8", 0.025), (1, "f87171", 0.065)):
        corners = [
            point(lane_xs[0] - 16, 0, p),
            point(lane_xs[-1] + 16, 0, p),
            point(lane_xs[-1] + 16, 1, p),
            point(lane_xs[0] - 16, 1, p),
        ]
        cr.move_to(*corners[0])
        for corner in corners[1:]:
            cr.line_to(*corner)
        cr.close_path()
        set_hex(cr, fill, alpha)
        cr.fill_preserve()
        set_hex(cr, fill, alpha * 3.1)
        cr.set_line_width(1)
        cr.stroke()

    for t in (0, ELAPSED, 1):
        a = point(lane_xs[0] - 16, t, 0)
        b = point(lane_xs[-1] + 16, t, 0)
        set_hex(cr, "f8fafc" if t != ELAPSED else "facc15", 0.08 if t != ELAPSED else 0.24)
        cr.move_to(*a)
        cr.line_to(*b)
        cr.stroke()

    for lane_x in lane_xs:
        for p, color, alpha in ((0, "f8fafc", 0.10), (1, "f87171", 0.25)):
            a, b = point(lane_x, 0, p), point(lane_x, 1, p)
            set_hex(cr, color, alpha)
            cr.move_to(*a)
            cr.line_to(*b)
            cr.stroke()

    # A faint on-pace diagonal in each lane makes calendar pace explicit.
    for lane_x in lane_xs:
        start, end = point(lane_x, 0, 0), point(lane_x, 1, 1)
        set_hex(cr, "f8fafc", 0.10)
        cr.set_dash([3, 3])
        cr.move_to(*start)
        cr.line_to(*end)
        cr.stroke()
        cr.set_dash([])

    for lane_x, item in zip(lane_xs, SERIES):
        current = point(lane_x, ELAPSED, item["s"])
        forecast = point(lane_x, 1, item["f"])
        cap_at_eom = point(lane_x, 1, 1)
        glow_line(cr, *current, *forecast, item["color"], width=1.8, alpha=0.92)
        set_hex(cr, item["color"], 0.14)
        cr.set_dash([2, 3])
        cr.move_to(*forecast)
        cr.line_to(*cap_at_eom)
        cr.stroke()
        cr.set_dash([])
        bead(cr, *current, 4.4, item["color"])
        arrowhead(
            cr, *forecast,
            math.atan2(forecast[1] - current[1], forecast[0] - current[0]),
            item["color"], 4.7, filled=False,
        )
        flat_text(cr, item["code"], lane_x, ground_y + 17, 8.5, item["color"], 0.88, align="center")
        flat_text(cr, f"{item['s'] * 100:.0f}→{item['f'] * 100:.0f}%", lane_x, ground_y + 32, 7, "f8fafc", 0.66, align="center")

    flat_text(cr, "CAP PLANE", x + 22, y + 99, 7, "f87171", 0.64)
    flat_text(cr, "NOW", x + 300, y + 229, 7, "facc15", 0.70)
    flat_text(cr, "EOM", x + 329, y + 196, 7, "c4b5fd", 0.56)

    flat_text(cr, "OR", x + 368, y + 75, 8, "a78bfa", 0.84, align="center")
    flat_text(cr, "$12.44", x + 368, y + 91, 8, "f8fafc", 0.78, align="center")
    reserve_tower(cr, x + 368, y + 105, y + 245, compact=True)

    divider(cr, x + 18, x + PANEL_W - 18, y + 296)
    flat_text(cr, "DOT NOW", x + 24, y + 316, 7, "f8fafc", 0.54)
    flat_text(cr, "TIP EOM", x + 97, y + 316, 7, "f8fafc", 0.54)
    flat_text(cr, "DASH ON-PACE", x + 173, y + 316, 7, "f8fafc", 0.54)
    flat_text(cr, "29D > 12D", x + PANEL_W - 22, y + 316, 7, "a78bfa", 0.78, align="right")
    common_footer(cr, x, y, height)
    return PANEL_W, height


VARIANTS = [
    ("01-landing-field", draw_landing_field, 342, "LANDING FIELD", "quietest / most immediately legible"),
    ("02-forecast-rain", draw_forecast_rain, 338, "FORECAST RAIN", "time falls downward; cap becomes a wall"),
    ("03-affine-cap-map", draw_diamond_map, 352, "AFFINE CAP MAP", "same axes rotated into a compact diamond"),
    ("04-isometric-runway", draw_runway_deck, 360, "ISOMETRIC RUNWAY", "most sculptural; lanes remain data-bearing"),
]


def render_one(filename, drawer, panel_height):
    width = 456
    height = panel_height + 46
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    wallpaper(cr, width, height)
    drawer(cr, 16, 22)
    path = os.path.join(HERE, f"{filename}.png")
    surface.write_to_png(path)
    return path


def render_sheet():
    width, height = 988, 884
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    wallpaper(cr, width, height)
    placements = [(28, 72), (532, 72), (28, 502), (532, 502)]

    for index, ((_, drawer, _, title, subtitle), (px, py)) in enumerate(zip(VARIANTS, placements), start=1):
        lit_text(cr, f"{index}  {title}", px, py - 42, 13, "f8fafc")
        flat_text(
            cr, subtitle, px, py - 24, 8, "cbd5e1", 0.60,
            weight=cairo.FONT_WEIGHT_NORMAL,
        )
        drawer(cr, px, py)

    flat_text(
        cr, "TRUE SIZE · SAME AUGUST DATA · DOT CURRENT · TIP FORECAST · ALL GEOMETRY RECOMPUTABLE",
        width / 2, height - 16, 8, "cbd5e1", 0.56,
        weight=cairo.FONT_WEIGHT_NORMAL, align="center",
    )
    path = os.path.join(HERE, "contact-sheet.png")
    surface.write_to_png(path)
    return path


if __name__ == "__main__":
    for args in VARIANTS:
        render_one(args[0], args[1], args[2])
    render_sheet()
    print(f"wrote {len(VARIANTS)} variants and contact sheet to {HERE}")
