# Ambient billing explorations

These are deliberately quiet alternatives to the existing rate-limit panel.
They use a chamfered sheet of glass, sparse geometry, and one shared threshold
instead of repeated cards, progress tubes, donuts, or decorative sparklines.
The figures are illustrative design data.

Every concept is rendered twice. The left/calm version and right/alert version
use exactly the same geometry; only the input state changes. In the alert state,
AWS projects past its cap and OpenRouter runway is three days short of month end.

## 01 — Cap Canopy

Three budgeted services hang from one literal cap line. The small square is MTD,
the diamond is EOM forecast, and their connecting thread is expected remaining
spend. Empty vertical space is headroom. A forecast crossing the canopy is the
only element allowed to glow red. OpenRouter lives on a separate day axis.

Strength: probably the clearest ambient concept. It communicates “how far from
the ceiling?” before it asks the eye to read any numbers.

## 02 — Threshold Tide

Identical-width smooth mounds encode only height: the filled inner mound is MTD,
the dashed outer crest is EOM forecast. A crest piercing the cap becomes a sharp
red break, so calm states remain soft while risk becomes visually discontinuous.
OpenRouter again uses days, never currency percentage.

Strength: the most organic and wallpaper-like. Caveat: curved peaks trade some
precision for atmosphere, so the numeric forecast remains directly underneath.

## 03 — Delta Lenses

Each lens spans current spend to projected spend. Its length is the remaining
monthly burn; its distance from the cap is projected headroom. This gives two
useful quantities in one shape without implying historical data. Any portion
crossing the cap gains a red cut at the threshold.

Strength: the most novel shape with the cleanest actual-versus-forecast story.

## 04 — Threshold Ray

All metered services share one diagonal 0–100% axis. The small square is actual,
the diamond is forecast, and the short colored segment between them is expected
remaining burn. Only forecasts above 100% travel beyond the cap endpoint. The
separate violet ray is explicitly a day/runway scale with an EOM notch.

Strength: the lowest total ink and smallest eye movement. Caveat: the diagonal
axis is less immediately conventional than the canopy, so it needs a brief
learning moment.

## Suggested shortlist

1. **Cap Canopy** for best at-a-glance legibility.
2. **Delta Lenses** for the freshest identity without inventing data.
3. **Threshold Ray** if the target is maximum calm and minimum chrome.

The Tide is worth keeping as an aesthetic wildcard, but its organic form is less
precise than the other three.
