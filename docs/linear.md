# Linear overlay

- Card colors are stateful: green is recently completed, red is due today, cyan is normal active work.
- Non-red, non-green cards show their due date when one is available.
- If any unfinished card is due today, non-due unfinished cards are hidden so urgent work dominates the overlay.
- Unfinished issues in the `Competitions` project due in the next 3 days are always shown, with their due date beside the issue id.
- Cancelled and duplicate issues are never shown.
- Recently completed cards remain visible for `LINEAR_DONE_LOOKBACK_HOURS`.
- Set `LINEAR_OVERLAY_ENABLED=0` to disable the Linear overlay and its refresh loop.