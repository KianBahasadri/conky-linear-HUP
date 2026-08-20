import cairo
import math
import os


OUT = os.path.dirname(__file__)
FONT = "JetBrains Mono"
TAU = math.pi * 2

WATCH = {
    "AWS": {
        "short": "AWS", "color": "ff9f1c", "spent": 68.0, "forecast": 92.0,
        "amount": "$17.00 / $25", "eom": "$23.00 EOM",
    },
    "AZURE": {
        "short": "AZR", "color": "00e5ff", "spent": 41.0, "forecast": 62.0,
        "amount": "$8.20 / $20", "eom": "$12.40 EOM",
    },
    "ANTHROPIC": {
        "short": "ANT", "color": "ff8f73", "spent": 57.0, "forecast": 84.0,
        "amount": "$11.40 / $20", "eom": "$16.80 EOM",
    },
}


def rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))


def shade(value, amount=0):
    channels = rgb(value)
    if amount >= 0:
        return tuple(channel + (1 - channel) * amount for channel in channels)
    return tuple(channel * (1 + amount) for channel in channels)


def set_hex(cr, value, alpha=1.0, amount=0):
    cr.set_source_rgba(*shade(value, amount), alpha)


def gradient(x0, y0, x1, y1, stops):
    pattern = cairo.LinearGradient(x0, y0, x1, y1)
    for stop, color, alpha, *amount in stops:
        pattern.add_color_stop_rgba(stop, *shade(color, amount[0] if amount else 0), alpha)
    return pattern


def rounded_rect(cr, x, y, width, height, radius):
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, math.pi * 1.5)
    cr.close_path()


def polygon(cr, points, close=True):
    cr.new_path()
    cr.move_to(*points[0])
    for point in points[1:]:
        cr.line_to(*point)
    if close:
        cr.close_path()


def draw_wallpaper(cr, width, height):
    base = cairo.LinearGradient(0, 0, width, height)
    base.add_color_stop_rgb(0, 0.075, 0.065, 0.125)
    base.add_color_stop_rgb(.50, 0.19, 0.14, 0.23)
    base.add_color_stop_rgb(1, 0.31, 0.23, 0.27)
    cr.set_source(base)
    cr.paint()
    glow = cairo.RadialGradient(width * .68, height * .25, 8,
                                width * .68, height * .25, width * .72)
    glow.add_color_stop_rgba(0, .34, .12, .48, .24)
    glow.add_color_stop_rgba(.55, .04, .28, .34, .08)
    glow.add_color_stop_rgba(1, 0, 0, 0, 0)
    cr.set_source(glow)
    cr.paint()
    for px in range(0, width, 64):
        cr.set_source_rgba(.65, .76, .95, .018)
        cr.move_to(px + .5, 0)
        cr.line_to(px + .5, height)
        cr.stroke()
    for py in range(0, height, 64):
        cr.set_source_rgba(.65, .76, .95, .014)
        cr.move_to(0, py + .5)
        cr.line_to(width, py + .5)
        cr.stroke()


def text(cr, label, x, y, size, color="f8fafc", alpha=1,
         align="left", weight=cairo.FONT_WEIGHT_BOLD, glow=False):
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    width = cr.text_extents(label).x_advance
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    if glow:
        set_hex(cr, color, alpha * .17)
        cr.set_line_width(3)
        cr.move_to(x, y)
        cr.text_path(label)
        cr.stroke()
        set_hex(cr, "000000", .55)
        cr.move_to(x, y + 1)
        cr.show_text(label)
    set_hex(cr, color, alpha)
    cr.move_to(x, y)
    cr.show_text(label)


def divider(cr, x1, x2, y, color="8b5cf6", alpha=.23):
    cr.set_source(gradient(x1, y, x2, y, [
        (0, color, 0), (.16, color, alpha), (.84, color, alpha), (1, color, 0),
    ]))
    cr.set_line_width(1)
    cr.move_to(x1, y + .5)
    cr.line_to(x2, y + .5)
    cr.stroke()


