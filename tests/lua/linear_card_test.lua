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
eq(factory(shared, cache_root).height_spacer(), '${voffset 124}',
  'missing cache falls back to empty height')
eq(spacer_for('{}'), '${voffset 124}', 'empty payload falls back to empty height')

local function card_objects(count)
  local parts = {}
  for index = 1, count do
    table.insert(parts, string.format('{"identifier":"HUP-%d","title":"Task %d"}', index, index))
  end
  return parts
end

local function cards_json(count)
  return '{"cards":[' .. table.concat(card_objects(count), ',') .. ']}'
end

-- Four columns at 1136px. The passive page holds at most three rows.
eq(spacer_for(cards_json(1)), '${voffset 124}', 'one card = one row')
eq(spacer_for(cards_json(4)), '${voffset 124}', 'four cards still one row')
eq(spacer_for(cards_json(5)), '${voffset 248}', 'five cards wrap to two rows')
eq(spacer_for(cards_json(6)), '${voffset 248}', 'six cards wrap to two rows')

-- A due-today unfinished card hides everything not due/done/backlog/competition.
local plain_six = card_objects(6)
table.insert(plain_six, 1, '{"identifier":"R","title":"red","dueToday":true}')
eq(spacer_for('{"cards":[' .. table.concat(plain_six, ',') .. ']}'),
  '${voffset 124}', 'red card filters hidden cards from the height math')
plain_six[1] = '{"identifier":"R","title":"red","dueToday":true,"done":true}'
eq(spacer_for('{"cards":[' .. table.concat(plain_six, ',') .. ']}'),
  '${voffset 248}', 'done card does not trigger the filter')

-- Structural characters and nested arrays inside strings/objects must not
-- truncate a card before its state flags are read.
eq(spacer_for([[{"cards":[
  {"identifier":"R","title":"close } [ bracket","metadata":{"nested":[1,2]},"dueToday":true},
  {"identifier":"HUP-2","title":"hidden"}
]}]]), '${voffset 124}', 'nested JSON and braces in title preserve due-today filter')

eq(spacer_for('{"cards":[{"identifier":"broken","title":"unterminated}]}'),
  '${voffset 124}', 'malformed cache degrades to an empty panel')

write_cards('{"cards":[{"identifier":"HUP-1","title":"Task with emoji","projectName":"Clusterfork","projectIcon":"🌀"}]}')
local parsed = factory(shared, cache_root).read_cards()
eq(#parsed.cards, 1, 'one card parsed')
eq(parsed.cards[1].project_name, 'Clusterfork', 'card retains project name')
eq(parsed.cards[1].project_icon, '🌀', 'card retains project icon')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('linear-card characterization OK')
