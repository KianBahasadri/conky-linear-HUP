-- Daily contribution calendar beside its total and latest-day metrics.
return function(shared, repo_root)
  local github_path = repo_root .. '/cache/github-contributions.json'
  local ui = shared.ui
  local weeks_max, columns = 105, 7
  local month_names = {'Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'}
  local function parse_entries()
    local content = shared.read_file(github_path)
    if not content or not shared.json_boolean(content, 'ok', false) then
      return {}
    end

    local entries = {}
    for _, object in ipairs(shared.json_array_objects(content, 'contributions')) do
      local date = shared.json_string(object, 'date', '')
      local year, month, day = date:match('^(%d+)%-(%d+)%-(%d+)$')
      local level = shared.json_number(object, 'level', 0)
      local count = shared.json_number(object, 'count', nil)
      if year then
        table.insert(entries, {
          year = tonumber(year),
          month = tonumber(month),
          day = tonumber(day),
          level = shared.clamp(level, 0, 4),
          count = count,
        })
      end
    end

    while #entries > weeks_max * columns do
      table.remove(entries, 1)
    end

    return entries
  end

  local function weekday_offset(entry)
    if not entry then
      return 0
    end
    local stamp = os.time({ year = entry.year, month = entry.month, day = entry.day, hour = 12 })
    return (tonumber(os.date('*t', stamp).wday) or 1) - 1
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local entries = parse_entries()
      local raw = shared.read_file(github_path) or '{}'
      if #entries == 0 then
        ui.text(cr, 'Contribution data unavailable', 0, 16, {size = 13.5, color = ui.muted}); return
      end
      local total, known = 0, true
      for _, entry in ipairs(entries) do
        if entry.count == nil then known = false else total = total + entry.count end
      end
      local stale = shared.json_boolean(raw, 'stale', false)
      -- The calendar keeps whatever width the metrics and stale badge leave it.
      local metrics_width = width >= 900 and 256 or 0
      local badge_width = 0
      if stale then badge_width = ui.badge(cr, 'Stale', width, 0, 'caution', {right = true}) + 12 end
      local reserved = math.max(metrics_width, badge_width)
      local offset = weekday_offset(entries[1])
      local weeks = math.ceil((offset + #entries) / 7)
      local left, top = 24, 16
      local step = math.min((width - left - reserved) / weeks, (height - top) / 7)
      local size = math.max(1, step - 3)
      ui.text(cr, 'M', 0, top + step + size, {size = 11, mono = true, color = ui.muted})
      ui.text(cr, 'W', 0, top + step * 3 + size, {size = 11, mono = true, color = ui.muted})
      ui.text(cr, 'F', 0, top + step * 5 + size, {size = 11, mono = true, color = ui.muted})
      local prior_month, last_label_x = nil, -100
      for index, entry in ipairs(entries) do
        local slot = index - 1 + offset
        local week, day = math.floor(slot / 7), slot % 7
        local x, y = left + week * step, top + day * step
        ui.rect(cr, x, y, size, size, ui.surface, 0)
        if entry.level > 0 then ui.rect(cr, x, y, size, size, ui.accent, 0, 0.18 + entry.level * 0.18) end
        if entry.month ~= prior_month then
          if x - last_label_x >= 40 then
            ui.text(cr, month_names[entry.month], x, top - 6, {size = 11, mono = true, color = ui.muted})
            last_label_x = x
          end
          prior_month = entry.month
        end
      end
      if metrics_width > 0 then
        local x = width - metrics_width + 16
        local half = (metrics_width - 32) / 2
        local y = math.max(0, (height - 51) / 2)
        local latest = entries[#entries]
        ui.metric(cr, 'Latest day', latest.count and tostring(latest.count) or '—', x, y, half)
        ui.metric(cr, 'Last ' .. #entries .. ' days', known and tostring(total) or '—', x + half, y, half)
      end
    end)
  end
  return {draw = draw}
end
