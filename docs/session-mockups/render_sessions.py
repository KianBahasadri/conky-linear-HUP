#!/usr/bin/env python3
"""Mockups for the tmux + remote-session overlay.

Four concepts drawn with the shipped overlay palette and the billing study's
Cairo primitives:

  1. patch-bay-maps - inbound jacks, patch cables, per-session pane wireframes
  2. patch-bay      - inbound jacks and patch cables only
  3. pane-maps      - session cards with true-to-scale pane wireframes
  4. radar          - ingress radar sweep with device blips

Device and session values are this machine's real state at capture time
(pixel-8a over Tailscale SSH, driving tmux session "0"), padded with
illustrative extras so the panels show a populated layout.
"""

import math
import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))
import render_variants as rv

FONT = rv.FONT

CYAN = "00e5ff"
TEAL = "00f5d4"
GREEN = "39ff88"
VIOLET = "8b5cf6"
LILAC = "a78bfa"
PINK = "f472b6"
AMBER = "facc15"
RED = "f87171"
MUTED = "94a3b8"
DIM = "64748b"
LINE = "334155"
TEXT = "f8fafc"


# --- data ------------------------------------------------------------------
# ("h", [...]) splits side by side; ("v", [...]) stacks; leaves are panes.

def pane(label, active=False, weight=1):
    return {"kind": "pane", "label": label, "active": active, "weight": weight}


def split(axis, children, weight=1):
    return {"kind": axis, "children": children, "weight": weight}


SESSIONS = [
    {
        "name": "0",
        "attached": "pixel-8a",
        "age": "12m",
        "path": "~/clusterfork",
        "windows": 1,
        "panes": 1,
        "layout": pane("▸ Repo Review", active=True),
    },
    {
        "name": "build",
        "attached": None,
        "age": "4h",
        "path": "~/conky-linear-HUP",
        "windows": 2,
        "panes": 3,
        "layout": split("v", [
            split("h", [pane("nvim", active=True, weight=2), pane("tail -f", weight=1)], weight=2),
            pane("pytest", weight=1),
        ]),
    },
    {
        "name": "notes",
        "attached": "tty2",
        "age": "3m",
        "path": "~/notes",
        "windows": 1,
        "panes": 2,
        "layout": split("h", [pane("nvim", active=True, weight=3), pane("rg", weight=2)]),
    },
]

DEVICES = [
    {"name": "pixel-8a", "os": "android", "glyph": "phone", "addr": "100.94.58.124",
     "session": "0", "age": "12m", "state": "live"},
    {"name": "azure", "os": "windows", "glyph": "monitor", "addr": "100.111.23.10",
     "session": None, "age": "2h", "state": "idle"},
    {"name": "tty2", "os": "local", "glyph": "terminal", "addr": "seat0",
     "session": "notes", "age": "3m", "state": "live"},
]

ALERT_DEVICE = {"name": "10.0.0.99", "os": "UNKNOWN", "glyph": "alert", "addr": "no tailnet id",
                "session": None, "age": "8s", "state": "alert"}


# --- small primitives ------------------------------------------------------

def device_glyph(cr, kind, x, y, color, alpha=1.0):
    """Draw a ~13px device icon centred on (x, y)."""
    rv.set_hex(cr, color, alpha)
    cr.set_line_width(1.2)

    if kind == "phone":
        rv.rounded_rect(cr, x - 4.5, y - 7, 9, 14, 2)
        cr.stroke()
        cr.move_to(x - 2, y - 4.6)
        cr.line_to(x + 2, y - 4.6)
        cr.stroke()
        rv.bead(cr, x, y + 4.6, 1.0, color, alpha=alpha)
    elif kind == "monitor":
        rv.rounded_rect(cr, x - 8, y - 6.5, 16, 11, 1.8)
        cr.stroke()
        cr.move_to(x - 3.5, y + 7)
        cr.line_to(x + 3.5, y + 7)
        cr.stroke()
        cr.move_to(x, y + 4.5)
        cr.line_to(x, y + 7)
        cr.stroke()
    elif kind == "laptop":
        rv.rounded_rect(cr, x - 6.5, y - 6.5, 13, 9, 1.6)
        cr.stroke()
        cr.move_to(x - 9, y + 4.5)
        cr.line_to(x + 9, y + 4.5)
        cr.stroke()
    elif kind == "terminal":
        rv.rounded_rect(cr, x - 8, y - 6, 16, 12, 2)
        cr.stroke()
        cr.set_line_width(1.4)
        cr.move_to(x - 4.5, y - 2.4)
        cr.line_to(x - 1.6, y + 0.2)
        cr.line_to(x - 4.5, y + 2.8)
        cr.stroke()
        cr.move_to(x + 0.6, y + 3)
        cr.line_to(x + 4.6, y + 3)
        cr.stroke()
    elif kind == "alert":
        cr.move_to(x, y - 7.5)
        cr.line_to(x + 8, y + 6)
        cr.line_to(x - 8, y + 6)
        cr.close_path()
        cr.stroke()
        cr.set_line_width(1.6)
        cr.move_to(x, y - 3)
        cr.line_to(x, y + 1.6)
        cr.stroke()
        rv.bead(cr, x, y + 4, 1.0, color, alpha=alpha)


