return function(shared, repo_root)
  local weather_path = repo_root .. '/cache/weather-status.json'
  local workouts_path = repo_root .. '/cache/workouts-status.json'
  local font = 'JetBrains Mono'
  local panel_width = 424
  local panel_height = 322
  local radius = 18

  local function json_string(content, key, fallback)
    local value = shared.json_string(content, key, nil)
    return value ~= nil and value or fallback or ''
  end

  local function json_number(content, key, fallback)
    local value = shared.json_number(content, key, nil)
    return value ~= nil and value or fallback or 0
  end

  local function read_status()
    local content = shared.read_file(weather_path)
    if not content then
      return { ok = false, error = 'Waiting for the first weather update...' }
    end
    if not shared.json_boolean(content, 'ok', false) then
      return { ok = false, error = json_string(content, 'error', 'Weather data unavailable') }
    end

    local best_body = shared.json_field(content, 'bestWindow') or '{}'
    return {
      ok = true,
      stale = shared.json_boolean(content, 'stale', false),
      location = json_string(content, 'location', 'Local weather'),
      location_source = json_string(content, 'locationSource', ''),
      temperature = json_number(content, 'temperature'),
      temperature_unit = json_string(content, 'temperatureUnit', 'F'),
      apparent_temperature = json_number(content, 'apparentTemperature'),
      condition = json_string(content, 'condition', 'Unknown conditions'),
      weather_code = json_number(content, 'weatherCode'),
      is_day = shared.json_boolean(content, 'isDay', false),
      aqi = json_number(content, 'aqi'),
      aqi_label = json_string(content, 'aqiLabel', 'Unknown'),
      aqi_color = json_string(content, 'aqiColor', 'f8fafc'),
      uv_index = json_number(content, 'uvIndex'),
      uv_label = json_string(content, 'uvLabel', ''),
      humidity = json_number(content, 'humidityPercent'),
      rain = json_number(content, 'precipitationProbability'),
      wind_gust = json_number(content, 'windGust'),
      wind_unit = json_string(content, 'windUnit', 'mph'),
      sunset = json_string(content, 'sunset', '--'),
      run_score = json_number(content, 'runScore'),
      run_status = json_string(content, 'runStatus', 'WAIT'),
      run_color = json_string(content, 'runColor', 'f87171'),
      run_advice = json_string(content, 'runAdvice', 'Check conditions before heading out'),
      best_window = json_string(best_body, 'label', 'Now'),
      best_detail = json_string(best_body, 'detail', ''),
    }
  end

  local function read_workouts()
    local content = shared.read_file(workouts_path)
    if not content or not shared.json_boolean(content, 'ok', false) then
      local error_text = content and json_string(content, 'error', '') or ''
      return {
        ok = false,
        error = error_text ~= '' and error_text or 'No workouts uploaded yet',
      }
    end

    local recent = {}
    for _, entry in ipairs(shared.json_array_objects(content, 'recent')) do
      table.insert(recent, {
        distance_units = json_number(entry, 'distanceUnits'),
        is_last = shared.json_boolean(entry, 'isLast', false),
      })
    end

    return {
      ok = true,
      last_sport = json_string(content, 'lastSport', 'Workout'),
      last_date = json_string(content, 'lastDateText', ''),
      last_distance = json_string(content, 'lastDistanceText', '--'),
      last_duration = json_string(content, 'lastDurationText', '--'),
      last_pace = json_string(content, 'lastPaceText', '--'),
      last_heart_rate = json_string(content, 'lastHeartRateText', ''),
      last_cadence = json_string(content, 'lastCadenceText', ''),
      week_runs = json_number(content, 'weekRuns'),
      week_distance = json_string(content, 'weekDistanceText', '--'),
      week_duration = json_string(content, 'weekDurationText', '--'),
      recent = recent,
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
    shared.set_hex(cr, '020617', 0.59)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.70)
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

  local function short_uv_label(label)
    local compact = {
      ['Moderate'] = 'Med',
      ['Very high'] = 'V.High',
      ['Extreme'] = 'Xtreme',
    }
    return compact[label] or label
  end

  local function draw_workouts(cr, workouts, x, y, accent, secondary)
    shared.set_hex(cr, secondary, 0.26)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 18, y + 172)
    cairo_line_to(cr, x + panel_width - 18, y + 172)
    cairo_stroke(cr)

    if not workouts.ok then
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
      cairo_set_font_size(cr, 10)
      shared.set_hex(cr, 'f8fafc', 0.42)
      cairo_move_to(cr, x + 25, y + 212)
      cairo_show_text(cr, shared.truncate_title(cr, 'TRAINING  ' .. workouts.error, panel_width - 50))
      return
    end

    shared.set_hex(cr, secondary, 0.26)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 212, y + 182)
    cairo_line_to(cr, x + 212, y + 252)
    cairo_stroke(cr)

    local last_label = workouts.last_sport == 'Run' and 'LAST RUN'
      or 'LAST ' .. string.upper(workouts.last_sport)
    draw_label(cr, last_label, x + 25, y + 192)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 20)
    shared.set_hex(cr, 'f8fafc', 0.95)
    cairo_move_to(cr, x + 24, y + 216)
    cairo_show_text(cr, workouts.last_distance)

    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, 'f8fafc', 0.66)
    cairo_move_to(cr, x + 25, y + 234)
    cairo_show_text(cr, shared.truncate_title(
      cr,
      table.concat(
        {
          workouts.last_date,
          workouts.last_duration,
          workouts.last_pace,
        },
        ' · '
      ),
      178
    ))

    cairo_set_font_size(cr, 9)
    shared.set_hex(cr, accent, 0.78)
    cairo_move_to(cr, x + 25, y + 250)
    cairo_show_text(cr, shared.truncate_title(
      cr,
      workouts.last_heart_rate ~= '' and 'HR ' .. workouts.last_heart_rate
        or (workouts.last_cadence ~= '' and workouts.last_cadence or ''),
      178
    ))

    draw_label(cr, 'THIS WEEK', x + 232, y + 192)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 20)
    shared.set_hex(cr, 'f8fafc', 0.95)
    cairo_move_to(cr, x + 231, y + 216)
    cairo_show_text(cr, workouts.week_distance)

    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, 'f8fafc', 0.66)
    cairo_move_to(cr, x + 232, y + 234)
    cairo_show_text(cr, shared.truncate_title(
      cr,
      table.concat(
        {
          workouts.week_runs .. (workouts.week_runs == 1 and ' run' or ' runs'),
          workouts.week_duration,
        },
        ' · '
      ),
      174
    ))

    local entries = workouts.recent
    if #entries == 0 then
      return
    end
    local left, right = x + 25, x + panel_width - 25
    local slot = (right - left) / #entries
    local bar_width = math.min(16, slot * 0.62)
    local baseline = y + 302
    local max_distance = 0
    for _, entry in ipairs(entries) do
      max_distance = math.max(max_distance, entry.distance_units)
    end
    for index, entry in ipairs(entries) do
      local bar_height = max_distance > 0
        and math.max(3, entry.distance_units / max_distance * 30)
        or 3
      local bar_x = left + slot * (index - 1) + (slot - bar_width) / 2
      shared.rounded_rect(cr, bar_x, baseline - bar_height, bar_width, bar_height, 3)
      shared.set_hex(cr, accent, entry.is_last and 1 or 0.34)
      cairo_fill(cr)
    end
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 8)
    shared.set_hex(cr, 'f8fafc', 0.42)
    cairo_move_to(cr, left, y + 316)
    cairo_show_text(cr, 'LAST ' .. #entries .. ' WORKOUTS')
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

  local function draw_status(cr, status, workouts, x, y)
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

    local location_suffix = status.location_source == 'ip' and '  ~' or ''
    local location_text = status.location .. location_suffix

    draw_weather_icon(cr, x + 25, y + 26, status, secondary)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 43)
    shared.set_hex(cr, 'f8fafc', 0.98)
    cairo_move_to(cr, x + 67, y + 66)
    cairo_show_text(cr, string.format('%d', status.temperature))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, secondary, 0.82)
    cairo_move_to(cr, x + 119, y + 45)
    cairo_show_text(cr, '°' .. status.temperature_unit)

    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, 'f8fafc', 0.66)
    cairo_move_to(cr, x + 26, y + 92)
    cairo_show_text(cr, shared.truncate_title(cr, status.condition, 128))

    shared.set_hex(cr, secondary, 0.30)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 151, y + 22)
    cairo_line_to(cr, x + 151, y + 101)
    cairo_stroke(cr)

    draw_label(cr, 'US AQI', x + 172, y + 32)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 28)
    shared.set_hex(cr, status.aqi_color, 1)
    cairo_move_to(cr, x + 171, y + 63)
    cairo_show_text(cr, string.format('%d', status.aqi))
    cairo_set_font_size(cr, 10)
    cairo_move_to(cr, x + 172, y + 83)
    cairo_show_text(cr, shared.truncate_title(cr, status.aqi_label, 95))

    draw_label(cr, 'RUN SCORE', x + 292, y + 32)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 28)
    shared.set_hex(cr, status.run_color, 1)
    cairo_move_to(cr, x + 291, y + 63)
    cairo_show_text(cr, string.format('%d', status.run_score))
    cairo_set_font_size(cr, 9)
    shared.set_hex(cr, 'f8fafc', 0.64)
    local advice_lines = shared.wrap_title(cr, status.run_advice, 108, 3)
    for index, line in ipairs(advice_lines) do
      cairo_move_to(cr, x + 292, y + 81 + (index - 1) * 10)
      cairo_show_text(cr, line)
    end

    shared.set_hex(cr, secondary, 0.26)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 18, y + 108)
    cairo_line_to(cr, x + panel_width - 18, y + 108)
    cairo_stroke(cr)

    draw_metric(cr, 'FEELS', string.format('%d°%s', status.apparent_temperature, status.temperature_unit), x + 25, y + 127)
    draw_metric(cr, 'RAIN', string.format('%d%%', status.rain), x + 78, y + 127, status.rain >= 60 and 'facc15' or '00e5ff')
    draw_metric(cr, 'GUST', string.format('%d %s', status.wind_gust, status.wind_unit), x + 117, y + 127)
    draw_metric(cr, 'HUMID', string.format('%d%%', status.humidity), x + 176, y + 127)
    draw_metric(cr, 'UV', string.format('%.1f %s', status.uv_index, short_uv_label(status.uv_label)), x + 219, y + 127, status.uv_index >= 8 and 'facc15' or 'f8fafc')
    draw_metric(cr, 'SUNSET', status.sunset, x + 302, y + 127)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.92)
    cairo_move_to(cr, x + 25, y + 165)
    cairo_show_text(cr, 'BEST  ' .. status.best_window)
    shared.set_hex(cr, 'f8fafc', 0.52)
    cairo_show_text(cr, '  ' .. shared.truncate_title(cr, status.best_detail, 155))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 8)
    local location_extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, location_text, location_extents)
    shared.set_hex(cr, 'f8fafc', 0.48)
    cairo_move_to(cr, x + panel_width - 24 - location_extents.width, y + 165)
    cairo_show_text(cr, location_text)

    draw_workouts(cr, workouts, x, y, accent, secondary)
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local status = read_status()
    local workouts = read_workouts()
    local x = math.max(8, conky_window.width - panel_width - 12)
    local y = math.max(12, conky_window.height - panel_height - 12)
    if status.ok then
      draw_status(cr, status, workouts, x, y)
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
