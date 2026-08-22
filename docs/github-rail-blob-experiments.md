# GitHub rail blob experiments

Archive of the August 2026 attempt to replace the contribution rail’s year of squares with a poured organic shape. The rail itself has since been replaced by the [contribution skyline](github.md), which extrudes the same calendar instead of reshaping it. Nothing here shipped either way.

The target look was a smooth metaball / goo blob: round lobes, concave waists, no grid, no noise. The data is a 7×53 occupancy mask, and those constraints fight each other. Nothing in this file is live.

## Scalar field

Each contributing day dropped a Wyvill bump into a scalar field. The painted shape was the iso-contour where that field crossed a threshold, traced with marching squares and filled as one Cairo path.

- **`influence`** — how far one day reached, against a cell pitch of 11.
- **`drop_radius`** — radius of a lone day; it set the threshold.
- **`day_weight`** — busier days dropped heavier bumps, so intensity changed size as well as colour.

Overlapping bumps merged with no seam. That part worked. The rest of the study was fighting what the contour did with a real calendar.

## Outline

Marching squares on a 2 px sample grid left a staircase of 90° corners. An interpolating Catmull-Rom still followed those corners, so the edge looked jagged.

| Attempt | Result |
| --- | --- |
| `field_step` 2 → 1 | Closer to the true iso; remaining stairs were smaller but still there |
| Laplacian rounding of the traced loop | Smoothed stairs, but filled the concave waists and turned peanuts into capsules |
| Closed cubic B-spline instead of Catmull-Rom | Rounded without interpolating every grid corner; dense points still hugged the occupancy |

A smooth outline was solvable. A *designed* outline was not, on this data.

## Warp

A calendar-aligned iso has long straight runs wherever a week is solid. A position warp was added so those edges would wander like a poured puddle. It was a pure function of rail position, so the same calendar always produced the same shape.

Short waves (period ~20 px, `ripple` ~2.6) read as a jagged, random edge. Long waves (period ~100–200 px, `ripple` ~5) were worse: a slow, arbitrary wobble unrelated to the days. Both came off. There is no warp on the shipped rail.

## Colour

Colour was read from the same field through the GitHub greens with a ramp gamma.

- Gamma 2.4 kept quiet stretches dark, but busy days sat as bright coins on a dark puddle.
- Gamma 0.85 spread those highlights, but a summed field lights up a whole cluster, so the puddle went neon.
- Colour from the *max* of day bumps, not the sum, kept the body dark and let a single busy day glow. The coins vs wash tradeoff is inherent if the shape is still a merged occupancy field.

## Equal circles

To stop the outline swelling wherever the calendar was dense, every active day became the same-size circle and the painted shape was their union (`max` of bumps, `drop_radius` 8). Intensity stayed colour-only.

The edge became repeating circular lobes instead of a density-inflated amoeba. It also spelled out the 7-column grid: a dense block looked like a lattice of circles, which was the opposite of the target blob.

## Occupancy blur

Bumps were summed again, then a separable box blur (several passes, gaussian-like) dissolved the day lattice so a dense block would read as one puddle. Isolated days stayed round droplets.

That hid the grid and avoided the sine-wave warp, but it also erased the magenta-blob language (few equal lobes with deep waists). A 7×53 mask, blurred until the columns disappear, is a rounded occupancy envelope — a stadium or lumpy sausage — not a three-lobe goo shape.

## Why it was reverted

The square calendar is already a grid, and that is the honest display of this data. Every blob attempt had to pick a failure:

- Resolve days → looks like a grid of circles or a noisy amoeba.
- Merge and blur until the grid dies → a rounded occupancy hull with little structure.
- Add a warp so the hull is not straight → looks random, because the wander is not in the data.

The shipped rail keeps the squares and simply skips empty days, so the desktop shows through. Do not revive the field renderer without a different data aggregation (for example one blob per week, not per day).