def cable(cr, x1, y1, x2, y2, color, alpha=0.9, dashed=False, packets=2):
    """A patch cable: slack bezier from a jack to a socket."""
    lift = max(26, abs(x2 - x1) * 0.42)
    c1 = (x1 + lift, y1)
    c2 = (x2 - lift, y2)

    def path():
        cr.move_to(x1, y1)
        cr.curve_to(c1[0], c1[1], c2[0], c2[1], x2, y2)

    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    rv.set_hex(cr, color, 0.13 * alpha)
    cr.set_line_width(5.5)
    path()
    cr.stroke()

    if dashed:
        cr.set_dash([3, 4])
    cr.set_source(rv.gradient(x1, y1, x2, y2, [
        (0.00, color, alpha * 0.55, -0.10),
        (1.00, color, alpha, 0.30),
    ]))
    cr.set_line_width(1.7)
    path()
    cr.stroke()
    cr.set_dash([])
    cr.set_line_cap(cairo.LINE_CAP_BUTT)

    # Flow beads riding the cable, so a live link reads as moving.
    for index in range(packets):
        t = 0.34 + index * 0.24
        mt = 1 - t
        bx = (mt ** 3) * x1 + 3 * (mt ** 2) * t * c1[0] + 3 * mt * (t ** 2) * c2[0] + (t ** 3) * x2
        by = (mt ** 3) * y1 + 3 * (mt ** 2) * t * c1[1] + 3 * mt * (t ** 2) * c2[1] + (t ** 3) * y2
        rv.bead(cr, bx, by, 2.1, color, alpha=alpha * (0.9 - index * 0.22))


def jack(cr, x, y, color, live=True):
    """Panel-mount jack ring the cable plugs into."""
    rv.set_hex(cr, color, 0.16 if live else 0.08)
    cr.set_line_width(4.5)
    cr.arc(x, y, 5.4, 0, math.tau)
    cr.stroke()
    rv.set_hex(cr, color, 0.95 if live else 0.34)
    cr.set_line_width(1.4)
    cr.arc(x, y, 5.4, 0, math.tau)
    cr.stroke()
    if live:
        rv.bead(cr, x, y, 2.4, color)
    else:
        rv.set_hex(cr, "020617", 0.9)
        cr.arc(x, y, 2.4, 0, math.tau)
        cr.fill()


def pane_map(cr, node, x, y, width, height, accent=CYAN, dim=False, gap=2.4, depth=0):
    """Recursively draw a tmux layout tree as a scale wireframe."""
    kind = node["kind"]

    if kind == "pane":
        active = node["active"] and not dim
        color = accent if active else DIM
        rv.rounded_rect(cr, x, y, width, height, 2.4)
        if active:
            cr.set_source(rv.gradient(x, y, x, y + height, [
                (0.00, accent, 0.30),
                (1.00, accent, 0.12),
            ]))
            cr.fill_preserve()
        else:
            rv.set_hex(cr, "020617", 0.55)
            cr.fill_preserve()
        rv.set_hex(cr, color, 0.92 if active else 0.5)
        cr.set_line_width(1.0)
        cr.stroke()

        label = node["label"]
        if width > 26 and height >= 11:
            size = 7.0
            cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(size)
            while label and cr.text_extents(label).x_advance > width - 7:
                label = label[:-1]
            if label:
                rv.flat_text(cr, label, x + 4, y + height / 2 + 2.6, size,
                             TEXT if active else MUTED, 0.95 if active else 0.62)
        return

    children = node["children"]
    total = sum(child["weight"] for child in children)
    cursor = x if kind == "h" else y
    span = (width if kind == "h" else height) - gap * (len(children) - 1)

    for child in children:
        size = span * child["weight"] / total
        if kind == "h":
            pane_map(cr, child, cursor, y, size, height, accent, dim, gap, depth + 1)
        else:
            pane_map(cr, child, x, cursor, width, size, accent, dim, gap, depth + 1)
        cursor += size + gap


