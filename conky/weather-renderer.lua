-- Compact training and weight telemetry beside the thermometer in the bottom-left rail.
return function(shared, repo_root)
  local workouts_path = repo_root .. '/cache/workouts-status.json'
  local weight_path = repo_root .. '/cache/weight-status.json'
  local ui = shared.ui
  local section_h = 49
  local gap = 13

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
        score = shared.json_number(entry, 'score', nil),
        fitness = shared.json_number(entry, 'fitness', nil),
        in_window = shared.json_boolean(entry, 'inWindow', true),
        is_last = shared.json_boolean(entry, 'isLast', false),
      })
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
      last_date = json_string(content, 'lastDateText', ''),
      last_age = json_string(content, 'lastAgeText', ''),
      last_age_days = json_number(content, 'lastAgeDays', 0),
      last_distance = json_string(content, 'lastDistanceText', '--'),
      last_duration = json_string(content, 'lastDurationText', '--'),
      last_pace = pace_compact,
      last_score = json_string(content, 'lastScoreText', ''),
      last_heart_rate = hr_short,
      trend = json_string(content, 'trendText', ''),
      fitness_baseline = shared.json_number(content, 'fitnessBaselineScore', nil),
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

  -- Bars are total distance with the walked share hollow; dots are each run's
  -- effort score and the line is the smoothed fitness level, dashed where it
  -- stood at the start of the trend window.
  local function draw_run_sparkline(cr, workouts, x, y, w, h)
    local recent = workouts.recent
    local n = math.min(#recent, 12)
    if n == 0 then return end
    local start_idx = #recent - n + 1
    local kind = workouts.kind
    local color = semantic_color(kind)
    local max_dist = 1.0
    local lo, hi = math.huge, -math.huge
    local function widen(value, top_only)
      if value == nil then return end
      if value > hi then hi = value end
      if not top_only and value < lo then lo = value end
    end
    widen(workouts.fitness_baseline)
    for i = start_idx, #recent do
      local item = recent[i]
      if item.distance_units > max_dist then max_dist = item.distance_units end
      widen(item.fitness)
      widen(item.score, true)
    end
    local scaled = lo < math.huge
    if scaled then
      lo = lo - 3
      hi = math.max(hi, lo + 4)
    end
    local function level_y(value)
      return y + h - 2 - shared.clamp((value - lo) / (hi - lo), 0, 1) * (h - 4)
    end

    local bar_gap = 3
    local bar_w = math.max(3, math.floor((w - bar_gap * (n - 1)) / n))
    local total_w = bar_w * n + bar_gap * (n - 1)
    local left_x = x + math.floor((w - total_w) / 2)

    if scaled and workouts.fitness_baseline then
      local base_y = level_y(workouts.fitness_baseline)
      ui.dash(cr, left_x, base_y, left_x + total_w, base_y, ui.line_strong, 1, 2, 2, 0.75)
    end

    local line = {}
    for idx = 1, n do
      local item = recent[start_idx + idx - 1]
      local bx = left_x + (idx - 1) * (bar_w + bar_gap)
      local frac = shared.clamp(item.distance_units / max_dist, 0.14, 1.0)
      local bh = math.max(2, math.floor(frac * h + 0.5))
      local run_share = 1
      if item.run_units and item.distance_units > 0 then
        run_share = shared.clamp(item.run_units / item.distance_units, 0, 1)
      end
      local run_h = math.floor(bh * run_share + 0.5)
      local bar_color = item.is_last and color or (item.in_window and ui.muted or ui.line_strong)
      local bar_alpha = item.is_last and 0.85 or (item.in_window and 0.55 or 0.35)
      if run_h < bh then
        ui.rect(cr, bx + 0.5, y + h - bh + 0.5, bar_w - 1, bh - 1, bar_color, 1.5, math.min(1, bar_alpha + 0.2), 1)
      end
      if run_h > 0 then
        ui.rect(cr, bx, y + h - run_h, bar_w, run_h, bar_color, 1.5, bar_alpha)
      end
      if scaled and item.fitness then line[#line + 1] = {bx + bar_w / 2, level_y(item.fitness)} end
    end

    if not scaled then return end
    for idx = 1, n do
      local item = recent[start_idx + idx - 1]
      if item.score then
        local cx = left_x + (idx - 1) * (bar_w + bar_gap) + bar_w / 2
        ui.circle(cr, cx, level_y(item.score), 1.25, item.is_last and ui.strong or ui.ink, item.is_last and 1 or 0.7)
      end
    end
    if #line >= 2 then
      ui.polyline(cr, line, color, 1.5, 0.95, true)
      draw_endpoint(cr, line[#line][1], line[#line][2], kind, color)
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

  local function draw_training(cr, workouts, width, top)
    top = top or 0
    if not workouts.ok then
      ui.text(cr, workouts.error, 0, top + 14, {size = 11, mono = true, color = ui.muted, width = width})
      return
    end
    local color = semantic_color(workouts.kind)
    local recency = short_age(workouts.last_age, workouts.last_date)
    local recency_w = recency ~= '' and (ui.width(cr, recency, 11, true) + 6) or 0
    local recency_color = workouts.last_age_days >= 10 and ui.caution or ui.muted

    local x = 0
    x = x + ui.text(cr, workouts.last_distance, x, top + 11, {size = 13.5, bold = 'bold', color = ui.ink}) + 6
    local limit = width - recency_w
    local trend_w = workouts.trend ~= '' and ui.width(cr, workouts.trend, 11, true, 'bold') or 0
    local pace = workouts.last_pace ~= '--' and workouts.last_pace or ''
    local pace_str = width < 160 and pace:gsub('/[a-zA-Z]+$', '') or pace
    local pace_inline = pace_str ~= ''
      and x + ui.width(cr, pace_str, 11, true) + (trend_w > 0 and 5 + trend_w or 0) <= limit
    if pace_inline then
      x = x + ui.text(cr, pace_str, x, top + 11, {size = 11, mono = true, color = ui.muted}) + 5
    end
    if trend_w > 0 and x + trend_w <= limit then
      ui.text(cr, workouts.trend, x, top + 11, {size = 11, mono = true, bold = 'bold', color = color})
    end
    if recency ~= '' then
      ui.text(cr, recency, width, top + 11, {size = 11, mono = true, color = recency_color, align = 'right'})
    end

    local hr_part = width < 160 and workouts.last_heart_rate:gsub('%s*bpm$', '') or workouts.last_heart_rate
    local score_part = workouts.last_score ~= '' and ('5K ' .. workouts.last_score) or ''
    local telemetry = ''
    for _, part in ipairs({pace_inline and '' or pace, score_part, workouts.last_duration, hr_part}) do
      local candidate = join({telemetry, part}, ' · ')
      if ui.width(cr, candidate, 11, true) > width then break end
      telemetry = candidate
    end
    ui.text(cr, telemetry, 0, top + 26, {size = 11, mono = true, color = ui.muted, width = width})

    if #workouts.recent >= 2 then
      draw_run_sparkline(cr, workouts, 0, top + 31, width, 18)
    else
      ui.line_between(cr, 0, top + 40, width, top + 40, color, 1.5, 0.7)
    end
  end

  local function draw_weight(cr, weight, width, top)
    top = top or 0
    if not weight.ok then
      ui.text(cr, weight.error, 0, top + 14, {size = 11, mono = true, color = ui.muted, width = width})
      return
    end
    local color = semantic_color(weight.kind)
    local right_tag = weight.stale and 'Stale' or short_age(weight.age, weight.last_date)
    local right_color = (weight.stale or weight.age_days >= 10) and ui.caution or ui.muted
    local right_w = right_tag ~= '' and (ui.width(cr, right_tag, 11, true) + 6) or 0

    local x = 0
    x = x + ui.text(cr, weight.last_weight, x, top + 11, {size = 13.5, bold = 'bold', color = ui.ink}) + 6
    if weight.trend_delta ~= '' and x + ui.width(cr, weight.trend_delta, 11, true, 'bold') <= width - right_w then
      ui.text(cr, weight.trend_delta, x, top + 11, {size = 11, mono = true, bold = 'bold', color = color})
    end
    if right_tag ~= '' then
      ui.text(cr, right_tag, width, top + 11, {size = 11, mono = true, color = right_color, align = 'right'})
    end

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

    if #weight.recent >= 2 then
      draw_weight_sparkline(cr, weight.recent, weight.kind, 0, top + 31, width, 18)
    else
      ui.line_between(cr, 0, top + 40, width, top + 40, color, 1.5, 0.7)
    end
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local sections = {
        {height = section_h, draw = draw_training, data = read_workouts()},
        {height = section_h, draw = draw_weight, data = read_weight()},
      }
      local content_height = section_h + gap + section_h
      local available = height < content_height and height - 16 or height
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
      local top = height >= content_height and (height - content_height) or 0
      for _, section in ipairs(pages[page_index]) do
        section.draw(cr, section.data, width, top)
        top = top + section.height + gap
      end
      if #pages > 1 then ui.footer(cr, page_index .. '/' .. #pages, width, height) end
    end)
  end
  return {draw = draw}
end
