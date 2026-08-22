# Testing

```bash
uv run pytest tests/
```

The Lua characterization tests (`tests/lua/`, run by
`tests/test_lua_renderers.py`) need a Lua interpreter on PATH (`lua5.4`
preferred). Locally, the tests skip with a note when none is installed; in CI
the workflow installs `lua5.4` via apt.