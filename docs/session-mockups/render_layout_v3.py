#!/usr/bin/env python3
"""Layout study v3: the skyline as the rate limit panel's roof.

v2 floated a diagonal skyline in the middle of the band. This one uses the
level lattice instead, sized to the rate limit panel's drawn width and dropped
onto its top edge so the two objects read as one stack. The patch bay keeps the
column the GitHub rail vacates.

Run against a `scripts/render_desktop.py --monitor 0` frame rendered *without*
the github overlay:

    uv run python scripts/render_desktop.py --monitor 0 \\
        --overlay linear --overlay rate-limit-panel --overlay weather \\
        --overlay resource-monitor --overlay billing --overlay git -o /tmp/f.png
    uv run --with pycairo python docs/session-mockups/render_layout_v3.py /tmp/f.png
"""

import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "github-mockups")))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))
import render_placement as rp
import render_skyline as sky

# Head 0, monitor-local. The rate limit panel's *drawn* frame — not its 1548px
# window — is what the roof has to match, measured off a real render.
PANEL_X, PANEL_W = 458, 1008
PANEL_TOP = 758          # 2px above the provider chips that straddle the frame
TOWER_MAX = 205          # height of the busiest day; the band allows ~400

# Right edge flush with PANEL_X and bottom flush with PANEL_TOP, so the bay
# and the roof deck share both a seam and a baseline.
PATCH_X = PANEL_X - rp.PANEL_W


def main():
    desktop = sys.argv[1]
    sky.set_mode("level")
    sky.fit_width(PANEL_W)
    sky.set_height(TOWER_MAX)

    base = cairo.ImageSurface.create_from_png(desktop)
    cr = cairo.Context(base)

    probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8))
    patch_y = PANEL_TOP - rp.draw_patch_bay(probe, -4000, -4000)

    bx0, by0, bx1, by1 = sky.bounds()
    sky.draw(cr, PANEL_X - bx0, PANEL_TOP - by1)
    rp.draw_patch_bay(cr, PATCH_X, patch_y)

    out = os.path.join(HERE, "placement-layout-v3.png")
    base.write_to_png(out)
    print(out)
    print(f"  roof      {int(bx1 - bx0)}x{int(by1 - by0)} at "
          f"+{PANEL_X}+{int(PANEL_TOP - (by1 - by0))}  week step {sky.WEEK[0]:.1f}px")
    print(f"  patch bay {rp.PANEL_W} at +{PATCH_X}+{patch_y}")


if __name__ == "__main__":
    main()
