# Billing panel design archive

This directory preserves the complete useful output of the August 19, 2026 billing-panel design study. It is a design prototype, not a shipped overlay: no billing fetcher, cache schema, Conky config, or production Lua renderer was added as part of this work.

## Open the mockup

- [Full interactive gallery](billing-innovation-showcase.html) contains the complete concept survey, state switches, desktop placement studies, and full-size image viewer.
- [Focused final view](billing-innovation-showcase.html?focus=affine) hides the gallery chrome and shows only the selected Affine Month Map plus its OpenRouter explanation.
- [Final map render](affine-map-only.png) is the bare 420 × 300 Cairo output with no enclosing panel, title, legend card, or footer.

The HTML uses only relative local assets, so the directory can be moved or checked out elsewhere and opened directly in a browser.

## Selected direction: Affine Month Map

The selected object is an affine transform of a conventional time-by-cap chart. Its diamond shape is unusual, but its reference lines remain mathematically straight and reversible:

- The time axis runs from day 1 through the common August 31 month-end edge.
- The pressure axis is normalized independently for each provider; `1.0` is that provider's own cap.
- A filled bead marks the current observation, the colored segment marks the forecast, and a hollow diamond marks the August 31 landing.
- The red line is the 100% cap, the yellow line is August 19 (`19 / 31` through the month), and the faint diagonal is calendar pace.
- Provider labels are attached directly to the geometry, allowing the surrounding legend and widget chrome to be removed.

The illustrative metered values are:

| Provider | Current | August 31 forecast | Normalized current | Normalized forecast |
| --- | ---: | ---: | ---: | ---: |
| AWS | $8.41 of $25 | $13.20 | 34% | 53% |
| Azure | $4.27 of $20 | $7.10 | 21% | 36% |
| Anthropic | $6.04 of $20 | $10.10 | 30% | 51% |

For these services, the plotted values are `current spend / cap` and `forecast spend / cap`. The chart never adds their dollar amounts together.

## OpenRouter mapping

OpenRouter began as a separate instrument in the exploratory concepts because a prepaid balance is not the same quantity as a monthly budget. A runway in days could not honestly be placed on the metered providers' cap axis or included in a combined dollar total.

The final decision keeps that semantic distinction while giving OpenRouter the same visible August 31 endpoint:

- The current $12.44 balance is the OpenRouter-specific 100% ceiling.
- A trailing usage history may estimate the $0.43 average daily burn, but the visible x-axis remains August 19 through August 31 rather than becoming a rolling 30-day chart.
- With 12 days remaining, expected future draw is `$0.43 × 12 = $5.16`.
- Its August 31 pressure is `$5.16 / $12.44 = 41.5%`, rendered as 41%.
- Projected credit left at month end is `$12.44 - $5.16 = $7.28`.
- The violet bead starts at zero future draw on August 19. The violet hollow diamond lands on the same August 31 edge as AWS, Azure, and Anthropic.

This means the violet percentage reads “share of today's available credit expected to be consumed by the common month-end date,” not “share of a contractual monthly allowance already used.”

## Design path and decisions

The first studies used balanced, compact, and forecast-first arrangements. They established footprint and data hierarchy, but they remained too visually close to the existing rate-limit panel. A trajectory-well direction was more distinctive, yet its instrument-like treatment risked feeling ornamental.

Claude and Grok were then used as independent design critics. Their preserved outputs are [Claude's review](claude-design-review-2.txt) and [Grok's review](grok-design-review-2.txt). The shared constraints that materially shaped the next round were:

1. Do not manufacture a grand cross-provider dollar total.
2. Make danger change geometry by crossing a ceiling, wall, or plane.
3. Keep prepaid runway semantically distinct from monthly caps.
4. Draw only the current-to-forecast segment until genuine historical samples exist.

Three parallel concept lanes followed:

- [Trajectory studies](trajectory_variants/NOTES.md): Landing Field, Forecast Rain, Affine Cap Map, and Isometric Runway.
- [Ambient studies](ambient_variants/NOTES.md): Cap Canopy, Threshold Tide, Delta Lenses, and Threshold Ray, each in calm and breach states.
- [Geometric studies](geometric_variants/NOTES.md): Facet Ledger, Surprise Map, Allowance Facets, and Budget Shards.

Forecast Rain was initially the strongest fresh general-purpose option, while Landing Field was the safest conventional baseline. The Affine Cap Map became the chosen direction after stripping away its surrounding widget and moving OpenRouter into the same month-end geometry.

## Archive contents

- `affine-map-only.py` and `affine-map-only.png` are the selected renderer and output.
- `billing-innovation-showcase.html` is the final gallery; `billing-showcase.html` preserves the earlier round.
- `billing_mockups.py` and `innovative_mockups.py` generate the first-round panels, trajectory well, history study, state sheet, and desktop placement renders.
- `trajectory_variants/`, `ambient_variants/`, and `geometric_variants/` each contain deterministic Pycairo source, individual renders, a contact sheet, and design notes.
- `showcase-*.png` files preserve browser verification screenshots from the iterations that introduced the affine view, OpenRouter, its focus mode, and the shared month-end horizon.
- `harness_png.lua`, `harness_overlay.lua`, `replay.py`, and `replay_transparent.py` preserve the Cairo operation-dump/replay technique used when desktop screenshot APIs were unavailable.
- `rate-limit.ops`, `resource.ops`, and `weather.ops` are the captured operation logs; their corresponding PNGs preserve the reference appearance used for placement and visual comparison.
- `claude-design-review-2.txt` and `grok-design-review-2.txt` preserve the external critique that informed the concept lanes.

Only transient Python bytecode and empty stderr capture files were omitted from the scratch directory. All useful source, HTML, notes, operation logs, rendered artwork, and verification screenshots are retained here.

## Regenerate the artwork

The sketches require Python 3, Pycairo, and JetBrains Mono. From this directory:

```bash
python3 billing_mockups.py
python3 innovative_mockups.py
python3 trajectory_variants/render_variants.py
python3 ambient_variants/render_ambient_variants.py
python3 geometric_variants/render.py
python3 affine-map-only.py
```

The scripts write their PNGs beside their source. They contain illustrative data and do not call billing APIs.

To recapture the current production renderers through the preserved operation-dump pipeline, run these commands from the repository root:

```bash
lua docs/billing-mockups/harness_png.lua "$PWD" > docs/billing-mockups/rate-limit.ops
python3 docs/billing-mockups/replay.py \
  docs/billing-mockups/rate-limit.ops \
  docs/billing-mockups/rate-limit-reference.png

lua docs/billing-mockups/harness_overlay.lua "$PWD" resource > docs/billing-mockups/resource.ops
python3 docs/billing-mockups/replay_transparent.py \
  docs/billing-mockups/resource.ops docs/billing-mockups/resource.png 280 258

lua docs/billing-mockups/harness_overlay.lua "$PWD" weather > docs/billing-mockups/weather.ops
python3 docs/billing-mockups/replay_transparent.py \
  docs/billing-mockups/weather.ops docs/billing-mockups/weather.png 456 276
```

Those harnesses load the repository's current Lua renderers and cached data, so rerunning them later is a regression check rather than a reproduction of the exact 2026 snapshot.
