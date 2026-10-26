-- Validate the weather integration and reference geometry without Cairo in CI.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local factory = dofile(root .. '/conky/thermometer-component.lua')
local midnight, offset = 1725148800, -14400
local content, icons, labels, fills, bulbs, text_colors = '', {}, {}, {}, {}, {}
shared.read_file = function() return content end
shared.set_hex = function() end
ui.group = function(_, _, callback) callback() end
ui.path = function() end
ui.width = function(_, value, size) return utf8.len(value) * size * 0.6 end
ui.text = function(_, value, x, y, opts)
  labels[#labels + 1] = tostring(value)
  text_colors[#text_colors + 1] = opts and opts.color
end
ui.rect = function(_, x, y, w, h, color) fills[#fills + 1] = {x = x, y = y, w = w, h = h, color = color} end
ui.circle = function(_, x, y, r, color) bulbs[#bulbs + 1] = {x = x, y = y, r = r, color = color} end
ui.icon = function(_, name, x, y, size, color)
  icons[#icons + 1] = {name = name, x = x, y = y, size = size, color = color}
end
for _, name in ipairs({'cairo_save', 'cairo_restore', 'cairo_translate', 'cairo_scale', 'cairo_new_path',
    'cairo_fill_preserve', 'cairo_set_line_width', 'cairo_stroke'}) do _G[name] = function() end end

local function fixture(temperature, condition, count, stale, uv, rain, danger, aqi, wind_speed, wind_unit)
  local days = {}
  for index = 1, count or 7 do
    local date = os.date('!%Y-%m-%d', midnight - (8 - index) * 86400)
    days[#days + 1] = string.format('{"date":"%s","temperatureCelsius":21}', date)
  end
  local extra = ''
  if aqi ~= nil then extra = extra .. string.format(',"aqi":%s', aqi) end
  if wind_speed ~= nil then extra = extra .. string.format(',"windSpeed":%s', wind_speed) end
  if wind_unit ~= nil then extra = extra .. string.format(',"windUnit":"%s"', wind_unit) end
  content = string.format([[{"ok":true,"stale":%s,"uvIndex":%s,"precipitationProbability":%s%s,"thermometer":{
    "ok":true,"date":"%s","temperatureCelsius":%s,"previousDays":[%s],
    "condition":"%s","danger":%s,"sunriseMinute":390,"sunsetMinute":1140,"utcOffsetSeconds":%d}}]],
    stale and 'true' or 'false', uv or 4, rain or 35, extra, os.date('!%Y-%m-%d', midnight), temperature,
    table.concat(days, ','), condition or 'clear', danger and 'true' or 'false', offset)
end

local function at_minute(minute) return midnight - offset + minute * 60 end
local component = factory(shared, '/fixture')
assert(component.height == 232)
for _, sample in ipairs({{15, 1, 160, ui.muted}, {15.1, 2, 114, ui.muted}, {18.9, 2, 114, ui.muted},
    {19, 3, 80, ui.muted}, {23, 3, 80, ui.muted}, {23.1, 4, 46, ui.caution},
    {26.9, 4, 46, ui.caution}, {27, 5, 12, ui.caution}}) do
  fixture(sample[1])
  local state = component.read(at_minute(840))
  assert(state.ok and state.level == sample[2] and not state.danger,
    'Celsius threshold boundary was misclassified')
  icons, labels, fills, bulbs = {}, {}, {}, {}
  component.draw({}, state, 0, 0)
  assert(fills[1].y == sample[3] and fills[1].h == 160 - sample[3], 'wrong quantitative tube fill')
  assert(fills[1].w == 6 and bulbs[1].r == 11, 'reference tube and bulb dimensions changed')
  assert(fills[1].color == sample[4] and bulbs[1].color == sample[4],
    'tube fill must be muted below three-quarter and caution at three-quarter or full')
  assert(icons[1].name ~= 'triangle-alert' and icons[1].color == ui.muted,
    'safe weather must keep the muted condition glyph')
  assert(#labels == 4 and labels[1] == '6:30 AM' and labels[2] == '7:00 PM'
    and labels[3] == 'UV 4' and labels[4] == '35%',
    'details must show sun times, UV, and rain chance, with no temperature text')
end

fixture(21, 'rain', 7, false, 4, 35, true)
local alert = component.read(at_minute(840))
assert(alert.ok and alert.danger and alert.glyph == 'triangle-alert',
  'dangerous conditions must replace the weather glyph with a danger icon')
icons, fills, bulbs = {}, {}, {}
component.draw({}, alert, 0, 0)
assert(icons[1].name == 'triangle-alert' and icons[1].color == ui.danger,
  'danger glyph must be red')
assert(fills[1].color == ui.danger and bulbs[1].color == ui.danger,
  'danger must override tube color with red')

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

-- 0% rain, barely anything UV (<1), and unavailable values are omitted
for _, sample in ipairs({{0, 0}, {'null', 'null'}, {-1, 101}, {'true', '1e999'}}) do
  fixture(21, 'clear', 7, false, sample[1], sample[2])
  local state = component.read(at_minute(840))
  assert(state.ok, 'unavailable optional readings must not remove the thermometer')
  labels = {}
  component.draw({}, state, 0, 0)
  assert(#labels == 2 and labels[1] == '6:30 AM' and labels[2] == '7:00 PM',
    'zero and unavailable optional readings must be omitted')
end

-- Notable UV: muted for 1-2.9, caution (yellow) for 3-7.9, danger (red) for >=8
fixture(21, 'clear', 7, false, 2.0, 0)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == 'UV 2' and text_colors[3] == ui.muted and icons[4].color == ui.muted,
  'low notable UV must be muted')

fixture(21, 'clear', 7, false, 4.26, 0)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == 'UV 4.3' and text_colors[3] == ui.caution and icons[4].color == ui.caution,
  'moderate UV must be caution yellow')

fixture(21, 'clear', 7, false, 8.5, 0)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == 'UV 8.5' and text_colors[3] == ui.danger and icons[4].color == ui.danger,
  'dangerous UV must be danger red')

-- Notable Rain: muted for 1-49%, caution (yellow) for >=50%
fixture(21, 'clear', 7, false, 0, 35.6)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == '36%' and text_colors[3] == ui.muted and icons[4].color == ui.muted,
  'moderate rain chance must be muted')

fixture(21, 'clear', 7, false, 0, 65)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == '65%' and text_colors[3] == ui.caution and icons[4].color == ui.caution,
  'rain >=50% must turn caution yellow')

-- Air Quality: omitted when fine (<=50), caution (yellow) for 51-100, danger (red) for >100
fixture(21, 'clear', 7, false, 0, 0, false, 45)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 2, 'good air quality must be omitted')

