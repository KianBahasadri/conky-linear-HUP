-- Real cache parsing and row layout, with measured primitives at the Cairo seam.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local files, labels, icons, boxes = {}, {}, {}, {}
local width, height, now = 316, 800, 0
local scale, last_scale, saved_scales = 1, 1, {}
cairo_save = function() saved_scales[#saved_scales + 1] = scale end
cairo_scale = function(_, sx, sy)
  assert(sx == sy and sx > 0 and sx <= 1, 'repository scaling must preserve proportions')
  scale = scale * sx
  last_scale = scale
end
cairo_restore = function()
  scale = assert(table.remove(saved_scales), 'unbalanced Cairo restore')
end
local env = {SESSIONS_OVERLAY_ENABLED = '1', GIT_DEFAULT_BRANCHES = 'main,master'}
local getenv = os.getenv
os.getenv = function(key) return env[key] or getenv(key) end
os.time = function() return now end
shared.read_file = function(path) return files[path:match('/([^/]+)$')] end
ui.draw = function(callback) callback({}, width, height) end
ui.width = function(_, text, _, mono) return (utf8.len(tostring(text or '')) or 0) * (mono and 7.2 or 6.8) end
ui.text = function(cr, text, x, y, opts)
  opts = opts or {}
  local natural = ui.width(cr, text, opts.size, opts.mono)
  local w = math.min(natural, opts.width or natural)
  assert(w >= 0, 'negative text allocation: ' .. text)
  if opts.align == 'right' then x = x - w end
  labels[#labels + 1] = tostring(text)
  if w > 0 then boxes[#boxes + 1] = {text = text, x = x * scale, y = y * scale,
    w = w * scale, natural = natural * scale, color = opts.color} end
  return w
end
ui.icon = function(_, name, x, y, size, color)
  assert(ui.icons[name], 'icon must be vendored: ' .. name)
  icons[#icons + 1] = {name = name, color = color, x = x * scale, y = y * scale, size = size * scale}
  return true
end
ui.badge = function(cr, text, right, y)
  local w = ui.width(cr, text, 12, false) + 16
  boxes[#boxes + 1] = {text = text, x = (right - w) * scale, y = (y + 14) * scale,
    w = w * scale, natural = w * scale}
  labels[#labels + 1] = text
  return w
end
local renderer = dofile(root .. '/conky/git-status-renderer.lua')(shared, '/fixture')
local function draw()
  labels, icons, boxes = {}, {}, {}
  last_scale = 1
  renderer.draw()
  assert(scale == 1 and #saved_scales == 0, 'drawing must restore the Cairo transform before the footer')
  for i, box in ipairs(boxes) do
    assert(box.x >= -0.01 and box.x + box.w <= width + 0.01, 'horizontal overflow: ' .. box.text)
    assert(box.y <= height + 0.01, 'vertical overflow: ' .. box.text)
    for j = i + 1, #boxes do
      local other = boxes[j]
      if box.y == other.y then
        assert(box.x + box.w <= other.x + 0.01 or other.x + other.w <= box.x + 0.01,
          'overlapping text: ' .. box.text .. ' / ' .. other.text)
      end
    end
  end
  for _, mark in ipairs(icons) do
    assert(mark.y + mark.size <= height + 0.01, 'glyph must stay within the panel')
    assert(mark.x >= 0 and mark.x + mark.size <= width + 0.01, 'glyph must stay within the panel width')
    if mark.name == 'eye' or mark.name == 'eye-closed' then
      assert(mark.color == ui.muted, 'eyes must stay neutral in every state')
    end
  end
  for _, text in ipairs(labels) do
    assert(not text:lower():find('tmux', 1, true) and not text:lower():find('cv ', 1, true),
      'glyph identity must not be repeated in text: ' .. text)
  end
end
local function count(value)
  local n = 0
  for _, text in ipairs(labels) do if text == value then n = n + 1 end end
  return n
end
local function mark_count(name)
  local n = 0
  for _, mark in ipairs(icons) do if mark.name == name then n = n + 1 end end
  return n
end

files['git-status.json'] = [[{"ok":true,"repos":[
  {"name":"alpha","path":"/work/alpha","ok":true,"branch":"main","state":"clean","actions":"ok"},
  {"name":"bravo","path":"/work/bravo","ok":true,"branch":"checkpoint/extremely-long-branch-name","state":"dirty","modified":11,"untracked":1,"actions":"fail"},
  {"name":"dashboard","path":"/work/dashboard","ok":true,"branch":"main","state":"clean","actions":"ok"}]}]]
files['sessions.json'] = [[{"ok":true,"devices":[
  {"name":"laptop","glyph":"laptop","session":"edit","state":"live"},
  {"name":"phone","glyph":"phone","session":"edit","state":"live"}],"sessions":[
  {"name":"edit","repo":"alpha","path":"/work/alpha/src","windows":1,"attached":"laptop, phone","glyph":null,"idleSeconds":79,"codeviewPresent":true,"codeviewRunning":true,"codeviewIndexAgeSeconds":9400},
  {"name":"debug","repo":"alpha","path":"/work/alpha","windows":1,"attached":"laptop","idleSeconds":15},
  {"name":"dashboard","repo":"dashboard","path":"/work/dashboard","windows":0,"codeviewPresent":true,"codeviewRunning":false}]}]]
draw()
assert(last_scale == 1, 'a fitting list must keep its normal text and icon sizes')
assert(count('alpha') == 1 and count('dashboard') == 1, 'repositories must not be duplicated by sessions')
assert(mark_count('laptop-minimal') == 2 and mark_count('smartphone') == 1,
  'one glyph per session attachment, including repeats on the same host')
assert(count('2×') == 0, 'session count is the glyphs')
assert(count('15s') == 0 and count('1m') == 0, 'session idle is not drawn')
assert(mark_count('eye') == 1 and count('2h') == 0, 'running CodeView keeps its open eye without index age text')
assert(mark_count('eye-closed') == 1 and count('off') == 0, 'stopped CodeView uses a closed eye without text')
assert(count('CI failed') == 1 and count('M11  U1') == 1, 'health badges and counts must survive long branches')
for _, box in ipairs(boxes) do
  if box.text == 'M11  U1' then
    assert(box.w == box.natural, 'counts must not truncate')
    assert(box.color == ui.strong, 'counts must be in white')
  end
end
width = 248
draw()
width = 304


-- A path is authoritative even when the session repo key equals a visible
-- basename. Nested working directories still attach to their actual parent.
files['sessions.json'] = [[{"ok":true,"devices":[
  {"name":"unknown-peer","glyph":"alert","state":"alert","session":"edit"},
  {"name":"spare-host","glyph":"monitor","state":"idle","ageSeconds":480}],"sessions":[
  {"name":"edit","repo":"alpha","path":"/work/alpha","windows":1,"attached":"unknown-peer","idleSeconds":0},
  {"name":"unrelated-copy","repo":"alpha","path":"/other/alpha","windows":1,"idleSeconds":300},
  {"name":"scratch","repo":"","path":"/notes","windows":1},
  {"name":"extra-dashboard","repo":"not-in-fleet","path":"/work/not-in-fleet","windows":0,"codeviewPresent":true,"codeviewRunning":false}]}]]
draw()
assert(count('Unknown remote') == 1, 'unknown remote must remain loud even when attached')
assert(count('spare-host') == 0 and count('login 8m') == 0, 'a login without a session stays off the list')
assert(count('unrelated-copy') == 1 and count('scratch') == 1, 'orphan sessions and equal basenames must survive')
assert(count('extra-dashboard') == 1 and mark_count('eye-closed') == 1, 'dashboards outside the visible fleet must survive')
assert(count('0s') == 0 and count('5m') == 0 and count('unknown') == 0, 'session idle is not drawn')
height = 80
draw()
assert(last_scale < 1 and count('alpha') == 1 and count('bravo') == 1 and count('dashboard') == 1,
  'overflow must keep every Git repository')
assert(count('Unknown remote') == 1 and count('unrelated-copy') == 1 and count('scratch') == 1
  and count('extra-dashboard') == 1, 'overflow must also keep alerts, orphan sessions, and dashboards')
height = 800

-- A fresh session cache is consumed on every draw; no restart is required.
files['sessions.json'] = '{"ok":true,"devices":[],"sessions":[]}'
draw()
assert(mark_count('eye') == 0 and mark_count('eye-closed') == 0 and count('unrelated-copy') == 0, 'removed sessions must disappear')
files['sessions.json'] = '{"ok":false,"error":"scan failed"}'
draw()
assert(count('alpha') == 1 and count('scan failed') == 1, 'failed session data must not hide repositories or imply no sessions')
files['sessions.json'] = nil
draw()
assert(count('Waiting for the first session scan') == 1, 'missing cache must explain missing presence')
env.SESSIONS_OVERLAY_ENABLED = 'off'
draw()
assert(count('Sessions') == 0 and #icons == 0, 'disabled sessions must not read or render cached presence')
env.SESSIONS_OVERLAY_ENABLED = '1'
files['sessions.json'] = '{"ok":true,"devices":[],"sessions":[]}'

-- Every row stays on screen together, even when the list outgrows the window.
height = 60
for i = 0, 3 do
  now = i * 30
  draw()
  assert(count('alpha') == 1 and count('bravo') == 1 and count('dashboard') == 1,
    'overflow must scale the complete list without dropping or paging repositories')
  assert(last_scale < 1, 'an overflowing list must shrink to fit')
end
height, now = 800, 0
draw()
assert(last_scale == 1, 'normal sizing must return when space becomes available')

-- Reproduce the live 340px panel: five busy rows push the 14th repo to 342px.
local function fleet(busy, stale)
  local repos = {}
  for index = 1, 14 do
    local name = index == 13 and 'Chainreactor-paper' or index == 14 and 'bahasadri_cisc595' or 'repo-' .. index
    repos[index] = string.format('{"name":"%s","ok":true,"branch":"main","state":"%s","modified":%d}',
      name, index <= busy and 'dirty' or 'clean', index <= busy and 1 or 0)
  end
  files['git-status.json'] = '{"ok":true,"stale":' .. tostring(stale) .. ',"repos":[' .. table.concat(repos, ',') .. ']}'
end
height = 340
for _, busy in ipairs({0, 5, 14, 0}) do
  fleet(busy, false)
  draw()
  assert(count('Chainreactor-paper') == 1 and count('bahasadri_cisc595') == 1,
    'status changes must never hide pinned repositories at the end')
  assert((last_scale < 1) == (busy > 0), 'scale only when the list needs more room')
end
fleet(5, true)
draw()
assert(count('Stale cache') == 1 and count('bahasadri_cisc595') == 1,
  'the stale footer must coexist with the full fleet')
for _, box in ipairs(boxes) do
  if box.text ~= 'Stale cache' then assert(box.y < height - 16, 'rows must leave the stale footer clear') end
end
height = 800
files['git-status.json'] = '{"ok":false,"error":"git scan failed","repos":[]}'
files['sessions.json'] = [[{"ok":true,"devices":[],"sessions":[
  {"name":"scratch","path":"/notes","windows":1,"idleSeconds":120}]}]]
draw()
assert(count('git scan failed') == 1 and count('scratch') == 1, 'session records survive an unavailable fleet')

files['git-status.json'] = [[{"ok":true,"repos":[
  {"name":"mixed","path":"/work/mixed","ok":true,"branch":"main","state":"dirty","staged":3,"modified":5,"ahead":1,"actions":"ok"}]}]]
files['sessions.json'] = '{"ok":true,"devices":[],"sessions":[]}'
draw()
assert(count('S3') == 1 and count('M5') == 1 and count('ahead 1') == 1, 'mixed counts draw distinct runs')
for _, box in ipairs(boxes) do
  if box.text == 'S3' then assert(box.color == ui.muted, 'staged count must be muted') end
  if box.text == 'M5' then assert(box.color == ui.strong, 'modified count must be white') end
  if box.text == 'ahead 1' then assert(box.color == ui.muted, 'ahead count must be muted') end
end

width = 160
files['git-status.json'] = [[{"ok":true,"repos":[
  {"name":"mixed_wrap","path":"/work/mixed_wrap","ok":true,"branch":"feature/long-branch-name-forces-wrap","state":"dirty","staged":1,"modified":2,"untracked":3,"ahead":4,"behind":5,"stash":6,"actions":"ok"}]}]]
draw()
assert(count('M2  U3') == 1, 'wrapped dirty counts group and render')
for _, box in ipairs(boxes) do
  if box.text == 'M2  U3' then assert(box.color == ui.strong, 'wrapped dirty counts must be white') end
  if box.text == 'S1' then assert(box.color == ui.muted, 'wrapped staged count must be muted') end
end

-- Presence icons must align vertically across rows whether formed by multiple devices or device + CodeView (running or stopped)
width = 316
files['git-status.json'] = [[{"ok":true,"repos":[
  {"name":"running_cv","path":"/work/one","ok":true,"branch":"main","state":"clean"},
  {"name":"stopped_cv","path":"/work/two","ok":true,"branch":"main","state":"clean"},
  {"name":"two_devs","path":"/work/three","ok":true,"branch":"main","state":"clean"}]}]]
files['sessions.json'] = [[{"ok":true,"devices":[
  {"name":"lap1","glyph":"laptop","session":"s1","state":"live"},
  {"name":"lap2","glyph":"laptop","session":"s2","state":"live"}],"sessions":[
  {"name":"s1","repo":"running_cv","path":"/work/one","windows":1,"attached":"lap1","codeviewPresent":true,"codeviewRunning":true,"codeviewIndexAgeSeconds":120},
  {"name":"s2","repo":"stopped_cv","path":"/work/two","windows":1,"attached":"lap1","codeviewPresent":true,"codeviewRunning":false},
  {"name":"s3","repo":"two_devs","path":"/work/three","windows":1,"attached":"lap1, lap2"}]}]]
draw()
local by_y = {}
for _, mark in ipairs(icons) do
  by_y[mark.y] = by_y[mark.y] or {}
  table.insert(by_y[mark.y], mark)
end
local y_keys = {}
for y in pairs(by_y) do y_keys[#y_keys + 1] = y end
table.sort(y_keys)
assert(#y_keys == 3, 'expected three rows with presence icons')
for _, y in ipairs(y_keys) do
  local row_marks = by_y[y]
  table.sort(row_marks, function(a, b) return a.x > b.x end)
  assert(#row_marks == 2, 'each row should have 2 presence icons')
  assert(row_marks[1].x == width - 14, 'rightmost icon must align at width - 14')
  assert(row_marks[2].x == width - 34, 'second icon must align at width - 34')
end

print('merged repository presence and layout OK')

