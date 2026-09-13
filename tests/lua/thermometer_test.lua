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
ui.width = function(_, value) return #value * 8.4 end
ui.text = function(_, value) labels[#labels + 1] = value end
ui.rect = function(_, x, y, w, h) fills[#fills + 1] = {x = x, y = y, w = w, h = h} end
ui.circle = function(_, x, y, r) bulbs[#bulbs + 1] = {x = x, y = y, r = r} end
ui.icon = function(_, name, x, y, size)
  icons[#icons + 1] = {name = name, x = x, y = y, size = size}
end
for _, name in ipairs({'cairo_save', 'cairo_restore', 'cairo_translate', 'cairo_scale', 'cairo_new_path',
    'cairo_fill_preserve', 'cairo_set_line_width', 'cairo_stroke'}) do _G[name] = function() end end

local function fixture(temperature, condition, count, stale)
  local days = {}
  for index = 1, count or 7 do
    local date = os.date('!%Y-%m-%d', midnight - (8 - index) * 86400)
    days[#days + 1] = string.format('{"date":"%s","temperatureCelsius":21}', date)
  end
  content = string.format([[{"ok":true,"stale":%s,"thermometer":{
    "ok":true,"date":"%s","temperatureCelsius":%s,"previousDays":[%s],
    "condition":"%s","sunriseMinute":390,"sunsetMinute":1140,"utcOffsetSeconds":%d}}]],
    stale and 'true' or 'false', os.date('!%Y-%m-%d', midnight), temperature,
    table.concat(days, ','), condition or 'clear', offset)
end

local function at_minute(minute) return midnight - offset + minute * 60 end
local component = factory(shared, '/fixture')
assert(component.width == 160 and component.height == 338)
for _, sample in ipairs({{15, 1, 160}, {15.1, 2, 114}, {18.9, 2, 114}, {19, 3, 80},
    {23, 3, 80}, {23.1, 4, 46}, {26.9, 4, 46}, {27, 5, 12}}) do
  fixture(sample[1])
  local state = component.read(at_minute(840))
  assert(state.ok and state.level == sample[2], 'Celsius threshold boundary was misclassified')
  icons, labels, fills, bulbs = {}, {}, {}, {}
  component.draw({}, state, 0, 0)
  assert(fills[1].y == sample[3] and fills[1].h == 160 - sample[3], 'wrong quantitative tube fill')
  assert(fills[1].w == 6 and bulbs[1].r == 11, 'reference tube and bulb dimensions changed')
  assert(#labels == 2 and labels[1] == '06:30' and labels[2] == '19:00',
    'only zero-padded sun times should be visible, with no temperature text')
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

fixture(21)
for _, size in ipairs({16, 32, 64}) do
  for _, placement in ipairs({'close-right', 'close-left', 'beside-right', 'beside-left', 'above', 'below'}) do
    local variant = factory(shared, '/fixture', {glyph_size = size, placement = placement})
    icons, labels = {}, {}
    variant.draw({}, variant.read(at_minute(840)), 0, 0)
    assert(variant.height == 306 + size, 'the stage must reserve space for the glyph size')
    for _, icon in ipairs(icons) do
      assert(icon.x >= 0 and icon.x + icon.size <= variant.width)
      assert(icon.y >= 0 and icon.y + icon.size <= variant.height)
    end
    assert(icons[1].size == size and icons[2].size == 16 and icons[3].size == 16,
      'weather glyph sizing must not resize the sun-time glyphs')
    assert(icons[2].y == 24 + 192 + size + 16 + 2.5, 'placements must not move the time rows')
  end
end

print('thermometer component: ok')
