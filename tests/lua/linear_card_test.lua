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
eq(factory(shared, cache_root).height_spacer(), '${voffset 50}',
  'missing cache falls back to empty height')
eq(spacer_for('{}'), '${voffset 50}', 'empty payload falls back to empty height')

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
eq(spacer_for(cards_json(1)), '${voffset 50}', 'one card = one row')
eq(spacer_for(cards_json(4)), '${voffset 50}', 'four cards still one row')
eq(spacer_for(cards_json(5)), '${voffset 100}', 'five cards wrap to two rows')
eq(spacer_for(cards_json(6)), '${voffset 100}', 'six cards wrap to two rows')

-- A due-today unfinished card hides everything not due/done/backlog/competition.
local plain_six = card_objects(6)
table.insert(plain_six, 1, '{"identifier":"R","title":"red","dueToday":true}')
eq(spacer_for('{"cards":[' .. table.concat(plain_six, ',') .. ']}'),
  '${voffset 50}', 'red card filters hidden cards from the height math')
plain_six[1] = '{"identifier":"R","title":"red","dueToday":true,"done":true}'
eq(spacer_for('{"cards":[' .. table.concat(plain_six, ',') .. ']}'),
  '${voffset 100}', 'done card does not trigger the filter')

-- Structural characters and nested arrays inside strings/objects must not
-- truncate a card before its state flags are read.
eq(spacer_for([[{"cards":[
  {"identifier":"R","title":"close } [ bracket","metadata":{"nested":[1,2]},"dueToday":true},
  {"identifier":"HUP-2","title":"hidden"}
]}]]), '${voffset 50}', 'nested JSON and braces in title preserve due-today filter')

eq(spacer_for('{"cards":[{"identifier":"broken","title":"unterminated}]}'),
  '${voffset 50}', 'malformed cache degrades to an empty panel')

write_cards('{"cards":[{"identifier":"HUP-1","title":"Task with emoji","projectName":"Clusterfork","projectIcon":"🌀"}]}')
local parsed = factory(shared, cache_root).read_cards()
eq(#parsed.cards, 1, 'one card parsed')
eq(parsed.cards[1].project_name, 'Clusterfork', 'card retains project name')
eq(parsed.cards[1].project_icon, '🌀', 'card retains project icon')

-- Title font stepping and truncation:
-- Titles start at 15px and do not wrap: if a title overflows one line, try
-- 14px, then 13px. If 13px still overflows, truncate on line 1 with ellipsis.
local current_font_size = 15
cairo_text_extents_t = cairo_text_extents_t or { create = function() return {} end }
cairo_set_font_size = function(_cr, size) current_font_size = size end
cairo_select_font_face = function() end
cairo_text_extents = function(_cr, value, extents)
  extents.width = #value * current_font_size
end

local linear_inst = factory(shared, cache_root)
local card_width = 224 -- 200px text width after 24px margins

local r_short = linear_inst.title_layout({}, {title = 'Short title'}, card_width)
eq(r_short.size, 15, 'short title stays at 15px')
eq(#r_short.lines, 1, 'short title has 1 line')

local r15 = linear_inst.title_layout({}, {title = '123456 abcdef'}, card_width)
eq(r15.size, 15, 'title fitting at 15px stays at 15px')
eq(#r15.lines, 1, 'title fitting at 15px has 1 line')

local r14 = linear_inst.title_layout({}, {title = '123456 abcdefg'}, card_width)
eq(r14.size, 14, 'title overflowing 15px steps down to 14px')
eq(#r14.lines, 1, 'title stepped down to 14px fits in 1 line')

local r13 = linear_inst.title_layout({}, {title = '123456 abcdefgh'}, card_width)
eq(r13.size, 13, 'title overflowing 14px steps down to 13px')
eq(#r13.lines, 1, 'title stepped down to 13px fits in 1 line')

local rover = linear_inst.title_layout({}, {title = '123456 abcdefghi'}, card_width)
eq(rover.size, 13, 'title overflowing 13px stays at 13px')
eq(#rover.lines, 1, 'title overflowing 13px does not wrap to line 2')
eq(rover.lines[1]:sub(-3), '...', 'title overflowing 13px is truncated with ellipsis')

-- Contrast follows progress: In Progress titles stay bright; other titles become muted.
eq(linear_inst.title_color({state = 'In Progress', done = false}), shared.ui.ink,
  'in-progress title is bright')
eq(linear_inst.title_color({state = 'Todo', done = false}), shared.ui.muted,
  'todo title is muted')
eq(linear_inst.title_color({state = 'Backlog', done = false}), shared.ui.muted,
  'backlog title is muted')
eq(linear_inst.title_color({state = 'Done', done = true}), shared.ui.muted,
  'done title is muted')
eq(linear_inst.title_color({state = 'In Progress', done = true}), shared.ui.muted,
  'completed in-progress task title is muted')

-- Upstairs describe behavior:
-- In Progress, Todo, and Done labels are dropped.
-- Nonessential labels (e.g. Bug) are dropped.
-- Deadlines move upstairs. Urgency states remain.
local s, t = linear_inst.describe({state = 'In Progress', due_date = ''})
eq(s, '', 'in-progress without deadline has no state text')
eq(t, 'neutral', 'in-progress has neutral tone')

local s2, t2 = linear_inst.describe({state = 'Todo', label = 'Bug', due_date = ''})
eq(s2, '', 'todo without deadline has no state text and drops label')
eq(t2, 'neutral', 'todo has neutral tone')

local s3, t3 = linear_inst.describe({state = 'In Progress', due_date = 'Sep 08'})
eq(s3, 'Due Sep 08', 'in-progress with deadline shows deadline upstairs')
eq(t3, 'neutral', 'in-progress with deadline has neutral tone')

local s4, t4 = linear_inst.describe({state = 'Todo', label = 'Bug', due_date = 'Sep 10'})
eq(s4, 'Due Sep 10', 'todo with deadline shows deadline upstairs and drops label')

local s5, t5 = linear_inst.describe({urgent = true, due_date = 'Sep 08'})
eq(s5, 'Urgent · Due Sep 08', 'urgent card with deadline shows both')
eq(t5, 'caution', 'urgent card has caution tone')

local s6, t6 = linear_inst.describe({urgent = true, due_date = ''})
eq(s6, 'Urgent', 'urgent card without deadline shows Urgent')
eq(t6, 'caution', 'urgent card without deadline has caution tone')

local s7, t7 = linear_inst.describe({due_today = true, due_date = 'Sep 06'})
eq(s7, 'Due today', 'due today card shows Due today')
eq(t7, 'danger', 'due today card has danger tone')

local s8, t8 = linear_inst.describe({done = true, due_date = 'Sep 05'})
eq(s8, '', 'done card has no state text')
eq(t8, 'good', 'done card has good tone')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('linear-card characterization OK')
