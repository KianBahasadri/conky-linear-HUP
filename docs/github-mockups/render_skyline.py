#!/usr/bin/env python3
"""Isometric contribution skyline: the year of squares extruded into towers.

The shipped rail draws one flat square per day from `data-level` (0-4). A
skyline needs a real magnitude per day, so this study uses contribution
*counts* scraped from the same page's `<tool-tip>` text and cached in
`sample-counts.json`.
"""

import datetime
import json
import math
import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))
import render_variants as rv

# GitHub's own dark-theme ramp, matching conky/github-tracker-renderer.lua.
LEVEL_COLORS = ["0e4429", "0e4429", "006d32", "26a641", "39d353"]
EMPTY = "1e293b"
MUTED = "94a3b8"
DIM = "64748b"
TEXT = "f8fafc"

# Two lattices, both with near-equal basis lengths so plan-view cells stay
# square. "iso" runs one week right and slightly toward the viewer, which makes
# the whole ribbon drift 122px downhill across the year. "level" is the same
# lattice rotated by that 6.56deg drift, so the week axis is exactly horizontal
# and the front row is a straight line the panel below can be stacked under.
PROJECTIONS = {
    "iso": ((20.0, 2.3), (12.4, -16.0)),
    "level": ((20.132, 0.0), (10.491, -17.312)),
}
MODE = "iso"

WEEK, DAY = PROJECTIONS[MODE]
FILL = 0.86           # cell footprint as a fraction of the step, leaving gutters
HEIGHT_SCALE = 8.5    # tower height = HEIGHT_SCALE * sqrt(count)
DECK = "1e293b"       # roof slab under the towers, level mode only
DECK_THICK = 15.0

# Stat readout offsets, in object-box coordinates (see draw()).
STAT_TOP_X = 690
STAT_TOP_GAP = 280
STAT_FLOOR_UP = 78
STAT_FLOOR_GAP = 44
STAT_FLOOR_IN = 14


def set_mode(mode):
    """Switch lattices. Call before set_scale/fit_width; resets to base scale."""
    global MODE
    MODE = mode
    set_scale(PROJECTIONS[mode][0][0])


def set_scale(week_px):
    """Rescale the lattice around a new week step, keeping the cells square."""
    global WEEK, DAY, HEIGHT_SCALE, DECK_THICK, STAT_TOP_X, STAT_TOP_GAP
    global STAT_FLOOR_UP, STAT_FLOOR_GAP, STAT_FLOOR_IN
    base_week, base_day = PROJECTIONS[MODE]
    factor = week_px / base_week[0]
    WEEK = (base_week[0] * factor, base_week[1] * factor)
    DAY = (base_day[0] * factor, base_day[1] * factor)
    HEIGHT_SCALE = 8.5 * factor
    DECK_THICK = 15.0 * factor
    STAT_TOP_X = 690 * factor
    STAT_TOP_GAP = 280 * factor
    STAT_FLOOR_UP = 78 * factor
    STAT_FLOOR_GAP = 44 * factor
    STAT_FLOOR_IN = 14 * factor


def fit_width(target_px, days=None):
    """Pick the week step that makes the object exactly target_px wide.

    Level mode measures the plinth, which is what has to line up with the edges
    of the panel it sits on; iso mode has no plinth, so it measures the cells.
    """
    weeks = max(cell["week"] for cell in grid(days or load_days())) + 1
    base_week, base_day = PROJECTIONS[MODE]
    ratio = base_day[0] / base_week[0]
    if MODE == "level":
        steps = weeks + (1 - FILL) + 7 * ratio
    else:
        steps = (weeks - 1) + FILL + ratio * (6 + FILL)
    set_scale(target_px / steps)
    return WEEK[0]


def set_height(px_at_max, days=None):
    """Scale the extrusion so the busiest day stands px_at_max tall."""
    global HEIGHT_SCALE
    busiest = max(entry.get("count", 0) for entry in (days or load_days()))
    HEIGHT_SCALE = px_at_max / math.sqrt(busiest) if busiest else 0.0


def load_days(path=None):
    with open(path or os.path.join(HERE, "sample-counts.json")) as handle:
        return json.load(handle)


def tower_height(count):
    # sqrt, not linear: one 133-commit day against a median of 2 would flatten
    # every other tower into the ground plane under a linear scale.
    return HEIGHT_SCALE * math.sqrt(count) if count else 0.0


def grid(days):
    """Place each day on the (week, weekday) lattice GitHub itself uses."""
    first = datetime.date.fromisoformat(days[0]["date"])
    start = first - datetime.timedelta(days=(first.weekday() + 1) % 7)
    cells = []
    for entry in days:
        date = datetime.date.fromisoformat(entry["date"])
        offset = (date - start).days
        cells.append({
            "week": offset // 7,
            "day": offset % 7,
            "date": date,
            "count": entry.get("count", 0),
            "level": entry.get("level", 0),
        })
    return cells