def status_dot(cr, x, y, state):
    color = {"live": GREEN, "idle": DIM, "alert": RED}[state]
    if state == "alert":
        rv.set_hex(cr, color, 0.22)
        cr.arc(x, y, 6.5, 0, math.tau)
        cr.fill()
    rv.bead(cr, x, y, 3.0, color, alpha=1.0 if state != "idle" else 0.6)


def header(cr, x, y, width, title, right):
    rv.flat_text(cr, title, x + 22, y + 30, 10, "dbeafe", 0.85)
    rv.flat_text(cr, right, x + width - 22, y + 30, 8, MUTED, 0.62, align="right")


# --- concept 1: patch bay + pane micro-maps --------------------------------

PANEL_W = 540


def draw_patch_bay(cr, x, y, with_maps=True, alert=False):
    devices = list(DEVICES)
    if alert:
        devices.insert(1, ALERT_DEVICE)

    card_h = 78 if with_maps else 40
    row_h = 52
    top = y + 62
    height = 44 + max(len(devices) * row_h, len(SESSIONS) * (card_h + 12)) + 34

    accent = RED if alert else CYAN
    rv.panel_frame(cr, x, y, PANEL_W, height, accent=accent, secondary=VIOLET)
    header(cr, x, y, PANEL_W, "SESSIONS",
           f"{len(devices)} IN · {len(SESSIONS)} TMUX")
    rv.divider(cr, x + 20, x + PANEL_W - 20, y + 42)

    rv.flat_text(cr, "INBOUND", x + 24, top - 4, 7, VIOLET, 0.72)
    rv.flat_text(cr, "TMUX", x + 246, top - 4, 7, VIOLET, 0.72)

    jack_x = x + 210
    socket_x = x + 246
    card_w = PANEL_W - (socket_x - x) - 24

    # Session cards first, so cables land on top of their edges.
    card_tops = {}
    for index, session in enumerate(SESSIONS):
        cy = top + index * (card_h + 12)
        card_tops[session["name"]] = cy
        live = session["attached"] is not None
        tone = GREEN if live else DIM

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
                    TEXT if live else MUTED, 1.0 if live else 0.7)
        state = "attached" if live else "detached"
        rv.flat_text(cr, state, socket_x + card_w - 10, cy + 16, 7,
                     tone, 0.9 if live else 0.6, align="right")
        rv.flat_text(cr, f"{session['windows']}w · {session['panes']}p  {session['path']}",
                     socket_x + 12, cy + 27, 7, MUTED, 0.62)

        if with_maps:
            pane_map(cr, session["layout"], socket_x + 12, cy + 34,
                     card_w - 24, card_h - 42,
                     accent=TEAL if live else DIM, dim=not live)
        else:
            rv.flat_text(cr, session["age"] + " idle" if not live else "active " + session["age"],
                         socket_x + 12, cy + 33, 7, DIM, 0.6)

    # Inbound jacks and their cables.
    for index, device in enumerate(devices):
        dy = top + index * row_h + 14
        tone = {"live": GREEN, "idle": DIM, "alert": RED}[device["state"]]

        device_glyph(cr, device["glyph"], x + 32, dy, tone,
                     0.95 if device["state"] != "idle" else 0.5)
        rv.lit_text(cr, device["name"], x + 48, dy - 1, 9,
                    TEXT if device["state"] == "live" else (RED if device["state"] == "alert" else MUTED),
                    1.0 if device["state"] != "idle" else 0.7)
        rv.flat_text(cr, device["os"], x + 48, dy + 10, 6.6, MUTED, 0.58)
        rv.flat_text(cr, device["age"], x + 178, dy + 10, 6.6, DIM, 0.6, align="right")

        live = device["session"] is not None
        jack(cr, jack_x, dy, tone, live=live)

        if live:
            target = card_tops[device["session"]]
            cable(cr, jack_x + 6, dy, socket_x - 1, target + card_h / 2, tone,
                  alpha=0.9, packets=2)
        elif device["state"] == "alert":
            # Dead-ends before the session column: the login attached to no tmux.
            stub_x = socket_x - 12
            cable(cr, jack_x + 6, dy, stub_x, dy, RED, alpha=0.85,
                  dashed=True, packets=0)
            rv.set_hex(cr, RED, 0.9)
            cr.set_line_width(1.5)
            cr.move_to(stub_x - 3, dy - 3.5)
            cr.line_to(stub_x + 3, dy + 3.5)
            cr.move_to(stub_x + 3, dy - 3.5)
            cr.line_to(stub_x - 3, dy + 3.5)
            cr.stroke()
            rv.flat_text(cr, "bare shell", x + 48, dy + 19, 6.4, RED, 0.85)

        status_dot(cr, x + 202, dy - 4, device["state"])

    footer = "tailscale ssh · sshd:22 closed"
    rv.flat_text(cr, footer, x + 22, y + height - 14, 6.8, DIM, 0.55)
    if alert:
        rv.flat_text(cr, "⚠ UNKNOWN DEVICE", x + PANEL_W - 22, y + height - 14,
                     7.2, RED, 0.95, align="right")
    return height


