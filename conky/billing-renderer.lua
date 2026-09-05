-- Budget map: one affine time/limit plane shared by every provider.
return function(shared, repo_root)
  local data_path = repo_root .. '/cache/billing-usage-render.tsv'
  local ui = shared.ui
  local warning_at = 90

  local function split_tsv(line)
    local fields = {}
    for field in (line .. '\t'):gmatch('(.-)\t') do
      table.insert(fields, field)
    end
    return fields
  end

  local function unescape_tsv(value)
    local placeholder = '\1'
    return (value or '')
      :gsub('\\\\', placeholder)
      :gsub('\\t', ' ')
      :gsub('\\n', ' ')
      :gsub(placeholder, '\\')
  end

  local function fallback_status()
    local now = os.date('*t')
    local days_in_month = os.date('*t', os.time({
      year = now.year,
      month = now.month + 1,
      day = 0,
      hour = 12,
    })).day
    return {
      ok = false,
      day = now.day,
      days_in_month = days_in_month,
      elapsed = now.day / days_in_month,
      error = 'Waiting for billing data',
      providers = {},
    }
  end

  local function read_status()
    local content = shared.read_file(data_path)
    if not content then
      return fallback_status()
    end

    local status = fallback_status()
    local history_by_id = {}
    for line in content:gmatch('[^\r\n]+') do
      local fields = split_tsv(line)
      if fields[1] == 'meta' then
        local meta = {}
        for index = 2, #fields - 1, 2 do
          meta[fields[index]] = unescape_tsv(fields[index + 1])
        end
        status.ok = meta.ok == '1'
        status.day = tonumber(meta.day) or status.day
        status.days_in_month = tonumber(meta.daysInMonth) or status.days_in_month
        status.elapsed = tonumber(meta.elapsedFraction) or status.elapsed
        status.error = meta.error or ''
      elseif fields[1] == 'provider' then
        table.insert(status.providers, {
          id = unescape_tsv(fields[2]),
          code = unescape_tsv(fields[3]),
          kind = unescape_tsv(fields[5]),
          ok = fields[6] == '1',
          stale = fields[7] == '1',
          current_pressure = tonumber(fields[8]) or 0,
          forecast_pressure = tonumber(fields[9]) or 0,
          forecast_available = fields[10] == '1',
          source = unescape_tsv(fields[11]),
          detail = unescape_tsv(fields[12]),
          history = {},
        })
      elseif fields[1] == 'history' then
        local id = unescape_tsv(fields[2])
        history_by_id[id] = history_by_id[id] or {}
        table.insert(history_by_id[id], {
          day = tonumber(fields[3]),
          pressure = tonumber(fields[4]) or 0,
        })
      end
    end
    for _, provider in ipairs(status.providers) do
      provider.history = history_by_id[provider.id] or provider.history
    end
    return status
  end

  local names = {aws = 'AWS', openrouter = 'OpenRouter', github_actions = 'GitHub Actions',
    blacksmith = 'Blacksmith', azure = 'Azure'}
  local logos = {aws = 'aws', openrouter = 'openrouter', github_actions = 'github-actions',
    blacksmith = 'blacksmith', azure = 'azure'}

  -- Normalize every provider to percent of its own limit and classify it the
  -- way the budget map's inspection text does.
  local function prepare(state)
    local model = {items = {}, elapsed = shared.clamp(state.elapsed, 0, 0.999), maximum = 105}
    for _, provider in ipairs(state.providers) do
      local item = {id = provider.id, name = names[provider.id] or provider.code,
        logo = logos[provider.id], stale = provider.stale, detail = provider.detail,
        ok = provider.ok, history = {}}
      if provider.ok then
        item.current = provider.current_pressure * 100
        item.forecast = provider.forecast_available and provider.forecast_pressure * 100 or nil
        table.sort(provider.history, function(a, b) return (a.day or 0) < (b.day or 0) end)
        for _, sample in ipairs(provider.history) do
          if sample.day and sample.day >= 1 and sample.day < state.day then
            item.history[#item.history + 1] = {day = sample.day,
              t = sample.day / state.days_in_month, value = sample.pressure * 100}
            model.maximum = math.max(model.maximum, sample.pressure * 100)
          end
        end
        model.maximum = math.max(model.maximum, item.current, item.forecast or 0)
      end
      if item.current and item.current > 100 then item.severity, item.status = 'danger', 'Over limit now'
      elseif item.forecast and item.forecast > 100 then item.severity, item.status = 'danger', 'Forecast over limit'
      elseif item.forecast and item.forecast >= warning_at then item.severity, item.status = 'caution', 'Near limit'
      elseif item.forecast then item.severity, item.status = 'good', 'Within limit'
      elseif item.current then item.severity, item.status = 'neutral', 'No forecast'
      else item.severity, item.status = 'danger', 'Unavailable' end
      model.items[#model.items + 1] = item
    end
    return model
  end

  -- The guide's camera: the time-zero edge is near, time recedes up and right.
  local function draw_map(cr, model, state, width, top)
    local scale = math.min(width - 32, 720) / 305
    local rise = 94 * 0.82 * scale
    local height = rise * 2 + 32
    local origin_x, origin_y = (width - 15 * scale) / 2, top + height - 16
    local function point(t, value)
      local usage = value / model.maximum
      return {origin_x + 160 * scale * t - 145 * scale * usage, origin_y - rise * t - rise * usage}
    end
    local maximum = model.maximum
    ui.polygon(cr, {point(0, 100), point(1, 100), point(1, maximum), point(0, maximum)}, ui.danger, 0.14)
    for _, t in ipairs({0, 0.25, 0.5, 0.75, 1}) do
      local a, b = point(t, 0), point(t, maximum)
      ui.line_between(cr, a[1], a[2], b[1], b[2], ui.line, 1)
    end
    local ticks = {}
    for tick = 0, maximum, 25 do ticks[#ticks + 1] = tick end
    if ticks[#ticks] < maximum then ticks[#ticks + 1] = maximum end
    for _, value in ipairs(ticks) do
      local a, b = point(0, value), point(1, value)
      if value == 100 then ui.line_between(cr, a[1], a[2], b[1], b[2], ui.danger, 1.5)
      else ui.line_between(cr, a[1], a[2], b[1], b[2], ui.line, 1) end
    end
    local near_top, near_bottom = point(0, maximum), point(0, 0)
    ui.line_between(cr, near_top[1], near_top[2], near_bottom[1], near_bottom[2], ui.line_strong, 1.5)
    local pace_end = point(1, 100)
    ui.dash(cr, near_bottom[1], near_bottom[2], pace_end[1], pace_end[2], ui.muted, 1, 2, 5, 0.5)
    local now_a, now_b = point(model.elapsed, 0), point(model.elapsed, maximum)
    ui.dash(cr, now_a[1], now_a[2], now_b[1], now_b[2], ui.ink, 1, 5, 4)

    local plotted = false
    for _, item in ipairs(model.items) do
      if item.current or item.forecast then plotted = true end
      ui.group(cr, item.stale and 0.6 or 1, function()
        local observations = {}
        for _, sample in ipairs(item.history) do observations[#observations + 1] = sample end
        if item.current then
          observations[#observations + 1] = {day = state.day, t = model.elapsed, value = item.current}
        end
        -- Only consecutive stored days join into a trail; a lone sample stays a point.
        local run = {}
        for index, sample in ipairs(observations) do
          local p = point(sample.t, sample.value)
          sample.p = p
          local previous = observations[index - 1]
          if previous and sample.day == previous.day + 1 then run[#run + 1] = p
          else
            ui.polyline(cr, run, ui.accent, 2, 1, true)
            run = {p}
          end
        end
        ui.polyline(cr, run, ui.accent, 2, 1, true)
        for _, sample in ipairs(observations) do
          ui.circle(cr, sample.p[1], sample.p[2], 2, ui.accent)
        end
        local current = item.current and point(model.elapsed, item.current)
        local forecast = item.forecast and point(1, item.forecast)
        if current and forecast then
          ui.dash(cr, current[1], current[2], forecast[1], forecast[2], ui.derived, 2, 5, 5)
          if item.current > 100 or item.forecast > 100 then
            local delta = item.forecast - item.current
            local crossing = delta ~= 0 and (100 - item.current) / delta or 0
            local boundary = point(model.elapsed + (1 - model.elapsed) * shared.clamp(crossing, 0, 1), 100)
            local from = item.current > 100 and current or boundary
            local to = item.forecast > 100 and forecast or boundary
            ui.dash(cr, from[1], from[2], to[1], to[2], ui.danger, 2, 5, 5)
          end
        end
        if current and not ui.mark(cr, item.logo, current[1], current[2], width < 480 and 16 or 22) then
          ui.circle(cr, current[1], current[2], 4, ui.accent)
          ui.circle(cr, current[1], current[2], 4, ui.canvas, 1, 2)
        end
        if forecast then
          local color = ui[item.severity] or ui.muted
          if item.severity == 'good' then
            ui.circle(cr, forecast[1], forecast[2], 5.5, ui.canvas)
            ui.circle(cr, forecast[1], forecast[2], 5.5, color, 1, 2)
          else
            local radius = item.severity == 'caution' and 4 or 0
            ui.rect(cr, forecast[1] - 5.5, forecast[2] - 5.5, 11, 11, ui.canvas, radius)
            ui.rect(cr, forecast[1] - 5.5, forecast[2] - 5.5, 11, 11, color, radius, 1, 2)
          end
        end
      end)
    end
    if not plotted then
      ui.text(cr, 'Budget data unavailable', width / 2, top + height / 2,
        {size = 14, color = ui.muted, align = 'center'})
    end
    return height
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local state = read_status()
      local model = prepare(state)
      -- An empty dataset gets a visible message rather than a healthy-looking
      -- empty plane.
      if #model.items == 0 then
        ui.callout(cr, 'Unavailable', state.error ~= '' and state.error or 'No billing data',
          0, 0, width, 'danger')
        return
      end
      local top = draw_map(cr, model, state, width, 0)
    end)
  end

  return {draw = draw}
end
