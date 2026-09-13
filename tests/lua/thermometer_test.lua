-- Validate the weather integration and reference geometry without Cairo in CI.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local factory = dofile(root .. '/conky/thermometer-component.lua')
local midnight, offset = 1725148800, -14400
local content, icons, labels, fills, bulbs = '', {}, {}, {}, {}
shared.read_file = function() return content end
shared.set_hex = function() end
ui.group = function(_, _, callback) callback() end
ui.path = function() end
ui.width = function(_, value, size) return utf8.len(value) * size * 0.6 end
ui.text = function(_, value) labels[#labels + 1] = value end
ui.rect = function(_, x, y, w, h) fills[#fills + 1] = {x = x, y = y, w = w, h = h} end
ui.circle = function(_, x, y, r) bulbs[#bulbs + 1] = {x = x, y = y, r = r} end
ui.icon = function(_, name, x, y, size)
  icons[#icons + 1] = {name = name, x = x, y = y, size = size}
end
for _, name in ipairs({'cairo_save', 'cairo_restore', 'cairo_translate', 'cairo_scale', 'cairo_new_path',
    'cairo_fill_preserve', 'cairo_set_line_width', 'cairo_stroke'}) do _G[name] = function() end end

local function fixture(temperature, condition, count, stale, uv, rain)
  local days = {}
  for index = 1, count or 7 do
    local date = os.date('!%Y-%m-%d', midnight - (8 - index) * 86400)
    days[#days + 1] = string.format('{"date":"%s","temperatureCelsius":21}', date)
  end
  content = string.format([[{"ok":true,"stale":%s,"uvIndex":%s,"precipitationProbability":%s,"thermometer":{
    "ok":true,"date":"%s","temperatureCelsius":%s,"previousDays":[%s],
    "condition":"%s","sunriseMinute":390,"sunsetMinute":1140,"utcOffsetSeconds":%d}}]],
    stale and 'true' or 'false', uv or 4, rain or 35, os.date('!%Y-%m-%d', midnight), temperature,
    table.concat(days, ','), condition or 'clear', offset)
end

local function at_minute(minute) return midnight - offset + minute * 60 end
local component = factory(shared, '/fixture')
assert(component.height == 232)
for _, sample in ipairs({{15, 1, 160}, {15.1, 2, 114}, {18.9, 2, 114}, {19, 3, 80},
    {23, 3, 80}, {23.1, 4, 46}, {26.9, 4, 46}, {27, 5, 12}}) do
  fixture(sample[1])
  local state = component.read(at_minute(840))
  assert(state.ok and state.level == sample[2], 'Celsius threshold boundary was misclassified')
  icons, labels, fills, bulbs = {}, {}, {}, {}
  component.draw({}, state, 0, 0)
  assert(fills[1].y == sample[3] and fills[1].h == 160 - sample[3], 'wrong quantitative tube fill')
  assert(fills[1].w == 6 and bulbs[1].r == 11, 'reference tube and bulb dimensions changed')
  assert(#labels == 4 and labels[1] == '06:30' and labels[2] == '19:00'
    and labels[3] == 'UV 4' and labels[4] == '35%',
    'details must show sun times, UV, and rain chance, with no temperature text')
end

for _, condition in ipairs({'clear', 'cloudy', 'rain', 'snow'}) do
  fixture(21, condition)
  local day = ({clear = 'sun', cloudy = 'cloud-sun', rain = 'cloud-rain', snow = 'snowflake'})[condition]
  local night = ({clear = 'moon', cloudy = 'cloud-moon', rain = 'cloud-rain', snow = 'snowflake'})[condition]
  assert(component.read(at_minute(389)).glyph == night)
  assert(component.read(at_minute(390)).glyph == day, 'sunrise must switch immediately using location time')
  assert(component.read(at_minute(1139)).glyph == day)
  assert(component.read(at_minute(1140)).glyph == night, 'sunset must switch immediately using location time')
end

for _, temperature in ipairs({'null', '1e999', 'true'}) do
  fixture(temperature)
  assert(not component.read(at_minute(840)).ok, 'invalid current readings must not look average')
end
fixture(21, 'clear', 6)
assert(not component.read(at_minute(840)).ok, 'a partial week must be unavailable')
fixture(21)
content = content:gsub('"temperatureCelsius":21}', '"temperatureCelsius":null}', 1)
assert(not component.read(at_minute(840)).ok, 'an invalid historical reading must be unavailable')
fixture(21)
assert(not component.read(at_minute(1440)).ok, 'a new local day needs a fresh complete week and sun times')
fixture(21, 'unknown')
assert(not component.read(at_minute(840)).ok, 'unknown weather must not invent clear skies')
fixture(21, 'clear', 7, true)
labels = {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(labels[#labels] == 'Stale', 'retained weather must be visibly marked stale')

for _, sample in ipairs({{0, 0, 'UV 0', '0%'}, {4.26, 35.6, 'UV 4.3', '36%'},
    {'null', 'null', 'UV —', '—'}, {-1, 101, 'UV —', '—'},
    {'true', '1e999', 'UV —', '—'}}) do
  fixture(21, 'clear', 7, false, sample[1], sample[2])
  local state = component.read(at_minute(840))
  assert(state.ok, 'unavailable optional readings must not remove the thermometer')
  labels = {}
  component.draw({}, state, 0, 0)
  assert(labels[3] == sample[3] and labels[4] == sample[4],
    'optional readings must preserve zero and distinguish unavailable values')
end

local function close(a, b) return math.abs(a - b) < 0.001 end
local function separate(a, b)
  return a.x + a.width <= b.x + 0.001 or b.x + b.width <= a.x + 0.001
    or a.y + a.height <= b.y + 0.001 or b.y + b.height <= a.y + 0.001
end
local placements = {'right-icon-above', 'left-icon-above', 'right-icon-below', 'left-icon-below', 'stack-above', 'stack-below'}
fixture(21, 'clear', 7, false, 4.2, 35)
for _, scale in ipairs({0.5, 1}) do
  for _, size in ipairs({16, 32, 64}) do
    for _, placement in ipairs(placements) do
      for mask = 0, 7 do
        local sun, uv, rain = mask % 2 == 1, math.floor(mask / 2) % 2 == 1, mask >= 4
        local variant = factory(shared, '/fixture', {scale = scale, glyph_size = size, placement = placement,
          show_sun_times = sun, show_uv_index = uv, show_rain_chance = rain})
        local state = variant.read(at_minute(840))
        local layout = variant.layout({}, state)
        local row_count = (sun and 2 or 0) + (uv and 1 or 0) + (rain and 1 or 0)
        icons, labels = {}, {}
        variant.draw({}, state, 0, 0)
        assert(#labels == row_count and #icons == row_count + 1, 'hidden rows must remove their glyphs and values')
        assert(separate(layout.tube, layout.info), 'the complete glyph-and-details stack must clear the thermometer')
        if row_count > 0 then
          assert(separate(layout.glyph, layout.details), 'the main glyph must clear the details')
          assert(close(layout.glyph.x + layout.glyph.width / 2, layout.details.x + layout.details.width / 2),
            'the weather glyph must center over the entire detail group')
        else
          assert(layout.details.height == 0 and close(layout.info.height, size * scale),
            'hiding all details must also remove their space')
        end
        if placement:sub(1, 5) == 'stack' then
          assert(close(layout.tube.x + layout.tube.width / 2, layout.info.x + layout.info.width / 2),
            'vertical layouts must center every block on one axis')
          if placement == 'stack-above' then assert(layout.info.y < layout.tube.y)
          else assert(layout.info.y > layout.tube.y) end
        else
          assert(close(layout.tube.y + layout.tube.height / 2, layout.info.y + layout.info.height / 2),
            'side layouts must recenter against the full visible stack')
          if placement:sub(1, 4) == 'left' then assert(layout.info.x < layout.tube.x)
          else assert(layout.info.x > layout.tube.x) end
        end
        for index, icon in ipairs(icons) do
          assert(icon.x >= 0 and icon.x + icon.size <= layout.width + 0.001)
          assert(icon.y >= 0 and icon.y + icon.size <= layout.height + 0.001)
          assert(icon.size == (index == 1 and size * scale or math.max(12, 16 * scale)),
            'changing weather glyph size must not resize detail glyphs')
          if index > 2 then assert(close(icon.x, icons[2].x), 'detail glyphs must share a column') end
        end
      end
    end
  end
end

local hidden = factory(shared, '/fixture', {show_sun_times = false, show_uv_index = false, show_rain_chance = false})
assert(hidden.read(at_minute(389)).glyph == 'moon' and hidden.read(at_minute(390)).glyph == 'sun',
  'hidden sun times must still control the day/night glyph')
fixture(21, 'clear', 7, false, 0, 0)
assert(hidden.read(at_minute(840)).uv_index == 0 and hidden.read(at_minute(840)).rain_chance_percent == 0,
  'hidden values must stay current')
for _, option in ipairs({'show_sun_times', 'show_uv_index', 'show_rain_chance'}) do
  assert(not pcall(factory, shared, '/fixture', {[option] = 0}), 'visibility options must require booleans')
end
assert(not pcall(factory, shared, '/fixture', {placement = 'close-right'}), 'retired layouts must not be accepted')

print('thermometer component: ok')
