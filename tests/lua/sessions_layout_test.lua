-- Characterization harness for sessions overlay height_spacer and layout.
local root = arg[1]
local cache_root = arg[2]

local shared = dofile(root .. '/conky/renderer-shared.lua')
local factory = dofile(root .. '/conky/sessions-renderer.lua')

local failures = 0

local function eq(actual, expected, label)
  if actual ~= expected then
    print('FAIL ' .. label .. ': expected ' .. string.format('%q', tostring(expected))
      .. ', got ' .. string.format('%q', tostring(actual)))
    failures = failures + 1
  end
end

local function write_sessions(json)
  os.execute('mkdir -p "' .. cache_root .. '/cache"')
  local file = io.open(cache_root .. '/cache/sessions.json', 'w')
  if not file then
    print('FAIL could not write ' .. cache_root .. '/cache/sessions.json')
    os.exit(1)
  end
  file:write(json)
  file:close()
end

local function spacer_for(json)
  write_sessions(json)
  return factory(shared, cache_root).height_spacer()
end

-- Empty/missing cache returns default minimum height + 8.
os.remove(cache_root .. '/cache/sessions.json')
eq(spacer_for('{}'), '${voffset 798}', 'missing cache falls back to panel_min_height + 8')

-- 1 to 3 sessions stay within the diamond zone height (790 + 8 = 798).
local single_session = '{"ok":true,"devices":[],"sessions":[{"name":"main","windows":1,"panes":1,"path":"~","repo":"main","attached":"","idle":"1m","idleSeconds":60}]}'
eq(spacer_for(single_session), '${voffset 798}', 'single session fits in base height')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('sessions-layout characterization OK')
