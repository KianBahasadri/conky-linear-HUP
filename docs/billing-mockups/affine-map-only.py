#!/usr/bin/env python3
"""Render the affine month map with no enclosing widget chrome."""

import os
import sys

import cairo


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "trajectory_variants"))
import render_variants as rv


WIDTH = 420
HEIGHT = 300


def render():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    cr = cairo.Context(surface)

    base_x, base_y = 203, 263
    time_vector = (160, -94)
    pressure_vector = (-145, -94)
    pressure_max = 1.12

    def point(time, pressure):
        return (
            base_x + time_vector[0] * time + pressure_vector[0] * pressure / pressure_max,
            base_y + time_vector[1] * time + pressure_vector[1] * pressure / pressure_max,
        )

    domain = [point(0, 0), point(1, 0), point(1, pressure_max), point(0, pressure_max)]

    # The diamond itself is the only surface: no panel, header, chips, footer,
    # legend, or prepaid side instrument.
    cr.move_to(*domain[0])
    for corner in domain[1:]:
        cr.line_to(*corner)
    cr.close_path()
    rv.set_hex(cr, "8b5cf6", 0.10)
    cr.set_line_width(12)
    cr.stroke()

    cr.move_to(*domain[0])
    for corner in domain[1:]:
        cr.line_to(*corner)
    cr.close_path()
    cr.set_source(rv.gradient(58, 72, 340, 262, [
        (0.00, "10182b", 0.90),
        (0.48, "050b18", 0.88),
        (1.00, "02050e", 0.78),
    ]))
    cr.fill_preserve()
    rv.set_hex(cr, "c4b5fd", 0.30)
    cr.set_line_width(1.1)
    cr.stroke()

    # Overshoot is part of the map domain, not a separate warning card.
    cap_start, cap_end = point(0, 1), point(1, 1)
    top_start, top_end = point(0, pressure_max), point(1, pressure_max)
    cr.move_to(*cap_start)
    cr.line_to(*cap_end)
    cr.line_to(*top_end)
    cr.line_to(*top_start)
    cr.close_path()
    rv.set_hex(cr, "f87171", 0.085)
    cr.fill()

    # Shared coordinate mesh.
    cr.set_line_width(1)
    for day in (7, 14, 21, 28):
        a, b = point(day / rv.DAYS, 0), point(day / rv.DAYS, pressure_max)
        rv.set_hex(cr, "f8fafc", 0.065)
        cr.move_to(*a)
        cr.line_to(*b)
        cr.stroke()
    for pressure in (0.25, 0.50, 0.75):
        a, b = point(0, pressure), point(1, pressure)
        rv.set_hex(cr, "f8fafc", 0.065)
        cr.move_to(*a)
        cr.line_to(*b)
        cr.stroke()

    # The four laws needed to read the object.
    now_start, now_end = point(rv.ELAPSED, 0), point(rv.ELAPSED, pressure_max)
    eom_start, eom_end = point(1, 0), point(1, pressure_max)
    rv.set_hex(cr, "facc15", 0.50)
    cr.move_to(*now_start)
    cr.line_to(*now_end)
    cr.stroke()
    rv.set_hex(cr, "c4b5fd", 0.34)
    cr.move_to(*eom_start)
    cr.line_to(*eom_end)
    cr.stroke()
    rv.set_hex(cr, "f87171", 0.76)
    cr.set_line_width(1.5)
    cr.move_to(*cap_start)
    cr.line_to(*cap_end)
    cr.stroke()

    pace_start, pace_end = point(0, 0), point(1, 1)
    rv.set_hex(cr, "f8fafc", 0.19)
    cr.set_line_width(1)
    cr.set_dash([3, 3])
    cr.move_to(*pace_start)
    cr.line_to(*pace_end)
    cr.stroke()
    cr.set_dash([])

    rv.flat_text(cr, "DAY 1", domain[0][0], domain[0][1] + 17, 7.5, "94a3b8", 0.62, align="center")
    rv.flat_text(cr, "NOW", now_start[0] + 3, now_start[1] + 17, 7.5, "facc15", 0.86, align="center")
    rv.flat_text(cr, "EOM", eom_start[0] + 3, eom_start[1] + 17, 7.5, "c4b5fd", 0.78, align="center")
    rv.flat_text(cr, "CAP", cap_start[0] - 7, cap_start[1] - 2, 7.5, "f87171", 0.90, align="right")

    # Provider identity is attached directly to the geometry, replacing the
    # removed legend. Filled bead = now; hollow diamond = horizon landing.
    label_rows = {
        "AWS": 91,
        "ANT": 108,
        "OR": 125,
        "AZR": 142,
    }
    for item in sorted(rv.SERIES, key=lambda entry: entry["f"]):
        current = point(rv.ELAPSED, item["s"])
        forecast = point(1, item["f"])
        rv.glow_line(cr, *current, *forecast, item["color"], width=1.9, alpha=0.96)
        rv.bead(cr, *current, 4.3, item["color"])
        rv.diamond(cr, *forecast, 5.0, item["color"], hollow=True)
        label_y = label_rows[item["code"]]
        rv.set_hex(cr, item["color"], 0.42)
        cr.set_line_width(0.8)
        cr.move_to(forecast[0] + 5, forecast[1])
        cr.line_to(322, label_y - 3)
        cr.stroke()
        rv.flat_text(
            cr,
            f"{item['code']} {item['f'] * 100:.0f}%",
            328,
            label_y,
            7.5,
            item["color"],
            0.92,
        )

    # OpenRouter shares the exact same August 31 horizon as every metered
    # provider. Its current balance is the 100% ceiling, while the trajectory
    # is only the additional credit expected to be consumed from now to EOM.
    # Recent history informs the daily burn rate; it does not change the x-axis.
    reserve = rv.RESERVE
    eom_spend = reserve["burn"] * rv.DAYS_LEFT
    forecast_pressure = eom_spend / reserve["balance"]
    current = point(rv.ELAPSED, 0)
    forecast = point(1, forecast_pressure)

    rv.glow_line(cr, *current, *forecast, reserve["color"], width=2.0, alpha=0.98)
    rv.bead(cr, *current, 4.5, reserve["color"])
    rv.diamond(cr, *forecast, 5.2, reserve["color"], hollow=True)

    label_y = label_rows["OR"]
    rv.set_hex(cr, reserve["color"], 0.48)
    cr.set_line_width(0.8)
    cr.move_to(forecast[0] + 5, forecast[1])
    cr.line_to(322, label_y - 3)
    cr.stroke()
    rv.flat_text(
        cr,
        f"OR {forecast_pressure * 100:.0f}%",
        328,
        label_y,
        7.5,
        reserve["color"],
        0.98,
    )

    output = os.path.join(HERE, "affine-map-only.png")
    surface.write_to_png(output)
    print(output)


if __name__ == "__main__":
    render()
