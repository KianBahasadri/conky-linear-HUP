return function(shared, repo_root)
  local github_path = repo_root .. '/cache/github-contributions.json'
  local log_path = repo_root .. '/cache/conky-github.log'
  local font = 'JetBrains Mono'

  -- The lattice. A week steps straight right; a weekday steps right and away.
  -- The level week axis is the whole point: it gives the skyline a straight
  -- front edge, so it can sit on the rate limit panel's top edge as its roof
  -- instead of floating. Both basis vectors stay the same length, so plan-view
  -- cells read square. Ratios are relative to the week step.
  local day_dx_ratio = 0.5211
  local day_dy_ratio = 0.8600
  local fill = 0.86            -- cell footprint as a fraction of the step
  local deck_ratio = 0.7451    -- plinth thickness, also relative to the step
  local columns = 7
  local weeks_max = 53
  local window_inset = 4       -- Conky window border around the text area

  -- GitHub's own dark-theme ramp. Index is data-level + 1.
  local colors = { '0e4429', '0e4429', '006d32', '26a641', '39d353' }
  local deck_color = '1e293b'
  local muted = '94a3b8'
  local dim = '64748b'
  local text_color = 'f8fafc'
  local value_color = '39d353'

  -- Stat readout band above the skyline. The band is inset from the left so
  -- the first column clears the sessions panel, whose right edge meets the
  -- skyline's left edge.
  local band_height = 46
  local band_inset = 14
  local band_label_baseline = 8
  local band_value_baseline = 28
  local band_value_size = 17

  local month_names = {
    'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
    'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC',
  }

  local logged_signature = nil

  local function flat_text(cr, label, x, baseline, size, color, alpha, align)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, size)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    if align == 'right' then
      x = x - extents.x_advance
    elseif align == 'center' then
      x = x - extents.x_advance / 2
    end
    shared.set_hex(cr, color, alpha or 1)
    cairo_move_to(cr, x, baseline)
    cairo_show_text(cr, label)
    return extents.x_advance
  end

  local function lit_text(cr, label, x, baseline, size, color, alpha)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, size)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)

    shared.set_hex(cr, '000000', 0.44)
    cairo_move_to(cr, x, baseline + 1.5)
    cairo_show_text(cr, label)

    shared.set_hex_shaded(cr, color, alpha or 1, 0.24)
    cairo_move_to(cr, x, baseline)
    cairo_show_text(cr, label)
    return extents.x_advance
  end

  -- Entries are already date-sorted oldest-first by the fetcher.
  local function parse_entries()
    local content = shared.read_file(github_path)
    if not content or content:match('"ok"%s*:%s*true') == nil then
      return {}
    end

    local entries = {}
    for object in content:gmatch('{%s-"date".-}') do
      local year, month, day = object:match('"date"%s*:%s*"(%d+)%-(%d+)%-(%d+)"')
      local level = tonumber(object:match('"level"%s*:%s*(%d+)')) or 0
      local count = tonumber(object:match('"count"%s*:%s*(%d+)'))
      if not count then
        -- Cache written before counts were scraped: fall back to the level so
        -- the skyline still has a magnitude to extrude.
        count = level == 0 and 0 or level * 2
      end
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

  -- Column 0 of GitHub's calendar is a Sunday, so the first entry's weekday
  -- decides where the grid starts.
  local function weekday_offset(entry)
    if not entry then
      return 0
    end
    local stamp = os.time({ year = entry.year, month = entry.month, day = entry.day, hour = 12 })
    return (tonumber(os.date('*t', stamp).wday) or 1) - 1
  end

  local function streaks(entries)
    local best, best_end, run = 0, nil, 0
    for _, entry in ipairs(entries) do
      if entry.count > 0 then
        run = run + 1
        if run > best then
          best, best_end = run, entry
        end
      else
        run = 0
      end
    end

    local current, current_end = 0, nil
    for index = #entries, 1, -1 do
      local entry = entries[index]
      if entry.count > 0 then
        current = current + 1
        if not current_end then
          current_end = entry
        end
      elseif current > 0 or index < #entries then
        break
      end
    end

    return best, best_end, current, current_end
  end

  local function short_date(entry)
    if not entry then
      return ''
    end
    return string.format('%s %d', month_names[entry.month], entry.day)
  end

  local function with_thousands(value)
    local text = tostring(math.floor(value))
    local grouped = text:reverse():gsub('(%d%d%d)', '%1,'):reverse()
    return (grouped:gsub('^,', ''))
  end

  local function poly(cr, points)
    cairo_move_to(cr, points[1][1], points[1][2])
    for index = 2, #points do
      cairo_line_to(cr, points[index][1], points[index][2])
    end
    cairo_close_path(cr)
  end

  local function draw_tower(cr, base, height, color)
    local top = {}
    for index, point in ipairs(base) do
      top[index] = { point[1], point[2] - height }
    end

    -- Only two of the four walls face the camera: the day-0 (south) edge and
    -- the week-max (east) edge. Three fills per tower, not six.
    poly(cr, { base[1], base[2], top[2], top[1] })
    shared.set_hex_shaded(cr, color, 0.95, -0.55)
    cairo_fill(cr)

    poly(cr, { base[2], base[3], top[3], top[2] })
    shared.set_hex_shaded(cr, color, 0.95, -0.30)
    cairo_fill(cr)

    poly(cr, top)
    shared.set_hex_shaded(cr, color, 0.98, 0.12)
    cairo_fill_preserve(cr)
    shared.set_hex_shaded(cr, color, 0.70, 0.45)
    cairo_set_line_width(cr, 0.7)
    cairo_stroke(cr)
  end

  local function draw_deck(cr, geo)
    local pad = geo.week * (1 - fill) / 2
    local front_l = { geo.x - pad, geo.y }
    local front_r = { geo.x + geo.weeks * geo.week + pad, geo.y }
    local back_r = { front_r[1] + columns * geo.day_dx, geo.y - columns * geo.day_dy }
    local back_l = { front_l[1] + columns * geo.day_dx, back_r[2] }

    local function drop(point)
      return { point[1], point[2] + geo.deck }
    end

    poly(cr, { front_l, front_r, drop(front_r), drop(front_l) })
    shared.set_hex_shaded(cr, deck_color, 0.94, -0.45)
    cairo_fill(cr)

    poly(cr, { front_r, back_r, drop(back_r), drop(front_r) })
    shared.set_hex_shaded(cr, deck_color, 0.94, -0.62)
    cairo_fill(cr)

    poly(cr, { front_l, front_r, back_r, back_l })
    shared.set_hex_shaded(cr, deck_color, 0.90, -0.12)
    cairo_fill_preserve(cr)
    shared.set_hex_shaded(cr, deck_color, 0.90, 0.50)
    cairo_set_line_width(cr, 0.9)
    cairo_stroke(cr)
  end

  -- Solve for the week step that makes the plinth exactly the panel's width,
  -- then scale the extrusion to whatever vertical room is left.
  local function geometry(entries, width, height)
    local offset = weekday_offset(entries[1])
    local weeks = math.ceil((offset + #entries) / columns)

    local steps = weeks + (1 - fill) + columns * day_dx_ratio
    local week = width / steps
    local day_dx = week * day_dx_ratio
    local day_dy = week * day_dy_ratio
    local deck = week * deck_ratio

    local busiest = 0
    for _, entry in ipairs(entries) do
      if entry.count > busiest then
        busiest = entry.count
      end
    end

    local headroom = height - band_height - deck - columns * day_dy
    if headroom < 20 then
      headroom = 20
    end

    return {
      offset = offset,
      weeks = weeks,
      week = week,
      day_dx = day_dx,
      day_dy = day_dy,
      deck = deck,
      busiest = busiest,
      -- sqrt, not linear: one 133-commit day against a median of 2 would press
      -- every other tower flat into the deck under a linear scale.
      unit = busiest > 0 and headroom / math.sqrt(busiest) or 0,
    }
  end

  local function tower_height(geo, count)
    if count <= 0 then
      return 0
    end
    return geo.unit * math.sqrt(count)
  end

  local function cell_origin(geo, week, day)
    return geo.x + week * geo.week + day * geo.day_dx,
           geo.y - day * geo.day_dy
  end

  local function footprint(geo, week, day)
    local x, y = cell_origin(geo, week, day)
    local wx = geo.week * fill
    local dx = geo.day_dx * fill
    local dy = geo.day_dy * fill
    return {
      { x, y },
      { x + wx, y },
      { x + wx + dx, y - dy },
      { x + dx, y - dy },
    }
  end

  local function draw_skyline(cr, entries, geo)
    draw_deck(cr, geo)

    -- Painter's order: the far row (day 6) first, then forward. Within a row
    -- the week axis carries no depth, so nothing there can overlap.
    for day = columns - 1, 0, -1 do
      for week = 0, geo.weeks - 1 do
        local index = week * columns + day - geo.offset + 1
        local entry = entries[index]
        if entry then
          local base = footprint(geo, week, day)
          if entry.count > 0 then
            draw_tower(cr, base, tower_height(geo, entry.count), colors[entry.level + 1])
          else
            poly(cr, base)
            shared.set_hex(cr, deck_color, 0.42)
            cairo_set_line_width(cr, 0.8)
            cairo_stroke(cr)
          end
        end
      end
    end

    -- Month scale rides the plinth's fascia. Below the front edge is the panel
    -- this thing is standing on, so there is nowhere else for it to go.
    local seen = {}
    for week = 0, geo.weeks - 1 do
      local entry = entries[week * columns - geo.offset + 1]
      if entry and entry.day <= 7 and not seen[entry.month] then
        seen[entry.month] = true
        local x = cell_origin(geo, week, 0)
        flat_text(cr, month_names[entry.month], x + 3, geo.y + geo.deck - 4, 6.6, dim, 0.7)
      end
    end
  end

  local function draw_stat(cr, x, y, label, value, unit, sub)
    flat_text(cr, label, x, y + band_label_baseline, 6.8, muted, 0.7)
    local advance = lit_text(cr, value, x, y + band_value_baseline, band_value_size, value_color, 1)
    flat_text(cr, unit, x + advance + 8, y + band_value_baseline - 5, 7.2, text_color, 0.82)
    flat_text(cr, sub, x + advance + 8, y + band_value_baseline + 5, 6.6, dim, 0.72)
  end

  -- Every edge of the level skyline is horizontal and the towers reach the full
  -- width, so there are no pockets to tuck a readout into. It becomes a band
  -- across the top: a third horizontal layer above the skyline above the panel.
  local function draw_stat_band(cr, entries, geo, x, y, width)
    local total = 0
    local busiest = entries[1]
    for _, entry in ipairs(entries) do
      total = total + entry.count
      if entry.count > busiest.count then
        busiest = entry
      end
    end

    local best, best_end, current, current_end = streaks(entries)
    local first, last = entries[1], entries[#entries]
    x = x + band_inset
    width = width - band_inset
    local step = width / 4

    draw_stat(cr, x, y, 'LAST YEAR', with_thousands(total), 'contributions',
      string.format('%s, %d - %s, %d', short_date(first), first.year,
        short_date(last), last.year))
    draw_stat(cr, x + step, y, 'BUSIEST DAY', tostring(busiest.count), 'contributions',
      short_date(busiest))
    draw_stat(cr, x + step * 2, y, 'LONGEST STREAK', tostring(best), 'days',
      best_end and ('ended ' .. short_date(best_end)) or '')
    draw_stat(cr, x + step * 3, y, 'CURRENT STREAK', tostring(current), 'days',
      current_end and ('through ' .. short_date(current_end)) or '')

    shared.set_hex(cr, dim, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x, y + band_height - 12)
    cairo_line_to(cr, x + width, y + band_height - 12)
    cairo_stroke(cr)
  end

  -- Only log when the shape of the object changes, so the log tracks geometry
  -- rather than repeating every frame.
  local function log_geometry(entries, geo)
    local signature = string.format('%d/%.1f/%.1f', #entries, geo.week, geo.unit)
    if signature == logged_signature then
      return
    end
    logged_signature = signature

    local log_file = io.open(log_path, 'a')
    if not log_file then
      return
    end
    log_file:write(string.format(
      '[%s] github-tracker-renderer: skyline days=%d weeks=%d week_px=%.1f busiest=%d deck=%.1f\n',
      os.date('!%Y-%m-%dT%H:%M:%SZ'), #entries, geo.weeks, geo.week, geo.busiest, geo.deck))
    log_file:close()
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local entries = parse_entries()
    if #entries == 0 then
      cairo_destroy(cr)
      if should_destroy_surface and cairo_surface_destroy then
        cairo_surface_destroy(surface)
      end
      return
    end

    local width = conky_window.width - window_inset * 2
    local height = conky_window.height - window_inset * 2
    local geo = geometry(entries, width, height)

    -- The plinth's bottom edge is the roof line: the launcher has already put
    -- the window's bottom exactly where that has to land.
    geo.x = window_inset
    geo.y = conky_window.height - window_inset - geo.deck

    draw_skyline(cr, entries, geo)
    draw_stat_band(cr, entries, geo, window_inset, window_inset, width)
    log_geometry(entries, geo)

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
