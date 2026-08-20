return function(shared, repo_root)
  local data_path = repo_root .. '/cache/billing-usage-render.tsv'
  local font = 'JetBrains Mono'
  local pressure_max = 1.12

  -- This is the production port of docs/billing-mockups/affine-map-only.py.
  -- The affine object is intentionally the whole component: no enclosing card,
  -- title bar, legend box, or footer is drawn around it.
  -- The 280px footprint shares the resource monitor's centerline. Horizontal
  -- vectors are a compact affine projection of the selected 420px mockup;
  -- vertical geometry and all data semantics remain unchanged.
  local base_x, base_y = 133.4, 263
  local time_x, time_y = 140.5, -94
  local pressure_x, pressure_y = -127.3, -94

  local colors = {
    text = 'f8fafc',
    muted = '94a3b8',
    violet = 'c4b5fd',
    cap = 'f87171',
    now = 'facc15',
  }

  local function hex_rgb(hex)
    return tonumber(hex:sub(1, 2), 16) / 255,
      tonumber(hex:sub(3, 4), 16) / 255,
      tonumber(hex:sub(5, 6), 16) / 255
  end

  local function set_hex(cr, hex, alpha)
    local r, g, b = hex_rgb(hex)
    cairo_set_source_rgba(cr, r, g, b, alpha or 1)
  end

  local function add_stop(pattern, offset, hex, alpha)
    local r, g, b = hex_rgb(hex)
    cairo_pattern_add_color_stop_rgba(pattern, offset, r, g, b, alpha)
  end

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
      error = 'WAITING FOR BILLING DATA',
      providers = {},
    }
  end

  local function read_status()
    local content = shared.read_file(data_path)
    if not content then
      return fallback_status()
    end

    local status = fallback_status()
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
        status.period_end = meta.periodEnd or ''
        status.error = meta.error or ''
      elseif fields[1] == 'provider' then
        table.insert(status.providers, {
          id = unescape_tsv(fields[2]),
          code = unescape_tsv(fields[3]),
          color = fields[4] ~= '' and fields[4] or colors.violet,
          kind = unescape_tsv(fields[5]),
          ok = fields[6] == '1',
          stale = fields[7] == '1',
          current_pressure = tonumber(fields[8]) or 0,
          forecast_pressure = tonumber(fields[9]) or 0,
          forecast_available = fields[10] == '1',
          source = unescape_tsv(fields[11]),
          detail = unescape_tsv(fields[12]),
        })
      end
    end
    return status
  end

  local function point(time_value, pressure)
    local safe_time = shared.clamp(time_value or 0, 0, 1)
    local safe_pressure = shared.clamp(pressure or 0, 0, pressure_max)
    return base_x + time_x * safe_time + pressure_x * safe_pressure / pressure_max,
      base_y + time_y * safe_time + pressure_y * safe_pressure / pressure_max
  end

  local function domain_path(cr)
    local x0, y0 = point(0, 0)
    local x1, y1 = point(1, 0)
    local x2, y2 = point(1, pressure_max)
    local x3, y3 = point(0, pressure_max)
    cairo_move_to(cr, x0, y0)
    cairo_line_to(cr, x1, y1)
    cairo_line_to(cr, x2, y2)
    cairo_line_to(cr, x3, y3)
    cairo_close_path(cr)
  end

  local function text(cr, value, x, y, size, color, alpha, align, bold)
    cairo_select_font_face(
      cr,
      font,
      CAIRO_FONT_SLANT_NORMAL,
      bold and CAIRO_FONT_WEIGHT_BOLD or CAIRO_FONT_WEIGHT_NORMAL
    )
    cairo_set_font_size(cr, size)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, value, extents)
    local draw_x = x
    if align == 'center' then
      draw_x = x - extents.width / 2 - extents.x_bearing
    elseif align == 'right' then
      draw_x = x - extents.width - extents.x_bearing
    end
    set_hex(cr, color, alpha)
    cairo_move_to(cr, draw_x, y)
    cairo_show_text(cr, value)
  end

  local function glow_line(cr, x1, y1, x2, y2, color, width, alpha)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    for _, layer in ipairs({ { width + 7, 0.08 }, { width + 3, 0.15 } }) do
      cairo_new_path(cr)
      cairo_move_to(cr, x1, y1)
      cairo_line_to(cr, x2, y2)
      cairo_set_line_width(cr, layer[1])
      set_hex(cr, color, layer[2])
      cairo_stroke(cr)
    end
    cairo_new_path(cr)
    cairo_move_to(cr, x1, y1)
    cairo_line_to(cr, x2, y2)
    cairo_set_line_width(cr, width)
    set_hex(cr, color, alpha)
    cairo_stroke(cr)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
  end

  local function bead(cr, x, y, radius, color, alpha)
    cairo_new_path(cr)
    cairo_arc(cr, x, y, radius + 4, 0, math.pi * 2)
    set_hex(cr, color, 0.12 * alpha)
    cairo_fill(cr)
    cairo_new_path(cr)
    cairo_arc(cr, x, y, radius, 0, math.pi * 2)
    set_hex(cr, color, 0.96 * alpha)
    cairo_fill_preserve(cr)
    set_hex(cr, colors.text, 0.72 * alpha)
    cairo_set_line_width(cr, 0.8)
    cairo_stroke(cr)
  end

  local function diamond(cr, x, y, radius, color, alpha)
    cairo_new_path(cr)
    cairo_move_to(cr, x, y - radius)
    cairo_line_to(cr, x + radius, y)
    cairo_line_to(cr, x, y + radius)
    cairo_line_to(cr, x - radius, y)
    cairo_close_path(cr)
    set_hex(cr, color, 0.96 * alpha)
    cairo_set_line_width(cr, 1.6)
    cairo_stroke(cr)
  end

  local function dashed_pace_line(cr)
    local segments = 28
    for index = 0, segments - 1, 2 do
      local x1, y1 = point(index / segments, index / segments)
      local x2, y2 = point((index + 1) / segments, (index + 1) / segments)
      cairo_move_to(cr, x1, y1)
      cairo_line_to(cr, x2, y2)
    end
    set_hex(cr, colors.text, 0.19)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
  end

  local function draw_map(cr, status)
    -- The object itself is the surface and the glow is its only shadow.
    domain_path(cr)
    set_hex(cr, '8b5cf6', 0.10)
    cairo_set_line_width(cr, 12)
    cairo_stroke(cr)

    domain_path(cr)
    local background = cairo_pattern_create_linear(4, 72, 252, 262)
    add_stop(background, 0.00, '10182b', 0.90)
    add_stop(background, 0.48, '050b18', 0.88)
    add_stop(background, 1.00, '02050e', 0.78)
    cairo_set_source(cr, background)
    cairo_fill_preserve(cr)
    set_hex(cr, colors.violet, 0.30)
    cairo_set_line_width(cr, 1.1)
    cairo_stroke(cr)
    cairo_pattern_destroy(background)

    local cap_start_x, cap_start_y = point(0, 1)
    local cap_end_x, cap_end_y = point(1, 1)
    local top_start_x, top_start_y = point(0, pressure_max)
    local top_end_x, top_end_y = point(1, pressure_max)
    cairo_move_to(cr, cap_start_x, cap_start_y)
    cairo_line_to(cr, cap_end_x, cap_end_y)
    cairo_line_to(cr, top_end_x, top_end_y)
    cairo_line_to(cr, top_start_x, top_start_y)
    cairo_close_path(cr)
    set_hex(cr, colors.cap, 0.085)
    cairo_fill(cr)

    -- Calendar and pressure mesh. Calendar ticks adapt to short Februarys.
    cairo_set_line_width(cr, 1)
    for _, day in ipairs({ 7, 14, 21, 28 }) do
      if day <= status.days_in_month then
        local a_x, a_y = point(day / status.days_in_month, 0)
        local b_x, b_y = point(day / status.days_in_month, pressure_max)
        set_hex(cr, colors.text, 0.065)
        cairo_move_to(cr, a_x, a_y)
        cairo_line_to(cr, b_x, b_y)
        cairo_stroke(cr)
      end
    end
    for _, pressure in ipairs({ 0.25, 0.50, 0.75 }) do
      local a_x, a_y = point(0, pressure)
      local b_x, b_y = point(1, pressure)
      set_hex(cr, colors.text, 0.065)
      cairo_move_to(cr, a_x, a_y)
      cairo_line_to(cr, b_x, b_y)
      cairo_stroke(cr)
    end

    local now_start_x, now_start_y = point(status.elapsed, 0)
    local now_end_x, now_end_y = point(status.elapsed, pressure_max)
    local eom_start_x, eom_start_y = point(1, 0)
    local eom_end_x, eom_end_y = point(1, pressure_max)
    set_hex(cr, colors.now, 0.50)
    cairo_move_to(cr, now_start_x, now_start_y)
    cairo_line_to(cr, now_end_x, now_end_y)
    cairo_stroke(cr)
    set_hex(cr, colors.violet, 0.34)
    cairo_move_to(cr, eom_start_x, eom_start_y)
    cairo_line_to(cr, eom_end_x, eom_end_y)
    cairo_stroke(cr)
    set_hex(cr, colors.cap, 0.76)
    cairo_set_line_width(cr, 1.5)
    cairo_move_to(cr, cap_start_x, cap_start_y)
    cairo_line_to(cr, cap_end_x, cap_end_y)
    cairo_stroke(cr)
    dashed_pace_line(cr)

    local origin_x, origin_y = point(0, 0)
    text(cr, 'DAY 1', origin_x, origin_y + 17, 7.5, colors.muted, 0.62, 'center')
    text(cr, 'NOW', now_start_x + 3, now_start_y + 17, 7.5, colors.now, 0.86, 'center')
    text(cr, 'EOM', eom_start_x - 1, eom_start_y + 17, 7.5, colors.violet, 0.78, 'center')
    text(cr, 'CAP', cap_start_x + 5, cap_start_y - 2, 7.5, colors.cap, 0.90, 'left')

    local label_rows = {
      aws = 91,
      anthropic = 108,
      openrouter = 125,
      azure = 142,
    }
    local drawn = 0
    table.sort(status.providers, function(left, right)
      return left.forecast_pressure < right.forecast_pressure
    end)
    for _, provider in ipairs(status.providers) do
      if provider.ok then
        drawn = drawn + 1
        local alpha = provider.stale and 0.50 or 1
        local current_x, current_y = point(status.elapsed, provider.current_pressure)
        local forecast_x, forecast_y = point(1, provider.forecast_pressure)
        if provider.forecast_available then
          glow_line(
            cr,
            current_x,
            current_y,
            forecast_x,
            forecast_y,
            provider.color,
            provider.kind == 'prepaid' and 2.0 or 1.9,
            0.96 * alpha
          )
        end
        bead(cr, current_x, current_y, provider.kind == 'prepaid' and 4.5 or 4.3, provider.color, alpha)
        if provider.forecast_available then
          diamond(cr, forecast_x, forecast_y, provider.kind == 'prepaid' and 5.2 or 5.0, provider.color, alpha)
        end

        local label_y = label_rows[provider.id] or (88 + drawn * 17)
        local anchor_x = provider.forecast_available and forecast_x or current_x
        local anchor_y = provider.forecast_available and forecast_y or current_y
        set_hex(cr, provider.color, 0.42 * alpha)
        cairo_set_line_width(cr, 0.8)
        cairo_move_to(cr, anchor_x + 5, anchor_y)
        cairo_line_to(cr, 235, label_y - 3)
        cairo_stroke(cr)
        local label
        if provider.forecast_available then
          label = string.format('%s %.0f%%', provider.code, provider.forecast_pressure * 100)
        else
          label = provider.code .. ' --'
        end
        if provider.stale then
          label = label .. ' ~'
        end
        text(cr, label, 241, label_y, 7.0, provider.color, 0.92 * alpha, 'left', true)
      end
    end

    if drawn == 0 then
      text(cr, 'NO BILLING DATA', 205, 116, 7.5, colors.violet, 0.70, 'left', true)
      text(cr, 'CHECK BILLING LOG', 205, 133, 7.0, colors.muted, 0.55, 'left')
    end
  end

  local renderer = {}

  function renderer.draw()
    if conky_window == nil then
      return
    end
    local surface = cairo_xlib_surface_create(
      conky_window.display,
      conky_window.drawable,
      conky_window.visual,
      conky_window.width,
      conky_window.height
    )
    local cr = cairo_create(surface)
    draw_map(cr, read_status())
    cairo_destroy(cr)
    cairo_surface_destroy(surface)
  end

  return renderer
end
