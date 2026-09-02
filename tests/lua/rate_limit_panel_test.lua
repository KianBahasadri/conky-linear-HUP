-- Characterization harness for the quota panel's self-sizing cache adapters.
local root = arg[1]
local cache_root = arg[2]

local shared = dofile(root .. '/conky/renderer-shared.lua')
local factory = dofile(root .. '/conky/rate-limit-panel-renderer.lua')

local failures = 0

local function eq(actual, expected, label)
  if actual ~= expected then
    print('FAIL ' .. label .. ': expected ' .. string.format('%q', tostring(expected))
      .. ', got ' .. string.format('%q', tostring(actual)))
    failures = failures + 1
  end
end

os.execute('mkdir -p "' .. cache_root .. '/cache"')
for _, name in ipairs({
  'codex', 'claude', 'cursor', 'gemini', 'grok', 'opencode', 'commandcode',
}) do
  os.remove(cache_root .. '/cache/' .. name .. '-usage-render.tsv')
end

local json_path = cache_root .. '/cache/codex-usage.json'
local function write_json(content)
  local file = io.open(json_path, 'w')
  if not file then
    print('FAIL could not write ' .. json_path)
    os.exit(1)
  end
  file:write(content)
  file:close()
end

local function spacer_for(content)
  write_json(content)
  return factory(shared, cache_root).height_spacer()
end

os.remove(json_path)
eq(factory(shared, cache_root).height_spacer(), '${voffset 320}',
  'missing caches use the window floor')

local accounts = {}
for index = 1, 20 do
  table.insert(accounts, string.format([[
    {"ok":true,"label":"acct-%d","planType":"plus","isSelected":false,
     "note":"brace } and bracket ] stay text","windows":[
       {"label":"weekly","usedPercent":0,"remainingPercent":100,
        "resetAtEpoch":0,"resetAfterSeconds":0,"windowSeconds":604800}
     ]}]], index))
end

local current_shape = '{"ok":true,"error":"","accounts":['
  .. table.concat(accounts, ',') .. ']}'
eq(spacer_for(current_shape), '${voffset 368}',
  'current nested Codex JSON fallback sizes all accounts')

local bars = {}
for index = 1, 20 do
  table.insert(bars, string.format(
    '{"account":"acct-%d","planType":"plus","window":"weekly","usedPercent":0,"remainingPercent":100}',
    index
  ))
end
eq(spacer_for('{"ok":true,"bars":[' .. table.concat(bars, ',') .. ']}'),
  '${voffset 368}', 'legacy flattened Codex JSON fallback remains supported')

eq(spacer_for('{"ok":true,"accounts":[{"label":"unterminated}]}'),
  '${voffset 320}', 'malformed JSON cache degrades to the window floor')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('rate-limit-panel characterization OK')
