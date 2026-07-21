return function(shared, repo_root)
  local weather_path = repo_root .. '/cache/weather-status.json'
  local font = 'JetBrains Mono'
  local panel_width = 424
  local panel_height = 240
  local radius = 18

  local function json_string(content, key, fallback)
    local value = content:match('"' .. key .. '"%s*:%s*"(.-)"')
    if not value then
      return fallback or ''
    end
    return shared.unescape_json_string(value)
  end

  local function json_number(content, key, fallback)
    return tonumber(content:match('"' .. key .. '"%s*:%s*([%d%.%-]+)')) or fallback or 0
  end

  local function read_status()
    local content = shared.read_file(weather_path)
    if not content then
      return { ok = false, error = 'Waiting for the first weather update...' }
    end
    if content:match('"ok"%s*:%s*true') == nil then
      return { ok = false, error = json_string(content, 'error', 'Weather data unavailable') }
    end

    local best_body = content:match('"bestWindow"%s*:%s*{(.-)}') or ''
    return {
      ok = true,
      stale = content:match('"stale"%s*:%s*true') ~= nil,
      location = json_string(content, 'location', 'Local weather'),
      location_source = json_string(content, 'locationSource', ''),
      temperature = json_number(content, 'temperature'),
      temperature_unit = json_string(content, 'temperatureUnit', 'F'),
      apparent_temperature = json_number(content, 'apparentTemperature'),
      condition = json_string(content, 'condition', 'Unknown conditions'),
      weather_code = json_number(content, 'weatherCode'),
      is_day = content:match('"isDay"%s*:%s*true') ~= nil,
      aqi = json_number(content, 'aqi'),
      aqi_label = json_string(content, 'aqiLabel', 'Unknown'),
      aqi_color = json_string(content, 'aqiColor', 'f8fafc'),
      uv_index = json_number(content, 'uvIndex'),
      uv_label = json_string(content, 'uvLabel', ''),
      humidity = json_number(content, 'humidityPercent'),
      rain = json_number(content, 'precipitationProbability'),
      wind_speed = json_number(content, 'windSpeed'),
      wind_gust = json_number(content, 'windGust'),
      wind_direction = json_string(content, 'windDirection', ''),
      wind_unit = json_string(content, 'windUnit', 'mph'),
      visibility = json_number(content, 'visibility'),
      visibility_unit = json_string(content, 'visibilityUnit', 'mi'),
      sunset = json_string(content, 'sunset', '--'),
      run_score = json_number(content, 'runScore'),
      run_status = json_string(content, 'runStatus', 'WAIT'),
      run_color = json_string(content, 'runColor', 'f87171'),
      run_advice = json_string(content, 'runAdvice', 'Check conditions before heading out'),
      best_window = json_string(best_body, 'label', 'Now'),
      best_detail = json_string(best_body, 'detail', ''),
      attribution = json_string(content, 'attribution', 'Open-Meteo / CAMS'),
    }
  end

  local function draw_frame(cr, x, y, accent, secondary)
    shared.rounded_rect(cr, x + 4, y + 7, panel_width, panel_height, radius)
    shared.set_hex(cr, accent, 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, panel_width, panel_height, radius)
    shared.set_hex(cr, accent, 0.16)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, panel_width, panel_height, radius)
    shared.set_hex(cr, secondary, 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, panel_width, panel_height, radius)
    shared.set_hex(cr, '020617', 0.84)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.94)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 8, y + 8, panel_width - 16, panel_height - 16, radius - 6)
    shared.set_hex(cr, secondary, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
  end

  local function draw_chip(cr, label, x, y, width, color)
    shared.rounded_rect(cr, x, y, width, 20, 6)
    shared.set_hex(cr, '020617', 0.96)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, color, 0.84)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 11)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    shared.set_hex(cr, color, 1)
    cairo_move_to(cr, x + (width - extents.width) / 2 - extents.x_bearing, y + 15)
    cairo_show_text(cr, label)
  end

  local function draw_weather_icon(cr, x, y, status, color)
    -- Drop any leftover current point (e.g. after location text) so the first
    -- arc does not stroke a line from that point into the icon.
    cairo_new_path(cr)

    if status.is_day then
      shared.set_hex(cr, 'facc15', 0.95)
      cairo_arc(cr, x + 16, y + 15, 8, 0, math.pi * 2)
      cairo_fill(cr)
      cairo_set_line_width(cr, 2)
      for index = 0, 7 do
        local angle = index * math.pi / 4
        cairo_move_to(cr, x + 16 + math.cos(angle) * 12, y + 15 + math.sin(angle) * 12)
        cairo_line_to(cr, x + 16 + math.cos(angle) * 16, y + 15 + math.sin(angle) * 16)
      end
      cairo_stroke(cr)
    else
      -- Filled crescent: outer disc path closed by an offset inner cut.
      local cx, cy = x + 15, y + 14
      local outer_r, inner_r, cut_dx = 9.5, 8.2, 4.8
      local cos_a = (cut_dx * cut_dx + outer_r * outer_r - inner_r * inner_r) / (2 * cut_dx * outer_r)
      local cos_b = (cut_dx * cut_dx + inner_r * inner_r - outer_r * outer_r) / (2 * cut_dx * inner_r)
      local alpha = math.acos(math.max(-1, math.min(1, cos_a)))
      local beta = math.acos(math.max(-1, math.min(1, cos_b)))
      shared.set_hex(cr, 'c4b5fd', 0.96)
      cairo_new_sub_path(cr)
      cairo_arc(cr, cx, cy, outer_r, alpha, math.pi * 2 - alpha)
      cairo_arc_negative(cr, cx + cut_dx, cy, inner_r, math.pi + beta, math.pi - beta)
      cairo_close_path(cr)
      cairo_fill(cr)
    end

    if status.weather_code >= 2 then
      shared.set_hex(cr, 'cbd5e1', 0.96)
      cairo_new_sub_path(cr)
      cairo_arc(cr, x + 11, y + 26, 7, math.pi, math.pi * 2)
      cairo_arc(cr, x + 20, y + 22, 9, math.pi, math.pi * 2)
      cairo_arc(cr, x + 30, y + 27, 7, math.pi, math.pi * 2)
      cairo_line_to(cr, x + 30, y + 32)
      cairo_line_to(cr, x + 11, y + 32)
      cairo_close_path(cr)
      cairo_fill(cr)
    end

    if status.weather_code >= 51 and status.weather_code < 70 or status.weather_code >= 80 then
      shared.set_hex(cr, color, 0.88)
      cairo_set_line_width(cr, 2)
      for offset = 0, 2 do
        cairo_move_to(cr, x + 14 + offset * 7, y + 35)
        cairo_line_to(cr, x + 11 + offset * 7, y + 41)
      end
      cairo_stroke(cr)
    end
  end

  local function draw_label(cr, label, x, y)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 9)
    shared.set_hex(cr, 'f8fafc', 0.43)
    cairo_move_to(cr, x, y)
    cairo_show_text(cr, label)
  end

  local function draw_metric(cr, label, value, x, y, color)
    draw_label(cr, label, x, y)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 11)
    shared.set_hex(cr, color or 'f8fafc', 0.92)
    cairo_move_to(cr, x, y + 16)
    cairo_show_text(cr, value)
  end

  local function wrap_text(cr, value, max_width, max_lines)
    local words = {}
    for word in value:gmatch('%S+') do
      table.insert(words, word)
    end

    local lines = {}
    local current = ''
    local extents = cairo_text_extents_t:create()
    for _, word in ipairs(words) do
      local candidate = current == '' and word or current .. ' ' .. word
      cairo_text_extents(cr, candidate, extents)
      if extents.width <= max_width or current == '' then
        current = candidate
      else
        table.insert(lines, current)
        current = word
      end
    end
    if current ~= '' then
      table.insert(lines, current)
    end

    if #lines > max_lines then
      lines[max_lines] = shared.truncate_title(
        cr,
        table.concat(lines, ' ', max_lines),
        max_width
      )
      while #lines > max_lines do
        table.remove(lines)
      end
    end
    return lines
  end

  local function draw_error(cr, status, x, y)
    draw_frame(cr, x, y, 'f87171', 'ff4d00')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 28)
    shared.set_hex(cr, 'f87171', 1)
    cairo_move_to(cr, x + 26, y + 74)
    cairo_show_text(cr, 'NO WEATHER DATA')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 11)
    shared.set_hex(cr, 'f8fafc', 0.74)
    cairo_move_to(cr, x + 26, y + 105)
    cairo_show_text(cr, shared.truncate_title(cr, status.error, panel_width - 52))

    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, 'f8fafc', 0.46)
    cairo_move_to(cr, x + 26, y + 137)
    cairo_show_text(cr, 'Set WEATHER_LOCATION or coordinates in .env')
  end

  local function draw_status(cr, status, x, y)
    local accent = status.run_color
    local secondary = status.aqi_color
    draw_frame(cr, x, y, accent, secondary)
    draw_chip(
      cr,
      status.stale and 'STALE' or 'RUN ' .. status.run_status,
      x + panel_width - 126,
      y - 9,
      100,
      status.stale and 'facc15' or accent
    )

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 11)
    shared.set_hex(cr, 'f8fafc', 0.68)
    cairo_move_to(cr, x + 25, y + 31)
    local location_suffix = status.location_source == 'ip' and '  ~' or ''
    cairo_show_text(cr, shared.truncate_title(cr, status.location .. location_suffix, 258))

    draw_weather_icon(cr, x + 25, y + 42, status, secondary)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 43)
    shared.set_hex(cr, 'f8fafc', 0.98)
    cairo_move_to(cr, x + 67, y + 82)
    cairo_show_text(cr, string.format('%d', status.temperature))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, secondary, 0.82)
    cairo_move_to(cr, x + 119, y + 61)
    cairo_show_text(cr, '°' .. status.temperature_unit)

    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, 'f8fafc', 0.66)
    cairo_move_to(cr, x + 26, y + 108)
    cairo_show_text(cr, shared.truncate_title(cr, status.condition, 128))

    shared.set_hex(cr, secondary, 0.30)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 151, y + 38)
    cairo_line_to(cr, x + 151, y + 117)
    cairo_stroke(cr)

    draw_label(cr, 'US AQI', x + 172, y + 48)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 28)
    shared.set_hex(cr, status.aqi_color, 1)
    cairo_move_to(cr, x + 171, y + 79)
    cairo_show_text(cr, string.format('%d', status.aqi))
    cairo_set_font_size(cr, 10)
    cairo_move_to(cr, x + 172, y + 99)
    cairo_show_text(cr, shared.truncate_title(cr, status.aqi_label, 95))

    draw_label(cr, 'RUN SCORE', x + 292, y + 48)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 28)
    shared.set_hex(cr, status.run_color, 1)
    cairo_move_to(cr, x + 291, y + 79)
    cairo_show_text(cr, string.format('%d', status.run_score))
    cairo_set_font_size(cr, 9)
    shared.set_hex(cr, 'f8fafc', 0.64)
    local advice_lines = wrap_text(cr, status.run_advice, 108, 3)
    for index, line in ipairs(advice_lines) do
      cairo_move_to(cr, x + 292, y + 97 + (index - 1) * 10)
      cairo_show_text(cr, line)
    end

    shared.set_hex(cr, secondary, 0.26)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 18, y + 124)
    cairo_line_to(cr, x + panel_width - 18, y + 124)
    cairo_stroke(cr)

    draw_metric(cr, 'FEELS', string.format('%d°%s', status.apparent_temperature, status.temperature_unit), x + 25, y + 143)
    draw_metric(cr, 'RAIN', string.format('%d%%', status.rain), x + 102, y + 143, status.rain >= 60 and 'facc15' or '00e5ff')
    draw_metric(cr, 'WIND', string.format('%s %d', status.wind_direction, status.wind_speed), x + 166, y + 143)
    draw_metric(cr, 'GUST', string.format('%d %s', status.wind_gust, status.wind_unit), x + 244, y + 143)
    draw_metric(cr, 'HUMID', string.format('%d%%', status.humidity), x + 337, y + 143)

    draw_metric(cr, 'UV', string.format('%.1f %s', status.uv_index, status.uv_label), x + 25, y + 180, status.uv_index >= 8 and 'facc15' or 'f8fafc')
    draw_metric(cr, 'VIS', string.format('%.1f %s', status.visibility, status.visibility_unit), x + 137, y + 180)
    draw_metric(cr, 'SUNSET', status.sunset, x + 244, y + 180)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.92)
    cairo_move_to(cr, x + 25, y + 224)
    cairo_show_text(cr, 'BEST  ' .. status.best_window)
    shared.set_hex(cr, 'f8fafc', 0.52)
    cairo_show_text(cr, '  ' .. shared.truncate_title(cr, status.best_detail, 155))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 8)
    local attribution_extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, status.attribution, attribution_extents)
    shared.set_hex(cr, 'f8fafc', 0.48)
    cairo_move_to(cr, x + panel_width - 24 - attribution_extents.width, y + 224)
    cairo_show_text(cr, status.attribution)
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local status = read_status()
    local x = math.max(8, conky_window.width - panel_width - 12)
    local y = math.max(12, conky_window.height - panel_height - 12)
    if status.ok then
      draw_status(cr, status, x, y)
    else
      draw_error(cr, status, x, y)
    end

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
