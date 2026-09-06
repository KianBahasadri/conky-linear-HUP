# Linear overlay

- Each card carries the project and issue identifier on the left of the header
  line, and deadlines or urgency states (`Urgent`, `Due today`) on the right,
  followed by a left-aligned title. Completed cards have no status text.
  Permanent footers and nonessential labels are removed; workflow state labels
  (`In Progress`, `Todo`) are omitted because contrast follows progress:
  `In Progress` titles stay bright, while other titles become muted. Urgency
  colors and the completed-task fade remain.
  Titles start at 15px and do not wrap: if a title overflows, the renderer retries
  at 14px then 13px, and truncates if 13px still overflows. Cards form a gapless grid.
- The card's fill and any header text carry the tone together: completed cards
  are good, `Due today` is danger with square corners, `Urgent` is caution, and
  every ordinary workflow state is neutral. There is no separate status badge,
  status dot, or inset rail inside a card.
- The project name is shown as an acronym: every uppercase letter is kept,
  including camelCase capitals with no preceding space, except that an all-caps
  word contributes only its first letter; digits, dashes, and other non-letters
  stay. The project's emoji is drawn to the left of that acronym from `Noto
  Color Emoji`, resolved by the fetcher from Linear's shortcode icons; projects
  using built-in icon names or no icon show the acronym alone. Metadata
  truncates at the available width. Shared styling and paging belong to the
  [Desktop design system](design-system.md).
- If any unfinished card is due today, non-due unfinished cards are hidden so urgent work dominates the overlay.
- Unfinished issues in the `Competitions` project due in the next 3 days are always shown, with their due date in the card header.
- Issues in the `Backlog` state with a due date in the next 3 days are also shown (including when urgent due-today filtering is active).
- Cancelled and duplicate issues are never shown.
- Recently completed cards remain visible for `LINEAR_DONE_LOOKBACK_HOURS`, fading linearly from full opacity when completed to fully transparent as the lookback window expires; the fetcher stamps each card with `completedAtEpoch` and the payload with `doneLookbackSeconds` so the renderer can compute the fade locally on every tick. Done cards are ordered most-recently-completed first, so they read newest-to-oldest top-down and left-to-right.
- Card width is fluid with a 252px minimum and no gaps. A card is 50px tall;
  a grid row is as tall as its tallest card. Default desktop pages have four
  columns and up to three rows. The renderer applies the due-today
  visibility filter before allocating page slots.
- Window bounds are established at startup. Cache refreshes update cards
  without rewriting configs or reloading Conky; extra cards rotate in place.
- A failed Linear fetch keeps the last successful cards instead of writing an empty cache.
- `LINEAR_TASK_LIMIT` sets the query depth for each workflow state, not a global
  card cap. `LINEAR_COMPETITION_TASK_LIMIT` and
  `LINEAR_BACKLOG_DUE_SOON_LIMIT` independently size their supplemental
  connections. Each defaults to and is capped at `25`: larger pages are valid
  in isolation, but this combined operation is rejected by Linear as too
  complex. Invalid or non-positive values also fall back to `25`.
- Set `LINEAR_OVERLAY_ENABLED=0` to disable the Linear overlay and its refresh loop.
