-- The design-guide weather summary, adapted to a passive Cairo surface.
return function(shared, repo_root, options)
  local ui = shared.ui
  options = options or {}
  local size = options.glyph_size or 32
  local scale = options.scale or 1
  assert(type(scale) == 'number' and scale > 0 and scale < math.huge, 'Invalid weather scale')
  local placement = options.placement or 'right-icon-above'
  assert(type(size) == 'number' and size >= 16 and size <= 64, 'Invalid weather glyph size')
  local placements = {['right-icon-above'] = true, ['left-icon-above'] = true,
    ['right-icon-below'] = true, ['left-icon-below'] = true, ['stack-above'] = true, ['stack-below'] = true}
  assert(placements[placement], 'Invalid weather glyph placement')
  local function visible(name)
    local value = options[name]
    if value == nil then return true end
    assert(type(value) == 'boolean', 'Invalid weather visibility: ' .. name)
    return value
  end
  local show_sun = visible('show_sun_times')
  local show_uv = visible('show_uv_index')
  local show_rain = visible('show_rain_chance')
  local padding_x, padding_y, stack_gap = 20 * scale, 24 * scale, 12 * scale
  local text_size, detail_icon, detail_gap = math.max(11, 14 * scale), math.max(12, 16 * scale), math.max(4, 8 * scale)
  local row_height, row_gap = text_size * 1.5, math.max(4, 8 * scale)
  local count = (show_sun and 2 or 0) + (show_uv and 1 or 0) + (show_rain and 1 or 0)
  local details_height = count > 0 and count * row_height + (count - 1) * row_gap or 0
  local glyph_size, tube_width, tube_height = size * scale, 48 * scale, 184 * scale
  local info_height = glyph_size + (count > 0 and stack_gap + details_height or 0)
  local vertical = placement == 'stack-above' or placement == 'stack-below'
  local icon_above = placement == 'right-icon-above' or placement == 'left-icon-above' or placement == 'stack-above'
  local composition_height = vertical and tube_height + stack_gap + info_height or math.max(tube_height, info_height)
  local component = {height = padding_y * 2 + composition_height}
  local modes = {'Far below average', 'Below average', 'Around average', 'Above average', 'Far above average'}
  local fill_tops = {160, 114, 80, 46, 12}
  local outline = 'M30 142V16a8 8 0 0 1 16 0v126a20 20 0 1 1-16 0Z'

  local function minute(value)
    return value and value == math.floor(value) and value >= 0 and value < 1440
  end

  local function optional_number(content, key, maximum)
    local value = shared.json_number(content, key)
    if value and value >= 0 and (not maximum or value <= maximum) then return value end
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
      level = level, mode = modes[level], glyph = glyphs[condition], sunrise = sunrise, sunset = sunset,
      uv_index = optional_number(content, 'uvIndex'),
      rain_chance_percent = optional_number(content, 'precipitationProbability', 100)}
  end

  local function sun_time(value)
    if value == nil then return '—' end
    local hour = math.floor(value / 60)
    return string.format('%d:%02d %s', hour % 12 == 0 and 12 or hour % 12,
      value % 60, hour < 12 and 'AM' or 'PM')
  end

  local function detail_rows(data)
    local rows = {}
    if show_sun then
      for _, event in ipairs({{'sunrise', data.sunrise}, {'sunset', data.sunset}}) do
        rows[#rows + 1] = {icon = event[1], value = sun_time(event[2])}
      end
    end
    if show_uv then
      local value = data.uv_index and string.format('%.1f', data.uv_index):gsub('%.0$', '') or '—'
      rows[#rows + 1] = {icon = 'radiation', value = 'UV ' .. value}
    end
    if show_rain then
      rows[#rows + 1] = {icon = 'cloud-rain', value = data.rain_chance_percent
        and string.format('%d%%', math.floor(data.rain_chance_percent + 0.5)) or '—'}
    end
    return rows
  end

  function component.layout(cr, data)
    local rows, details_width = detail_rows(data), 0
    for _, row in ipairs(rows) do
      details_width = math.max(details_width, detail_icon + detail_gap + ui.width(cr, row.value, text_size, true))
    end
    local info_width = math.max(glyph_size, details_width)
    local width = vertical and math.max(tube_width, info_width) or tube_width + 16 * scale + info_width
    local tube_x, tube_y, info_x, info_y
    if vertical then
      tube_x, info_x = (width - tube_width) / 2, (width - info_width) / 2
      if placement == 'stack-above' then tube_y, info_y = info_height + stack_gap, 0
      else tube_y, info_y = 0, tube_height + stack_gap end
    else
      tube_y, info_y = (composition_height - tube_height) / 2, (composition_height - info_height) / 2
      if placement:sub(1, 4) == 'left' then tube_x, info_x = info_width + 16 * scale, 0
      else tube_x, info_x = 0, tube_width + 16 * scale end
    end
    tube_x, tube_y = padding_x + tube_x, padding_y + tube_y
    info_x, info_y = padding_x + info_x, padding_y + info_y
    return {width = padding_x * 2 + width, height = component.height, rows = rows,
      tube = {x = tube_x, y = tube_y, width = tube_width, height = tube_height},
      info = {x = info_x, y = info_y, width = info_width, height = info_height},
      glyph = {x = info_x + (info_width - glyph_size) / 2,
        y = info_y + (not icon_above and count > 0 and details_height + stack_gap or 0),
        width = glyph_size, height = glyph_size},
      details = {x = info_x + (info_width - details_width) / 2,
        y = info_y + (icon_above and count > 0 and glyph_size + stack_gap or 0),
        width = details_width, height = details_height}}
  end

  function component.draw(cr, data, x, y)
    local layout = component.layout(cr, data)
    if not data.ok then
      local lines = scale < 1 and {'Weather', 'unavailable'} or {'Weather unavailable'}
      for index, text in ipairs(lines) do
        ui.text(cr, text, x + layout.width / 2, y + component.height / 2 + (index - 1) * 14,
          {size = scale < 1 and 11 or 13.5, color = ui.muted, align = 'center'})
      end
      return
    end
    ui.group(cr, data.stale and 0.55 or 1, function()
      cairo_save(cr)
      cairo_translate(cr, x + layout.tube.x - 14 * scale, y + layout.tube.y)
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
      ui.icon(cr, data.glyph, x + layout.glyph.x, y + layout.glyph.y, glyph_size, ui.muted)
      for index, row in ipairs(layout.rows) do
        local row_x = x + layout.details.x
        local row_y = y + layout.details.y + (index - 1) * (row_height + row_gap)
        ui.icon(cr, row.icon, row_x, row_y + (row_height - detail_icon) / 2, detail_icon, ui.muted)
        ui.text(cr, row.value, row_x + detail_icon + detail_gap, row_y + row_height / 2 + text_size * 0.32,
          {size = text_size, mono = true, color = ui.muted})
      end
    end)
    if data.stale then
      ui.text(cr, 'Stale', x + layout.width / 2, y + component.height - 4,
        {size = 11, color = ui.muted, align = 'center'})
    end
  end
  return component
end
