#!/usr/bin/env python3
"""Render a taller, wider tmux patch bay on the left side of the desktop.

This is the design-study renderer for the shipped tall-left-rail direction. It
keeps the session-to-device data relationship from ``render_sessions.py`` but
gives the bay a dedicated vertical rail, larger source rows, and roomier
destination cards.
"""

import argparse
import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))

import render_sessions as rs
import render_variants as rv


CYAN = "00e5ff"
TEAL = "00f5d4"
GREEN = "39ff88"
VIOLET = "8b5cf6"
RED = "f87171"
MUTED = "94a3b8"
DIM = "64748b"
TEXT = "f8fafc"

PANEL_W = 360
PANEL_H = 760
MARGIN = 34

SOURCE_TOP = 132
SOURCE_ROW_H = 72
CARD_TOP = 394
CARD_H = 82
CARD_GAP = 14
CARD_X = 208
CARD_W = PANEL_W - (CARD_X - 0) - 20
JACK_X = 178


def source_color(device):
    return {"live": GREEN, "idle": DIM, "alert": RED}[device["state"]]


def source_by_session():
    return {
        device["session"]: device
        for device in rs.DEVICES
        if device["session"] is not None
    }


def draw_card(cr, x, y, session, source):
    live = session["attached"] is not None
    tone = GREEN if live else DIM

    rv.rounded_rect(cr, x, y, CARD_W, CARD_H, 8)
    cr.set_source(rv.gradient(x, y, x, y + CARD_H, [
        (0.00, "0d1a30", 0.86 if live else 0.58),
        (1.00, "020617", 0.78 if live else 0.50),
    ]))
    cr.fill_preserve()
    rv.set_hex(cr, tone, 0.66 if live else 0.28)
    cr.set_line_width(1.2)
    cr.stroke()

    rv.set_hex(cr, tone, 0.90 if live else 0.30)
    cr.rectangle(x + 1, y + 8, 2.6, CARD_H - 16)
    cr.fill()

    rv.flat_text(cr, "SOCKET %02d" % (rs.SESSIONS.index(session) + 1),
                 x + 12, y + 16, 6.3, VIOLET, 0.80)
    rv.flat_text(cr, "ATTACHED" if live else "DETACHED",
                 x + CARD_W - 10, y + 16, 6.4, tone,
                 0.92 if live else 0.62, align="right")
    rv.lit_text(cr, session["name"], x + 12, y + 37, 11,
                TEXT if live else MUTED, 1.0 if live else 0.72)
    rv.flat_text(cr, session["path"], x + 12, y + 53, 6.8, MUTED, 0.68)
    rv.flat_text(cr, "%dw / %dp" % (session["windows"], session["panes"]),
                 x + 12, y + 68, 6.6, DIM, 0.78)

    if source:
        rv.flat_text(cr, "via " + source["name"], x + CARD_W - 10, y + 68,
                     6.4, TEAL, 0.78, align="right")
    else:
        rv.flat_text(cr, "no inbound route", x + CARD_W - 10, y + 68,
                     6.4, DIM, 0.62, align="right")


def draw_source(cr, x, y, device, index):
    tone = source_color(device)
    active = device["state"] != "idle"

    rv.set_hex(cr, "cbd5e1", 0.075)
    cr.set_line_width(1)
    cr.move_to(x + 22, y + 50)
    cr.line_to(x + PANEL_W - 22, y + 50)
    cr.stroke()

    rs.device_glyph(cr, device["glyph"], x + 30, y + 14, tone,
                    0.95 if active else 0.48)
    rv.flat_text(cr, "IN %02d" % index, x + 48, y - 1, 6.2, VIOLET, 0.72)
    rv.lit_text(cr, device["name"], x + 48, y + 16, 8.7,
                TEXT if active else MUTED, 1.0 if active else 0.72)
    rv.flat_text(cr, device["os"], x + 48, y + 31, 6.5, MUTED, 0.62)
    rv.flat_text(cr, device["age"], x + 154, y + 31, 6.5, DIM, 0.68,
                 align="right")

    rs.jack(cr, x + JACK_X, y + 14, tone, live=device["session"] is not None)
    rs.status_dot(cr, x + JACK_X + 16, y + 6, device["state"])
    rv.flat_text(cr, "route " + device["session"] if device["session"] else "unpatched",
                 x + 48, y + 45, 6.4, tone if active else DIM,
                 0.82 if active else 0.58)