def project(ox, oy, week, day):
    return (ox + week * WEEK[0] + day * DAY[0],
            oy + week * WEEK[1] + day * DAY[1])


def footprint(ox, oy, week, day):
    x0, y0 = project(ox, oy, week, day)
    wx, wy = WEEK[0] * FILL, WEEK[1] * FILL
    dx, dy = DAY[0] * FILL, DAY[1] * FILL
    return [(x0, y0), (x0 + wx, y0 + wy), (x0 + wx + dx, y0 + wy + dy), (x0 + dx, y0 + dy)]


def poly(cr, points):
    cr.move_to(*points[0])
    for point in points[1:]:
        cr.line_to(*point)
    cr.close_path()


def draw_tower(cr, base, height, color):
    top = [(x, y - height) for x, y in base]

    # Only two of the four sides face the camera: the day-0 edge and the
    # week-max edge.
    for edge, shade in (((0, 1), -0.55), ((1, 2), -0.30)):
        a, b = edge
        poly(cr, [base[a], base[b], top[b], top[a]])
        rv.set_hex(cr, color, 0.95, shade)
        cr.fill()

    poly(cr, top)
    rv.set_hex(cr, color, 0.98, 0.12)
    cr.fill_preserve()
    rv.set_hex(cr, color, 0.7, 0.45)
    cr.set_line_width(0.7)
    cr.stroke()


def deck_corners(ox, oy, weeks):
    """Full lattice quad (no FILL inset), padded out to a slab edge."""
    pad = WEEK[0] * (1 - FILL) / 2
    front_l = project(ox - pad, oy, 0, 0)
    front_r = project(ox + pad, oy, weeks, 0)
    back_r = project(ox + pad, oy, weeks, 7)
    back_l = project(ox - pad, oy, 0, 7)
    return [front_l, front_r, back_r, back_l]


def draw_deck(cr, ox, oy, weeks):
    """A thin plinth under the lattice, so the ribbon reads as sitting on
    something rather than floating. Its south and east walls are the two that
    face the camera, same pair the towers show."""
    front_l, front_r, back_r, back_l = deck_corners(ox, oy, weeks)
    drop = lambda p: (p[0], p[1] + DECK_THICK)

    for wall, shade in (((front_l, front_r), -0.45), ((front_r, back_r), -0.62)):
        a, b = wall
        poly(cr, [a, b, drop(b), drop(a)])
        rv.set_hex(cr, DECK, 0.94, shade)
        cr.fill()

    poly(cr, [front_l, front_r, back_r, back_l])
    rv.set_hex(cr, DECK, 0.9, -0.12)
    cr.fill_preserve()
    rv.set_hex(cr, DECK, 0.9, 0.5)
    cr.set_line_width(0.9)
    cr.stroke()


def streaks(cells):
    ordered = sorted(cells, key=lambda cell: cell["date"])
    best = run = 0
    best_end = current_end = None
    for cell in ordered:
        if cell["count"]:
            run += 1
            if run > best:
                best, best_end = run, cell["date"]
        else:
            run = 0
    current = 0
    for cell in reversed(ordered):
        if cell["count"]:
            current += 1
            if current_end is None:
                current_end = cell["date"]
        elif current or cell is ordered[-1]:
            break
    return best, best_end, current, current_end


