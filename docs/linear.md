# Linear overlay

- Card headers show only the project name, centered in the bold accent row; the issue title is centered in the main card body, and a footer row along the bottom edge carries the muted issue identifier on the left and the due date on the right.
- The project's emoji is drawn to the left of the project name and centers with it as one block, rendered from `Noto Color Emoji` because the card font has no emoji glyphs. Linear returns the icon as a shortcode (`:trophy:`) on a separate `icon` field, which `emoji_from_project_icon` resolves; projects using a built-in Linear icon (`Users`) or an unresolvable shortcode simply show no icon.
- Issue titles keep the normal font size for up to two lines; longer titles shrink slightly to fit up to three lines before truncating with an ellipsis.
- Card colors are stateful: green is recently completed, red is due today, cyan is normal active work.
- Non-red, non-green cards show their due date when one is available.
- If any unfinished card is due today, non-due unfinished cards are hidden so urgent work dominates the overlay.
- Unfinished issues in the `Competitions` project due in the next 3 days are always shown, with their due date beside the issue id.
- Issues in the `Backlog` state with a due date in the next 3 days are also shown (including when urgent due-today filtering is active).
- Cancelled and duplicate issues are never shown.
- Recently completed cards remain visible for `LINEAR_DONE_LOOKBACK_HOURS`.
- Overlay window height is computed from the card grid (rows × card size + gaps) on each Linear fetch and when overlays start, so any number of rows fits without clipping.
- Set `LINEAR_OVERLAY_ENABLED=0` to disable the Linear overlay and its refresh loop.
