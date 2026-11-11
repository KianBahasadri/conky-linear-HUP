# Testing

```bash
uv run pytest tests/
```

The Lua characterization tests (`tests/lua/`, run by
`tests/test_lua_renderers.py`) need a Lua interpreter on PATH (`lua5.4`
preferred). Locally, the tests skip with a note when none is installed; in CI
the workflow builds Lua 5.4.8 from a pinned commit in the official `lua/lua`
repository. The noninteractive build disables Readline and uses the runner's
compiler, avoiding Ubuntu package-mirror availability as a test dependency.
