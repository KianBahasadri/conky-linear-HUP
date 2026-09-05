# Linear overlay

- Each card carries the project and its state on the first line, a left-aligned
  title wrapping to at most three lines, then the identifier with the optional
  label and due date. Cards form a gapless grid.
- The card's fill and its state text carry the tone together: `Done` is good,
  `Due today` is danger with square corners, `Urgent` is caution, and every
  ordinary workflow state is neutral. There is no separate status badge, status
  dot, or inset rail inside a card.
- Titles wrap and metadata truncates at the available width; project emoji are
  omitted. Shared styling and paging belong to the
  [Desktop design system](design-system.md).
- If any unfinished card is due today, non-due unfinished cards are hidden so urgent work dominates the overlay.
- Unfinished issues in the `Competitions` project due in the next 3 days are always shown, with their due date beside the issue id.
- Issues in the `Backlog` state with a due date in the next 3 days are also shown (including when urgent due-today filtering is active).
- Cancelled and duplicate issues are never shown.
- Recently completed cards remain visible for `LINEAR_DONE_LOOKBACK_HOURS`, fading linearly from full opacity when completed to fully transparent as the lookback window expires; the fetcher stamps each card with `completedAtEpoch` and the payload with `doneLookbackSeconds` so the renderer can compute the fade locally on every tick. Done cards are ordered most-recently-completed first, so they read newest-to-oldest top-down and left-to-right.
- Card width is fluid with a 252px minimum and no gaps. A card is at least
  104px tall and grows with its title, and a grid row is as tall as its tallest
  card. Default desktop pages have four columns and up to three rows. The
  renderer applies the same due-today visibility filter before allocating page
  slots.
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
