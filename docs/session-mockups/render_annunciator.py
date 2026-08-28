#!/usr/bin/env python3
"""Bonus concept: a master caution / annunciator strip.

Not a replacement for any overlay. It aggregates the alarm state every existing
overlay already computes into one press-to-test legend panel, so "is anything
wrong" is a single glance instead of a scan across three monitors.
"""

import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))
import render_variants as rv

from render_sessions import GREEN, AMBER, RED, MUTED, DIM, TEXT, VIOLET, header

# (legend, state, source overlay)
LEGENDS = [
    ("SSH INGRESS", "warn", "sessions"),
    ("CI FAIL", "alarm", "git"),
    ("QUOTA 90%", "warn", "rate limit"),
    ("BUDGET PACE", "ok", "billing"),
    ("DISK LOW", "ok", "resource"),
    ("MC OFFLINE", "ok", "minecraft"),
    ("THERMAL", "ok", "resource"),
    ("LINEAR DUE", "warn", "linear"),
    ("NET LINK", "ok", "resource"),
    ("STALE CACHE", "ok", "caches"),
    ("AQI HIGH", "ok", "weather"),
    ("TOKEN EXP", "alarm", "credentials"),
]

TILE_W = 118
TILE_H = 40
COLS = 4
PANEL_W = 540


def tile(cr, x, y, label, state):
    color = {"alarm": RED, "warn": AMBER, "ok": GREEN}[state]
    lit = state in ("alarm", "warn")

    if lit:
        rv.set_hex(cr, color, 0.16)
        rv.rounded_rect(cr, x - 3, y - 3, TILE_W + 6, TILE_H + 6, 6)
        cr.fill()

    rv.rounded_rect(cr, x, y, TILE_W, TILE_H, 4)
    if lit:
        cr.set_source(rv.gradient(x, y, x, y + TILE_H, [
            (0.00, color, 0.62, -0.30),
            (0.55, color, 0.40, -0.55),
            (1.00, color, 0.52, -0.42),
        ]))
    else:
        cr.set_source(rv.gradient(x, y, x, y + TILE_H, [
            (0.00, "0d1a30", 0.85),
            (1.00, "020617", 0.80),
        ]))
    cr.fill_preserve()
    rv.set_hex(cr, color, 0.95 if lit else 0.20)
    cr.set_line_width(1.3)
    cr.stroke()

    # Bulb split line: real annunciators are two-lamp tiles.
    rv.set_hex(cr, "000000", 0.35 if lit else 0.18)
    cr.set_line_width(1)
    cr.move_to(x + TILE_W / 2, y + 4)
    cr.line_to(x + TILE_W / 2, y + TILE_H - 4)
    cr.stroke()

    words = label.split(" ")
    if len(words) == 1:
        words = [label, ""]
    top = " ".join(words[:-1]) if len(words) > 2 else words[0]
    bottom = words[-1]
    text_color = TEXT if lit else DIM
    alpha = 1.0 if lit else 0.45
    rv.flat_text(cr, top, x + TILE_W / 2, y + 17, 8.4, text_color, alpha, align="center")
    rv.flat_text(cr, bottom, x + TILE_W / 2, y + 30, 8.4, text_color, alpha, align="center")


def draw_annunciator(cr, x, y):
    rows = (len(LEGENDS) + COLS - 1) // COLS
    height = 96 + rows * (TILE_H + 10) + 34

    alarms = sum(1 for _l, s, _o in LEGENDS if s == "alarm")
    warns = sum(1 for _l, s, _o in LEGENDS if s == "warn")
    accent = RED if alarms else (AMBER if warns else GREEN)

    rv.panel_frame(cr, x, y, PANEL_W, height, accent=accent, secondary=VIOLET)
    header(cr, x, y, PANEL_W, "ANNUNCIATOR", "PRESS TO TEST")

    # Master caution / warning cans.
    for index, (label, color, active) in enumerate(
        [("MASTER WARN", RED, alarms > 0), ("MASTER CAUT", AMBER, warns > 0)]
    ):
        bx = x + 22 + index * 122
        by = y + 50
        rv.rounded_rect(cr, bx, by, 112, 30, 4)
        if active:
            cr.set_source(rv.gradient(bx, by, bx, by + 30, [
                (0.00, color, 0.85, -0.10),
                (1.00, color, 0.65, -0.40),
            ]))
        else:
            rv.set_hex(cr, "020617", 0.85)
        cr.fill_preserve()
        rv.set_hex(cr, color, 0.95 if active else 0.22)
        cr.set_line_width(1.5)
        cr.stroke()
        rv.flat_text(cr, label, bx + 56, by + 19, 9,
                     "020617" if active else DIM, 1.0 if active else 0.45, align="center")

    counts = f"{alarms} WARN · {warns} CAUT"
    rv.flat_text(cr, counts, x + PANEL_W - 22, y + 69, 8, MUTED, 0.7, align="right")
    rv.divider(cr, x + 20, x + PANEL_W - 20, y + 84)

    grid_x = x + (PANEL_W - (COLS * TILE_W + (COLS - 1) * 10)) / 2
    for index, (label, state, _source) in enumerate(LEGENDS):
        row, column = divmod(index, COLS)
        tile(cr, grid_x + column * (TILE_W + 10), y + 96 + row * (TILE_H + 10), label, state)

    rv.flat_text(cr, "aggregates every overlay's existing alarm state",
                 x + 22, y + height - 14, 6.8, DIM, 0.55)
    return height


MARGIN = 34


def main():
    probe = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
    height = draw_annunciator(cairo.Context(probe), -4000, -4000)
    width = PANEL_W + MARGIN * 2
    total = height + MARGIN * 2
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, total)
    cr = cairo.Context(surface)
    rv.wallpaper(cr, width, total)
    draw_annunciator(cr, MARGIN, MARGIN)
    out = os.path.join(HERE, "06-annunciator.png")
    surface.write_to_png(out)
    print(f"06-annunciator.png: {width}x{total}")


if __name__ == "__main__":
    main()