def draw(cr, ox, oy, days=None, stats=True):
    cells = grid(days or load_days())
    level = MODE == "level"
    if level:
        draw_deck(cr, ox, oy, max(cell["week"] for cell in cells) + 1)

    # Painter's order: higher on screen is farther away, so it goes down first.
    for cell in sorted(cells, key=lambda c: (project(0, 0, c["week"], c["day"])[1], c["week"])):
        base = footprint(ox, oy, cell["week"], cell["day"])
        if not cell["count"]:
            poly(cr, base)
            rv.set_hex(cr, EMPTY, 0.42)
            cr.set_line_width(0.8)
            cr.stroke()
            continue
        draw_tower(cr, base, tower_height(cell["count"]), LEVEL_COLORS[cell["level"]])

    # Month ticks ride the day-0 edge, which is the front of the ribbon.
    seen = set()
    for cell in sorted(cells, key=lambda c: c["date"]):
        if cell["day"] != 0:
            continue
        key = (cell["date"].year, cell["date"].month)
        if key in seen or cell["date"].day > 7:
            continue
        seen.add(key)
        x, y = project(ox, oy, cell["week"], 0)
        # In level mode the fascia of the plinth is the month scale; in iso
        # there is no plinth, so the ticks sit just under the front edge.
        rv.flat_text(cr, cell["date"].strftime("%b").upper(), x + 3,
                     y + (DECK_THICK - 4 if level else 15), 6.6, DIM, 0.7)

    if not stats:
        return cells

    if level:
        draw_stats_row(cr, ox, oy, cells, days)
        return cells

    total = sum(cell["count"] for cell in cells)
    busiest = max(cells, key=lambda cell: cell["count"])
    best, best_end, current, current_end = streaks(cells)

    # The ribbon descends left to right, which clears two areas inside the
    # object's own box: the strip above its right end, and the floor below
    # its left end. The readout splits across both.
    bx0, by0, _bx1, by1 = bounds(days)

    def stat(label, value, unit, sub, x, y):
        rv.flat_text(cr, label, x, y, 6.8, MUTED, 0.7)
        rv.lit_text(cr, value, x, y + 21, 18, "39d353", 1.0)
        width = rv.text_width(cr, value, 18, cairo.FONT_WEIGHT_BOLD)
        rv.flat_text(cr, unit, x + width + 8, y + 16, 7.2, TEXT, 0.82)
        rv.flat_text(cr, sub, x + width + 8, y + 26, 6.6, DIM, 0.72)

    total = sum(cell["count"] for cell in cells)
    busiest = max(cells, key=lambda cell: cell["count"])
    best, best_end, current, current_end = streaks(cells)

    top_x, top_y = ox + bx0 + STAT_TOP_X, oy + by0 + 13
    stat("LAST YEAR", f"{total:,}", "contributions",
         f"{cells[0]['date']:%b %-d, %Y} — {cells[-1]['date']:%b %-d, %Y}", top_x, top_y)
    stat("BUSIEST DAY", str(busiest["count"]), "contributions",
         f"{busiest['date']:%b %-d}", top_x + STAT_TOP_GAP, top_y)

    floor_x, floor_y = ox + bx0 + STAT_FLOOR_IN, oy + by1 - STAT_FLOOR_UP
    stat("LONGEST STREAK", str(best), "days",
         f"ended {best_end:%b %-d}" if best_end else "", floor_x, floor_y)
    stat("CURRENT STREAK", str(current), "days",
         f"through {current_end:%b %-d}" if current_end else "", floor_x, floor_y + STAT_FLOOR_GAP)

    return cells


def draw_stats_row(cr, ox, oy, cells, days=None):
    """Level mode keeps every edge horizontal, so the readout is a band across
    the top rather than the two pockets the diagonal ribbon opens up."""
    bx0, by0, bx1, _by1 = bounds(days)
    total = sum(cell["count"] for cell in cells)
    busiest = max(cells, key=lambda cell: cell["count"])
    best, best_end, current, current_end = streaks(cells)

    entries = [
        ("LAST YEAR", f"{total:,}", "contributions",
         f"{cells[0]['date']:%b %-d, %Y} - {cells[-1]['date']:%b %-d, %Y}"),
        ("BUSIEST DAY", str(busiest["count"]), "contributions",
         f"{busiest['date']:%b %-d}"),
        ("LONGEST STREAK", str(best), "days",
         f"ended {best_end:%b %-d}" if best_end else ""),
        ("CURRENT STREAK", str(current), "days",
         f"through {current_end:%b %-d}" if current_end else ""),
    ]

    width = bx1 - bx0
    step = width / len(entries)
    top = oy + by0 - 46
    for index, (label, value, unit, sub) in enumerate(entries):
        x = ox + bx0 + index * step
        rv.flat_text(cr, label, x, top, 6.8, MUTED, 0.7)
        rv.lit_text(cr, value, x, top + 20, 17, "39d353", 1.0)
        offset = rv.text_width(cr, value, 17, cairo.FONT_WEIGHT_BOLD) + 8
        rv.flat_text(cr, unit, x + offset, top + 15, 7.2, TEXT, 0.82)
        rv.flat_text(cr, sub, x + offset, top + 25, 6.6, DIM, 0.72)

    rv.divider(cr, ox + bx0, ox + bx1, top + 32)


def bounds(days=None):
    cells = grid(days or load_days())
    xs, ys = [], []
    for cell in cells:
        for x, y in footprint(0, 0, cell["week"], cell["day"]):
            xs.append(x)
            ys.append(y)
            ys.append(y - tower_height(cell["count"]))
    if MODE == "level":
        weeks = max(cell["week"] for cell in cells) + 1
        for x, y in deck_corners(0, 0, weeks):
            xs.append(x)
            ys += [y, y + DECK_THICK]
    return min(xs), min(ys), max(xs), max(ys)


def plate(name, setup):
    setup()
    x0, y0, x1, y1 = bounds()
    margin = 40
    top = margin + (56 if MODE == "level" else 0)   # room for the stat band
    width = int(x1 - x0) + margin * 2
    height = int(y1 - y0) + top + margin
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    rv.wallpaper(cr, width, height)
    draw(cr, margin - x0, top - y0)
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {width}x{height}")


def main():
    def iso():
        set_mode("iso")

    def level():
        set_mode("level")
        fit_width(1008)          # the rate limit panel's drawn width
        set_height(170)

    plate("01-skyline.png", iso)
    plate("02-skyline-level.png", level)


if __name__ == "__main__":
    main()