def panel_frame(cr, x, y, width=424, height=338, accent="00e5ff"):
    rounded_rect(cr, x + 4, y + 6, width, height, 18)
    set_hex(cr, accent, .11)
    cr.fill()
    rounded_rect(cr, x + 1, y + 2, width, height, 18)
    set_hex(cr, "8b5cf6", .20)
    cr.set_line_width(4)
    cr.stroke()
    rounded_rect(cr, x, y, width, height, 18)
    cr.set_source(gradient(x, y, x, y + height, [
        (0, "0d1a30", .88), (.09, "050d1c", .84),
        (.76, "020617", .82), (1, "08111f", .88),
    ]))
    cr.fill_preserve()
    cr.set_source(gradient(x, y, x, y + height, [
        (0, accent, .94, .30), (.48, accent, .58), (1, "8b5cf6", .72, .12),
    ]))
    cr.set_line_width(1.6)
    cr.stroke()
    rounded_rect(cr, x + 8, y + 8, width - 16, height - 16, 12)
    set_hex(cr, "c4b5fd", .18)
    cr.set_line_width(1)
    cr.stroke()


def header(cr, x, y, title, subtitle, status="WATCH", status_color="ffb454"):
    # Asymmetric tab deliberately avoids the centered chip stack of the quota panel.
    points = [(x + 17, y + 9), (x + 211, y + 9), (x + 224, y + 20),
              (x + 211, y + 31), (x + 17, y + 31), (x + 27, y + 20)]
    polygon(cr, points)
    cr.set_source(gradient(x + 17, y, x + 224, y, [
        (0, "00e5ff", .20), (.62, "8b5cf6", .12), (1, "8b5cf6", .02),
    ]))
    cr.fill_preserve()
    set_hex(cr, "00e5ff", .46)
    cr.set_line_width(1)
    cr.stroke()
    text(cr, title, x + 38, y + 24, 11, "f8fafc", .95, glow=True)
    text(cr, subtitle, x + 236, y + 24, 7.5, "94a3b8", .70,
         weight=cairo.FONT_WEIGHT_NORMAL)
    diamond(cr, x + 376, y + 20, 9, status_color, fill_alpha=.22)
    text(cr, status, x + 358, y + 24, 8, status_color, .94, align="right")


def diamond(cr, cx, cy, radius, color, fill_alpha=.25, line_alpha=.9):
    polygon(cr, [(cx, cy - radius), (cx + radius, cy),
                 (cx, cy + radius), (cx - radius, cy)])
    set_hex(cr, color, fill_alpha)
    cr.fill_preserve()
    set_hex(cr, color, line_alpha, .18)
    cr.set_line_width(1.2)
    cr.stroke()


def hex_points(cx, cy, radius):
    return [(cx + math.cos(math.pi / 3 * index) * radius,
             cy + math.sin(math.pi / 3 * index) * radius)
            for index in range(6)]


def fraction_clip_fill(cr, points, fraction, color, alpha, y0, y1):
    if fraction <= 0:
        return
    xs = [point[0] for point in points]
    cr.save()
    polygon(cr, points)
    cr.clip()
    cr.rectangle(min(xs) - 1, y0 - 1, (max(xs) - min(xs) + 2) * min(1, fraction), y1 - y0 + 2)
    set_hex(cr, color, alpha)
    cr.fill()
    cr.restore()


def budget_honeycomb(cr, x, y, color, spent, forecast):
    radius = 8.2
    centers = []
    for index in range(5):
        centers.append((x + index * 19, y))
    for index in range(5):
        centers.append((x + 9.5 + index * 19, y + 15))
    for index, (cx, cy) in enumerate(centers):
        points = hex_points(cx, cy, radius)
        polygon(cr, points)
        set_hex(cr, "07101f", .92)
        cr.fill()
        projected_amount = max(0, min(1, forecast / 10 - index))
        current_amount = max(0, min(1, spent / 10 - index))
        fraction_clip_fill(cr, points, projected_amount, color, .20, cy - radius, cy + radius)
        fraction_clip_fill(cr, points, current_amount, color, .74, cy - radius, cy + radius)
        polygon(cr, points)
        set_hex(cr, color if projected_amount else "334155", .76 if projected_amount else .44)
        cr.set_line_width(1)
        cr.stroke()
        if projected_amount > current_amount:
            cr.save()
            polygon(cr, points)
            cr.clip()
            set_hex(cr, color, .25)
            cr.set_line_width(.8)
            for hatch in range(-14, 16, 5):
                cr.move_to(cx + hatch, cy + radius)
                cr.line_to(cx + hatch + 13, cy - radius)
            cr.stroke()
            cr.restore()


