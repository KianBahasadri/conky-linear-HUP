# Desktop design system

The overlays apply the design-guide's dark theme to passive Cairo readouts.
`conky/design-system.lua`, loaded by `renderer-shared.lua`, owns typography,
colors, geometry, badges, callouts, metrics, resource readings, vector paths,
and bounded list paging.

## Visual contract

- IBM Plex Sans is the UI face; IBM Plex Mono is reserved for identifiers,
  timestamps, chart scales, and aligned numbers. Body text is 15px, compact
  record text 13.5px, metadata 12px, and chart annotations 11px. Metric labels
  are uppercase 12px mono with 0.08em tracking; values are 26px bold in the
  muted color.
- The dark tokens are canvas `#080b0d`, surface `#11171b`, raised surface
  `#151d21`, ink `#dbe3e6`, strong ink `#f3f6f5`, muted `#849094`, faint
  `#566166`, border `#263137`, and strong border `#3a4a51`.
- Observed data uses `#62c8d8`; modeled data uses `#b9aaef` and dashed strokes.
  Healthy, caution, and error states use `#79c99e`, `#d6ad63`, and `#df7e78`,
  always with visible status text. Severity also changes geometry: good shapes
  are the most rounded, caution shapes use a 4px radius, and danger shapes are
  square.
- Every panel begins directly with its content. There are no section titles,
  table headers, subtitles, or separator rules, because each window is a
  separate object on a transparent desktop rather than a section of a page.
  Records identify themselves through their own labels, values, and states.
- Nothing is bordered. Only objects that carry their own boundary are filled:
  task cards, status badges, and callouts. Badges carry a 14% semantic tint,
  callouts a 14% tint over a bold status label, and neutral variants of both
  use the raised surface. Sections, plots, metrics, and record lists are
  transparent and shadowless.
- The desktop remains transparent between objects. The dark palette assumes a
  dark desktop background; the render tool can preview the canonical canvas
  with `--background 080b0d`.

## Components

- **Task cards** are the only real card boundary, because issues are
  independently stateful objects. They form a gapless grid of 252px-minimum
  columns; each card has 12px padding, a 104px minimum height, and three rows:
  project with state, the wrapped title, then identifier with deadline. The
  card's soft fill and its state text carry the tone together. See
  [Linear overlay](linear.md).
- **The budget map** is the shared time-and-limit plane behind the billing
  panel. See [Billing forecast panel](billing.md).
- **Resource readings** center a Lucide symbol over a 26px value with its unit
  alongside, then a 64px history on a fixed zero-based scale. See
  [Configuration](configuration.md#system-resource-monitor).
- **Record lists** (repositories, sessions, quota accounts, budget summaries)
  are aligned text rows on a fixed pitch, with a status badge or status text at
  the right edge.
- **Metrics** render only a label and a value, with no supporting subline.

## Icons and provider marks

Lucide path data is vendored in `conky/lucide-icons.lua` under the
[ISC license](../assets/LUCIDE-LICENSE.txt); every icon keeps the 24×24 grid,
2px stroke, and round caps and joins. `conky/provider-marks.lua` holds the
billing providers' own vector marks. Both are drawn by the shared SVG path
reader, which accepts absolute and relative move, line, cubic, quadratic, arc,
and close commands. Brand colors identify a provider and never encode state.

## Composition and overflow

`scripts/overlay_layout.py` plans each monitor in local pixels. It reads only
current cache counts; startup does not fetch data to measure the windows.
The default has 16px outer insets, 24px gutters, and 40px top clearance on the
primary monitor (16px on other monitors).

Each region is sized to its records and the remainder is spent on its rail, so
no gap is left between panels. The left rail holds repositories above sessions,
with Minecraft pinned to the foot when enabled. The center holds the task grid,
the contribution calendar, and AI usage rows at the bottom. The right rail
holds resource readings, the budget map, then weather and training. The
standard 1920×1080 layout has 304px and 400px side rails and a flexible center.
The smaller layout uses 248px and 360px rails; 1280×720 and 1366×768 are
covered by geometry tests and headless renders.

Windows have explicit sizes and zero Conky border margins. They stay inside
separate allocated regions when new records arrive. A list that fits is drawn
whole; one that overflows gives up a single 16px line to a footer naming the
visible range, then rotates in 30-second pages so every record appears once per
complete cycle. Short displays alternate weather and training with `1/2` and
`2/2`. Narrow quota rows place up to four windows in a two-column arrangement.
Rerunning the launcher reallocates space using the latest cache counts.

`*_GAP_X` and `*_GAP_Y` overrides still use their documented original edges;
explicit positions can override the automatic clearance. Leave them empty for
coordinated placement. See [Configuration](configuration.md).

## Native runtime and fonts

These are passive Conky windows, so web-only navigation, search launchers,
hover explorers, copy buttons, focus states, and theme controls are not drawn.
No fake clickable controls are added. Where the design guide puts a fact in an
accessible name, a hover readout, or a details dialog, a passive surface has
nowhere to put it, so the fact is either drawn as visible text (the budget
map's provider summary) or dropped (the monitor's feed cadence). See
[Conky windows and input](conky-windows-and-input.md).

IBM Plex font files and their SIL Open Font License are vendored under
`assets/fonts/`. The launcher runs `scripts/install_overlay_fonts.sh`, which
copies changed files to `${XDG_DATA_HOME:-$HOME/.local/share}/fonts/conky-linear-HUP`
and refreshes that font cache only when needed. Live Conky and headless Cairo
therefore use the same fonts without a network request at startup.
It also installs `70-conky-plex.conf` in the user's Fontconfig `conf.d` directory.
Private `Conky Plex Sans Medium` and `Conky Plex Sans SemiBold` aliases select
the actual 500/600 font faces, which Cairo's normal/bold-only toy API cannot
otherwise request. The aliases affect only the named Conky families.

Rendering and live-window verification are documented in [Desktop render](desktop-render.md).
