-- Compact training and weight telemetry beside the thermometer in the bottom-left rail.
return function(shared, repo_root)
  local workouts_path = repo_root .. '/cache/workouts-status.json'
  local weight_path = repo_root .. '/cache/weight-status.json'
  local ui = shared.ui
  local section_h = 49
  local training_h = 62
  local gap = 8

  local function json_string(content, key, fallback)
    local value = shared.json_string(content, key, nil)
    return value ~= nil and value or fallback or ''
  end

  local function json_number(content, key, fallback)
    local value = shared.json_number(content, key, nil)
    return value ~= nil and value or fallback or 0
  end

  local function join(parts, sep)
    local kept = {}
    for _, part in ipairs(parts) do
      if part and part ~= '' then kept[#kept + 1] = part end
    end
    return table.concat(kept, sep or ' · ')
  end

  local function short_age(age_text, date_text)
    if age_text and age_text ~= '' then
      return age_text:gsub('%s*ago$', '')
    end
    if date_text == 'Yesterday' then return '1d' end
    if date_text == 'Today' then return '0d' end
    return date_text or ''
  end

  local function strip_unit(value_text)
    if not value_text or value_text == '--' then return '' end
    return (value_text:gsub('%s+[a-zA-Z/]+$', ''))
  end

  local function semantic_color(kind)
    if kind == 'good' then return ui.good end
    if kind == 'caution' then return ui.caution end
    if kind == 'danger' then return ui.danger end
    return ui.muted
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
        run_units = shared.json_number(entry, 'runUnits', nil),
        in_window = shared.json_boolean(entry, 'inWindow', true),
        is_last = shared.json_boolean(entry, 'isLast', false),
        volumeRunMeters = shared.json_number(entry, 'volumeRunMeters', nil),
        volumePushups = shared.json_number(entry, 'volumePushups', nil),
        volumePullups = shared.json_number(entry, 'volumePullups', nil),
        volumeSitups = shared.json_number(entry, 'volumeSitups', nil),
        volume_break = shared.json_boolean(entry, 'volumeBreak', true),
        combined_index = shared.json_number(entry, 'combinedWorkIndex', nil),
        combined_break = shared.json_boolean(entry, 'combinedWorkBreak', true),
      })
    end
    local changes = shared.json_field(content, 'volumeChanges') or '{}'
    local combined = shared.json_field(content, 'combinedWork') or '{}'
    local forecast = {}
    for _, entry in ipairs(shared.json_array_objects(combined, 'forecast')) do
      local value = shared.json_number(entry, 'value', nil)
      if value and value >= 0 then forecast[#forecast + 1] = value end
    end

    local hr_short = json_string(content, 'lastHeartRateShortText', '')
    if hr_short == '' then
      local hr_full = json_string(content, 'lastHeartRateText', '')
      hr_short = hr_full:match('^(%d+)%s*avg') and (hr_full:match('^(%d+)%s*avg') .. ' bpm') or hr_full
    end

    local pace_raw = json_string(content, 'lastRunPaceText', '')
    if pace_raw == '' then pace_raw = json_string(content, 'lastPaceText', '--') end
    local pace_compact = pace_raw:gsub('%s+/', '/')

    return {
      ok = true,
      stale = shared.json_boolean(content, 'stale', false),
      headline = json_string(content, 'trainingHeadline', ''),
      short_headline = json_string(content, 'trainingShortHeadline', ''),
      detail = json_string(content, 'trainingDetail', ''),
      short_detail = json_string(content, 'trainingShortDetail', ''),
      pace_text = json_string(content, 'trainingPace', ''),
      comparison = json_string(content, 'trainingComparison', ''),
      training_kind = json_string(content, 'trainingKind', 'neutral'),
      duration = json_string(content, 'trainingDuration', json_string(content, 'lastDurationText', '')),
      weather_text = json_string(content, 'trainingWeather', ''),
      weather_short = json_string(content, 'trainingWeatherShort', ''),
      weather_minimal = json_string(content, 'trainingWeatherMinimal', ''),
      hr_partial = shared.json_boolean(content, 'trainingHeartRatePartial', false),
      cadence = json_string(content, 'lastCadenceShortText', ''),
      laps = shared.json_number(content, 'lastLapCount', nil),
      volume_changes = {
        volumeRunMeters = shared.json_number(changes, 'volumeRunMeters', nil),
        volumePushups = shared.json_number(changes, 'volumePushups', nil),
        volumePullups = shared.json_number(changes, 'volumePullups', nil),
        volumeSitups = shared.json_number(changes, 'volumeSitups', nil),
      },
      distance_unit = json_string(content, 'unitName', 'metric') == 'imperial' and 'mi' or 'km',
      combined_value = shared.json_number(combined, 'value', nil),
      combined_change = shared.json_number(combined, 'change', nil),
      combined_percent = shared.json_number(combined, 'changePercent', nil),
      forecast = forecast,
      last_date = json_string(content, 'lastDateText', ''),
      last_age = json_string(content, 'lastAgeText', ''),
      last_age_days = json_number(content, 'lastAgeDays', 0),
      last_distance = json_string(content, 'lastDistanceText', '--'),
      last_duration = json_string(content, 'lastDurationText', '--'),
      last_pace = pace_compact,
      last_strength = json_string(content, 'lastStrengthText', ''),
      last_heart_rate = hr_short,
      trend = json_string(content, 'trendText', ''),
      kind = json_string(content, 'progressKind', 'neutral'),
      recent = recent,
    }
  end

  local function read_weight()
    local content = shared.read_file(weight_path)
    if not content or not shared.json_boolean(content, 'ok', false) then
      return {
        ok = false,
        error = content and json_string(content, 'error', 'Weight data unavailable')
          or 'No openScale backup uploaded yet',
      }
    end
    local recent = {}
    for _, entry in ipairs(shared.json_array_objects(content, 'recent')) do
      table.insert(recent, {
        value = json_number(entry, 'value'),
        is_last = shared.json_boolean(entry, 'isLast', false),
      })
    end
    local change = json_string(content, 'changeText', '--')
    local prev_date = json_string(content, 'previousDateText', '')
    local trend_delta = strip_unit(json_string(content, 'trendDeltaText', ''))
    if trend_delta == '' then trend_delta = strip_unit(change) end
    local unit = json_string(content, 'unit', 'lb')
    local goal_weight_num = shared.json_number(content, 'goalWeight', nil)
    local goal_compact = goal_weight_num and string.format('→ %.0f %s', goal_weight_num, unit) or ''

    return {
      ok = true,
      stale = shared.json_boolean(content, 'stale', false),
      last_weight = json_string(content, 'lastWeightText', '--'),
      last_date = json_string(content, 'lastDateText', ''),
      age = json_string(content, 'ageText', ''),
      age_days = json_number(content, 'ageDays', 0),
      change = change,
      previous_date = prev_date,
      trend_delta = trend_delta,
      goal_compact = goal_compact,
      kind = json_string(content, 'progressKind', 'neutral'),
      recent = recent,
    }
  end

  local function draw_endpoint(cr, x, y, kind, color)
    if kind == 'danger' then
      ui.rect(cr, x - 2.5, y - 2.5, 5, 5, color, 0, 1)
    elseif kind == 'caution' then
      ui.rect(cr, x - 2.5, y - 2.5, 5, 5, color, 1.5, 1)
    else
      ui.circle(cr, x, y, 2.5, color, 1)
    end
  end

  -- One normalized work index from recorded inputs, followed by a separate
  -- short projection. Source colors are fixed: blue data, dashed purple estimate.
  local function draw_combined_work(cr, workouts, x, y, w, h, show_labels)
    local observed = ui.theme == 'light' and '2563b8' or '72aaff'
    local estimated = ui.derived
    local recent, forecast = workouts.recent, workouts.forecast
    local n = math.min(#recent, 12)
    if n == 0 then return end
    local first = #recent - n + 1
    local function valid(value) return value and value >= 0 and value < math.huge end
    if show_labels then
      local value, percent = workouts.combined_value, workouts.combined_percent
      local full = valid(value) and string.format('Work %.0f', value) or 'Work —'
      local short = full
      if percent then
        full = full .. string.format(' · %+.0f%%', percent)
        short = string.format('Work %+.0f%%', percent)
      elseif workouts.combined_change and workouts.combined_change ~= 0 then
        full = full .. (workouts.combined_change > 0 and ' ↑' or ' ↓')
      end
      local weather = workouts.weather_text
      local weather_w = weather ~= '' and ui.width(cr, weather, 11, true) + 4 or 0
      if ui.width(cr, full, 11, true) + weather_w > w then full = short end
      if ui.width(cr, full, 11, true) + weather_w > w then
        weather = workouts.weather_short
        weather_w = weather ~= '' and ui.width(cr, weather, 11, true) + 4 or 0
      end
      if ui.width(cr, full, 11, true) + weather_w > w then
        weather = workouts.weather_minimal
        weather_w = weather ~= '' and ui.width(cr, weather, 11, true) + 4 or 0
      end
      ui.text(cr, full, x, y - 5, {size = 11, mono = true, color = observed, width = w - weather_w})
      if weather ~= '' then
        ui.text(cr, weather, x + w, y - 5, {size = 11, mono = true, color = estimated, align = 'right'})
      end
    end
    local maximum = 100
    for i = first, #recent do
      if valid(recent[i].combined_index) then maximum = math.max(maximum, recent[i].combined_index) end
    end
    for _, value in ipairs(forecast) do if valid(value) then maximum = math.max(maximum, value) end end
    maximum = maximum * 1.05
    local function px(index) return x + 2 + (index - 1) / math.max(1, n + #forecast - 1) * (w - 4) end
    local function py(value) return y + h - 2 - value / maximum * (h - 4) end
    ui.line_between(cr, x, y + h - 0.5, x + w, y + h - 0.5, ui.line_strong, 1, 0.5)
    ui.dash(cr, x, py(100), x + w, py(100), ui.line_strong, 1, 2, 2, 0.5)
    local max_distance = 1
    for i = first, #recent do max_distance = math.max(max_distance, recent[i].distance_units) end
    for index = 1, n do
      local item = recent[first + index - 1]
      local bh = math.max(0, (h - 3) * item.distance_units / max_distance)
      local bw = math.min(7, (w - 4) / math.max(1, n + #forecast) - 2)
      if bh > 0 and bw > 0 then
        local share = item.run_units and item.distance_units > 0 and shared.clamp(item.run_units / item.distance_units, 0, 1) or 1
        ui.rect(cr, px(index) - bw / 2, y + h - bh, bw, bh, ui.muted, 0, 0.16, 0.6)
        ui.rect(cr, px(index) - bw / 2, y + h - bh * share, bw, bh * share, observed, 0, 0.12)
      end
    end
    local previous
    for index = 1, n do
      local item = recent[first + index - 1]
      if item.combined_break or not valid(item.combined_index) then previous = nil end
      if valid(item.combined_index) then
        local cx, cy = px(index), py(item.combined_index)
        if previous then ui.line_between(cr, previous[1], previous[2], cx, cy, observed, 1.5, 0.95) end
        ui.circle(cr, cx, cy, item.is_last and 2.5 or 1.2, observed, 1)
        previous = {cx, cy}
      end
    end
    if previous and valid(recent[#recent].combined_index) then
      for step, value in ipairs(forecast) do
        if valid(value) then
          local cx, cy = px(n + step), py(value)
          ui.dash(cr, previous[1], previous[2], cx, cy, estimated, 1.5, 3, 2, 0.95)
          ui.circle(cr, cx, cy, 2, estimated, 0.9, 1)
          previous = {cx, cy}
        end
      end
    end
  end

  local function draw_weight_sparkline(cr, recent, kind, x, y, w, h)
    local n = math.min(#recent, 12)
    if n < 2 then return end
    local start_idx = #recent - n + 1
    local min_v, max_v = math.huge, -math.huge
    local sum_prior, count_prior = 0, 0
    for i = start_idx, #recent do
      local v = recent[i].value
      if v < min_v then min_v = v end
      if v > max_v then max_v = v end
      if i < #recent then
        sum_prior = sum_prior + v
        count_prior = count_prior + 1
      end
    end
    local span = math.max(1.0, max_v - min_v)

    local pts = {}
    for idx = 1, n do
      local v = recent[start_idx + idx - 1].value
      local px = x + 2 + ((idx - 1) / (n - 1)) * (w - 5)
      local py = y + h - 2 - ((v - min_v) / span) * (h - 4)
      pts[#pts + 1] = {px, py}
    end

    local runs = {}
    local current_run = nil
    for idx = 1, n - 1 do
      local v1 = recent[start_idx + idx - 1].value
      local v2 = recent[start_idx + idx].value
      local seg_color = ui.muted
      local seg_kind = 'neutral'
      if v2 > v1 then
        seg_color = ui.danger
        seg_kind = 'danger'
      elseif v2 < v1 then
        seg_color = ui.good
        seg_kind = 'good'
      end
      if not current_run or current_run.color ~= seg_color then
        current_run = {color = seg_color, kind = seg_kind, pts = {pts[idx], pts[idx + 1]}}
        runs[#runs + 1] = current_run
      else
        current_run.pts[#current_run.pts + 1] = pts[idx + 1]
      end
    end

    for _, run in ipairs(runs) do
      local area = {{run.pts[1][1], y + h}}
      for _, pt in ipairs(run.pts) do area[#area + 1] = pt end
      area[#area + 1] = {run.pts[#run.pts][1], y + h}
      ui.polygon(cr, area, run.color, 0.08)
    end

    if count_prior > 0 then
      local avg_v = sum_prior / count_prior
      local avg_y = y + h - 2 - ((avg_v - min_v) / span) * (h - 4)
      ui.dash(cr, x, avg_y, x + w, avg_y, ui.line_strong, 1, 2, 2, 0.75)
    end

    ui.line_between(cr, x, y + h - 0.5, x + w, y + h - 0.5, ui.line_strong, 1, 0.75)

    for _, run in ipairs(runs) do
      ui.polyline(cr, run.pts, run.color, 1.5, 0.95, true)
    end

    local last_pt = pts[#pts]
    local last_run = runs[#runs]
    local end_kind = last_run and last_run.kind or kind
    local end_color = last_run and last_run.color or semantic_color(kind)
    draw_endpoint(cr, last_pt[1], last_pt[2], end_kind, end_color)
  end

  local function draw_training(cr, workouts, width, top, available_height)
    top = top or 0
    if not workouts.ok then
      ui.text(cr, workouts.error, 0, top + 14, {size = 11, mono = true, color = ui.muted, width = width})
      return
    end
    local recency = workouts.stale and 'Stale' or short_age(workouts.last_age, workouts.last_date)
    local recency_w = recency ~= '' and (ui.width(cr, recency, 11, true) + 6) or 0
    local recency_color = (workouts.stale or workouts.last_age_days >= 10) and ui.caution or ui.muted
    local limit = width - recency_w
    local distance = workouts.last_distance:gsub('%s+', '')
    local head_size = width < 160 and 11 or 13.5
    local lap_text = workouts.laps and tostring(workouts.laps) or ''
    local lap_w = lap_text ~= '' and (14 + ui.width(cr, lap_text, 11, true)) or 0
    local text_limit = limit - (lap_w > 0 and lap_w + 5 or 0)
    local x = 0
    local distance_w = ui.width(cr, distance, head_size, true, 'bold')
    ui.text(cr, distance, 0, top + 11, {size = head_size, mono = true, bold = 'bold', color = ui.ink, width = text_limit})
    x = distance_w + (width < 160 and 2 or 4)
    local pace = workouts.last_pace
    if x + ui.width(cr, pace, 11, true) > text_limit then pace = pace:gsub('/[a-z]+$', '') end
    if x + ui.width(cr, pace, 11, true) <= text_limit then
      ui.text(cr, pace, x, top + 11, {size = 11, mono = true, color = ui.muted})
    end
    if lap_w > 0 then
      local lap_x = limit - lap_w
      ui.icon(cr, 'rotate-cw', lap_x, top + 1, 12, ui.muted)
      ui.text(cr, lap_text, lap_x + 14, top + 11, {size = 11, mono = true, color = ui.muted})
    end
    if recency ~= '' then
      ui.text(cr, recency, width, top + 11, {size = 11, mono = true, color = recency_color, align = 'right'})
    end
    if (available_height or training_h) >= 30 then
      local duration = workouts.duration
      local duration_w = duration ~= '' and ui.width(cr, duration, 11, true) or 0
      local heart = workouts.last_heart_rate:match('(%d+)') or ''
      if heart ~= '' and workouts.hr_partial then heart = '~' .. heart end
      local heart_w = heart ~= '' and (12 + ui.width(cr, heart, 11, true)) or 0
      local detail = workouts.last_strength ~= '' and (workouts.short_detail ~= '' and workouts.short_detail or workouts.last_strength) or workouts.cadence
      if detail == '' and heart == '' then detail = workouts.detail end
      local detail_limit = width - duration_w - (duration_w > 0 and 6 or 0) - heart_w - (heart_w > 0 and 2 or 0)
      if ui.width(cr, detail, 11, true) > detail_limit then detail = detail:gsub(' reps$', '') end
      if ui.width(cr, detail, 11, true) > detail_limit then
        heart, heart_w = '', 0
        detail_limit = width - duration_w - (duration_w > 0 and 6 or 0)
      end
      ui.text(cr, detail, 0, top + 26, {size = 11, mono = true, color = ui.muted, width = detail_limit})
      if heart_w > 0 then
        local heart_x = width - duration_w - (duration_w > 0 and 6 or 0) - heart_w
        ui.icon(cr, 'heart', heart_x, top + 16, 11, ui.muted)
        ui.text(cr, heart, heart_x + 12, top + 26, {size = 11, mono = true, color = ui.muted})
      end
      if duration_w > 0 then
        ui.text(cr, duration, width, top + 26, {size = 11, mono = true, color = ui.muted, align = 'right'})
      end
    end
    local compact = (available_height or training_h) < training_h
    if #workouts.recent > 0 and (available_height or training_h) >= 48 then
      draw_combined_work(cr, workouts, 0, top + (compact and 31 or 45), width, 17, not compact)
    end
  end

  local function draw_weight(cr, weight, width, top, available_height)
    top = top or 0
    if not weight.ok then
      ui.text(cr, weight.error, 0, top + 14, {size = 11, mono = true, color = ui.muted, width = width})
      return
    end
    local color = semantic_color(weight.kind)
    local right_tag = weight.stale and 'Stale' or short_age(weight.age, weight.last_date)
    local right_color = ui.muted
    if weight.age_days > 5 then
      right_color = ui.danger
    elseif weight.age_days > 3 or weight.stale then
      right_color = ui.caution
    end
    local right_w = right_tag ~= '' and (ui.width(cr, right_tag, 11, true) + 6) or 0

    local x = 0
    x = x + ui.text(cr, weight.last_weight, x, top + 11, {size = 13.5, bold = 'bold', color = ui.ink}) + 6
    if weight.trend_delta ~= '' and x + ui.width(cr, weight.trend_delta, 11, true, 'bold') <= width - right_w then
      ui.text(cr, weight.trend_delta, x, top + 11, {size = 11, mono = true, bold = 'bold', color = color})
    end
    if right_tag ~= '' then
      ui.text(cr, right_tag, width, top + 11, {size = 11, mono = true, color = right_color, align = 'right'})
    end
    if (available_height or section_h) < 30 then return end

    local goal_str = width < 160 and weight.goal_compact:gsub('%s+[a-zA-Z]+$', '') or weight.goal_compact
    local goal_w = goal_str ~= '' and (ui.width(cr, goal_str, 11, true) + 6) or 0
    local step_str = join({
      strip_unit(weight.change),
      weight.previous_date ~= '' and weight.previous_date or weight.last_date,
    }, ' · ')
    ui.text(cr, step_str, 0, top + 26, {
      size = 11,
      mono = true,
      color = ui.muted,
      width = math.max(40, width - goal_w),
    })
    if goal_str ~= '' then
      ui.text(cr, goal_str, width, top + 26, {
        size = 11,
        mono = true,
        color = ui.muted,
        align = 'right',
      })
    end

    if #weight.recent >= 2 and (available_height or section_h) >= 49 then
      draw_weight_sparkline(cr, weight.recent, weight.kind, 0, top + 31, width, 18)
    elseif (available_height or section_h) >= 41 then
      ui.line_between(cr, 0, top + 40, width, top + 40, color, 1.5, 0.7)
    end
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local content_height = training_h + gap + section_h
      local top = math.max(0, height - content_height)
      local training_height, weight_height, section_gap = training_h, section_h, gap
      if height < content_height then
        section_gap = 4
        training_height = math.floor((height - section_gap) * 0.55)
        weight_height = height - section_gap - training_height
      end
      draw_training(cr, read_workouts(), width, top, training_height)
      draw_weight(cr, read_weight(), width, top + training_height + section_gap, weight_height)
    end)
  end
  return {draw = draw}
end