# --- concept 3: pane micro-maps only ---------------------------------------

def draw_pane_maps(cr, x, y):
    card_h = 96
    height = 54 + len(SESSIONS) * (card_h + 10) + 26
    rv.panel_frame(cr, x, y, PANEL_W, height, accent=TEAL, secondary=VIOLET)
    total_panes = sum(session["panes"] for session in SESSIONS)
    header(cr, x, y, PANEL_W, "TMUX",
           f"{len(SESSIONS)} SESSIONS · {total_panes} PANES")
    rv.divider(cr, x + 20, x + PANEL_W - 20, y + 42)

    for index, session in enumerate(SESSIONS):
        cy = y + 54 + index * (card_h + 10)
        live = session["attached"] is not None
        tone = GREEN if live else DIM
        inner_x = x + 22
        inner_w = PANEL_W - 44

        rv.rounded_rect(cr, inner_x, cy, inner_w, card_h, 10)
        cr.set_source(rv.gradient(inner_x, cy, inner_x, cy + card_h, [
            (0.00, "0d1a30", 0.78 if live else 0.52),
            (1.00, "020617", 0.70 if live else 0.48),
        ]))
        cr.fill_preserve()
        rv.set_hex(cr, tone, 0.5 if live else 0.22)
        cr.set_line_width(1.1)
        cr.stroke()

        rv.lit_text(cr, session["name"], inner_x + 14, cy + 20, 12,
                    TEXT if live else MUTED, 1.0 if live else 0.72)

        if live:
            device = next((d for d in DEVICES if d["session"] == session["name"]), None)
            if device:
                glyph_x = inner_x + inner_w - 150
                device_glyph(cr, device["glyph"], glyph_x, cy + 15, GREEN, 0.9)
                rv.flat_text(cr, f"attached ← {device['name']}", glyph_x + 12, cy + 18,
                             7.4, GREEN, 0.88)
        else:
            rv.flat_text(cr, "detached", inner_x + inner_w - 62, cy + 18, 7.4, DIM, 0.7)
        rv.flat_text(cr, session["age"], inner_x + inner_w - 14, cy + 18, 7.4,
                     MUTED, 0.6, align="right")

        pane_map(cr, session["layout"], inner_x + 14, cy + 28,
                 inner_w - 28, card_h - 48,
                 accent=TEAL if live else DIM, dim=not live)

        rv.flat_text(cr, session["path"], inner_x + 14, cy + card_h - 8, 7, MUTED, 0.55)
        rv.flat_text(cr, f"{session['windows']}w · {session['panes']}p",
                     inner_x + inner_w - 14, cy + card_h - 8, 7, DIM, 0.6, align="right")

    return height


# --- concept 4: ingress radar ----------------------------------------------
# Radius encodes staleness: dead centre is "active right now", the outer ring
# is the idle horizon. Bearing is a stable hash of the device name, so a blip
# keeps its bearing between frames and only walks inward/outward.

RADAR_RANGES = [("NOW", 0.0), ("5m", 0.34), ("1h", 0.63), ("IDLE", 1.0)]


def bearing_for(index):
    """Golden-angle slots keep blips from stacking up on one bearing."""
    return math.radians((index * 137.508 + 24) % 360)


RECENCY = {"8s": 0.26, "3m": 0.42, "12m": 0.58, "2h": 0.88}


def radar_blips():
    devices = DEVICES + [ALERT_DEVICE]
    order = sorted(range(len(devices)), key=lambda i: devices[i]["name"])
    blips = []
    for slot, index in enumerate(order):
        device = devices[index]
        blips.append((device, RECENCY[device["age"]], bearing_for(slot)))
    return sorted(blips, key=lambda item: item[0]["name"])


