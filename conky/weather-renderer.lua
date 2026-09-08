-- Weather, air quality, and run guidance above the training summary, as
-- metrics, aligned readouts, and explicit status badges.
return function(shared, repo_root)
  local weather_path = repo_root .. '/cache/weather-status.json'
  local workouts_path = repo_root .. '/cache/workouts-status.json'
  local ui = shared.ui
  local weather_block, gap = 100, 16
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
      return { ok = false, error = 'Waiting for the first weather update' }
    end
    if not shared.json_boolean(content, 'ok', false) then
      return { ok = false, error = json_string(content, 'error', 'Weather data unavailable') }
    end

    return {
      ok = true,
      stale = shared.json_boolean(content, 'stale', false),
      location = json_string(content, 'location', 'Local weather'),
      temperature = json_number(content, 'temperature'),
      temperature_unit = json_string(content, 'temperatureUnit', 'F'),
      apparent_temperature = json_number(content, 'apparentTemperature'),
      condition = json_string(content, 'condition', 'Unknown conditions'),
      aqi = json_number(content, 'aqi'),
      uv_index = json_number(content, 'uvIndex'),
      sunset = json_string(content, 'sunset', '--'),
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

  local function join(parts)
    local kept = {}
    for _, part in ipairs(parts) do if part and part ~= '' then kept[#kept + 1] = part end end
    return table.concat(kept, ' · ')
  end

  local function draw_weather(cr, weather, width, top)
    top = top or 0
    if not weather.ok then
      ui.callout(cr, 'Unavailable', weather.error, 0, top, width, 'danger')
      return
    end
    local unit = '°' .. weather.temperature_unit
    local half = (width - 16) / 2
    ui.metric(cr, 'Temp ' .. unit, string.format('%.0f', weather.temperature), 0, top, half)
    ui.metric(cr, 'AQI', string.format('%.0f', weather.aqi), half + 16, top, half)
    local context = join({weather.condition, weather.stale and 'Stale' or weather.location})
    ui.text(cr, context, 0, top + 66, {size = 12, color = weather.stale and ui.caution or ui.muted,
      width = width})
    local readouts = {
      {'Feels', string.format('%.0f', weather.apparent_temperature) .. unit},
      {'UV', string.format('%.1f', weather.uv_index)},
      {'Sunset', weather.sunset},
    }
    local label_column = 0
    for _, pair in ipairs(readouts) do
      label_column = math.max(label_column, ui.width(cr, pair[1], 12) + 8)
    end
    local column = width / 3
    for index, pair in ipairs(readouts) do
      local x = (index - 1) * column
      local y = top + 88
      ui.text(cr, pair[1], x, y, {size = 12, color = ui.muted})
      ui.text(cr, pair[2], x + label_column, y, {size = 13, mono = true, width = column - label_column - 8})
    end
  end

  local function draw_training(cr, workouts, width, top)
    top = top or 0
    if not workouts.ok then
      ui.text(cr, workouts.error, 0, top + 16, {size = 13.5, color = ui.muted, width = width}); return
    end
    local half = (width - 16) / 2
    ui.metric(cr, 'Last run', workouts.last_distance, 0, top, half)
    ui.metric(cr, 'Last 7 days', workouts.week_distance, half + 16, top, half)
    -- Aligned detail rows under each metric, not supporting sublines.
    local detail = {size = 11, mono = true, color = ui.muted, width = half}
    ui.text(cr, join({workouts.last_date, workouts.last_pace}), 0, top + 64, detail)
    ui.text(cr, join({workouts.last_duration, workouts.last_heart_rate, workouts.last_cadence}), 0, top + 80, detail)
    ui.text(cr, workouts.week_duration, half + 16, top + 64, detail)
    ui.text(cr, workouts.week_runs .. ' runs', half + 16, top + 80, detail)
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local weather, workouts = read_status(), read_workouts()
      local content_height = weather_block + gap + 94
      local compact = height < content_height
      if not compact then
        local top = 0
        draw_weather(cr, weather, width, top)
        draw_training(cr, workouts, width, top + weather_block + gap)
        return
      end
      -- Short displays alternate the two blocks as labeled pages.
      local training_page = math.floor(os.time() / 30) % 2 == 1
      if training_page then draw_training(cr, workouts, width, 0)
      else draw_weather(cr, weather, width, 0) end
      ui.footer(cr, training_page and '2/2' or '1/2', width, height)
    end)
  end
  return {draw = draw}
end