def draw_panel(cr, x, y):
    rv.panel_frame(cr, x, y, PANEL_W, PANEL_H, accent=CYAN, secondary=VIOLET)

    # A quiet vertical rail gives the taller panel a strong edge without
    # turning the whole surface into another bright rounded rectangle.
    rv.set_hex(cr, CYAN, 0.16)
    cr.set_line_width(1)
    cr.move_to(x + 14, y + 22)
    cr.line_to(x + 14, y + PANEL_H - 22)
    cr.stroke()
    rv.set_hex(cr, VIOLET, 0.22)
    cr.move_to(x + 18, y + 22)
    cr.line_to(x + 18, y + PANEL_H - 22)
    cr.stroke()

    rv.flat_text(cr, "PATCH BAY", x + 30, y + 31, 11, "dbeafe", 0.92)
    rv.flat_text(cr, "TMUX / INBOUND ROUTING", x + 30, y + 48, 7, MUTED, 0.66)
    rv.flat_text(cr, "%02d IN  /  %02d TMUX" % (len(rs.DEVICES), len(rs.SESSIONS)),
                 x + PANEL_W - 22, y + 31, 7, MUTED, 0.72, align="right")
    rv.flat_text(cr, "LEFT RAIL CONCEPT", x + PANEL_W - 22, y + 48, 6.4,
                 VIOLET, 0.78, align="right")
    rv.divider(cr, x + 22, x + PANEL_W - 22, y + 67, color=CYAN, alpha=0.24)

    rv.flat_text(cr, "INBOUND SOURCES", x + 30, y + 91, 7, VIOLET, 0.84)
    rv.flat_text(cr, "SOURCE / ORIGIN", x + 48, y + 108, 6.1, DIM, 0.74)
    rv.flat_text(cr, "AGE", x + 154, y + 108, 6.1, DIM, 0.74, align="right")
    rv.flat_text(cr, "JACK", x + JACK_X + 4, y + 108, 6.1, DIM, 0.74,
                 align="center")

    source_map = source_by_session()
    card_positions = {}

    # Cards are painted first; cables can then visibly terminate at their
    # sockets instead of disappearing beneath the card fill.
    for index, session in enumerate(rs.SESSIONS):
        card_y = y + CARD_TOP + index * (CARD_H + CARD_GAP)
        card_positions[session["name"]] = (x + CARD_X, card_y)
        draw_card(cr, x + CARD_X, card_y, session, source_map.get(session["name"]))
        rs.jack(cr, x + CARD_X + 1, card_y + CARD_H / 2,
                GREEN if session["attached"] else DIM,
                live=session["attached"] is not None)

    # Live routes form the visual backbone of the bay. The large vertical
    # separation is intentional: it makes each source-to-session relationship
    # legible at a glance instead of compressing everything into one row.
    for index, device in enumerate(rs.DEVICES):
        if not device["session"] or device["session"] not in card_positions:
            continue
        _card_x, card_y = card_positions[device["session"]]
        source_y = y + SOURCE_TOP + index * SOURCE_ROW_H + 14
        rs.cable(cr, x + JACK_X + 6, source_y, x + CARD_X + 1,
                 card_y + CARD_H / 2, source_color(device), alpha=0.94,
                 packets=3)

    for index, device in enumerate(rs.DEVICES, start=1):
        draw_source(cr, x, y + SOURCE_TOP + (index - 1) * SOURCE_ROW_H,
                    device, index)

    rv.divider(cr, x + 22, x + PANEL_W - 22, y + 349, color=VIOLET, alpha=0.28)
    rv.flat_text(cr, "TMUX DESTINATIONS", x + 30, y + 373, 7, VIOLET, 0.84)
    rv.flat_text(cr, "SOCKETS / WORKTREES", x + PANEL_W - 22, y + 373, 6.2,
                 DIM, 0.72, align="right")

    rv.divider(cr, x + 22, x + PANEL_W - 22, y + 690, color=VIOLET, alpha=0.24)
    rv.flat_text(cr, "ROUTING STATUS", x + 30, y + 714, 6.6, VIOLET, 0.78)
    rv.flat_text(cr, "02 LIVE", x + 30, y + 735, 8, GREEN, 0.92)
    rv.flat_text(cr, "01 IDLE", x + 106, y + 735, 8, DIM, 0.84)
    rv.flat_text(cr, "TAILSCALE SSH", x + PANEL_W - 22, y + 714, 6.6,
                 MUTED, 0.58, align="right")
    rv.flat_text(cr, "SSHD:22 CLOSED", x + PANEL_W - 22, y + 735, 6.6,
                 DIM, 0.74, align="right")


def render_panel(path):
    width = PANEL_W + MARGIN * 2
    height = PANEL_H + MARGIN * 2
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    rv.wallpaper(cr, width, height)
    draw_panel(cr, MARGIN, MARGIN)
    surface.write_to_png(path)
    return width, height


def render_desktop(desktop_path, output_path):
    surface = cairo.ImageSurface.create_from_png(desktop_path)
    cr = cairo.Context(surface)

    # Remove the previous short bay from its known lower-left slot while
    # preserving the Linear cards above it and the GitHub skyline to the right.
    rv.set_hex(cr, "000000", 1)
    cr.rectangle(0, 500, 462, 300)
    cr.fill()
    draw_panel(cr, 20, 306)
    surface.write_to_png(output_path)
    return surface.get_width(), surface.get_height()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "desktop",
        nargs="?",
        default=os.path.join(HERE, "placement-layout-v3.png"),
        help="desktop PNG to composite onto (default: placement-layout-v3.png)",
    )
    args = parser.parse_args()

    panel_path = os.path.join(HERE, "08-tall-left-rail.png")
    desktop_path = os.path.join(HERE, "placement-tall-left-rail.png")
    panel_size = render_panel(panel_path)
    desktop_size = render_desktop(args.desktop, desktop_path)
    print("08-tall-left-rail.png: %dx%d" % panel_size)
    print("placement-tall-left-rail.png: %dx%d" % desktop_size)


if __name__ == "__main__":
    main()
