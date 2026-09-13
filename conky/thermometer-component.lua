-- The design-guide weather summary, adapted to a passive Cairo surface.
return function(shared, repo_root, options)
  local ui = shared.ui
  options = options or {}
  local size = options.glyph_size or 32
  local scale = options.scale or 1
  assert(type(scale) == 'number' and scale > 0 and scale < math.huge, 'Invalid weather scale')
  local placement = options.placement or 'close-right'
  assert(type(size) == 'number' and size >= 16 and size <= 64, 'Invalid weather glyph size')
  local placements = {['close-right'] = true, ['close-left'] = true,
    ['beside-right'] = true, ['beside-left'] = true, above = true, below = true}
  assert(placements[placement], 'Invalid weather glyph placement')
  local padding, stage_height, stage_gap = 24 * scale, (192 + size) * scale, 16 * scale
  local time_size, time_icon, time_gap = math.max(11, 14 * scale), math.max(12, 16 * scale), math.max(4, 8 * scale)
  local row_height, row_gap = time_size * 1.5, math.max(4, 8 * scale)
  local component = {width = math.max(96, 160 * scale),
    height = padding * 2 + stage_height + stage_gap + row_height * 2 + row_gap}
  local modes = {'Far below average', 'Below average', 'Around average', 'Above average', 'Far above average'}
  local fill_tops = {160, 114, 80, 46, 12}
  local outline = 'M30 142V16a8 8 0 0 1 16 0v126a20 20 0 1 1-16 0Z'

  local function minute(value)
    return value and value == math.floor(value) and value >= 0 and value < 1440
  end

  function component.read(now)
    local content = shared.read_file(repo_root .. '/cache/weather-status.json')
    local data = shared.json_field(content, 'thermometer')
    local unavailable = {ok = false}
    if not shared.json_boolean(content, 'ok', false)
        or not shared.json_boolean(data, 'ok', false) then return unavailable end
    local temperature = shared.json_number(data, 'temperatureCelsius')
    local previous = shared.json_array_objects(data, 'previousDays')
    local offset = shared.json_number(data, 'utcOffsetSeconds')
    local sunrise = shared.json_number(data, 'sunriseMinute')
    local sunset = shared.json_number(data, 'sunsetMinute')
    if not temperature or #previous ~= 7 or not offset or offset ~= math.floor(offset)
        or math.abs(offset) > 86400 or not minute(sunrise) or not minute(sunset)
        or sunrise >= sunset then return unavailable end
    local local_now = (now or os.time()) + offset
    if shared.json_string(data, 'date') ~= os.date('!%Y-%m-%d', local_now) then return unavailable end
    local sum = 0
    for index, day in ipairs(previous) do
      local value = shared.json_number(day, 'temperatureCelsius')
      local expected = os.date('!%Y-%m-%d', local_now - (8 - index) * 86400)
      if not value or shared.json_string(day, 'date') ~= expected then return unavailable end
      sum = sum + value
    end
    local difference = temperature - sum / 7
    local level = difference <= -6 and 1 or difference < -2 and 2
      or difference <= 2 and 3 or difference < 6 and 4 or 5
    local clock = os.date('!*t', local_now)
    local is_day = clock.hour * 60 + clock.min >= sunrise and clock.hour * 60 + clock.min < sunset
    local condition = shared.json_string(data, 'condition')
    local glyphs = {clear = is_day and 'sun' or 'moon', cloudy = is_day and 'cloud-sun' or 'cloud-moon',
      rain = 'cloud-rain', snow = 'snowflake'}
    if not glyphs[condition] then return unavailable end
    return {ok = true, stale = shared.json_boolean(content, 'stale', false),
      level = level, mode = modes[level], glyph = glyphs[condition], sunrise = sunrise, sunset = sunset}
  end

  local function geometry()
    local width, height, tube_x, tube_y, glyph_x, glyph_y = 36 + size, 184, 0, 0, 36, 80 - size / 2
    if placement == 'close-left' then tube_x, glyph_x = size - 12, 0
    elseif placement == 'beside-right' or placement == 'beside-left' then
      width, height, glyph_y = 48 + size, math.max(184, 160 + size / 2), 160 - size / 2
      if placement == 'beside-right' then glyph_x = 48 else tube_x, glyph_x = size, 0 end
    elseif placement == 'above' or placement == 'below' then
      width, height = math.max(48, size), 192 + size
      tube_x, glyph_x = (width - 48) / 2, (width - size) / 2
      if placement == 'above' then tube_y, glyph_y = size + 4, 0 else glyph_y = 192 end
    end
    local x, y = (component.width - width * scale) / 2, padding + (stage_height - height * scale) / 2
    return x + (tube_x - 14) * scale, y + tube_y * scale, x + glyph_x * scale, y + glyph_y * scale
  end

  function component.draw(cr, data, x, y)
    if not data.ok then
      local lines = scale < 1 and {'Weather', 'unavailable'} or {'Weather unavailable'}
      for index, text in ipairs(lines) do
        ui.text(cr, text, x + component.width / 2, y + padding + stage_height / 2 + (index - 1) * 14,
          {size = scale < 1 and 11 or 13.5, color = ui.muted, align = 'center'})
      end
      return
    end
    ui.group(cr, data.stale and 0.55 or 1, function()
      local tube_x, tube_y, glyph_x, glyph_y = geometry()
      cairo_save(cr)
      cairo_translate(cr, x + tube_x, y + tube_y)
      cairo_scale(cr, scale, scale)
      cairo_new_path(cr)
      ui.path(cr, outline)
      shared.set_hex(cr, ui.raised)
      cairo_fill_preserve(cr)
      shared.set_hex(cr, ui.line_strong)
      cairo_set_line_width(cr, 1.5)
      cairo_stroke(cr)
      local fill_top = fill_tops[data.level]
      ui.rect(cr, 35, fill_top, 6, 160 - fill_top, ui.accent, 3)
      ui.circle(cr, 38, 160, 11, ui.accent)
      cairo_restore(cr)
      ui.icon(cr, data.glyph, x + glyph_x, y + glyph_y, size * scale, ui.ink)
      local row_top = y + padding + stage_height + stage_gap
      for index, event in ipairs({{'sunrise', data.sunrise}, {'sunset', data.sunset}}) do
        local time = string.format('%02d:%02d', math.floor(event[2] / 60), event[2] % 60)
        local row_x = x + (component.width - time_icon - time_gap - ui.width(cr, time, time_size, true)) / 2
        local row_y = row_top + (index - 1) * (row_height + row_gap)
        ui.icon(cr, event[1], row_x, row_y + (row_height - time_icon) / 2, time_icon, ui.muted)
        ui.text(cr, time, row_x + time_icon + time_gap, row_y + row_height / 2 + time_size * 0.32,
          {size = time_size, mono = true})
      end
    end)
    if data.stale then
      ui.text(cr, 'Stale', x + component.width / 2, y + component.height - 4,
        {size = 11, color = ui.caution, align = 'center'})
    end
  end
  return component
end
