-- Exercise the real cache adapters and display decisions without a Cairo
-- dependency in CI. Record semantic output at the shared drawing boundary.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local files, labels, trails = {}, {}, {}
local width, height = 1136, 420
shared.read_file = function(path) return files[path:match('/([^/]+)$')] end
shared.wrap_title = function(_, value) return {value} end
ui.draw = function(callback) callback({}, width, height) end
ui.font = function() end
ui.text = function(_, value) labels[#labels + 1] = tostring(value); return #tostring(value) * 6 end
ui.width = function(_, value) return #tostring(value) * 6 end
ui.rect = function() end
ui.circle = function() end
ui.line_between = function() end
ui.dash = function() end
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
local original_time = os.time
os.time = function(date) return date and original_time(date) or 120000 end

local function draw(name)
  labels, trails = {}, {}
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
assert(has('42%'), 'unexpired cached quota must remain visible')
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

files['weather-status.json'] = [[{"ok":true,"temperature":16,"aqi":23,"runScore":100,
  "aqiLabel":"Good","runStatus":"RUN GREAT"}]]
files['workouts-status.json'] = [[{"ok":true,"weekRuns":4,"lastDistanceText":"2.6 km","weekDistanceText":"12.5 km"}]]
height = 240
draw('weather-renderer.lua')
assert(has('AQI Good') and has('1/2'), 'compact weather page must remain bounded and labeled')
assert(not has('12.5 km'), 'compact pages must not overlap')
os.time = function(date) return date and original_time(date) or 120030 end
draw('weather-renderer.lua')
assert(has('12.5 km') and has('2/2'), 'compact training page must expose workout data')
assert(not has('AQI Good'), 'compact pages must not overlap')
os.time = original_time
print('renderer data and state semantics OK')
