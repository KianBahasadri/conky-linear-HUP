# Agents

Conky desktop overlays with Python fetch scripts and Lua Cairo renderers.

- Docs: [docs/README.md](docs/README.md) — single source of truth; do not duplicate doc content in README or elsewhere.
- Fetch scripts: `scripts/fetch_*.py`
- Renderers: `conky/*-renderer.lua`
- Cache output: `cache/`
- Tests: `python -m pytest tests/`
- Config template: `.env.example`

Keep changes focused. Match existing patterns in the fetcher and renderer you are editing.