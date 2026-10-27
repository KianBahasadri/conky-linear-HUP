-- Exercise the rendered layout through its drawing boundary, keeping the real
-- cache parser and pagination while avoiding a Cairo dependency in CI.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local files, accounts, window_counts = {}, {}, {}
local width, height, now = 608, 532, 120000
local frame, current_account

local function add_account(provider, label, selected, windows)
  accounts[#accounts + 1] = label
  window_counts[label] = #windows
  local filename = provider .. '-usage-render.tsv'
  local rows = files[filename] or {'meta\tok\t1'}
  rows[#rows + 1] = table.concat({'account', label, 'pro', selected and '1' or '0', '1', '', '0'}, '\t')
  for _, name in ipairs(windows) do
    local seconds = name == '5h' and 18000 or name == 'monthly' and 2592000 or 604800
    rows[#rows + 1] = table.concat({
      'bar', label, 'pro', selected and '1' or '0', name,
      '35', '65', '', tostring(now + 3600), '3600', tostring(seconds),
    }, '\t')
  end
  files[filename] = rows
end

for index = 1, 8 do
  add_account('codex', 'cdx' .. index, index == 3,
    index == 3 and {'5h', 'weekly', 'reserve'} or {'5h', 'weekly'})
end
for index = 1, 3 do add_account('cursor', 'cur' .. index, index == 2, {'auto', 'api'}) end
for index = 1, 2 do
  add_account('gemini', 'gem' .. index, index == 2,
    index == 1 and {'gemini-5h', 'gemini-weekly', 'argon'} or {'gemini-5h', 'gemini-weekly'})
end
for name, rows in pairs(files) do files[name] = table.concat(rows, '\n') end

shared.read_file = function(path) return files[path:match('/([^/]+)$')] end
ui.draw = function(callback) callback({}, width, height) end
ui.width = function(_, value, size) return #tostring(value) * (size or 13.5) * 0.6 end
ui.text = function(cr, value, x, y, opts)
  value = tostring(value)
  if window_counts[value] then
    current_account = value
    frame.names[value] = (frame.names[value] or 0) + 1
  end
  if value:find(' of ', 1, true) then frame.footer = value end
  frame.labels[#frame.labels + 1] = {value = value, x = x, y = y}
  return ui.width(cr, value, opts and opts.size)
end
ui.rect = function(_, x, y, w, h, color)
  local rect = {x = x, y = y, w = w, h = h}
  assert(w > 0 and h > 0, 'rendered rectangles must have positive dimensions')
  assert(x >= 0 and y >= 0 and x + w <= width + 0.001 and y + h <= height + 0.001,
    'rendered rectangles must stay inside the panel')
  if color == ui.raised then frame.selected[#frame.selected + 1] = rect end
  if color == ui.line and h == 3 then
    assert(current_account, 'quota bars must belong to an account')
    local bars = frame.bars[current_account] or {}
    bars[#bars + 1] = rect
    frame.bars[current_account] = bars
  end
end
ui.mark = function() return true end
ui.line_between = function() end
local original_time = os.time
os.time = function() return now end
local renderer = dofile(root .. '/conky/rate-limit-panel-renderer.lua')(shared, '/fixture')

local function draw()
  frame = {names = {}, labels = {}, bars = {}, selected = {}}
  current_account = nil
  renderer.draw()
  return frame
end

local function assert_all_accounts(result)
  for _, label in ipairs(accounts) do
    assert(result.names[label] == 1, 'each account must be drawn exactly once: ' .. label)
    assert(#(result.bars[label] or {}) == window_counts[label],
      'all quota windows must remain visible: ' .. label)
  end
end

local complete = draw()
assert_all_accounts(complete)
assert(not complete.footer, '13 accounts must fit without pagination on the left monitor')
assert(#complete.selected == 3, 'selected accounts must retain their highlighted rows')
local last_bottom = 0
for _, rect in ipairs(complete.selected) do
  assert(rect.h <= 24, 'selected rows must remain compact on the left monitor')
  last_bottom = math.max(last_bottom, rect.y + rect.h)
end
assert(last_bottom == height, 'the last selected account must end at the panel bottom')
assert(complete.labels[1].y > 100, 'fitting compact content must move down inside its reserved region')
local found_reserve, found_argon = false, false
for _, label in ipairs(complete.labels) do
  if label.value == 'Reserve' then found_reserve = true end
  if label.value == 'Argon' then found_argon = true end
end
assert(found_reserve, 'the reserve pool must retain its distinguishing label')
assert(found_argon, 'the argon pool must retain its distinguishing label')
for _, bars in pairs(complete.bars) do
  for index, bar in ipairs(bars) do
    assert(bar.w >= 30, 'every horizontal quota bar needs usable width, including Reserve')
    if index > 1 then
      local previous = bars[index - 1]
      assert(bar.y == previous.y and bar.x > previous.x + previous.w,
        'horizontal quota windows must share a baseline without overlapping')
    end
  end
end

-- A manually narrower panel must use vertical space for windows, including
-- the reserve third window, without clipping any bars.
width, height = 368, 700
local stacked = draw()
assert_all_accounts(stacked)
assert(not stacked.footer, 'the tall narrow fixture must fit all accounts')
for _, bars in pairs(stacked.bars) do
  for index, bar in ipairs(bars) do
    assert(bar.w >= 100, 'stacking must leave useful bar lengths on narrower panels')
    if index > 1 then
      local previous = bars[index - 1]
      assert(bar.y >= previous.y + 16, 'each narrow quota window needs its own text baseline')
    end
  end
end
assert(stacked.selected[#stacked.selected].y + stacked.selected[#stacked.selected].h == height,
  'fitting stacked rows must also remain bottom anchored')

-- Exercise actual timed pages at both widths and prove a full rotation visits
-- every account once, while every bar remains above the footer.
for _, panel_width in ipairs({608, 368}) do
  width, height, now = panel_width, 100, 120000
  local seen_pages, seen_accounts = {}, {}
  local completed_cycle = false
  for _ = 1, #accounts + 1 do
    local page = draw()
    assert(page.footer, 'short panels must report which accounts are visible')
    if seen_pages[page.footer] then
      completed_cycle = true
      break
    end
    seen_pages[page.footer] = true
    for label, count in pairs(page.names) do
      assert(count == 1 and not seen_accounts[label], 'an account must not repeat within one page cycle')
      seen_accounts[label] = true
    end
    for _, bars in pairs(page.bars) do
      for _, bar in ipairs(bars) do
        assert(bar.y + bar.h <= height - 16, 'paged bars must leave the footer clear')
      end
    end
    now = now + 30
  end
  assert(completed_cycle, 'page rotation must complete within the account count')
  for _, label in ipairs(accounts) do assert(seen_accounts[label], 'paging must reach ' .. label) end
end

-- Wide panels keep the same band while the live cache loses or gains profiles.
-- Highlight every row so its full bounds can be checked at the drawing boundary.
for name, content in pairs(files) do
  files[name] = content:gsub('(account\t[^\t]+\t[^\t]+\t)[01]', function(prefix)
    return prefix .. '1'
  end)
end
local codex_profiles = files['codex-usage-render.tsv']
local function set_codex_count(count)
  local rows = {}
  for line in codex_profiles:gmatch('[^\n]+') do
    local index = tonumber(line:match('^%w+\tcdx(%d+)\t'))
    if not index or index <= count then rows[#rows + 1] = line end
  end
  files['codex-usage-render.tsv'] = table.concat(rows, '\n')
end

local function assert_filled_columns(result, bottoms)
  local columns = {}
  for _, rect in ipairs(result.selected) do
    local bottom = columns[rect.x] or 0
    assert(rect.y == bottom, 'wide rows must fill their column without gaps')
    assert(rect.h >= 16, 'wide rows must retain readable minimum spacing')
    columns[rect.x] = rect.y + rect.h
  end
  for x, bottom in pairs(columns) do
    assert(bottom == (bottoms and bottoms[x] or height),
      'wide columns must stay flush with their allocated top and bottom edges')
  end
end

width, height = 1248, 112
for _, count in ipairs({7, 6, 4, 0, 7}) do
  set_codex_count(count)
  local band = draw()
  assert(not band.footer, 'fitting wide profiles must not need a footer')
  assert_filled_columns(band)
  for _, label in ipairs(accounts) do
    local codex_index = tonumber(label:match('^cdx(%d+)$'))
    local expected = not codex_index or codex_index <= count
    assert(band.names[label] == (expected and 1 or nil),
      'live profile changes must be reflected exactly once: ' .. label)
    if expected then
      assert(#band.bars[label] == window_counts[label], 'wide rows must preserve every quota window')
    end
  end
end

-- An overflowing provider pages within its half of the same band, keeping the
-- other column in place and leaving the footer clear.
set_codex_count(8)
local seen_codex = {}
for _ = 1, 2 do
  local page = draw()
  assert(page.footer, 'overflowing wide columns must report the visible profiles')
  assert_filled_columns(page, {[0] = height - 16, [width / 2] = height})
  for label in pairs(page.names) do
    if label:match('^cdx') then
      assert(not seen_codex[label], 'wide pages must not repeat profiles within a cycle')
      seen_codex[label] = true
    end
  end
  for label, bars in pairs(page.bars) do
    for _, bar in ipairs(bars) do
      assert(bar.y + bar.h <= (label:match('^cdx') and height - 16 or height),
        'wide quota bars must stay above their column footer')
    end
  end
  now = now + 30
end
for index = 1, 8 do assert(seen_codex['cdx' .. index], 'wide paging must reach every profile') end

-- Removing most profiles must retain the wide layout and its full height.
files['cursor-usage-render.tsv'], files['gemini-usage-render.tsv'] = nil, nil
set_codex_count(3)
local sparse = draw()
assert(not sparse.footer, 'a sparse wide panel must fit')
assert_filled_columns(sparse)

os.time = original_time
print('rate-limit-panel responsive layout OK')
