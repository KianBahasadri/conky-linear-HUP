# Billing geometry studies

These four studies use the same deliberately non-emergency `WATCH` scenario so the visual systems can be compared directly:

- AWS: 68% current, 92% EOM forecast (`$17 / $25`, `$23 EOM`)
- Azure: 41% current, 62% EOM forecast (`$8.20 / $20`, `$12.40 EOM`)
- Anthropic: 57% current, 84% EOM forecast (`$11.40 / $20`, `$16.80 EOM`)
- OpenRouter: `$6.45` at `$0.43/day`, 15 days runway versus 12 days left

Metered providers are normalized to their own caps. OpenRouter remains in days and dollars rather than being folded into an invalid cross-unit total. None of the concepts invents a historical time series.

## 01 — Facet Ledger

Ten hexagonal cells form a compact budget object for each provider. Every cell equals 10% of that provider's cap. Solid color is current spend, hatched/ghost color is forecast-only exposure, and dark cells are forecast headroom. The renderer partially clips the boundary cell, so 68% is not rounded to a deceptive seven cells. OpenRouter is a separate trail of twelve month-days followed by three green cushion-days.

Best quality: quickest comparison without looking like another tube-bar stack. It makes `how much of the allowance is spoken for?` almost pre-attentive.

Tradeoff: it still uses discrete units, so the exact number remains more precise than the shape. This is my strongest geometric candidate for an always-on widget.

## 02 — Surprise Map

Each metered provider is one diamond on a real two-dimensional field. X is current percentage of cap; Y is EOM forecast percentage. The dashed diagonal is `forecast = current`, so the vertical distance above it is expected additional consumption. Horizontal zones make 80–100% `WATCH` and >100% `DANGER`. OpenRouter is isolated in a prepaid runway rail.

Best quality: most analytically honest and best at distinguishing `already high` from `accelerating`. A breach is literally a marker entering the red field.

Tradeoff: highest reading cost. It is better as an expanded/hover view or a diagnostic mode than as the default ambient glance.

## 03 — Allowance Facets

The outer gem is 100% of one provider's cap. The dashed nested gem is EOM forecast and the solid nested gem is current spend. The renderer scales side length by `sqrt(percent)`, which makes polygon area—not radius—proportional to the percentage. Exact percentages remain inside each gem. OpenRouter stays a separate days-based trapezoid.

Best quality: calm, sculptural, and clearly unlike the existing quota and resource panels. Three silhouettes can be recognized peripherally.

Tradeoff: humans compare lengths more accurately than areas. This works as an ambient signal, not as a precision instrument; the text is essential.

## 04 — Budget Shards

Each asymmetric shard is a 0–100% vertical cap vessel. The saturated lower cut is current spend; the translucent middle cut reaches the EOM forecast; the dark tip is remaining headroom. The faceted outline changes the emotional texture while keeping the vertical scale conventional. OpenRouter becomes a directional runway chevron.

Best quality: strongest visual personality and easiest to notice peripherally when a forecast cut approaches the tip.

Tradeoff: it is intentionally gauge-adjacent—a shaped vertical bar in information-design terms—and therefore the least conceptually novel. It is useful in the gallery as the boundary between `fresh` and `ornamental`.

## Suggested shortlist

1. Facet Ledger for the default always-on panel.
2. Allowance Facets if atmosphere matters more than precision.
3. Surprise Map as the expanded detail state behind either one.

`contact-sheet.png` shows all four at true pixel dimensions. Individual PNGs are `facet-ledger.png`, `surprise-map.png`, `allowance-facets.png`, and `budget-shards.png`.
