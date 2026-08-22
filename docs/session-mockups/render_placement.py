#!/usr/bin/env python3
"""Placement study: the patch bay at overlay width, dropped on the real desktop.

Renders a 456px-wide patch bay (the width the right instrument column already
uses for billing and weather) and composites it onto `scripts/render_desktop.py`
output so the candidate slots can be compared against the live pixels.
"""

import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))
import render_variants as rv
import render_sessions as rs

# Matches billing/weather `minimum_width`, so the panel joins the existing
# right column instead of inventing a new left edge.
PANEL_W = 456


def draw_patch_bay(cr, x, y):
    """The patch bay reflowed from the 540px study width down to 456px."""
    devices = list(rs.DEVICES)
    card_h = 40
    row_h = 52
    top = y + 62
    height = 44 + max(len(devices) * row_h, len(rs.SESSIONS) * (card_h + 12)) + 34

    rv.panel_frame(cr, x, y, PANEL_W, height, accent=rs.CYAN, secondary=rs.VIOLET)
    rs.header(cr, x, y, PANEL_W, "SESSIONS",
              f"{len(devices)} IN · {len(rs.SESSIONS)} TMUX")
    rv.divider(cr, x + 20, x + PANEL_W - 20, y + 42)

    jack_x = x + 164
    socket_x = x + 196
    card_w = PANEL_W - (socket_x - x) - 24

    rv.flat_text(cr, "INBOUND", x + 24, top - 4, 7, rs.VIOLET, 0.72)
    rv.flat_text(cr, "TMUX", socket_x, top - 4, 7, rs.VIOLET, 0.72)

    card_tops = {}
    for index, session in enumerate(rs.SESSIONS):
        cy = top + index * (card_h + 12)
        card_tops[session["name"]] = cy
        live = session["attached"] is not None
        tone = rs.GREEN if live else rs.DIM

        rv.rounded_rect(cr, socket_x, cy, card_w, card_h, 8)
        cr.set_source(rv.gradient(socket_x, cy, socket_x, cy + card_h, [
            (0.00, "0d1a30", 0.80 if live else 0.55),
            (1.00, "020617", 0.72 if live else 0.50),
        ]))
        cr.fill_preserve()
        rv.set_hex(cr, tone, 0.55 if live else 0.24)
        cr.set_line_width(1.1)
        cr.stroke()

        rv.set_hex(cr, tone, 0.85 if live else 0.30)
        cr.rectangle(socket_x + 1, cy + 6, 2.4, card_h - 12)
        cr.fill()

        rv.lit_text(cr, session["name"], socket_x + 12, cy + 16, 10.5,
                    rs.TEXT if live else rs.MUTED, 1.0 if live else 0.7)
        rv.flat_text(cr, "attached" if live else "detached",
                     socket_x + card_w - 10, cy + 16, 7,
                     tone, 0.9 if live else 0.6, align="right")
        rv.flat_text(cr, f"{session['windows']}w · {session['panes']}p  {session['path']}",
                     socket_x + 12, cy + 28, 6.8, rs.MUTED, 0.62)

    for index, device in enumerate(devices):
        dy = top + index * row_h + 14
        tone = {"live": rs.GREEN, "idle": rs.DIM, "alert": rs.RED}[device["state"]]

        rs.device_glyph(cr, device["glyph"], x + 32, dy, tone,
                        0.95 if device["state"] != "idle" else 0.5)
        rv.lit_text(cr, device["name"], x + 48, dy - 1, 9,
                    rs.TEXT if device["state"] == "live" else rs.MUTED,
                    1.0 if device["state"] != "idle" else 0.7)
        rv.flat_text(cr, device["os"], x + 48, dy + 10, 6.6, rs.MUTED, 0.58)
        rv.flat_text(cr, device["age"], x + 138, dy + 10, 6.6, rs.DIM, 0.6, align="right")

        live = device["session"] is not None
        rs.jack(cr, jack_x, dy, tone, live=live)
        if live:
            target = card_tops[device["session"]]
            rs.cable(cr, jack_x + 6, dy, socket_x - 1, target + card_h / 2, tone,
                     alpha=0.9, packets=2)

        rs.status_dot(cr, x + 150, dy - 4, device["state"])

    rv.flat_text(cr, "tailscale ssh · sshd:22 closed", x + 22, y + height - 14,
                 6.8, rs.DIM, 0.55)
    return height


# Head 0, monitor-local coordinates. Right column: gap_x = 6 puts the 456px
# text area at 1920 - 6 - 456. Left column: linear and the rate limit panel
# both sit at gap_x = 190.
CANDIDATES = [
    ("placement-right-column.png", 1920 - 6 - PANEL_W, 316),
    ("placement-left-under-linear.png", 190, 360),
]


def main():
    desktop = sys.argv[1]
    height = draw_patch_bay(cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)), -4000, -4000)

    margin = 34
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, PANEL_W + margin * 2, height + margin * 2)
    cr = cairo.Context(surface)
    rv.wallpaper(cr, PANEL_W + margin * 2, height + margin * 2)
    draw_patch_bay(cr, margin, margin)
    surface.write_to_png(os.path.join(HERE, "07-patch-bay-456.png"))
    print(f"07-patch-bay-456.png  {PANEL_W}x{height}")

    for filename, px, py in CANDIDATES:
        base = cairo.ImageSurface.create_from_png(desktop)
        ctx = cairo.Context(base)
        draw_patch_bay(ctx, px, py)
        out = os.path.join(HERE, filename)
        base.write_to_png(out)
        print(f"{filename}  panel at +{px}+{py}")


if __name__ == "__main__":
    main()