fixture(21, 'clear', 7, false, 0, 0, false, 75)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == 'AQI 75' and text_colors[3] == ui.caution and icons[4].name == 'haze' and icons[4].color == ui.caution,
  'moderate AQI must be caution yellow with haze icon')

fixture(21, 'clear', 7, false, 0, 0, false, 150)
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == 'AQI 150' and text_colors[3] == ui.danger and icons[4].name == 'haze' and icons[4].color == ui.danger,
  'unhealthy AQI must be danger red')

-- Wind Speed: omitted when calm (<12 km/h / <8 mph), muted for 12-29, caution for 30-49, danger for >=50
fixture(21, 'clear', 7, false, 0, 0, false, nil, 8, 'km/h')
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 2, 'light wind under 12 km/h must be omitted')

fixture(21, 'clear', 7, false, 0, 0, false, nil, 15, 'km/h')
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == '15 km/h' and text_colors[3] == ui.muted and icons[4].name == 'wind' and icons[4].color == ui.muted,
  'notable wind must show with wind icon in muted color')

fixture(21, 'clear', 7, false, 0, 0, false, nil, 35, 'km/h')
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == '35 km/h' and text_colors[3] == ui.caution and icons[4].color == ui.caution,
  'strong wind >=30 km/h must be caution yellow')

fixture(21, 'clear', 7, false, 0, 0, false, nil, 55, 'km/h')
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == '55 km/h' and text_colors[3] == ui.danger and icons[4].color == ui.danger,
  'severe wind >=50 km/h must be danger red')

fixture(21, 'clear', 7, false, 0, 0, false, nil, 6, 'mph')
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 2, 'light wind under 8 mph must be omitted')

fixture(21, 'clear', 7, false, 0, 0, false, nil, 14, 'mph')
labels, text_colors, icons = {}, {}, {}
component.draw({}, component.read(at_minute(840)), 0, 0)
assert(#labels == 3 and labels[3] == '14 mph' and text_colors[3] == ui.muted,
  'mph wind must be supported')

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
for _, option in ipairs({'show_sun_times', 'show_uv_index', 'show_rain_chance', 'show_air_quality', 'show_wind_speed'}) do
  assert(not pcall(factory, shared, '/fixture', {[option] = 0}), 'visibility options must require booleans')
end
assert(not pcall(factory, shared, '/fixture', {placement = 'close-right'}), 'retired layouts must not be accepted')

print('thermometer component: ok')
