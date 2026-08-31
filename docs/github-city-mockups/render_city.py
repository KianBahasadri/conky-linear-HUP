#!/usr/bin/env python3
"""Art-deco contribution city at the shipped overlay camera.

Demos only — nothing here is wired into Conky.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))
import render_variants as rv

# Live overlay lattice: week axis flat, weekday mostly up the screen.
SHIPPED_DX = 0.015
SHIPPED_DY = 0.095
FILL = 0.86

STONE = "d4c6a8"
STONE_SIDE = "8a7c62"
STONE_TOP = "e4d7bb"
GLASS = "101816"
GOLD = "d4af37"
GOLD_LIT = "f3e27a"
GOLD_DIM = "8a7340"
PLINTH = "0c0c10"
GLOW = ["1c3320", "2f7a32", "6adf45", "b4ff6a", "e8ffb0"]
PALETTES = [
    (STONE, STONE_SIDE, STONE_TOP),
    ("cbb892", "7d6c4e", "e6d7b4"),
    ("8b4a3c", "5a2e28", "b56a5a"),
    ("9aa3a0", "5c6462", "c5ccc9"),
    ("e2d6bc", "a09070", "f3ead8"),
]

WEEK = (20.0, 0.0)
DAY = (20.0 * SHIPPED_DX, -20.0 * SHIPPED_DY)
HEIGHT_SCALE = 8.5
DECK_THICK = 11.0


def set_shipped(week_px):
    global WEEK, DAY, HEIGHT_SCALE, DECK_THICK
    WEEK = (week_px, 0.0)
    DAY = (week_px * SHIPPED_DX, -week_px * SHIPPED_DY)
    DECK_THICK = week_px * 0.55


def set_height(px_at_max, days):
    global HEIGHT_SCALE
    busiest = max(entry.get("count", 0) for entry in days)
    HEIGHT_SCALE = px_at_max / math.sqrt(busiest) if busiest else 0.0


def fit_shipped_width(target_px, days):
    weeks = max(cell["week"] for cell in grid(days)) + 1
    steps = weeks + (1 - FILL) + 7 * SHIPPED_DX
    set_shipped(target_px / steps)
    return WEEK[0]


def fit_shipped_height(window_h, days):
    global HEIGHT_SCALE
    busiest = max(entry.get("count", 0) for entry in days)
    headroom = window_h - DECK_THICK - 7 * (-DAY[1])
    if headroom < 20:
        headroom = 20
    HEIGHT_SCALE = headroom / math.sqrt(busiest) if busiest else 0.0


def load_days():
    live = os.path.normpath(os.path.join(HERE, "..", "..", "cache", "github-contributions.json"))
    sample = os.path.normpath(os.path.join(HERE, "..", "github-mockups", "sample-counts.json"))
    if os.path.exists(live):
        payload = json.load(open(live))
        if payload.get("ok") and payload.get("contributions"):
            return payload["contributions"]
    return json.load(open(sample))


def tower_height(count):
    return HEIGHT_SCALE * math.sqrt(count) if count else 0.0


def grid(days):
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


def footprint(ox, oy, week, day, fill=FILL):
    x0, y0 = project(ox, oy, week, day)
    wx, wy = WEEK[0] * fill, WEEK[1] * fill
    dx, dy = DAY[0] * fill, DAY[1] * fill
    return [(x0, y0), (x0 + wx, y0 + wy), (x0 + wx + dx, y0 + wy + dy), (x0 + dx, y0 + dy)]


def poly(cr, points):
    cr.move_to(*points[0])
    for point in points[1:]:
        cr.line_to(*point)
    cr.close_path()


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def inset_quad(quad, t):
    cx = sum(p[0] for p in quad) / 4
    cy = sum(p[1] for p in quad) / 4
    return [(cx + (x - cx) * t, cy + (y - cy) * t) for x, y in quad]


def rnd(*parts):
    digest = hashlib.md5("|".join(str(p) for p in parts).encode()).digest()
    return digest[0] / 255.0


def deck_corners(ox, oy, weeks):
    pad = WEEK[0] * (1 - FILL) / 2
    front_l = project(ox - pad, oy, 0, 0)
    front_r = project(ox + pad, oy, weeks, 0)
    back_r = project(ox + pad, oy, weeks, 7)
    back_l = project(ox - pad, oy, 0, 7)
    return [front_l, front_r, back_r, back_l]


def iso_bounds(cells, extra_up=0):
    weeks = max(cell["week"] for cell in cells) + 1
    xs, ys = [], []
    for cell in cells:
        for x, y in footprint(0, 0, cell["week"], cell["day"]):
            xs.append(x)
            ys.append(y)
            ys.append(y - tower_height(cell["count"]) - extra_up)
    for x, y in deck_corners(0, 0, weeks):
        xs.append(x)
        ys += [y, y + DECK_THICK]
    return min(xs), min(ys), max(xs), max(ys)


def navy_wallpaper(cr, width, height):
    base = cairo.LinearGradient(0, 0, 0, height)
    base.add_color_stop_rgb(0, 0.043, 0.07, 0.125)
    base.add_color_stop_rgb(1, 0.015, 0.015, 0.02)
    cr.set_source(base)
    cr.paint()


def gold_edge(cr, a, b, width=1.1, color=GOLD, alpha=0.95):
    rv.set_hex(cr, color, alpha)
    cr.set_line_width(width)
    cr.move_to(*a)
    cr.line_to(*b)
    cr.stroke()


def paint_south_texture(cr, base, top, surf):
    """Map a PixelLab facade onto the south face, nearest-neighbour, tiled up."""
    b0, b1 = base[0], base[1]
    t0, t1 = top[0], top[1]
    cr.save()
    poly(cr, [b0, b1, t1, t0])
    cr.clip()
    width = math.hypot(b1[0] - b0[0], b1[1] - b0[1])
    height = math.hypot(t0[0] - b0[0], t0[1] - b0[1])
    if width < 1 or height < 1:
        cr.restore()
        return
    angle = math.atan2(b1[1] - b0[1], b1[0] - b0[0])
    cr.translate(b0[0], b0[1])
    cr.rotate(angle)
    scale = width / surf.get_width()
    cr.scale(scale, -scale)
    pattern = cairo.SurfacePattern(surf)
    pattern.set_extend(cairo.EXTEND_REPEAT)
    pattern.set_filter(cairo.FILTER_NEAREST)
    cr.set_source(pattern)
    cr.rectangle(0, 0, surf.get_width(), height / scale)
    cr.fill()
    cr.restore()


def load_png(name):
    path = os.path.join(HERE, "pixellab", name)
    return cairo.ImageSurface.create_from_png(path)


def stamp_png(cr, surf, x, y, target_h):
    sw, sh = surf.get_width(), surf.get_height()
    if sh <= 0:
        return
    scale = target_h / sh
    cr.save()
    cr.translate(x - sw * scale / 2, y - sh * scale)
    cr.scale(scale, scale)
    cr.set_source_surface(surf, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    cr.restore()


def artdeco_prism(cr, base, height, stone=None, side=None, topc=None, gold=True):
    if height <= 0:
        return list(base)
    stone = stone or STONE
    side = side or STONE_SIDE
    topc = topc or STONE_TOP
    top = [(x, y - height) for x, y in base]
    poly(cr, [base[0], base[1], top[1], top[0]])
    rv.set_hex(cr, stone, 1.0)
    cr.fill()
    poly(cr, [base[1], base[2], top[2], top[1]])
    rv.set_hex(cr, side, 1.0)
    cr.fill()
    poly(cr, top)
    rv.set_hex(cr, topc, 1.0)
    cr.fill()
    if gold:
        gold_edge(cr, top[0], top[1], 1.15, GOLD, 0.92)
        gold_edge(cr, top[1], top[2], 0.8, GOLD_DIM, 0.7)
    return top


def facade_windows(cr, base, top, count, level, seed, bay=0.14, cols=None, pitch=3.2, pad=0.18):
    south_w = abs(base[1][0] - base[0][0])
    south_h = abs(base[0][1] - top[0][1])
    if south_w < 3 or south_h < 3:
        return
    b0 = lerp(base[0], base[1], bay)
    b1 = lerp(base[0], base[1], 1 - bay)
    t0 = lerp(top[0], top[1], bay)
    t1 = lerp(top[0], top[1], 1 - bay)
    b0 = lerp(b0, t0, 0.08)
    b1 = lerp(b1, t1, 0.08)
    t0 = lerp(b0, t0, 0.92)
    t1 = lerp(b1, t1, 0.92)
    poly(cr, [b0, b1, t1, t0])
    rv.set_hex(cr, GLASS, 0.96)
    cr.fill()
    if cols is None:
        cols = 1 if south_w < 8 else 2 if south_w < 16 else 3 if south_w < 28 else 4 if south_w < 42 else 5
    rows = max(1, int(south_h / pitch))
    lit = 0.55 + 0.40 * min(1.0, math.sqrt(max(count, 1) / 80.0))
    glow = GLOW[min(max(level, 0), 4)]
    for row in range(rows):
        if rows >= 10 and row and row % 6 == 0:
            gold_edge(cr, lerp(b0, t0, row / rows), lerp(b1, t1, row / rows), 0.8, STONE, 0.85)
        for col in range(cols):
            u0 = (col + pad) / cols
            u1 = (col + 1 - pad) / cols
            v0 = (row + 0.22) / rows
            v1 = (row + 0.78) / rows
            p00 = lerp(lerp(b0, b1, u0), lerp(t0, t1, u0), v0)
            p10 = lerp(lerp(b0, b1, u1), lerp(t0, t1, u1), v0)
            p11 = lerp(lerp(b0, b1, u1), lerp(t0, t1, u1), v1)
            p01 = lerp(lerp(b0, b1, u0), lerp(t0, t1, u0), v1)
            on = rnd(seed, row, col) <= lit
            poly(cr, [p00, p10, p11, p01])
            rv.set_hex(cr, glow if on else "0c1610", 0.95 if on else 0.8)
            cr.fill()


def pick_kind(cell, height):
    r = rnd(cell["date"], "kind")
    if height < 14:
        return "house" if r < 0.55 else "shop" if r < 0.85 else "warehouse"
    if height < 24:
        return "walkup" if r < 0.45 else "shop" if r < 0.7 else "house" if r < 0.88 else "gothic"
    if height < 42:
        return "office" if r < 0.4 else "walkup" if r < 0.65 else "setback" if r < 0.85 else "glass"
    if height < 72:
        return ("setback", "office", "chrysler", "empire", "glass")[int(r * 5) % 5]
    return ("empire", "chrysler", "setback", "slab")[int(r * 4) % 4]


def pick_palette(cell, kind):
    r = rnd(cell["date"], "pal")
    if kind in ("house", "shop", "warehouse"):
        return PALETTES[int(r * 5) % 5]
    if kind == "gothic":
        return PALETTES[3]
    if kind == "glass":
        return ("2a4038", "1a2822", "3d5a4c")
    return PALETTES[int(r * 3) % 3]


def roof_frame(top):
    cx = (top[0][0] + top[1][0]) / 2
    cy = min(p[1] for p in top)
    w = max(4.0, abs(top[1][0] - top[0][0]))
    return cx, cy, w


def pitched_roof(cr, top, rise, side_color):
    cx, cy, w = roof_frame(top)
    rise = min(rise, w * 0.55)
    peak = (cx, cy - rise)
    poly(cr, [top[0], top[1], peak])
    rv.set_hex(cr, "6a3a32", 1.0)
    cr.fill()
    poly(cr, [top[1], top[2], peak])
    rv.set_hex(cr, side_color, 1.0, -0.15)
    cr.fill()
    hx = lerp(top[0], top[1], 0.28)[0]
    cr.rectangle(hx - 1.4, peak[1] + rise * 0.35, 2.8, rise * 0.28)
    rv.set_hex(cr, "4a322c", 1.0)
    cr.fill()


def hip_roof(cr, top):
    cx, cy, w = roof_frame(top)
    rise = w * 0.38
    peak = (cx, cy - rise)
    poly(cr, [top[0], top[1], peak])
    rv.set_hex(cr, "7a4a36", 1.0)
    cr.fill()
    poly(cr, [top[1], top[2], peak])
    rv.set_hex(cr, "5a3428", 1.0)
    cr.fill()


def mansard(cr, top):
    cx, cy, w = roof_frame(top)
    h = w * 0.42
    inset = w * 0.22
    poly(cr, [
        (cx - w / 2, cy), (cx + w / 2, cy),
        (cx + w / 2 - inset, cy - h), (cx - w / 2 + inset, cy - h),
    ])
    rv.set_hex(cr, "5c4030", 1.0)
    cr.fill()
    cr.rectangle(cx - w / 2 + inset, cy - h - w * 0.08, w - 2 * inset, w * 0.08)
    rv.set_hex(cr, GOLD, 0.92)
    cr.fill()


def gold_dome(cr, top, height):
    cx, cy, w = roof_frame(top)
    rx = max(4.0, w * 0.42)
    ry = max(3.5, min(rx * 0.78, w * 0.36))
    cr.save()
    cr.translate(cx, cy)
    cr.scale(1.0, ry / rx)
    cr.arc(0, 0, rx, math.pi, 0)
    cr.close_path()
    rv.set_hex(cr, GOLD, 0.95)
    cr.fill()
    cr.restore()
    cr.rectangle(cx - rx * 0.55, cy - 1.5, rx * 1.1, 2.2)
    rv.set_hex(cr, GOLD_DIM, 0.95)
    cr.fill()


def barrel_vault(cr, top):
    cx, cy, w = roof_frame(top)
    rx = w * 0.48
    ry = w * 0.28
    cr.save()
    cr.translate(cx, cy)
    cr.scale(1.0, ry / rx)
    cr.arc(0, 0, rx, math.pi, 0)
    cr.close_path()
    cr.restore()
    rv.set_hex(cr, "8a7c62", 1.0)
    cr.fill()


def water_tank(cr, top):
    cx, cy, w = roof_frame(top)
    tw = max(5.0, w * 0.42)
    th = max(5.0, tw * 0.72)
    cr.rectangle(cx - tw / 2, cy - th, tw, th)
    rv.set_hex(cr, "5a6570", 0.95)
    cr.fill()
    cr.save()
    cr.translate(cx, cy - th)
    cr.scale(1.0, 0.35)
    cr.arc(0, 0, tw / 2, 0, math.tau)
    cr.restore()
    rv.set_hex(cr, "6a7580", 0.95)
    cr.fill()


def penthouse(cr, top, stone=STONE, side=STONE_SIDE):
    cap = inset_quad(top, 0.58)
    h = max(5.5, abs(top[1][0] - top[0][0]) * 0.38)
    ph = artdeco_prism(cr, cap, h, stone, side, STONE_TOP, gold=True)
    facade_windows(cr, cap, ph, 8, 2, ("ph", cap[0][0]), bay=0.16, cols=2, pitch=4.0)


def lantern(cr, top):
    cx, cy, w = roof_frame(top)
    s = max(5.0, w * 0.40)
    cr.rectangle(cx - s / 2, cy - s, s, s)
    rv.set_hex(cr, GOLD, 0.95)
    cr.fill()
    cr.rectangle(cx - s * 0.28, cy - s * 0.78, s * 0.56, s * 0.42)
    rv.set_hex(cr, "1c3320", 0.95)
    cr.fill()
    cr.rectangle(cx - s / 2, cy - s - w * 0.08, s, w * 0.08)
    rv.set_hex(cr, GOLD_LIT, 0.95)
    cr.fill()


def parapet(cr, top):
    cx, cy, w = roof_frame(top)
    cr.rectangle(cx - w / 2, cy - w * 0.12, w, w * 0.12)
    rv.set_hex(cr, GOLD, 0.92)
    cr.fill()
    for t in (0.08, 0.92):
        x = cx - w / 2 + w * t
        cr.rectangle(x - 1.4, cy - w * 0.22, 2.8, w * 0.22)
        rv.set_hex(cr, GOLD_DIM, 0.95)
        cr.fill()


def arcade(cr, top):
    cx, cy, w = roof_frame(top)
    n = 3 if w < 22 else 4
    bw = w / n
    for i in range(n):
        x = cx - w / 2 + (i + 0.5) * bw
        cr.save()
        cr.translate(x, cy)
        cr.scale(1.0, 0.7)
        cr.arc(0, 0, bw * 0.38, math.pi, 0)
        cr.close_path()
        cr.restore()
        rv.set_hex(cr, GOLD, 0.9)
        cr.fill()


def sawtooth(cr, top):
    cx, cy, w = roof_frame(top)
    n = 3 if w < 20 else 4
    bw = w / n
    h = bw * 0.55
    for i in range(n):
        x0 = cx - w / 2 + i * bw
        poly(cr, [(x0, cy), (x0 + bw, cy), (x0 + bw * 0.45, cy - h)])
        rv.set_hex(cr, "6a6458" if i % 2 == 0 else "8a7c62", 1.0)
        cr.fill()


def billboard(cr, top):
    cx, cy, w = roof_frame(top)
    bw = w * 0.72
    bh = max(4.0, w * 0.28)
    cr.rectangle(cx - bw / 2, cy - bh, bw, bh)
    rv.set_hex(cr, "1a1814", 0.95)
    cr.fill()
    cr.rectangle(cx - bw / 2 + 1.2, cy - bh + 1.0, bw - 2.4, bh - 2.0)
    rv.set_hex(cr, "6adf45", 0.55)
    cr.fill()


def hvac_farm(cr, top):
    cx, cy, w = roof_frame(top)
    for i, t in enumerate((0.28, 0.52, 0.76)):
        x = cx - w / 2 + w * t
        bw = max(3.2, w * 0.18)
        bh = bw * (0.7 + 0.15 * (i % 2))
        cr.rectangle(x - bw / 2, cy - bh, bw, bh)
        rv.set_hex(cr, "4a5560" if i != 1 else "5a6570", 0.95)
        cr.fill()


def chrysler_crown(cr, top, height):
    cx, cy, w = roof_frame(top)
    h = max(6.0, min(w * 0.55, height * 0.10))
    for i, t in enumerate((1.0, 0.68, 0.40)):
        hw = w * 0.48 * t
        y0 = cy - i * (h / 2.6)
        poly(cr, [
            (cx - hw, y0), (cx + hw, y0),
            (cx + hw * 0.55, y0 - h / 2.8), (cx - hw * 0.55, y0 - h / 2.8),
        ])
        rv.set_hex(cr, GOLD if i else GOLD_DIM, 0.95)
        cr.fill()
    s = max(4.0, w * 0.24)
    cr.rectangle(cx - s / 2, cy - h - s * 0.15, s, s * 0.65)
    rv.set_hex(cr, GOLD, 0.95)
    cr.fill()


def empire_cap(cr, top, height):
    cap = inset_quad(top, 0.62)
    h1 = max(5.0, abs(top[1][0] - top[0][0]) * 0.28)
    mid = artdeco_prism(cr, cap, h1, STONE, STONE_SIDE, STONE_TOP, gold=True)
    facade_windows(cr, cap, mid, 6, 2, ("emp", cap[0][0]), bay=0.18, cols=2, pitch=3.8)
    lantern(cr, mid)


def gothic_hat(cr, top):
    hip_roof(cr, top)


def artdeco_crown(cr, top, height, cell, kind):
    if kind == "house":
        return
    if kind == "warehouse":
        water_tank(cr, top)
        return
    if kind == "gothic":
        gothic_hat(cr, top)
        return
    if kind == "chrysler":
        chrysler_crown(cr, top, height)
        return
    if kind == "empire":
        empire_cap(cr, top, height)
        return
    if kind == "slab":
        penthouse(cr, top)
        return
    if kind == "glass":
        hvac_farm(cr, top)
        return
    if kind == "shop":
        parapet(cr, top)
        return
    if height < 14:
        parapet(cr, top)
        return
    pick = int(rnd(cell["date"], "crown") * 9)
    fns = (penthouse, lantern, hip_roof, gold_dome, barrel_vault,
           mansard, arcade, sawtooth, billboard)
    fn = fns[pick % len(fns)]
    if fn in (penthouse,):
        fn(cr, top)
    elif fn in (gold_dome,):
        fn(cr, top, height)
    else:
        fn(cr, top)


def stages_for(kind, height):
    if kind in ("house", "shop", "warehouse", "walkup", "gothic"):
        return [(1.00, 1.00)]
    if kind == "glass":
        return [(0.92, 1.00)]
    if kind == "office":
        return [(1.00, 0.86), (0.82, 1.00)] if height >= 28 else [(1.00, 1.00)]
    if kind == "slab":
        return [(0.62, 0.78), (0.44, 1.00)]
    if kind == "chrysler":
        return [(1.00, 0.72), (0.78, 0.90), (0.52, 1.00)]
    if kind == "empire":
        return [(1.00, 0.62), (0.80, 0.78), (0.62, 0.90), (0.42, 1.00)]
    if height < 32:
        return [(1.00, 0.80), (0.80, 1.00)]
    if height < 60:
        return [(1.00, 0.74), (0.82, 0.90), (0.62, 1.00)]
    return [(1.00, 0.70), (0.84, 0.84), (0.68, 0.93), (0.50, 1.00)]


def draw_artdeco_building(cr, base, height, cell, texture=None, kind=None):
    count, level = cell["count"], cell["level"]
    if height < 1.4:
        poly(cr, base)
        rv.set_hex(cr, "16161c", 0.9)
        cr.fill_preserve()
        rv.set_hex(cr, GOLD_DIM, 0.35)
        cr.set_line_width(0.6)
        cr.stroke()
        return

    kind = kind or pick_kind(cell, height)
    stone, side, topc = pick_palette(cell, kind)
    slim = 0.70 + 0.28 * rnd(cell["date"], "w")
    if kind == "slab":
        slim = 0.55
    elif kind in ("house", "shop", "warehouse"):
        slim = 0.88 + 0.10 * rnd(cell["date"], "w")
    elif kind == "empire":
        slim = 0.78
    base = inset_quad(base, slim)

    stages = stages_for(kind, height)
    prev = 0.0
    top = None
    first = True
    gold_trim = kind not in ("house", "warehouse", "gothic")
    for inset, frac in stages:
        h = height * frac
        slab = h - prev
        slab_base = [(x, y - prev) for x, y in inset_quad(base, inset)]
        top = artdeco_prism(cr, slab_base, slab, stone, side, topc, gold=gold_trim)
        if first:
            wt = min(4.0, slab * 0.10)
            poly(cr, [slab_base[0], slab_base[1],
                      (slab_base[1][0], slab_base[1][1] - wt),
                      (slab_base[0][0], slab_base[0][1] - wt)])
            rv.set_hex(cr, side, 0.7)
            cr.fill()
            if kind == "shop":
                aw = min(5.0, slab * 0.18)
                poly(cr, [slab_base[0], slab_base[1],
                          (slab_base[1][0], slab_base[1][1] - aw),
                          (slab_base[0][0], slab_base[0][1] - aw)])
                rv.set_hex(cr, "2a1c14", 0.9)
                cr.fill()
            first = False
        cols = 1 if kind in ("house", "gothic") else 2 if kind in ("shop", "warehouse", "walkup") else None
        pitch = 4.6 if kind in ("house", "shop") else 3.2
        bay = 0.18 if kind in ("house", "shop") else 0.14
        if texture is not None and kind not in ("house", "shop", "warehouse"):
            b0 = lerp(slab_base[0], slab_base[1], bay)
            b1 = lerp(slab_base[0], slab_base[1], 1 - bay)
            t0 = lerp(top[0], top[1], bay)
            t1 = lerp(top[0], top[1], 1 - bay)
            b0 = lerp(b0, t0, 0.08)
            b1 = lerp(b1, t1, 0.08)
            t0 = lerp(b0, t0, 0.92)
            t1 = lerp(b1, t1, 0.92)
            paint_south_texture(cr, [b0, b1], [t0, t1], texture)
            if gold_trim:
                gold_edge(cr, top[0], top[1], 1.15, GOLD, 0.92)
        else:
            facade_windows(cr, slab_base, top, count, level, (cell["date"], inset),
                           bay=bay, cols=cols, pitch=pitch)
        prev = h
    if kind == "house":
        pitched_roof(cr, top, max(6.0, height * 0.28), side)
    else:
        artdeco_crown(cr, top, height, cell, kind)


def draw_artdeco_deck(cr, ox, oy, weeks):
    front_l, front_r, back_r, back_l = deck_corners(ox, oy, weeks)
    drop = lambda p: (p[0], p[1] + DECK_THICK)
    poly(cr, [front_l, front_r, drop(front_r), drop(front_l)])
    rv.set_hex(cr, PLINTH, 0.98)
    cr.fill()
    poly(cr, [front_r, back_r, drop(back_r), drop(front_r)])
    rv.set_hex(cr, "08080c", 0.98)
    cr.fill()
    poly(cr, [front_l, front_r, back_r, back_l])
    rv.set_hex(cr, "14141a", 0.96)
    cr.fill()
    gold_edge(cr, front_l, front_r, 1.4, GOLD, 0.9)
    gold_edge(cr, drop(front_l), drop(front_r), 1.0, GOLD_DIM, 0.7)
    gold_edge(cr, front_r, back_r, 0.9, GOLD_DIM, 0.55)


def month_ticks(cr, ox, oy, cells):
    seen = set()
    for cell in sorted(cells, key=lambda c: c["date"]):
        if cell["day"] != 0:
            continue
        key = (cell["date"].year, cell["date"].month)
        if key in seen or cell["date"].day > 7:
            continue
        seen.add(key)
        x, y = project(ox, oy, cell["week"], 0)
        rv.flat_text(cr, cell["date"].strftime("%b").upper(), x + 3,
                     y + DECK_THICK - 4, 6.6, GOLD_DIM, 0.85)


def draw_artdeco_city(cr, ox, oy, cells, texture=None):
    weeks = max(cell["week"] for cell in cells) + 1
    draw_artdeco_deck(cr, ox, oy, weeks)
    painter = sorted(cells, key=lambda c: (project(0, 0, c["week"], c["day"])[1], c["week"]))
    for cell in painter:
        draw_artdeco_building(cr, footprint(ox, oy, cell["week"], cell["day"]),
                             tower_height(cell["count"]), cell, texture=texture)
    month_ticks(cr, ox, oy, cells)


def plate_overlay(name, days, cells, caption, texture=None):
    canvas_w, canvas_h, inset = 1000, 200, 4
    cap = 28
    fit_shipped_width(canvas_w - inset * 2, days)
    fit_shipped_height(canvas_h - inset * 2, days)
    ox = inset
    oy = cap + canvas_h - inset - DECK_THICK
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, canvas_w, canvas_h + cap)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, canvas_w, canvas_h + cap)
    rv.flat_text(cr, caption, 12, 18, 9, GOLD_DIM, 0.8)
    draw_artdeco_city(cr, ox, oy, cells, texture=texture)
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {canvas_w}x{canvas_h + cap}")


def plate_zoom(name, days, cells, caption, texture=None, extra=60):
    x0, y0, x1, y1 = iso_bounds(cells, extra_up=extra)
    margin, top = 28, 40
    width = int(x1 - x0) + margin * 2
    height = int(y1 - y0) + top + margin
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, width, height)
    rv.flat_text(cr, caption, margin, 22, 9, GOLD_DIM, 0.8)
    draw_artdeco_city(cr, margin - x0, top - y0, cells, texture=texture)
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {width}x{height}")


def try_png(name):
    path = os.path.join(HERE, "pixellab", name)
    if not os.path.exists(path):
        return None
    return cairo.ImageSurface.create_from_png(path)


SPRITE_FILES = {
    "low": "sprite-low.png",
    "mid": "sprite-mid.png",
    "tower": "sprite-tower.png",
    "mega": "sprite-mega.png",
    "house": "sprite-house.png",
    "shop": "sprite-shop.png",
    "brownstone": "sprite-brownstone.png",
    "warehouse": "sprite-warehouse.png",
    "gothic": "sprite-gothic.png",
    "glass": "sprite-glass.png",
    "chrysler": "sprite-chrysler.png",
    "empire": "sprite-empire.png",
    "crown": "crown.png",
}


def load_sprites():
    out = {}
    for key, name in SPRITE_FILES.items():
        surf = try_png(name)
        if surf is not None:
            out[key] = surf
    return out


def pick_sprite(cell, height, max_h, sprites):
    frac = height / max_h if max_h else 0
    r = rnd(cell["date"], "spr")
    if frac < 0.18:
        pool = ["house", "shop", "warehouse", "low"]
    elif frac < 0.35:
        pool = ["brownstone", "gothic", "shop", "mid", "warehouse", "house"]
    elif frac < 0.55:
        pool = ["mid", "glass", "brownstone", "gothic", "tower"]
    elif frac < 0.78:
        pool = ["tower", "chrysler", "glass", "mid", "empire"]
    else:
        pool = ["empire", "mega", "chrysler", "tower"]
    pool = [k for k in pool if k in sprites]
    if not pool:
        pool = list(sprites)
    return sprites[pool[int(r * len(pool)) % len(pool)]]


def plate_kit(name):
    folder = os.path.join(HERE, "pixellab")
    files = sorted(f for f in os.listdir(folder) if f.endswith(".png"))
    sprites = [(f.replace(".png", "").replace("sprite-", ""),
                cairo.ImageSurface.create_from_png(os.path.join(folder, f))) for f in files]
    gap, ground_pad, top = 18, 40, 52
    widths = [max(56, s.get_width() * 2) for _, s in sprites]
    height = int(top + max(s.get_height() for _, s in sprites) * 2 + ground_pad)
    width = int(24 + sum(widths) + gap * (len(sprites) - 1) + 24)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, width, height)
    rv.flat_text(cr, "PIXELLAB KIT", 24, 24, 9, GOLD_DIM, 0.8)
    ground = height - ground_pad + 4
    x = 24
    for (label, surf), w in zip(sprites, widths):
        stamp_png(cr, surf, x + w / 2, ground, surf.get_height() * 2)
        rv.flat_text(cr, label.upper()[:12], x + w / 2, ground + 14, 7, GOLD_DIM, 0.75, align="center")
        x += w + gap
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {width}x{height}")


def plate_stamp(name, days, cells, caption, extra=60):
    sprites = load_sprites()
    x0, y0, x1, y1 = iso_bounds(cells, extra_up=extra)
    margin, top = 28, 40
    width = int(x1 - x0) + margin * 2
    height = int(y1 - y0) + top + margin
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, width, height)
    rv.flat_text(cr, caption, margin, 22, 9, GOLD_DIM, 0.8)
    ox, oy = margin - x0, top - y0
    weeks = max(c["week"] for c in cells) + 1
    draw_artdeco_deck(cr, ox, oy, weeks)
    painter = sorted(cells, key=lambda c: (project(0, 0, c["week"], c["day"])[1], c["week"]))
    max_h = max((tower_height(c["count"]) for c in cells), default=1)
    for cell in painter:
        base = footprint(ox, oy, cell["week"], cell["day"])
        h = tower_height(cell["count"])
        cx = (base[0][0] + base[1][0]) / 2
        cy = (base[0][1] + base[1][1]) / 2
        if h < 1.4:
            poly(cr, base)
            rv.set_hex(cr, "16161c", 0.9)
            cr.fill()
            continue
        stamp_png(cr, pick_sprite(cell, h, max_h, sprites), cx, cy, max(h, 12))
    month_ticks(cr, ox, oy, cells)
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {width}x{height}")


def plate_catalog(name):
    kinds = ["house", "shop", "warehouse", "walkup", "gothic",
             "office", "glass", "setback", "chrysler", "empire", "slab"]
    heights = [18, 20, 16, 36, 40, 52, 70, 90, 110, 130, 120]
    slot, gap = 70, 18
    ground_pad, top_pad = 36, 48
    width = int(40 + len(kinds) * (slot + gap))
    height = int(top_pad + 160 + ground_pad)
    set_shipped(22)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, width, height)
    rv.flat_text(cr, "CAIRO TYPES", 24, 24, 9, GOLD_DIM, 0.8)
    ground = height - ground_pad
    cr.rectangle(20, ground, width - 40, 10)
    rv.set_hex(cr, PLINTH, 0.96)
    cr.fill()
    gold_edge(cr, (20, ground), (width - 20, ground), 1.2, GOLD, 0.85)
    for i, (kind, h) in enumerate(zip(kinds, heights)):
        x = 40 + i * (slot + gap)
        cell = {"date": datetime.date(2026, 1, 1 + i), "count": 20, "level": 2}
        base = [(x, ground), (x + 28, ground), (x + 32, ground - 4), (x + 4, ground - 4)]
        draw_artdeco_building(cr, base, h, cell, kind=kind)
        rv.flat_text(cr, kind.upper(), x + 16, ground + 16, 7, GOLD_DIM, 0.75, align="center")
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {width}x{height}")


# Only parts that are actually a front-on strip or a small crown.
# Gothic church, water-tower cube, antenna pad, brick house, lobby room: out.
PART_ROOFS = [
    "part-roof-empire.png",
    "part-roof-chrysler.png",
    "part-roof-dome.png",
]
PART_FLOORS = [
    "part-floor-cream.png",
    "facade-grid.png",
]
PART_BASES = []


def existing_parts(names):
    return [n for n in names if try_png(n) is not None]


def pick_part(cell, key, names):
    have = existing_parts(names)
    if not have:
        return None
    return have[int(rnd(cell["date"], key) * len(have)) % len(have)]


def stamp_south(cr, b0, b1, t0, t1, surf):
    if surf is None:
        return
    paint_south_texture(cr, [b0, b1], [t0, t1], surf)


def stamp_roof_sprite(cr, top, surf, face_w, max_h):
    """Sit the sprite on the south roof edge. Cap height so it stays a hat."""
    if surf is None:
        return
    cx = (top[0][0] + top[1][0]) / 2
    cy = min(p[1] for p in top)
    sw, sh = surf.get_width(), surf.get_height()
    scale = min(max(4.0, face_w) / sw, max(8.0, max_h) / sh)
    stamp_png(cr, surf, cx, cy + 1, sh * scale)


def draw_parts_building(cr, base, height, cell):
    count, level = cell["count"], cell["level"]
    if height < 1.4:
        poly(cr, base)
        rv.set_hex(cr, "16161c", 0.9)
        cr.fill()
        return

    kind = pick_kind(cell, height)
    stone, side, topc = pick_palette(cell, kind)
    slim = 0.72 + 0.24 * rnd(cell["date"], "w")
    if kind == "slab":
        slim = 0.55
    elif kind in ("house", "shop", "warehouse"):
        slim = 0.9
    probe = inset_quad(base, slim)
    face_w0 = abs(probe[1][0] - probe[0][0])
    # 32px PixelLab parts turn to noise on a ~16px overlay cell.
    if face_w0 < 28:
        draw_artdeco_building(cr, base, height, cell, kind=kind)
        return
    base = probe
    use_roof = face_w0 >= 28
    use_floor = face_w0 >= 40
    use_base = face_w0 >= 52
    stages = stages_for(kind, height)

    roof_name = pick_part(cell, "proot", PART_ROOFS)
    floor_name = pick_part(cell, "pfloor", PART_FLOORS)
    base_name = pick_part(cell, "pbase", PART_BASES)
    have = existing_parts(PART_ROOFS)
    if kind in ("house", "shop", "warehouse", "gothic"):
        roof_name = None
    elif kind == "empire" and "part-roof-empire.png" in have:
        roof_name = "part-roof-empire.png"
    elif kind == "chrysler" and "part-roof-chrysler.png" in have:
        roof_name = "part-roof-chrysler.png"
    elif kind in ("office", "setback", "slab", "glass") and have:
        roof_name = pick_part(cell, "proot", PART_ROOFS)

    prev = 0.0
    top = None
    first = True
    floor_surf = try_png(floor_name) if (floor_name and use_floor) else None
    base_surf = try_png(base_name) if (base_name and use_base) else None
    for inset, frac in stages:
        h = height * frac
        slab = h - prev
        slab_base = [(x, y - prev) for x, y in inset_quad(base, inset)]
        top = artdeco_prism(cr, slab_base, slab, stone, side, topc, gold=True)
        if floor_surf:
            stamp_south(cr, slab_base[0], slab_base[1], top[0], top[1], floor_surf)
        if first and base_surf:
            face_w = abs(slab_base[1][0] - slab_base[0][0])
            cx = (slab_base[0][0] + slab_base[1][0]) / 2
            cy = (slab_base[0][1] + slab_base[1][1]) / 2
            sw, sh = base_surf.get_width(), base_surf.get_height()
            target = min(face_w * 0.92, max(10.0, slab * 0.40))
            stamp_png(cr, base_surf, cx, cy, sh * (target / sw))
        first = False
        prev = h

    face_w = abs(top[1][0] - top[0][0])
    roof_surf = try_png(roof_name) if (roof_name and use_roof) else None
    if roof_surf:
        stamp_roof_sprite(cr, top, roof_surf, face_w, max_h=max(12.0, height * 0.22))
    else:
        artdeco_crown(cr, top, height, cell, kind)


def draw_parts_city(cr, ox, oy, cells):
    weeks = max(cell["week"] for cell in cells) + 1
    draw_artdeco_deck(cr, ox, oy, weeks)
    painter = sorted(cells, key=lambda c: (project(0, 0, c["week"], c["day"])[1], c["week"]))
    for cell in painter:
        draw_parts_building(cr, footprint(ox, oy, cell["week"], cell["day"]),
                            tower_height(cell["count"]), cell)
    month_ticks(cr, ox, oy, cells)


def plate_parts_zoom(name, days, cells, caption, extra=70):
    x0, y0, x1, y1 = iso_bounds(cells, extra_up=extra)
    margin, top = 28, 40
    width = int(x1 - x0) + margin * 2
    height = int(y1 - y0) + top + margin
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, width, height)
    rv.flat_text(cr, caption, margin, 22, 9, GOLD_DIM, 0.8)
    draw_parts_city(cr, margin - x0, top - y0, cells)
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {width}x{height}")


def plate_parts_overlay(name, days, cells, caption):
    canvas_w, canvas_h, inset = 1000, 200, 4
    cap = 28
    fit_shipped_width(canvas_w - inset * 2, days)
    fit_shipped_height(canvas_h - inset * 2, days)
    ox = inset
    oy = cap + canvas_h - inset - DECK_THICK
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, canvas_w, canvas_h + cap)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, canvas_w, canvas_h + cap)
    rv.flat_text(cr, caption, 12, 18, 9, GOLD_DIM, 0.8)
    draw_parts_city(cr, ox, oy, cells)
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {canvas_w}x{canvas_h + cap}")


def plate_parts_kit(name):
    files = existing_parts(PART_ROOFS + PART_FLOORS + PART_BASES)
    if not files:
        return
    folder = os.path.join(HERE, "pixellab")
    sprites = [(f.replace("part-", "").replace(".png", ""),
                cairo.ImageSurface.create_from_png(os.path.join(folder, f))) for f in files]
    gap, ground_pad, top = 16, 36, 48
    widths = [max(48, s.get_width() * 3) for _, s in sprites]
    height = int(top + max(s.get_height() for _, s in sprites) * 3 + ground_pad)
    width = int(20 + sum(widths) + gap * (len(sprites) - 1) + 20)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    navy_wallpaper(cr, width, height)
    rv.flat_text(cr, "PIXELLAB PARTS  —  roofs, floors, bases", 20, 22, 9, GOLD_DIM, 0.8)
    ground = height - ground_pad + 4
    x = 20
    for (label, surf), w in zip(sprites, widths):
        stamp_png(cr, surf, x + w / 2, ground, surf.get_height() * 3)
        rv.flat_text(cr, label.upper()[:14], x + w / 2, ground + 14, 7, GOLD_DIM, 0.75, align="center")
        x += w + gap
    out = os.path.join(HERE, name)
    surface.write_to_png(out)
    print(f"{out}  {width}x{height}")


def main():
    days = load_days()
    cells = grid(days)
    last = max(c["week"] for c in cells)
    origin = last - 13
    zoom = [{**c, "week": c["week"] - origin} for c in cells if c["week"] >= origin]
    tight = [{**c, "week": c["week"] - (last - 7)} for c in cells if c["week"] >= last - 7]

    plate_catalog("artdeco-cairo-types.png")
    plate_overlay("artdeco-shipped.png", days, cells,
                  "CAIRO VARIETY  —  overlay box 1000×200")
    set_shipped(64)
    set_height(300, days)
    plate_zoom("artdeco-shipped-zoom.png", days, zoom,
               "CAIRO VARIETY  —  last 14 weeks")
    set_shipped(80)
    set_height(340, days)
    plate_zoom("artdeco-cairo-closeup.png", days, tight,
               "CAIRO VARIETY  —  last 8 weeks, close")


if __name__ == "__main__":
    main()
