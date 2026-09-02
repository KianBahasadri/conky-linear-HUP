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

local function sessions_payload(repos)
  local records = {}
  for index, repo in ipairs(repos) do
    table.insert(records, string.format(
      '{"name":"session-%d","windows":1,"panes":1,"path":"~/repo-%d","repo":"%s","attached":"","idle":"0s","idleSeconds":0}',
      index, index, repo
    ))
  end
  return '{"ok":true,"devices":[],"sessions":[' .. table.concat(records, ',') .. ']}'
end

-- Three destination rows fit the base height; a fourth grows by one 110px row.
eq(spacer_for(sessions_payload({'a','b','c','d','e','f','g','h','i'})),
  '${voffset 798}', 'nine independent sessions fit three rows')
eq(spacer_for(sessions_payload({'a','b','c','d','e','f','g','h','i','j'})),
  '${voffset 908}', 'ten independent sessions grow to four rows')

-- Same-repo pairs stay together.  Four pairs each start a fresh row because a
-- two-item group cannot fit the previous row's one remaining slot.
eq(spacer_for(sessions_payload({'a','a','b','b','c','c','d','d'})),
  '${voffset 908}', 'same-repo groups share one packing calculation')

eq(spacer_for('{"ok":true,"devices":[],"sessions":[{"name":"broken}]}'),
  '${voffset 798}', 'malformed cache degrades to the minimum height')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('sessions-layout characterization OK')