def draw_radar(cr, x, y):
    height = 470
    rv.panel_frame(cr, x, y, PANEL_W, height, accent=GREEN, secondary=VIOLET)
    header(cr, x, y, PANEL_W, "INGRESS", "TAILNET · SWEEP 4s")
    rv.divider(cr, x + 20, x + PANEL_W - 20, y + 42)

    cx = x + PANEL_W / 2
    cy = y + 218
    radius = 162
    sweep = math.radians(-52)

    # Scope well.
    glow = cairo.RadialGradient(cx, cy, radius * 0.05, cx, cy, radius)
    glow.add_color_stop_rgba(0, *rv.shaded(GREEN, -0.55), 0.20)
    glow.add_color_stop_rgba(0.62, *rv.shaded("020617", 0), 0.72)
    glow.add_color_stop_rgba(1, *rv.shaded("01030a", 0), 0.86)
    cr.set_source(glow)
    cr.arc(cx, cy, radius, 0, math.tau)
    cr.fill()

    # Range rings.
    for label, fraction in RADAR_RANGES:
        ring = radius * max(fraction, 0.06)
        rv.set_hex(cr, GREEN, 0.20 if fraction < 1 else 0.42)
        cr.set_line_width(1 if fraction < 1 else 1.4)
        cr.arc(cx, cy, ring, 0, math.tau)
        cr.stroke()
        rv.flat_text(cr, label, cx + 7, cy - ring - 4, 6.2, GREEN, 0.55)

    # Crosshair + bearing ticks.
    rv.set_hex(cr, GREEN, 0.16)
    cr.set_line_width(1)
    cr.move_to(cx - radius, cy)
    cr.line_to(cx + radius, cy)
    cr.move_to(cx, cy - radius)
    cr.line_to(cx, cy + radius)
    cr.stroke()
    for step in range(36):
        angle = step * math.tau / 36
        long_tick = step % 3 == 0
        r1 = radius - (7 if long_tick else 4)
        rv.set_hex(cr, GREEN, 0.42 if long_tick else 0.22)
        cr.set_line_width(1.2 if long_tick else 0.8)
        cr.move_to(cx + math.cos(angle) * r1, cy + math.sin(angle) * r1)
        cr.line_to(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
        cr.stroke()

    # Sweep wedge: bright leading edge trailing into afterglow.
    steps = 46
    span = math.radians(86)
    for step in range(steps):
        t = step / steps
        a1 = sweep - span * t
        a2 = sweep - span * (t + 1 / steps)
        cr.move_to(cx, cy)
        cr.arc(cx, cy, radius, min(a1, a2), max(a1, a2))
        cr.close_path()
        rv.set_hex(cr, GREEN, 0.26 * (1 - t) ** 2)
        cr.fill()

    rv.set_hex(cr, GREEN, 0.85)
    cr.set_line_width(1.6)
    cr.move_to(cx, cy)
    cr.line_to(cx + math.cos(sweep) * radius, cy + math.sin(sweep) * radius)
    cr.stroke()

    # Blips.
    for device, recency, angle in radar_blips():
        br = radius * max(recency, 0.26)
        bx = cx + math.cos(angle) * br
        by = cy + math.sin(angle) * br
        state = device["state"]
        tone = {"live": GREEN, "idle": DIM, "alert": RED}[state]

        if state == "alert":
            for ring_index in range(3):
                rv.set_hex(cr, RED, 0.30 - ring_index * 0.09)
                cr.set_line_width(1.2)
                cr.arc(bx, by, 7 + ring_index * 5.5, 0, math.tau)
                cr.stroke()

        rv.set_hex(cr, tone, 0.22)
        cr.arc(bx, by, 8.5, 0, math.tau)
        cr.fill()
        rv.bead(cr, bx, by, 3.6 if state != "idle" else 2.8, tone,
                alpha=1.0 if state != "idle" else 0.55)

        # Callout runs radially outward, so labels separate as blips do.
        lead = 15
        ex = cx + math.cos(angle) * (br + lead)
        ey = cy + math.sin(angle) * (br + lead)
        rv.set_hex(cr, tone, 0.45)
        cr.set_line_width(0.9)
        cr.move_to(bx + math.cos(angle) * 6, by + math.sin(angle) * 6)
        cr.line_to(ex, ey)
        cr.stroke()

        side = 1 if math.cos(angle) >= -0.15 else -1
        lx = ex + side * 4
        align = "left" if side > 0 else "right"
        rv.flat_text(cr, device["name"], lx, ey + 2.4, 7.4, tone,
                     0.95 if state != "idle" else 0.72, align=align)
        if device["session"]:
            rv.flat_text(cr, "tmux:" + device["session"], lx, ey + 11.4, 6.2, TEAL, 0.72,
                         align=align)

    rv.set_hex(cr, GREEN, 0.5)
    cr.set_line_width(1.6)
    cr.arc(cx, cy, radius, 0, math.tau)
    cr.stroke()
    rv.bead(cr, cx, cy, 2.6, TEAL)
    rv.flat_text(cr, "kianlaptop", cx - 9, cy + 4, 6.4, TEAL, 0.7, align="right")

    # Readout table.
    table_y = y + height - 116
    rv.divider(cr, x + 20, x + PANEL_W - 20, table_y - 12)
    for index, (device, _recency, _angle) in enumerate(radar_blips()):
        ry = table_y + index * 20
        tone = {"live": GREEN, "idle": DIM, "alert": RED}[device["state"]]
        status_dot(cr, x + 30, ry - 3, device["state"])
        device_glyph(cr, device["glyph"], x + 50, ry - 3, tone, 0.9)
        rv.flat_text(cr, device["name"], x + 66, ry, 7.6,
                     TEXT if device["state"] != "idle" else MUTED, 0.95)
        rv.flat_text(cr, device["os"], x + 198, ry, 7, MUTED, 0.6)
        rv.flat_text(cr, "tmux:" + device["session"] if device["session"] else "—",
                     x + 286, ry, 7, TEAL if device["session"] else DIM, 0.8)
        rv.flat_text(cr, device["addr"], x + 384, ry, 6.6, DIM, 0.55)
        rv.flat_text(cr, device["age"], x + PANEL_W - 24, ry, 7, tone, 0.8, align="right")

    return height


# --- output ----------------------------------------------------------------

VARIANTS = [
    ("01-patch-bay-maps.png", "PATCH BAY + PANE MAPS",
     lambda cr, x, y: draw_patch_bay(cr, x, y, with_maps=True)),
    ("02-patch-bay.png", "PATCH BAY",
     lambda cr, x, y: draw_patch_bay(cr, x, y, with_maps=False)),
    ("03-pane-maps.png", "PANE MICRO-MAPS", draw_pane_maps),
    ("04-radar.png", "INGRESS RADAR", draw_radar),
    ("05-patch-bay-alert.png", "PATCH BAY · UNKNOWN DEVICE",
     lambda cr, x, y: draw_patch_bay(cr, x, y, with_maps=True, alert=True)),
]

MARGIN = 34


def measure(drawer):
    probe = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
    return drawer(cairo.Context(probe), -4000, -4000)


def render_one(filename, drawer):
    height = measure(drawer)
    width = PANEL_W + MARGIN * 2
    total = height + MARGIN * 2
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, total)
    cr = cairo.Context(surface)
    rv.wallpaper(cr, width, total)
    drawer(cr, MARGIN, MARGIN)
    surface.write_to_png(os.path.join(HERE, filename))
    return width, total


