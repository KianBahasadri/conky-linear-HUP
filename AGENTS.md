# AGENTS.md

This project provides multi-monitor Conky desktop overlays backed by Python data fetchers and Lua/Cairo renderers.

## Rules

- Bottom-row widgets share the same visible top and bottom edges. Preserve existing widget and section heights and alignment, and fit content changes inside those bounds. Verify the rendered row together, including padding and drawing clearance.
- Do not ask for a screenshot to check how a change looks. Run `uv run python scripts/render_desktop.py` and read the PNG it writes.
- After editing anything under `conky/`, run `./scripts/start_conky_overlays.sh` so the live windows reload, then verify with `render_desktop.py`.
- Commit and push after feature changes.

## Documentation (read/write)

- **Read first:** For how this repo works, start at `docs/README.md`, then
  open only the topic files you need. Do not re-derive behavior from
  filenames alone when a doc covers it.
- **Before non-trivial changes:** Check the relevant doc so you match
  existing patterns.
- **After behavior changes:** Update the **one** topic file under `docs/`
  that owns that fact. Do not copy the same detail into AGENTS.md,
  README.md, or multiple docs.
- **Regenerate vs patch:** `docs/README.md` records the commit it was
  generated from; `git diff <sha>..HEAD --stat` shows what changed since.
  Prefer the `generate_docs` skill when docs are broadly stale or many
  topics shifted; for small, targeted edits, patch the single topic file
  (and `docs/README.md` if you add/remove a topic).
- `CLAUDE.md` is a symlink to this file.

Do not put implementation detail in this file — it lives under `docs/`.
