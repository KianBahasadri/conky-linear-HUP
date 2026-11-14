"""Add per-window draw CPU timing to copied configs, then exec the real Conky."""
import json
import os
from pathlib import Path
import re
import sys

from fixtures import NOW

root = Path(os.environ["CONKY_BENCH_ROOT"])
args = sys.argv[1:]
if "-c" in args:
    config = Path(args[args.index("-c")+1])
    text = config.read_text()
    entrypoint = re.search(r"lua_load\s*=\s*'([^']+)'", text).group(1)
    hook = re.search(r"lua_draw_hook_post\s*=\s*'([^']+)'", text).group(1)
    head = int(re.search(r"xinerama_head\s*=\s*(\d+)", text).group(1))
    monitors = json.loads((root / "benchmark-data/monitors.json").read_text())
    # Xvfb has one large screen. Place logical monitor heads in that canvas.
    text = re.sub(r"(gap_x\s*=\s*)(\d+)", lambda m: m[1]+str(int(m[2])+monitors[head][2]), text)
    text = re.sub(r"(xinerama_head\s*=\s*)\d+", r"\g<1>0", text)
    text = re.sub(r"(background\s*=\s*)true", r"\g<1>false", text)
    wrapper = config.with_suffix(".timed.lua")
    wrapper.write_text(f"""
local real_time = os.time
local started = real_time()
os.time = function(t) if t then return real_time(t) end return {NOW} + real_time() - started end
dofile({json.dumps(entrypoint)})
local draw = assert(conky_{hook})
function conky_{hook}()
  local start = os.clock()
  local ok, err = pcall(draw)
  local elapsed = (os.clock() - start) * 1000
  if not ok then
    local errors = assert(io.open({json.dumps(str(root / 'cache/benchmark-errors'))}, 'a'))
    errors:write(tostring(err), '\\n'); errors:close(); error(err)
  end
  local phase_file = assert(io.open({json.dumps(str(root / 'cache/benchmark-phase'))}, 'r'))
  local phase = phase_file:read('*a'); phase_file:close()
  local times = assert(io.open({json.dumps(str(root / 'cache/benchmark-render.tsv'))}, 'a'))
  times:write({json.dumps(config.stem)}, '\\t', phase, '\\t', string.format('%.6f', elapsed), '\\n')
  times:close()
end
""")
    text = text.replace(entrypoint, str(wrapper))
    config.write_text(text)
os.execv((root / "benchmark-data/conky").read_text(), ["conky", *args])
