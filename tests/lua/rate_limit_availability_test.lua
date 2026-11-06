-- Availability combinations must not move any text or quota columns. Exercise
-- the actual parsers/layout and theme tokens without requiring native Cairo.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local now, original_time = 1800000000, os.time
os.time = function() return now end
local files, rows, labels = {}, {}, {}
local width, height, frame, current
local states = {
  {local_available = true}, {cloud_available = true},
  {local_available = true, cloud_available = true}, {},
  {local_available = true, cloud_available = true, age = 301},
  {local_available = true, cloud_available = true, age = -1},
  {local_available = true, legacy = true},
}
local names = {
  codex = {'sepehr', '21kb60', 'dual01', 'unknow', 'stale1', 'future', 'long-account-name'},
  cursor = {'clocal', 'ccloud', 'cboth1', 'cunknw', 'cstale', 'cfutur', 'cursor-long-name'},
}
for _, provider in ipairs({'codex', 'cursor'}) do
  for index, state in ipairs(states) do
    local row = {label = names[provider][index], provider = provider, state = state, index = index,
      id = string.rep(string.format('%x', #rows + 1), 64)}
    rows[#rows + 1], labels[row.label] = row, row
  end
end

local function populate(selected)
  for _, provider in ipairs({'codex', 'cursor'}) do
    local records = {'meta\tok\t1'}
    for _, row in ipairs(rows) do
      if row.provider == provider then
        local state = row.state
        records[#records + 1] = table.concat({'account', row.label, '', row.index == selected and '1' or '0',
          '1', '', '0', state.local_available and '1' or 'unknown', row.id,
          tostring(now - (state.age or 0)), tostring(now - 30), '300', 'fresh',
          state.legacy and '' or state.cloud_available and '1' or 'unknown'}, '\t')
        for window = 1, 2 do
          local label = provider == 'cursor' and (window == 1 and 'api' or 'included')
            or (window == 1 and '5h' or 'weekly')
          records[#records + 1] = table.concat({'bar', row.label, '', '0', label, '25', '75', '',
            tostring(now + (window == 1 and 1800 or 300000)), '1800',
            window == 1 and '18000' or '604800', row.id, provider .. '/' .. label}, '\t')
        end
      end
    end
    files[provider .. '-usage-render.tsv'] = table.concat(records, '\n')
  end
end
shared.read_file = function(path) return files[path:match('/([^/]+)$')] end
ui.draw = function(callback) ui.refresh_theme(); callback({}, width, height) end
ui.width = function(_, value, size) return #tostring(value) * (size or 13.5) * 0.6 end
ui.mark = function() return true end
ui.line_between = function() end
ui.icon = function(_, name, x, y, size, color)
  assert(name == 'monitor' or name == 'cloud', 'availability must use the Lucide computer/cloud pair')
  assert(color == ui.muted and size == 11, 'both icons must use the same theme token and size')
  frame.icons[#frame.icons + 1] = {name = name, x = x, y = y, size = size}
end
ui.text = function(cr, value, x, y, opts)
  if labels[value] then
    current = value
    assert(not frame.names[value], 'one row per stable identity')
    frame.names[value] = {x = x, y = y, width = opts.width, weight = opts.bold}
  elseif current and (value == '30m' or value == '3d 11h' or value == 'API' or value == 'Incl') then
    frame.texts[current] = frame.texts[current] or {}
    frame.texts[current][value] = x
  end
  return ui.width(cr, value, opts and opts.size)
end
ui.rect = function(_, x, y, w, h, color)
  assert(x >= 0 and y >= 0 and x + w <= width and y + h <= height, 'rows and quota bars must fit')
  if color == ui.raised then frame.selected = frame.selected + 1 end
  if color == ui.line and h == 3 then
    frame.bars[current] = frame.bars[current] or {}
    table.insert(frame.bars[current], {x = x, w = w})
  end
end
local renderer = dofile(root .. '/conky/rate-limit-panel-renderer.lua')(shared, '/fixture')
for _, theme in ipairs({'dark', 'light'}) do
  files['desktop-theme'] = theme
  for _, panel_width in ipairs({368, 608, 880, 1200, 1248, 1600}) do
    width, height = panel_width, panel_width >= 1200 and 112 or 700
    for selected = 1, #states do
      populate(selected)
      frame, current = {icons = {}, names = {}, bars = {}, texts = {}, selected = 0}, nil
      renderer.draw()
      assert(ui.theme == theme, 'exercise both real palettes')
      assert(frame.selected == 2, 'availability must not affect selection highlighting')
      local baselines, countdowns = {}, {}
      local expected_icons = 0
      for _, row in ipairs(rows) do
        local name = assert(frame.names[row.label], 'every account must remain visible')
        local col_x = width >= 1200 and row.provider == 'cursor' and math.floor(width / 2) or 0
        local col_w = width >= 1200 and math.floor(width / 2) or width
        local provider_width = col_w < 760 and 56 or 64
        assert(name.x == col_x + provider_width + 28, 'all names must share a flush left edge')
        assert(name.width >= 54, 'both icons must preserve six-character name space')
        assert((name.weight == 'medium') == (row.index == selected), 'selection retains independent typography')
        if #row.label == 6 then assert(ui.width(nil, row.label, 13.5) <= name.width, 'six-character names must fit') end
        local found = {monitor = 0, cloud = 0}
        for _, icon in ipairs(frame.icons) do
          if icon.y + 10 == name.y and (icon.x + 28 == name.x or icon.x + 14 == name.x) then
            assert(icon.x + icon.size < name.x, 'icons must leave a gap before the account name')
            assert(icon.x + (icon.name == 'monitor' and 28 or 14) == name.x, 'each icon keeps its own slot')
            found[icon.name] = found[icon.name] + 1
          end
        end
        local fresh = not row.state.age
        local local_count = fresh and row.state.local_available and 1 or 0
        local cloud_count = fresh and row.state.cloud_available and 1 or 0
        assert(found.monitor == local_count and found.cloud == cloud_count,
          'local-only, cloud-only, both and unknown/stale states must be independent')
        expected_icons = expected_icons + local_count + cloud_count
        local bars = frame.bars[row.label]
        assert(#bars == 2, 'availability must never duplicate or hide quota contributions')
        local baseline = baselines[row.provider] or {bars = bars, texts = frame.texts[row.label]}
        baselines[row.provider] = baseline
        for index, bar in ipairs(bars) do
          assert(bar.x == baseline.bars[index].x and bar.w == baseline.bars[index].w,
            'availability and selection must not move quota columns')
        end
        for value, x in pairs(frame.texts[row.label]) do
          assert(x == baseline.texts[value], 'window labels and countdowns must stay aligned')
          if value == '30m' or value == '3d 11h' then
            countdowns[value] = countdowns[value] or x - col_x
            assert(math.abs(x - col_x - countdowns[value]) < 0.001, 'countdowns must align across provider groups')
          end
        end
      end
      assert(#frame.icons == expected_icons, 'unknown metadata must not introduce extra icons')
    end
  end
end
os.time = original_time
print('independent rate-limit availability and alignment OK')
