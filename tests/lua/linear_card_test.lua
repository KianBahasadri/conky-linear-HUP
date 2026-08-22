-- Characterization harness: pins linear-card-renderer.lua's exposed
-- height_spacer() (cache parse -> red-card filter -> grid math) as it behaves
-- today under Lua 5.4. Run via tests/test_lua_renderers.py; a nonzero exit
-- means an assertion failed.
local root = arg[1]
local cache_root = arg[2]

local shared = dofile(root .. '/conky/renderer-shared.lua')
local factory = dofile(root .. '/conky/linear-card-renderer.lua')

local failures = 0

local function eq(actual, expected, label)
  if actual ~= expected then
    print('FAIL ' .. label .. ': expected ' .. string.format('%q', tostring(expected))
      .. ', got ' .. string.format('%q', tostring(actual)))
    failures = failures + 1
  end
end

local function write_cards(json)
  os.execute('mkdir -p "' .. cache_root .. '/cache"')
  local file = io.open(cache_root .. '/cache/linear-cards.json', 'w')
  if not file then
    print('FAIL could not write ' .. cache_root .. '/cache/linear-cards.json')
    os.exit(1)
  end
  file:write(json)
  file:close()
end

local function spacer_for(json)
  write_cards(json)
  return factory(shared, cache_root).height_spacer()
end

-- Missing cache file: read_file returns nil -> empty state -> empty height.
os.remove(cache_root .. '/cache/linear-cards.json')
eq(spacer_for('{}'), '${voffset 100}', 'missing cache falls back to empty height')

local function cards_json(count, extra)
  local parts = {}
  for index = 1, count do
    table.insert(parts, string.format('{"identifier":"HUP-%d","title":"Task %d"}', index, index))
  end
  return table.concat(parts, ',') .. (extra or '')
end

-- Grid math at the default window width (1540): four cards of width 318 with
-- gap 24 fit per row; one row is top_padding + card_height + bottom_padding.
eq(spacer_for(cards_json(1)), '${voffset 138}', 'one card = one row')
eq(spacer_for(cards_json(4)), '${voffset 138}', 'four cards still one row')
eq(spacer_for(cards_json(5)), '${voffset 268}', 'five cards wrap to two rows')

-- A due-today unfinished card hides everything not due/done/backlog/competition.
local plain_five = ',' .. cards_json(5):sub(2)
eq(spacer_for('{"identifier":"R","title":"red","dueToday":true}' .. plain_five),
  '${voffset 138}', 'red card filters hidden cards from the height math')
eq(spacer_for('{"identifier":"R","title":"red","dueToday":true,"done":true}' .. plain_five),
  '${voffset 268}', 'done card does not trigger the filter')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('linear-card characterization OK')
