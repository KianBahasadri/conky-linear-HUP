#!/usr/bin/env python3
"""Layout study: 3D contribution skyline in the mid band, patch bay on the left.

Composites both proposed objects onto a real `scripts/render_desktop.py` frame
that was rendered with the GitHub rail switched off, so the vacated left column
and the empty mid band are the actual pixels being filled.
"""

import os
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "github-mockups")))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "billing-mockups", "trajectory_variants")))
import render_variants as rv
import render_placement as rp
import render_skyline as sky

# Head 0, monitor-local coordinates.
#   git panel      0..309   x,  -3..365 y
#   linear cards   186..1734,  30..325
#   rate limit     186..1734, 731..1078
#   billing        1454..1918, 576..884
# The freed rail column and the band between linear and the rate limit panel
# are what these two objects move into.
PATCH_X, PATCH_Y = 6, 420
SKYLINE_WEEK_PX = 16.0
SKYLINE_LEFT, SKYLINE_TOP = 500, 396


def main():
    desktop = sys.argv[1]
    sky.set_scale(SKYLINE_WEEK_PX)

    base = cairo.ImageSurface.create_from_png(desktop)
    cr = cairo.Context(base)

    bx0, by0, bx1, by1 = sky.bounds()
    sky.draw(cr, SKYLINE_LEFT - bx0, SKYLINE_TOP - by0)
    rp.draw_patch_bay(cr, PATCH_X, PATCH_Y)

    out = os.path.join(HERE, "placement-layout-v2.png")
    base.write_to_png(out)
    print(f"{out}")
    print(f"  skyline   {int(bx1 - bx0)}x{int(by1 - by0)} at "
          f"+{SKYLINE_LEFT}+{SKYLINE_TOP}")
    print(f"  patch bay {rp.PANEL_W} at +{PATCH_X}+{PATCH_Y}")


if __name__ == "__main__":
    main()
