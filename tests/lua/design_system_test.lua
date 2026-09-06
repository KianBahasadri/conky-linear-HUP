-- Shared component contracts: bounded paging, severity geometry, and the
-- vector path reader every Lucide icon and provider mark depends on.
local root = arg[1]
local ui = dofile(root .. '/conky/renderer-shared.lua').ui

-- A bounded passive list must eventually expose every record, exactly once
-- per cycle, without requesting a record outside the cached dataset.
local original_time = os.time
for count = 0, 40 do
  for capacity = 1, 12 do
    local seen = {}
    local pages = math.max(1, math.ceil(count / capacity))
    for page = 0, pages - 1 do
      os.time = function() return page * 30 end
      local first, last, label = ui.page(count, capacity)
      assert(last - first + 1 <= capacity)
      assert(last <= count)
      assert((label ~= '') == (pages > 1))
      for index = first, last do
        assert(not seen[index], 'record repeated within one complete cycle')
        seen[index] = true
      end
    end
    for index = 1, count do assert(seen[index], 'record never displayed') end
  end
end

-- Rows fit the region untouched; a list that overflows gives up one row of
-- height to the footer that reports the visible range.
os.time = function() return 0 end
local first, last, label = ui.rows(4, 200, 44)
assert(first == 1 and last == 4 and label == '', 'a fitting list must not page')
local _, overflow_last, overflow_label = ui.rows(40, 200, 44)
assert(overflow_last == 4 and overflow_label ~= '', 'an overflowing list reserves its footer')
local _, footer_last = ui.rows(4, 200, 44, 0, true)
assert(footer_last == 4, 'a reserved footer must not drop a fitting record')
os.time = original_time

-- Variable-height records fit within available height and drop extras without paging.
local fits_first, fits_last, fits_label = ui.stack({26, 26, 44}, 200, 0)
assert(fits_first == 1 and fits_last == 3 and fits_label == '', 'a fitting stack must return all records')
local _, reserved_last = ui.stack({26, 26, 44}, 200, 0, true)
assert(reserved_last == 3, 'a reserved footer must not drop a fitting record')

-- Overflowing stack: drops extras, never pages or rotates.
local over_first, over_last, over_label = ui.stack({44, 44, 44, 44, 44}, 120, 0)
assert(over_first == 1 and over_last == 2 and over_label == '', 'overflowing stack must drop extras and not page')

local over_footer_first, over_footer_last = ui.stack({44, 44, 44, 44}, 100, 0, true)
assert(over_footer_first == 1 and over_footer_last == 1, 'overflowing stack with footer reserves footer space')

local tall_first, tall_last = ui.stack({200, 26}, 100, 0)
assert(tall_first == 1 and tall_last == 1, 'an oversized first record is still displayed')

-- Variable-height records pack whole rows into pages and rotate.
os.time = function() return 0 end
local pack_first, pack_last, pack_label = ui.pack({18, 18, 36, 18}, 200, 0)
assert(pack_first == 1 and pack_last == 4 and pack_label == '', 'a fitting pack must not page')
local _, page_last, page_label = ui.pack({18, 18, 36, 18, 18, 18, 18, 18, 18, 18}, 90, 0)
assert(page_last == 3 and page_label ~= '', 'an overflowing pack reserves its footer and pages whole records')
os.time = function() return 30 end
local page2_first = ui.pack({18, 18, 36, 18, 18, 18, 18, 18, 18, 18}, 90, 0)
assert(page2_first > 1, 'pack pages rotate')
os.time = original_time

assert(ui.radius('danger') == 0, 'danger shapes are square')
assert(ui.radius('caution') == 4, 'caution shapes are intermediate')
assert(ui.radius('good') == 6 and ui.radius(nil, 10) == 10, 'good shapes keep the base radius')

-- Path data is parsed once per frame for every icon and mark; a silently
-- dropped command would leave a mark half-drawn on the desktop.
local operations = {}
local point = {0, 0}
local function record(name)
  return function(_, ...)
    local args = {...}
    operations[#operations + 1] = name
    if #args >= 2 then point = {args[#args - 1], args[#args]} end
  end
end
cairo_move_to, cairo_line_to, cairo_curve_to = record('move'), record('line'), record('curve')
cairo_close_path, cairo_arc, cairo_arc_negative = record('close'), record('arc'), record('arc')
cairo_save, cairo_restore = function() end, function() end
cairo_translate, cairo_rotate, cairo_scale = function() end, function() end, function() end

local function commands(d)
  operations, point = {}, {0, 0}
  ui.path({}, d)
  return table.concat(operations, ' ')
end
assert(commands('M0 0 L10 10') == 'move line', 'absolute lines are drawn')
assert(commands('m1 1 l2 2 z') == 'move line close', 'relative commands are drawn')
assert(commands('M0 0 h5 v5') == 'move line line', 'shorthand axes become lines')
assert(commands('M0 0 C1 1 2 2 3 3 S4 4 5 5') == 'move curve curve', 'smooth curves reflect')
assert(commands('M0 0 Q1 1 2 2 T4 4') == 'move curve curve', 'quadratics become cubics')
assert(commands('M0 0 A5 5 0 0 1 10 0') == 'move arc', 'elliptical arcs are drawn')
commands('M2 2 L5 5 Z l1 1')
assert(point[1] == 3 and point[2] == 3, 'close returns to the subpath start')

for name, paths in pairs(ui.icons) do
  for _, d in ipairs(paths) do
    assert(commands(d):find('move'), 'icon ' .. name .. ' has an unreadable path')
  end
end
for name, mark in pairs(ui.marks) do
  assert(#mark.view == 4 and mark.ratio > 0, 'mark ' .. name .. ' needs a viewBox and ratio')
  for _, piece in ipairs(mark.paths) do
    assert(commands(piece.d):find('move'), 'mark ' .. name .. ' has an unreadable path')
  end
end
print('design-system components OK')
