-- Weather, air quality, and run guidance above the training summary, as
-- metrics, aligned readouts, and explicit status badges.
return function(shared, repo_root)
  local weather_path = repo_root .. '/cache/weather-status.json'
  local workouts_path = repo_root .. '/cache/workouts-status.json'
  local ui = shared.ui
  local weather_block, gap = 140, 16
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

    local best_body = shared.json_field(content, 'bestWindow') or '{}'
    return {
      ok = true,
      stale = shared.json_boolean(content, 'stale', false),
      location = json_string(content, 'location', 'Local weather'),
      temperature = json_number(content, 'temperature'),
      temperature_unit = json_string(content, 'temperatureUnit', 'F'),
      apparent_temperature = json_number(content, 'apparentTemperature'),
      condition = json_string(content, 'condition', 'Unknown conditions'),
      aqi = json_number(content, 'aqi'),
      aqi_label = json_string(content, 'aqiLabel', 'Unknown'),
      uv_index = json_number(content, 'uvIndex'),
      humidity = json_number(content, 'humidityPercent'),
      rain = json_number(content, 'precipitationProbability'),
      wind_gust = json_number(content, 'windGust'),
      wind_unit = json_string(content, 'windUnit', 'mph'),
      sunset = json_string(content, 'sunset', '--'),
      run_score = json_number(content, 'runScore'),
      run_status = json_string(content, 'runStatus', 'WAIT'),
      best_window = json_string(best_body, 'label', 'Now'),
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

  local function draw_weather(cr, weather, width)
    if not weather.ok then
      ui.callout(cr, 'Unavailable', weather.error, 0, 0, width, 'danger')
      return
    end
    local unit = '°' .. weather.temperature_unit
    local third = (width - 32) / 3
    ui.metric(cr, 'Temp ' .. unit, string.format('%.0f', weather.temperature), 0, 0, third)
    ui.metric(cr, 'US AQI', string.format('%.0f', weather.aqi), third + 16, 0, third)
    ui.metric(cr, 'Run / 100', string.format('%.0f', weather.run_score), (third + 16) * 2, 0, third)
    local aqi_kind = weather.aqi <= 50 and 'good' or weather.aqi <= 100 and 'caution' or 'danger'
    local badge_width = ui.badge(cr, 'AQI ' .. weather.aqi_label, width, 52, aqi_kind, {right = true})
    local context = join({weather.condition, weather.stale and 'Stale' or weather.location})
    ui.text(cr, context, 0, 66, {size = 12, color = weather.stale and ui.caution or ui.muted,
      width = width - badge_width - 12})
    local readouts = {{'Feels', string.format('%.0f', weather.apparent_temperature) .. unit},
      {'Rain', string.format('%.0f%%', weather.rain)},
      {'Gust', string.format('%.0f %s', weather.wind_gust, weather.wind_unit)},
      {'Humidity', string.format('%.0f%%', weather.humidity)},
      {'UV', string.format('%.1f', weather.uv_index)}, {'Sunset', weather.sunset}}
    -- Every readout value starts at the same offset inside its column, so the
    -- two rows and the best-run line below them share one value edge.
    local label_column = ui.width(cr, 'Best run', 12) + 8
    for _, pair in ipairs(readouts) do
      label_column = math.max(label_column, ui.width(cr, pair[1], 12) + 8)
    end
    local column = width / 3
    for index, pair in ipairs(readouts) do
      local x = ((index - 1) % 3) * column
      local y = 88 + math.floor((index - 1) / 3) * 18
      ui.text(cr, pair[1], x, y, {size = 12, color = ui.muted})
      ui.text(cr, pair[2], x + label_column, y, {size = 13, mono = true, width = column - label_column - 8})
    end
    local run_kind = weather.run_score >= 80 and 'good' or weather.run_score >= 50 and 'caution' or 'danger'
    local run_width = ui.badge(cr, (weather.run_status:gsub('^RUN ', '')), width, 114, run_kind, {right = true})
    ui.text(cr, 'Best run', 0, 128, {size = 12, color = ui.muted})
    ui.text(cr, weather.best_window, label_column, 128,
      {size = 13.5, bold = 'medium', width = width - label_column - run_width - 12})
  end

  local function draw_training(cr, workouts, width, top, bottom)
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
    local count, peak = #workouts.recent, 0
    for _, run in ipairs(workouts.recent) do peak = math.max(peak, run.distance_units) end
    local chart_top, baseline = top + 92, bottom - 18
    if count > 0 and peak > 0 and baseline - chart_top >= 12 then
      local step = width / count
      for index, run in ipairs(workouts.recent) do
        local bar = run.distance_units / peak * (baseline - chart_top)
        ui.rect(cr, (index - 1) * step, baseline - bar, math.max(1, step - 6), bar,
          ui.accent, 0, run.is_last and 1 or 0.42)
      end
      local distance_unit = workouts.last_distance:match('%a+$') or ''
      ui.text(cr, 'Last ' .. count .. ' workouts · ' .. distance_unit, 0, bottom - 4,
        {size = 11, mono = true, color = ui.muted})
    end
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local weather, workouts = read_status(), read_workouts()
      local compact = height < 300
      if not compact then
        draw_weather(cr, weather, width)
        draw_training(cr, workouts, width, weather_block + gap, height)
        return
      end
      -- Short displays alternate the two blocks as labeled pages.
      local training_page = math.floor(os.time() / 30) % 2 == 1
      if training_page then draw_training(cr, workouts, width, 0, height - 16)
      else draw_weather(cr, weather, width) end
      ui.footer(cr, training_page and '2/2' or '1/2', width, height)
    end)
  end
  return {draw = draw}
end