def render_sheet():
    heights = [measure(drawer) for _name, _label, drawer in VARIANTS]
    columns = 3
    rows = (len(VARIANTS) + columns - 1) // columns
    col_w = PANEL_W + 40
    row_heights = []
    for row in range(rows):
        band = heights[row * columns:(row + 1) * columns]
        row_heights.append(max(band) if band else 0)

    width = columns * col_w + 40
    height = sum(row_heights) + rows * 62 + 50
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    rv.wallpaper(cr, width, height)

    cursor_y = 40
    for row in range(rows):
        for column in range(columns):
            index = row * columns + column
            if index >= len(VARIANTS):
                break
            _name, label, drawer = VARIANTS[index]
            px = 40 + column * col_w
            rv.flat_text(cr, label, px + 4, cursor_y - 12, 9, LILAC, 0.85)
            drawer(cr, px, cursor_y)
        cursor_y += row_heights[row] + 62

    surface.write_to_png(os.path.join(HERE, "contact-sheet.png"))
    return width, height


def main():
    for filename, _label, drawer in VARIANTS:
        size = render_one(filename, drawer)
        print(f"{filename}: {size[0]}x{size[1]}")
    size = render_sheet()
    print(f"contact-sheet.png: {size[0]}x{size[1]}")


if __name__ == "__main__":
    main()
