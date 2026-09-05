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

-- Empty/missing caches return the window floor.
os.remove(cache_root .. '/cache/sessions.json')
eq(spacer_for('{}'), '${voffset 100}', 'missing cache falls back to the window floor')

-- A single record fits the minimum list height.
local single_session = '{"ok":true,"devices":[],"sessions":[{"name":"main","windows":1,"panes":1,"path":"~","repo":"main","attached":"","idle":"1m","idleSeconds":60}]}'
eq(spacer_for(single_session), '${voffset 100}', 'single session fits in base height')

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

-- Natural height grows by one 44px row per session.
eq(spacer_for(sessions_payload({'a','b','c','d','e','f','g','h','i'})),
  '${voffset 412}', 'nine independent sessions occupy nine rows')
eq(spacer_for(sessions_payload({'a','b','c','d','e','f','g','h','i','j'})),
  '${voffset 456}', 'ten independent sessions occupy ten rows')

-- Each session remains a separate record, including same-repo pairs.
eq(spacer_for(sessions_payload({'a','a','b','b','c','c','d','d'})),
  '${voffset 368}', 'same-repo sessions remain individually visible')

eq(spacer_for('{"ok":true,"devices":[],"sessions":[{"name":"broken}]}'),
  '${voffset 100}', 'malformed cache degrades to the minimum height')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('sessions-layout characterization OK')
