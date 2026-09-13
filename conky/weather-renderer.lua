-- Training and weight below the resource gauges in the right rail.
return function(shared, repo_root)
  local workouts_path = repo_root .. '/cache/workouts-status.json'
  local weight_path = repo_root .. '/cache/weight-status.json'
  local ui = shared.ui
  local gap = 16
  local function json_string(content, key, fallback)
    local value = shared.json_string(content, key, nil)
    return value ~= nil and value or fallback or ''
  end

  local function json_number(content, key, fallback)
    local value = shared.json_number(content, key, nil)
    return value ~= nil and value or fallback or 0
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

  local function read_weight()
    local content = shared.read_file(weight_path)
    if not content or not shared.json_boolean(content, 'ok', false) then
      return {ok = false, error = content and json_string(content, 'error', 'Weight data unavailable')
        or 'No openScale backup uploaded yet'}
    end
    return {
      ok = true,
      stale = shared.json_boolean(content, 'stale', false),
      last_weight = json_string(content, 'lastWeightText', '--'),
      last_date = json_string(content, 'lastDateText'),
      age = json_string(content, 'ageText'),
      change = json_string(content, 'changeText', '--'),
      previous_date = json_string(content, 'previousDateText'),
    }
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

  local function draw_weight(cr, weight, width, top)
    if not weight.ok then
      ui.text(cr, weight.error, 0, top + 16, {size = 13.5, color = ui.muted, width = width}); return
    end
    local half = (width - 16) / 2
    ui.metric(cr, 'Last weight', weight.last_weight, 0, top, half)
    ui.metric(cr, 'Change', weight.change, half + 16, top, half)
    local detail = {size = 11, mono = true, color = ui.muted, width = half}
    ui.text(cr, join({weight.last_date, weight.age}), 0, top + 64, detail)
    ui.text(cr, weight.previous_date ~= '' and 'since ' .. weight.previous_date or 'First weigh-in',
      half + 16, top + 64, detail)
    if weight.stale then
      ui.text(cr, 'Stale', 0, top + 80, {size = 11, mono = true, color = ui.caution, width = half})
    end
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local sections = {
        {height = 94, draw = draw_training, data = read_workouts()},
        {height = 94, draw = draw_weight, data = read_weight()},
      }
      local content_height = 94 + gap + 94
      local available = height < content_height and height - 16 or height
      -- Keep whole sections together, in order, with a footer only when paging.
      local pages, used = {{}}, 0
      for _, section in ipairs(sections) do
        if used > 0 and used + gap + section.height > available then
          pages[#pages + 1], used = {}, 0
        end
        local page = pages[#pages]
        page[#page + 1] = section
        used = used + (used > 0 and gap or 0) + section.height
      end
      local page_index = math.floor(os.time() / 30) % #pages + 1
      local top = 0
      for _, section in ipairs(pages[page_index]) do
        section.draw(cr, section.data, width, top)
        top = top + section.height + gap
      end
      if #pages > 1 then ui.footer(cr, page_index .. '/' .. #pages, width, height) end
    end)
  end
  return {draw = draw}
end
