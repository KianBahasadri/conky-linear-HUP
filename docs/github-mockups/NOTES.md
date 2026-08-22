# Contribution skyline study

Extrudes the year-of-squares rail into a skyline, one tower per day. The `level`
lattice shipped — see [GitHub overlay](../github.md) for the overlay it became.
This file is the study that got there, kept for the reasoning and the rejected
`iso` alternative.

Two lattices, selected with `set_mode()`:

| Plate | Mode | Shape |
| --- | --- | --- |
| `01-skyline.png` | `iso` | Free-floating ribbon; drifts 122px downhill across the year |
| `02-skyline-level.png` | `level` | Week axis exactly horizontal, on a plinth; stacks onto a panel |

`render_skyline.py` draws it with the billing study's Cairo primitives and
GitHub's own dark ramp (`0e4429` / `006d32` / `26a641` / `39d353`), the same
colours `conky/github-tracker-renderer.lua` uses.

```bash
uv run --with pycairo python docs/github-mockups/render_skyline.py
```

## Levels are not enough

The shipped fetcher scrapes `data-level="0-4"` per day. Five discrete heights
make a flat carpet: this account's year is 146 zero days, 195 at level 1, and
only 3 at level 4.

The same page carries true counts in `<tool-tip>` elements, joined to each cell
by the `<td>`'s `id`:

```html
<td id="contribution-day-component-0-2" data-date="2025-08-31" data-level="1">
<tool-tip for="contribution-day-component-0-2">1 contribution on August 31st.</tool-tip>
```

One extra regex pass in `scripts/fetch_github_contributions.py` gets them.
`sample-counts.json` is a capture of that scrape (371 days, 2538 contributions,
max 133) so the mockup renders without network access.

## Geometry

- `iso` steps `WEEK = (20.0, 2.3)` right and slightly toward the viewer, and
  `DAY = (12.4, -16.0)` right and away. Near-equal lengths keep the plan-view
  cells square.
- `level` is that same lattice rotated by the 6.56° the week axis drifts:
  `WEEK = (20.132, 0)`, `DAY = (10.491, -17.312)`. Rotating rather than
  inventing a second projection keeps the cells square and the basis lengths
  matched for free.
- `set_scale(week_px)` rescales the lattice, tower heights, plinth and readout
  offsets together. `fit_width(px)` solves for the week step that makes the
  object an exact width, and `set_height(px)` scales the extrusion so the
  busiest day stands a given number of pixels tall.
- Painter's order is by base screen-y ascending: higher on screen is farther
  away, and towers only extend upward.
- Two of the four side faces are ever visible — the day-0 edge and the week-max
  edge — so each tower is three fills, not six.
- Height is `8.5 * sqrt(count)`. Linear scaling lets the single 133-commit day
  flatten every other tower into the ground plane.
- Zero days draw as an outlined plate, which keeps the calendar's shape visible
  through the gaps.

## Level mode

Levelling the week axis is what lets the skyline sit on something. With the
front row a straight horizontal line, the object has a real baseline, so it can
be dropped onto a panel's top edge and read as that panel's roof rather than as
a separate thing floating nearby.

- A plinth (`draw_deck`) fills the full lattice quad and extrudes `DECK_THICK`
  downward. Without it the front-left cells have nothing under them and the
  ribbon still looks airborne.
- The plinth shows the same two walls the towers do — south and east — because
  it is the same lattice.
- Month ticks move onto the plinth's fascia. In `iso` they hang below the front
  edge, which in `level` would put them on whatever the skyline is standing on.
- `bounds()` includes the plinth in `level` mode, so a caller can align the
  object's bottom edge to a panel edge directly.

## Readout placement

In `iso` the ribbon descends left to right, which leaves exactly two clear areas
inside the object's own bounding box: the strip above its right end, and the
floor below its left end. Year total and busiest day go top-right; the two
streaks go bottom-left. Every other position collides with towers or the month
ticks — including the single top row, which the tall autumn columns cut into.

The shipped `level` mode drops the readout entirely — the skyline is just the
plinth and the towers filling the available height.