def draw_facets(cr, x, y):
    panel_frame(cr, x, y)
    header(cr, x, y, "FACET LEDGER", "1 CELL = 10%")
    row_y = y + 73
    for name in ("AWS", "AZURE", "ANTHROPIC"):
        item = WATCH[name]
        text(cr, item["short"], x + 22, row_y + 5, 10, item["color"], .98)
        budget_honeycomb(cr, x + 87, row_y - 2, item["color"], item["spent"], item["forecast"])
        text(cr, f'{int(item["spent"])}%', x + 211, row_y + 2, 16,
             "f8fafc", .98, align="right", glow=True)
        text(cr, f'\u2192 {int(item["forecast"])}% EOM', x + 224, row_y + 2, 9,
             "ffb454" if item["forecast"] >= 80 else item["color"], .92)
        text(cr, item["amount"], x + 211, row_y + 31, 7.2, "94a3b8", .64,
             align="right", weight=cairo.FONT_WEIGHT_NORMAL)
        text(cr, item["eom"], x + 224, row_y + 31, 7.2, "94a3b8", .64,
             weight=cairo.FONT_WEIGHT_NORMAL)
        row_y += 58

    divider(cr, x + 18, x + 406, y + 238)
    text(cr, "OPENROUTER", x + 22, y + 260, 9, "c084fc", .96)
    text(cr, "$6.45", x + 22, y + 282, 16, "f8fafc", .96, glow=True)
    text(cr, "$0.43/D", x + 22, y + 297, 7.5, "94a3b8", .70)
    # A short stepping-stone runway: twelve month-days plus three days of cushion.
    start_x = x + 139
    for index in range(15):
        cx = start_x + (index % 8) * 28
        cy = y + 265 + (index // 8) * 25
        color = "c084fc" if index < 12 else "39ff88"
        diamond(cr, cx, cy, 6, color, fill_alpha=.38 if index < 12 else .17,
                line_alpha=.88)
    text(cr, "12D LEFT", x + 139, y + 318, 7.5, "c084fc", .84)
    text(cr, "+3D CUSHION", x + 400, y + 318, 8, "39ff88", .92, align="right")


def plot_map_y(y0, value):
    # 120% at the top and 0% at the bottom over a 184px field.
    return y0 + 184 * (1 - value / 120)


def plot_map_x(x0, value):
    return x0 + 250 * value / 100


def draw_risk_field(cr, x, y):
    panel_frame(cr, x, y)
    header(cr, x, y, "SURPRISE MAP", "NOW x EOM")
    plot_x, plot_y = x + 42, y + 58
    plot_w, plot_h = 250, 184

    # Horizontal forecast zones; x remains the current fraction of cap.
    cr.rectangle(plot_x, plot_map_y(plot_y, 120), plot_w, plot_map_y(plot_y, 100) - plot_map_y(plot_y, 120))
    set_hex(cr, "f87171", .085)
    cr.fill()
    cr.rectangle(plot_x, plot_map_y(plot_y, 100), plot_w, plot_map_y(plot_y, 80) - plot_map_y(plot_y, 100))
    set_hex(cr, "ffb454", .065)
    cr.fill()
    cr.rectangle(plot_x, plot_map_y(plot_y, 80), plot_w, plot_map_y(plot_y, 0) - plot_map_y(plot_y, 80))
    set_hex(cr, "00e5ff", .025)
    cr.fill()

    for level in (0, 20, 40, 60, 80, 100, 120):
        py = plot_map_y(plot_y, level)
        set_hex(cr, "f8fafc", .07)
        cr.set_line_width(1)
        cr.move_to(plot_x, py + .5)
        cr.line_to(plot_x + plot_w, py + .5)
        cr.stroke()
        text(cr, str(level), plot_x - 7, py + 3, 7, "94a3b8", .48, align="right")
    for level in (0, 25, 50, 75, 100):
        px = plot_map_x(plot_x, level)
        set_hex(cr, "f8fafc", .05)
        cr.move_to(px + .5, plot_y)
        cr.line_to(px + .5, plot_y + plot_h)
        cr.stroke()
        text(cr, str(level), px, plot_y + plot_h + 13, 7, "94a3b8", .48, align="center")

    # y=x means no further spending; distance above it is forecast growth.
    set_hex(cr, "f8fafc", .20)
    cr.set_dash([3, 4])
    cr.move_to(plot_map_x(plot_x, 0), plot_map_y(plot_y, 0))
    cr.line_to(plot_map_x(plot_x, 100), plot_map_y(plot_y, 100))
    cr.stroke()
    cr.set_dash([])
    text(cr, "NO GROWTH", plot_x + 9, plot_y + plot_h - 11, 7, "94a3b8", .44)
    cr.save()
    cr.translate(x + 14, plot_y + 92)
    cr.rotate(-math.pi / 2)
    text(cr, "EOM FORECAST %", 0, 0, 7, "94a3b8", .56, align="center")
    cr.restore()
    text(cr, "CURRENT % OF CAP", plot_x + plot_w / 2, plot_y + plot_h + 28,
         7, "94a3b8", .56, align="center")

    for name in ("AZURE", "ANTHROPIC", "AWS"):
        item = WATCH[name]
        px = plot_map_x(plot_x, item["spent"])
        py = plot_map_y(plot_y, item["forecast"])
        base_y = plot_map_y(plot_y, item["spent"])
        set_hex(cr, item["color"], .31)
        cr.set_dash([2, 3])
        cr.move_to(px, base_y)
        cr.line_to(px, py)
        cr.stroke()
        cr.set_dash([])
        diamond(cr, px, py, 6.5, item["color"], fill_alpha=.48)
        label_side = "right" if name == "AWS" else "left"
        label_x = px - 10 if label_side == "right" else px + 10
        text(cr, f'{item["short"]} {int(item["forecast"])}', label_x, py + 3, 8,
             item["color"], .96, align=label_side)

    # The independent prepaid unit lives in a narrow coordinate rail.
    rail_x0 = x + 315
    rounded_rect(cr, rail_x0, y + 58, 87, 184, 10)
    cr.set_source(gradient(rail_x0, y + 58, rail_x0, y + 242, [
        (0, "8b5cf6", .13), (.5, "020617", .52), (1, "00e5ff", .06),
    ]))
    cr.fill_preserve()
    set_hex(cr, "a78bfa", .30)
    cr.stroke()
    text(cr, "PREPAID", rail_x0 + 43.5, y + 76, 7, "a78bfa", .78, align="center")
    text(cr, "15D", rail_x0 + 43.5, y + 108, 20, "f8fafc", .98, align="center", glow=True)
    text(cr, "RUNWAY", rail_x0 + 43.5, y + 122, 7, "94a3b8", .64, align="center")
    diamond(cr, rail_x0 + 43.5, y + 157, 18, "c084fc", fill_alpha=.14)
    diamond(cr, rail_x0 + 43.5, y + 157, 8, "39ff88", fill_alpha=.32)
    text(cr, "+3D", rail_x0 + 43.5, y + 194, 12, "39ff88", .94, align="center")
    text(cr, "VS MONTH", rail_x0 + 43.5, y + 208, 7, "94a3b8", .58, align="center")
    text(cr, "$6.45", rail_x0 + 43.5, y + 231, 9, "c084fc", .90, align="center")

    divider(cr, x + 18, x + 406, y + 282)
    text(cr, "FARTHEST ABOVE DIAGONAL", x + 22, y + 305, 7.5, "94a3b8", .64)
    text(cr, "ANT +27 PTS", x + 400, y + 305, 9, "ff8f73", .92, align="right")
    text(cr, "HIGHEST LANDING", x + 22, y + 323, 7.5, "94a3b8", .64)
    text(cr, "AWS 92%", x + 400, y + 323, 9, "ffb454", .96, align="right")


def gem_points(cx, cy, scale=1):
    base = [(0, -61), (40, -36), (50, 24), (20, 57),
            (-20, 57), (-50, 24), (-40, -36)]
    return [(cx + px * scale, cy + py * scale) for px, py in base]


def fill_gem(cr, cx, cy, scale, color, alpha):
    points = gem_points(cx, cy, scale)
    polygon(cr, points)
    cr.set_source(gradient(cx, cy - 61 * scale, cx, cy + 57 * scale, [
        (0, color, alpha, .30), (.42, color, alpha, -.28), (1, color, alpha, -.62),
    ]))
    cr.fill_preserve()
    set_hex(cr, color, min(1, alpha + .27), .16)
    cr.set_line_width(1.2)
    cr.stroke()
    return points


def draw_nested_facets(cr, x, y):
    panel_frame(cr, x, y)
    header(cr, x, y, "ALLOWANCE FACETS", "AREA = % OF CAP")
    centers = [x + 82, x + 212, x + 342]
    for cx, name in zip(centers, ("AWS", "AZURE", "ANTHROPIC")):
        item = WATCH[name]
        cy = y + 140
        outer = gem_points(cx, cy, 1)
        polygon(cr, outer)
        cr.set_source(gradient(cx - 50, cy, cx + 50, cy, [
            (0, item["color"], .035), (.5, "020617", .42), (1, item["color"], .06),
        ]))
        cr.fill_preserve()
        set_hex(cr, item["color"], .38)
        cr.set_line_width(1.1)
        cr.stroke()

        # sqrt keeps nested polygon area proportional to the encoded fraction.
        forecast_scale = math.sqrt(item["forecast"] / 100)
        current_scale = math.sqrt(item["spent"] / 100)
        fill_gem(cr, cx, cy, forecast_scale, item["color"], .13)
        cr.set_dash([3, 3])
        polygon(cr, gem_points(cx, cy, forecast_scale))
        set_hex(cr, item["color"], .78)
        cr.stroke()
        cr.set_dash([])
        fill_gem(cr, cx, cy, current_scale, item["color"], .52)

        # Subtle construction facets make the objects feel engineered, not illustrative.
        set_hex(cr, "ffffff", .08)
        cr.set_line_width(.7)
        for point in outer[::2]:
            cr.move_to(cx, cy)
            cr.line_to(*point)
        cr.stroke()
        text(cr, item["short"], cx, cy - 3, 9, "f8fafc", .96, align="center", glow=True)
        text(cr, f'{int(item["spent"])}', cx, cy + 16, 17, "f8fafc", .98, align="center")
        text(cr, f'\u2192 {int(item["forecast"])}%', cx, cy + 30, 7.5,
             "ffb454" if item["forecast"] >= 80 else item["color"], .92, align="center")
        text(cr, item["amount"], cx, y + 224, 7.2, "94a3b8", .68, align="center",
             weight=cairo.FONT_WEIGHT_NORMAL)

    divider(cr, x + 18, x + 406, y + 245)
    text(cr, "FORECAST", x + 22, y + 267, 7, "94a3b8", .56)
    polygon(cr, [(x + 82, y + 260), (x + 92, y + 270),
                 (x + 82, y + 280), (x + 72, y + 270)])
    set_hex(cr, "c084fc", .10)
    cr.fill_preserve()
    set_hex(cr, "c084fc", .72)
    cr.set_dash([3, 3])
    cr.stroke()
    cr.set_dash([])
    text(cr, "CURRENT", x + 130, y + 267, 7, "94a3b8", .56)
    diamond(cr, x + 186, y + 270, 9, "00e5ff", fill_alpha=.48)

    polygon(cr, [(x + 244, y + 257), (x + 402, y + 257),
                 (x + 390, y + 296), (x + 256, y + 296)])
    cr.set_source(gradient(x + 244, y, x + 402, y, [
        (0, "8b5cf6", .18), (.55, "020617", .44), (1, "39ff88", .10),
    ]))
    cr.fill_preserve()
    set_hex(cr, "a78bfa", .34)
    cr.stroke()
    text(cr, "OPENROUTER", x + 257, y + 273, 7.5, "c084fc", .82)
    text(cr, "15D", x + 390, y + 276, 16, "f8fafc", .98, align="right", glow=True)
    text(cr, "+3D CUSHION", x + 390, y + 290, 7, "39ff88", .86, align="right")
    text(cr, "AREA COMPARISON IS APPROXIMATE · VALUES STAY EXACT", x + 212,
         y + 323, 6.8, "94a3b8", .48, align="center", weight=cairo.FONT_WEIGHT_NORMAL)


def shard_points(cx, top, bottom, width, skew):
    mid = (top + bottom) / 2
    return [
        (cx + skew, top),
        (cx + width * .48, top + 42),
        (cx + width * .38, mid + 18),
        (cx + width * .22, bottom),
        (cx - width * .34, bottom - 10),
        (cx - width * .48, mid - 10),
        (cx - width * .36, top + 32),
    ]


def shard_y(top, bottom, pct):
    return bottom - (bottom - top) * pct / 100


def draw_shard(cr, cx, top, bottom, item, skew):
    points = shard_points(cx, top, bottom, 72, skew)
    polygon(cr, points)
    cr.set_source(gradient(cx, top, cx, bottom, [
        (0, item["color"], .08), (.18, "07101f", .70), (1, "020617", .88),
    ]))
    cr.fill()
    cr.save()
    polygon(cr, points)
    cr.clip()
    forecast_y = shard_y(top, bottom, item["forecast"])
    current_y = shard_y(top, bottom, item["spent"])
    cr.rectangle(cx - 60, forecast_y, 120, bottom - forecast_y + 2)
    cr.set_source(gradient(cx, forecast_y, cx, bottom, [
        (0, item["color"], .16, .35), (1, item["color"], .18, -.48),
    ]))
    cr.fill()
    cr.rectangle(cx - 60, current_y, 120, bottom - current_y + 2)
    cr.set_source(gradient(cx, current_y, cx, bottom, [
        (0, item["color"], .88, .24), (.40, item["color"], .60),
        (1, item["color"], .30, -.60),
    ]))
    cr.fill()
    # Two facet planes make the fill read as a cut mineral rather than a tube.
    polygon(cr, [(cx + skew, top), (cx + 34, top + 42),
                 (cx + 25, bottom), (cx, bottom - 7)])
    set_hex(cr, "ffffff", .055)
    cr.fill()
    cr.restore()
    polygon(cr, points)
    set_hex(cr, item["color"], .66)
    cr.set_line_width(1.2)
    cr.stroke()
    # Current cut is solid, forecast cut is a dashed incision.
    cr.save()
    polygon(cr, points)
    cr.clip()
    set_hex(cr, "ffffff", .44)
    cr.move_to(cx - 48, current_y)
    cr.line_to(cx + 48, current_y)
    cr.stroke()
    set_hex(cr, item["color"], .76)
    cr.set_dash([3, 3])
    cr.move_to(cx - 48, forecast_y)
    cr.line_to(cx + 48, forecast_y)
    cr.stroke()
    cr.set_dash([])
    cr.restore()
    return current_y, forecast_y


def draw_shards(cr, x, y):
    panel_frame(cr, x, y)
    header(cr, x, y, "BUDGET SHARDS", "NOW / EOM CUTS")
    top, bottom = y + 62, y + 235
    centers = [x + 85, x + 212, x + 339]
    for index, (cx, name) in enumerate(zip(centers, ("AWS", "AZURE", "ANTHROPIC"))):
        item = WATCH[name]
        current_y, forecast_y = draw_shard(cr, cx, top, bottom, item, (-4, 7, -8)[index])
        text(cr, "CAP", cx, top - 6, 6.8, "f87171", .58, align="center")
        text(cr, f'{int(item["forecast"])}', cx + 31, forecast_y + 3, 7.2,
             item["color"], .88)
        text(cr, f'{int(item["spent"])}', cx - 31, current_y + 3, 7.2,
             "f8fafc", .82, align="right")
        text(cr, item["short"], cx, y + 255, 9, item["color"], .96, align="center")
        text(cr, item["amount"], cx, y + 269, 7, "94a3b8", .62, align="center",
             weight=cairo.FONT_WEIGHT_NORMAL)

    divider(cr, x + 18, x + 406, y + 281)
    text(cr, "OPENROUTER", x + 22, y + 303, 8, "c084fc", .88)
    # A flying chevron communicates runway direction without pretending it is currency.
    chevron = [(x + 125, y + 293), (x + 335, y + 293), (x + 353, y + 304),
               (x + 335, y + 315), (x + 125, y + 315), (x + 139, y + 304)]
    polygon(cr, chevron)
    cr.set_source(gradient(x + 125, y, x + 353, y, [
        (0, "8b5cf6", .18), (.72, "c084fc", .32), (1, "39ff88", .20),
    ]))
    cr.fill_preserve()
    set_hex(cr, "c084fc", .56)
    cr.stroke()
    text(cr, "15D RUNWAY", x + 239, y + 307, 8, "f8fafc", .88, align="center")
    text(cr, "+3D", x + 400, y + 307, 9, "39ff88", .94, align="right")
    text(cr, "SCULPTURAL / LOW-READING-PRECISION", x + 212, y + 330, 6.8,
         "94a3b8", .46, align="center", weight=cairo.FONT_WEIGHT_NORMAL)


def render_one(filename, drawer):
    width, height = 472, 390
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    draw_wallpaper(cr, width, height)
    drawer(cr, 24, 26)
    surface.write_to_png(os.path.join(OUT, filename))


def render_contact_sheet():
    width, height = 1016, 856
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    draw_wallpaper(cr, width, height)
    text(cr, "BILLING GEOMETRY STUDIES", 28, 28, 15, "f8fafc", .96, glow=True)
    text(cr, "SAME WATCH SCENARIO · FOUR ENCODING FAMILIES · TRUE SIZE", 988, 27,
         8, "94a3b8", .64, align="right", weight=cairo.FONT_WEIGHT_NORMAL)
    names = [
        ("facet-ledger.png", "01  DISCRETE / GLANCEABLE"),
        ("surprise-map.png", "02  ANALYTICAL / DIAGNOSTIC"),
        ("allowance-facets.png", "03  AMBIENT / AREA-BASED"),
        ("budget-shards.png", "04  SCULPTURAL / GAUGE-LIKE"),
    ]
    origins = [(20, 48), (524, 48), (20, 448), (524, 448)]
    for (filename, caption), (px, py) in zip(names, origins):
        image = cairo.ImageSurface.create_from_png(os.path.join(OUT, filename))
        cr.set_source_surface(image, px, py)
        cr.paint()
        text(cr, caption, px + 24, py + 382, 8, "cbd5e1", .68,
             weight=cairo.FONT_WEIGHT_NORMAL)
    text(cr, "METERED SERVICES NORMALIZED TO THEIR OWN CAPS · PREPAID RUNWAY KEPT IN DAYS",
         width / 2, height - 16, 7.5, "94a3b8", .60, align="center",
         weight=cairo.FONT_WEIGHT_NORMAL)
    surface.write_to_png(os.path.join(OUT, "contact-sheet.png"))


if __name__ == "__main__":
    render_one("facet-ledger.png", draw_facets)
    render_one("surprise-map.png", draw_risk_field)
    render_one("allowance-facets.png", draw_nested_facets)
    render_one("budget-shards.png", draw_shards)
    render_contact_sheet()
    print("wrote geometric billing variants to", OUT)
