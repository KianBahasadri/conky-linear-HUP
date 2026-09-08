-- Exercise the real cache adapters and display decisions without a Cairo
-- dependency in CI. Record semantic output at the shared drawing boundary.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local files, labels, trails, dashes, rects, lines = {}, {}, {}, {}, {}, {}
local width, height = 1136, 420
shared.read_file = function(path) return files[path:match('/([^/]+)$')] end
shared.wrap_title = function(_, value) return {value} end
ui.draw = function(callback) callback({}, width, height) end
ui.font = function() end
ui.text = function(_, value) labels[#labels + 1] = tostring(value); return #tostring(value) * 6 end
ui.width = function(_, value) return #tostring(value) * 6 end
ui.rect = function(_, x, y, w, h, color) rects[#rects + 1] = {x = x, y = y, w = w, h = h, color = color} end
ui.circle = function() end
ui.line_between = function(_, x1, y1, x2, y2, color)
  lines[#lines + 1] = {x1 = x1, y1 = y1, x2 = x2, y2 = y2, color = color}
end
ui.dash = function(_, x1, y1, x2, y2, color) dashes[#dashes + 1] = {x1 = x1, y1 = y1, x2 = x2, y2 = y2, color = color} end
ui.polygon = function() end
ui.polyline = function(_, points, color)
  trails[#trails + 1] = {points = points, color = color}
end
ui.icon = function() return true end
ui.mark = function() return true end
ui.group = function(_, alpha, callback) callback() end
ui.badge = function(_, value) labels[#labels + 1] = value; return #value * 6 + 16 end
ui.callout = function(_, label, message) labels[#labels + 1] = label .. ': ' .. message; return 36 end
ui.metric = function(_, label, value) labels[#labels + 1] = label; labels[#labels + 1] = value end
ui.reading = function(_, _, value, unit) labels[#labels + 1] = value .. (unit or '') end
local arc_gauge_calls = {}
ui.arc_gauge = function(_, icon, value, unit, x, y, width, opts)
  labels[#labels + 1] = value .. (unit or '')
  arc_gauge_calls[#arc_gauge_calls + 1] = {icon = icon, value = value, unit = unit, opts = opts}
end
ui.emoji = function(_, glyph) labels[#labels + 1] = glyph; return 12 end
local original_time = os.time
os.time = function(date) return date and original_time(date) or 120000 end

local function draw(name)
  labels, trails, dashes, rects, lines = {}, {}, {}, {}, {}
  dofile(root .. '/conky/' .. name)(shared, '/fixture').draw()
end
local function has(value)
  for _, label in ipairs(labels) do if label:find(value, 1, true) then return true end end
  return false
end

files['codex-usage-render.tsv'] = table.concat({
  'meta\tok\t1',
  'account\tcached\tplus\t1\t0\texpired\t1',
  'bar\tcached\tplus\t1\t5h\t95\t5\t\t119999\t0\t18000',
  'bar\tcached\tplus\t1\tweekly\t42\t58\t\t130000\t10000\t604800',
}, '\n')
draw('rate-limit-panel-renderer.lua')
assert(has('Refresh'), 'expired reset must request refresh')
assert(has('2h') and has('46m'), 'unexpired cached quota must remain visible')
assert(not has('95%'), 'expired quota must not remain a usable reading')
files['codex-usage-render.tsv'] = 'meta\tok\t0\naccount\tbroken\tplus\t0\t0\tUnauthorized\t0'
draw('rate-limit-panel-renderer.lua')
assert(has('Retrying: Unauthorized'), 'failed account must not disappear')

files['github-contributions.json'] = [[{"ok":true,"contributions":[
  {"date":"2026-09-01","level":2}]}]]
draw('github-tracker-renderer.lua')
assert(#labels == 0, 'the github tracker must stay free of text')

-- The map itself stays free of text.
files['billing-usage-render.tsv'] = table.concat({
  'meta\tok\t1\tday\t5\tdaysInMonth\t30\telapsedFraction\t0.1667',
  'provider\taws\tAWS\tffffff\tmetered\t1\t0\t0.3\t1.7\t1\tcache\t$3 now / $10 cap',
  'history\taws\t1\t0.1',
  'history\taws\t3\t0.2',
}, '\n')
draw('billing-renderer.lua')
assert(not has('AWS') and not has('Forecast over limit'), 'the budget map must stay free of provider summary text')
for _, trail in ipairs(trails) do
  assert(trail.color ~= ui.accent or #trail.points < 2,
    'observed history must not bridge missing calendar days')
end

local billing_mod = dofile(root .. '/conky/billing-renderer.lua')(shared, '/fixture')
local test_prep = billing_mod._test.prepare
local model_sub = test_prep({elapsed = 0.2, day = 6, days_in_month = 30, providers = {
  {id = 'aws', code = 'AWS', ok = true, stale = false, current_pressure = 0.3, forecast_pressure = 0.5, forecast_available = true, history = {}}
}})
assert(model_sub.maximum == 100, 'under-limit providers keep baseline 100 scale')

local model_mod = test_prep({elapsed = 0.2, day = 6, days_in_month = 30, providers = {
  {id = 'aws', code = 'AWS', ok = true, stale = false, current_pressure = 0.3, forecast_pressure = 1.6, forecast_available = true, history = {}}
}})
assert(model_mod.maximum == 160, 'overage expands scale to largest supplied percentage')

local model_high = test_prep({elapsed = 0.2, day = 6, days_in_month = 30, providers = {
  {id = 'bsm', code = 'BSM', ok = true, stale = false, current_pressure = 0.5, forecast_pressure = 3.9, forecast_available = true, history = {}}
}})
assert(model_high.maximum == 390, 'overage expands scale without capping at 200%')

files['billing-usage-render.tsv'] = table.concat({
  'meta\tok\t1\tday\t6\tdaysInMonth\t30\telapsedFraction\t0.2',
  'provider\tbsm\tBSM\tffffff\tallowance\t1\t0\t0.5\t3.9\t1\tblacksmith\t$5 now',
}, '\n')
draw('billing-renderer.lua')
local found_endpoint = false
local far_edge
for _, line in ipairs(lines) do
  if (line.color == ui.line or line.color == ui.danger) and line.y1 == line.y2 and (not far_edge or line.y1 < far_edge.y1) then
    far_edge = line
  end
end
assert(far_edge, 'the maximum-usage edge must be horizontal')
for _, rect in ipairs(rects) do
  if rect.color == ui.danger then
    found_endpoint = true
    assert(math.abs(rect.y + 3.5 - far_edge.y1) < 0.001, 'trajectory must end on the maximum-usage edge')
    assert(math.abs(rect.x + 3.5 - far_edge.x2) < 0.001,
      'trajectory must reach the month-end corner')
  end
end
assert(found_endpoint, 'forecast overage endpoint marker must be drawn')

local model_caution = test_prep({elapsed = 0.2, day = 6, days_in_month = 30, providers = {
  {id = 'aws', code = 'AWS', ok = true, stale = false, current_pressure = 0.1, forecast_pressure = 0.75, forecast_available = true, history = {}}
}})
assert(model_caution.items[1].severity == 'caution', 'forecast at 75% triggers caution')

files['billing-usage-render.tsv'] = table.concat({
  'meta\tok\t1\tday\t6\tdaysInMonth\t30\telapsedFraction\t0.2',
  'provider\taws\tAWS\tffffff\tmetered\t1\t0\t0.1\t0.45\t1\taws\t$1 now',
}, '\n')
draw('billing-renderer.lua')
assert(#rects == 0, 'trajectories under 50% usage omit the forecast endpoint')
local has_forecast_connector = false
for _, dash in ipairs(dashes) do
  if dash.color == ui.derived then has_forecast_connector = true end
end
assert(not has_forecast_connector, 'trajectories under 50% usage omit the predicted line')

files['weather-status.json'] = [[{"ok":true,"temperature":16,"aqi":23}]]
files['workouts-status.json'] = [[{"ok":true,"weekRuns":4,"lastDistanceText":"2.6 km","weekDistanceText":"12.5 km"}]]
height = 200
draw('weather-renderer.lua')
assert(has('AQI') and has('1/2'), 'compact weather page must remain bounded and labeled')
assert(not has('12.5 km'), 'compact pages must not overlap')
os.time = function(date) return date and original_time(date) or 120030 end
draw('weather-renderer.lua')
assert(has('12.5 km') and has('2/2'), 'compact training page must expose workout data')
assert(not has('AQI'), 'compact pages must not overlap')

-- A settled repository must collapse to its name: no badge, and no branch
-- unless it sits somewhere other than the default. Anything unsettled keeps
-- its badge, and the badge names the worst thing true of the repository.
files['git-status.json'] = [[{"ok":true,"stale":false,"repos":[
  {"name":"alpha","ok":true,"branch":"main","state":"clean","actions":"ok"},
  {"name":"bravo","ok":true,"branch":"release/2.4","state":"clean","actions":"ok"},
  {"name":"charlie","ok":true,"branch":"main","state":"dirty","actions":"ok","modified":2},
  {"name":"delta","ok":true,"branch":"main","state":"dirty","actions":"fail","modified":1},
  {"name":"echo","ok":true,"branch":"main","state":"conflict","actions":"ok","conflicted":3},
  {"name":"foxtrot","ok":true,"branch":"main","state":"clean","actions":"run"}]}]]
height = 420
draw('git-status-renderer.lua')
assert(has('alpha') and has('bravo') and has('charlie'), 'every repository must appear')
assert(not has('Passed'), 'a passing run must not put a badge on a settled repository')
assert(not has('Clean'), 'a settled repository must not spend a line saying so')
assert(has('release/2.4'), 'an off-default branch is the reason to read a settled line')
assert(has('Dirty') and has('M2'), 'an unsettled repository keeps its badge and counts')
assert(has('CI failed'), 'a failed run outranks the working tree it was run against')
assert(has('Conflicts'), 'a conflict outranks every other state')
assert(has('CI running'), 'a clean repository with a live run is not settled')
files['git-status.json'] = '{"ok":false,"stale":false,"error":"gh timed out","repos":[]}'
draw('git-status-renderer.lua')
assert(has('Unavailable') and has('gh timed out'), 'an empty fleet must explain itself')

files['linear-cards.json'] = [[{"cards":[
  {"identifier":"KIAN-100","title":"Ship emoji","projectName":"Clusterfork","projectIcon":"🌀","state":"In Progress"},
  {"identifier":"KIAN-101","title":"No icon","projectName":"Plain Project","projectIcon":"","state":"Todo"},
  {"identifier":"KIAN-102","title":"Fix crash","projectName":"WidgetProj","label":"Bug","dueDate":"Sep 09","state":"In Progress"},
  {"identifier":"KIAN-103","title":"Urgent task","projectName":"UrgProj","dueDate":"Sep 10","urgent":true}
]}]]
draw('linear-card-renderer.lua')
assert(has('Clusterfork') and has('🌀'), 'card with project emoji must render both')
assert(has('Plain Project'), 'card without emoji must render project name')
assert(has('Ship emoji') and has('KIAN-100'), 'card title and id must render')
assert(not has('In Progress'), 'in-progress state label must not render')
assert(not has('Todo'), 'todo state label must not render')
assert(not has('Bug'), 'nonessential labels must not render')
assert(has('Due Sep 09'), 'deadlines must render upstairs')
assert(has('Urgent · Due Sep 10'), 'urgent cards with deadlines must render both upstairs')
assert(has('KIAN-102') and has('KIAN-103'), 'all issue identifiers must render')

files['stat'] = 'cpu  1000 200 300 4000 50 10 20 0\n'
files['meminfo'] = 'MemTotal: 16000000 kB\nMemAvailable: 8000000 kB\n'
files['route'] = 'eth0\t00000000\t0102A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n'
files['dev'] = 'eth0: 1000000 0 0 0 0 0 0 0 500000 0 0 0 0 0 0 0\n'
files['resource-net-peaks.tsv'] = '# hour_epoch rx_peak_bps tx_peak_bps network_id\n119999 5000000 1000000 eth0@192.168.2.1\n'
draw('resource-monitor-renderer.lua')
assert(has('50%'), 'memory percentage must render')

-- Test resource monitor peak hold and slowed decay
local res_mod = dofile(root .. '/conky/resource-monitor-renderer.lua')(shared, '/fixture')
arc_gauge_calls = {}
os.time = function() return 1000 end
files['meminfo'] = 'MemTotal: 100000 kB\nMemAvailable: 20000 kB\n' -- 80% RAM
res_mod.draw()
local ram_peak_1 = res_mod._test.peaks['ram']
assert(ram_peak_1 == 80, 'initial peak equals reading: ' .. tostring(ram_peak_1))
assert(arc_gauge_calls[2].opts.peak == 80 and arc_gauge_calls[2].opts.peak_hold == true, 'passes peak and peak_hold')

-- 10 seconds later, reading drops to 40%.
-- Decay is 0.05% (0.0005) of max (100) per second = 0.05 / sec.
-- In 10 seconds, decay is 0.5. Peak should be 80 - 0.5 = 79.5%.
os.time = function() return 1010 end
files['meminfo'] = 'MemTotal: 100000 kB\nMemAvailable: 60000 kB\n' -- 40% RAM
res_mod.draw()
local ram_peak_2 = res_mod._test.peaks['ram']
assert(math.abs(ram_peak_2 - 79.5) < 0.01, 'decayed peak after 10s should be 79.5%: ' .. tostring(ram_peak_2))

-- 2 seconds later, reading spikes to 90%. Peak should immediately push up to 90%.
os.time = function() return 1012 end
files['meminfo'] = 'MemTotal: 100000 kB\nMemAvailable: 10000 kB\n' -- 90% RAM
res_mod.draw()
local ram_peak_3 = res_mod._test.peaks['ram']
assert(ram_peak_3 == 90, 'spike immediately pushes peak to 90%: ' .. tostring(ram_peak_3))

os.time = original_time
print('renderer data and state semantics OK')
