-- Managed-account identity, availability and freshness through the real cache
-- parsers and drawing boundary. No native Cairo dependency in CI.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local now = 1800000000
local original_time = os.time
os.time = function() return now end
local files = {}
local function account(label, id, selected, available, freshness)
  return table.concat({'account', label, '', selected and '1' or '0', '1', '', '0',
    available and '1' or '0', id, tostring(now), tostring(now - 60), '300', freshness or 'fresh'}, '\t')
end
local function bar(label, id, window, used, source)
  return table.concat({'bar', label, '', '0', window, tostring(used), tostring(100 - used), '',
    tostring(now + 300000), '300060', '604800', id, source}, '\t')
end
local a, b, c, d, e = string.rep('a', 64), string.rep('b', 64), string.rep('c', 64), string.rep('d', 64), string.rep('e', 64)
files['codex-usage-render.tsv'] = table.concat({
  account('dual', a, true, true), account('alias', a, false, false),
  account('cloud', b, false, false), account('local', c, false, true),
  'account\tunknown\t\t0\t0\tNo measurement\t0',
  bar('dual', a, 'weekly', 20, 'codex/secondary'),
  bar('cloud', b, 'weekly', 40, 'codex/secondary'),
  bar('local', c, 'weekly', 60, 'codex/secondary'),
}, '\n')
files['cursor-usage-render.tsv'] = table.concat({
  account('cursor', d, false, false), account('stale', e, false, true, 'stale'),
  bar('cursor', d, 'api', 10, 'cursor/api'), bar('cursor', d, 'included', 30, 'cursor/included'),
  bar('stale', e, 'api', 99, 'cursor/api'),
}, '\n')
shared.read_file = function(path) return files[path:match('/([^/]+)$')] end
local renderer = dofile(root .. '/conky/rate-limit-panel-renderer.lua')(shared, '/fixture')
local test = renderer._test
local usage = test.read_ai_usage()
assert(#usage.accounts == 6, 'stable identities must join aliases without adding quota rows')
local rows = {}
for _, row in ipairs(usage.accounts) do rows[row.label] = row end
assert(test.account_is_local(rows.dual) and rows.dual.is_selected, 'selected local account has both independent states')
assert(test.account_is_local(rows['local']) and not rows['local'].is_selected, 'unselected local account still has availability')
assert(not test.account_is_local(rows.cloud), 'cloud-only account has no local icon')
assert(not test.account_is_local(rows.unknown), 'legacy unknown metadata cannot imply local access')
assert(#test.get_row_windows(rows.cursor) == 2, 'Cursor API and Included windows are both retained')
assert(test.get_row_windows(rows.cursor)[2].label == 'included', 'Included must never be relabeled Auto')
local pace = test.calculate_provider_average_pace(usage.accounts, 'Codex')
local expected = 40 - (604800 - 300000) / 604800 * 100
assert(math.abs(pace - expected) < 0.0001, 'each stable account contributes once at baseline unknown-tier weight')
assert(not test.account_shows_pace(usage.accounts, rows.stale), 'stale measurements do not show pace ticks')
assert(test.calculate_provider_average_pace({rows.stale}, 'Cursor') == nil, 'stale quota cannot add apparent capacity')
local reset = rows.cloud.windows[1].reset_at_epoch
rows.cloud.windows[1].reset_at_epoch = now
assert(test.account_is_stale(rows.cloud), 'an elapsed reset invalidates a still-young cached fresh reading')
rows.cloud.windows[1].reset_at_epoch = reset

local frame, current, width, height
ui.draw = function(callback) callback({}, width, height) end
ui.width = function(_, value, size) return #tostring(value) * (size or 13.5) * 0.6 end
ui.mark = function() return true end
ui.line_between = function() end
ui.icon = function(_, name, x, y, size)
  assert(name == 'monitor', 'availability draws only the existing local/computer icon')
  frame.icons[#frame.icons + 1] = {x = x, y = y, size = size}
end
ui.text = function(cr, value, x, y, opts)
  if rows[value] then
    current = value
    frame.names[value] = {x = x, y = y, width = opts.width}
  end
  assert(not tostring(value):lower():find('cloud', 1, true) or value == 'cloud', 'never add a cloud indicator')
  return ui.width(cr, value, opts and opts.size)
end
ui.rect = function(_, x, y, w, h, color)
  assert(x >= 0 and x + w <= width + 0.001 and y >= 0 and y + h <= height + 0.001, 'all shapes fit')
  if color == ui.raised then frame.selected = frame.selected + 1 end
  if color == ui.line and h == 3 then
    frame.bars[current] = frame.bars[current] or {}
    table.insert(frame.bars[current], {x=x, y=y, w=w})
  end
end
for _, panel_width in ipairs({368, 608, 880, 1248}) do
  width, height = panel_width, panel_width >= 1200 and 112 or 300
  frame = {icons={}, names={}, bars={}, selected=0}
  renderer.draw()
  assert(#frame.icons == 3, 'both selected and unselected local rows draw one icon')
  assert(frame.selected == 1, 'availability does not change selection highlighting')
  for _, label in ipairs({'dual', 'local', 'stale'}) do
    local name = frame.names[label]
    local matching = 0
    for _, icon in ipairs(frame.icons) do
      if icon.x + 14 == name.x and icon.y + 10 == name.y then
        matching = matching + 1
        assert(icon.x + icon.size <= name.x, 'icon fits beside the name')
      end
    end
    assert(matching == 1, 'one icon sits beside each locally available name')
  end
  local dual, cloud, local_row = frame.bars.dual[1], frame.bars.cloud[1], frame.bars['local'][1]
  assert(dual.x == cloud.x and cloud.x == local_row.x and dual.w == cloud.w and cloud.w == local_row.w,
    'icon and selection must not move bar or reset columns')
  assert(#frame.bars.cursor == 2, 'both supplied Cursor pools survive drawing at compact widths')
end

now = now + 301
usage = test.read_ai_usage()
for _, row in ipairs(usage.accounts) do
  assert(not test.account_is_local(row), 'cached availability expires even when fetches stop')
end
assert(test.calculate_provider_average_pace(usage.accounts, 'Codex') == nil,
  'cached fresh strings cannot extend measurement lifetime')

-- The JSON fallback must honor the same availability and measurement fields.
files['codex-usage-render.tsv'], files['cursor-usage-render.tsv'] = nil, nil
files['codex-usage.json'] = string.format([[{"ok":true,"accounts":[
  {"label":"json","accountId":"%s","localAvailable":true,"availabilityGeneratedAt":%d,
   "isSelected":false,"freshness":"fresh","observedAt":%d,"maxAgeSeconds":300,
   "windows":[{"label":"weekly","sourceName":"codex/secondary","usedPercent":23,
     "windowSeconds":604800,"resetAtEpoch":%d}]}]}]], a, now, now - 30, now + 300000)
local json_row = test.read_ai_usage().accounts[1]
assert(test.account_is_local(json_row) and not json_row.is_selected, 'JSON preserves independent availability')
assert(not test.account_is_stale(json_row), 'JSON preserves measurement time')
assert(json_row.windows[1].source_name == 'codex/secondary', 'JSON preserves quota identity')
os.time = original_time
print('managed rate-limit consumer OK')
