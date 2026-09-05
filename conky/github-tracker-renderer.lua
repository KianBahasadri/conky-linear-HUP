-- Daily contribution calendar.
return function(shared, repo_root)
  local github_path = repo_root .. '/cache/github-contributions.json'
  local ui = shared.ui
  local weeks_max, columns = 105, 7
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
      local stale = shared.json_boolean(raw, 'stale', false)
      local badge_width = 0
      if stale then badge_width = ui.badge(cr, 'Stale', width, 0, 'caution', {right = true}) + 12 end
      local reserved = badge_width
      local offset = weekday_offset(entries[1])
      local weeks = math.ceil((offset + #entries) / 7)
      local step = math.floor(math.min((width - reserved) / weeks, height / 7))
      local size = math.max(1, step - 3)
      local left = 0
      local top = math.max(0, math.floor((height - 7 * step) / 2))
      for index, entry in ipairs(entries) do
        local slot = index - 1 + offset
        local week, day = math.floor(slot / 7), slot % 7
        local x, y = left + week * step, top + day * step
        ui.rect(cr, x, y, size, size, ui.surface, 0)
        if entry.level > 0 then ui.rect(cr, x, y, size, size, ui.accent, 0, 0.18 + entry.level * 0.18) end
      end
    end)
  end
  return {draw = draw}
end
