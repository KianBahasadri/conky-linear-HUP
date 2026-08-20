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
    violet = 'c4b5fd',
    cap = 'f87171',
    now = 'facc15',
  }

  -- Official GitHub mark path in a 16×16 viewBox (absolute M/C/Z ops).
  local github_mark_ops = {
    { 'M', 8.00000, 0.00000 },
    { 'C', 3.58000, 0.00000, 0.00000, 3.58000, 0.00000, 8.00000 },
    { 'C', 0.00000, 11.54000, 2.29000, 14.53000, 5.47000, 15.59000 },
    { 'C', 5.87000, 15.66000, 6.02000, 15.42000, 6.02000, 15.21000 },
    { 'C', 6.02000, 15.02000, 6.01000, 14.39000, 6.01000, 13.72000 },
    { 'C', 4.00000, 14.09000, 3.48000, 13.23000, 3.32000, 12.78000 },
    { 'C', 3.23000, 12.55000, 2.84000, 11.84000, 2.50000, 11.65000 },
    { 'C', 2.22000, 11.50000, 1.82000, 11.13000, 2.49000, 11.12000 },
    { 'C', 3.12000, 11.11000, 3.57000, 11.70000, 3.72000, 11.94000 },
    { 'C', 4.44000, 13.15000, 5.59000, 12.81000, 6.05000, 12.60000 },
    { 'C', 6.12000, 12.08000, 6.33000, 11.73000, 6.56000, 11.53000 },
    { 'C', 4.78000, 11.33000, 2.92000, 10.64000, 2.92000, 7.58000 },
    { 'C', 2.92000, 6.71000, 3.23000, 5.99000, 3.74000, 5.43000 },
    { 'C', 3.66000, 5.23000, 3.38000, 4.41000, 3.82000, 3.31000 },
    { 'C', 3.82000, 3.31000, 4.49000, 3.10000, 6.02000, 4.13000 },
    { 'C', 6.66000, 3.95000, 7.34000, 3.86000, 8.02000, 3.86000 },
    { 'C', 8.70000, 3.86000, 9.38000, 3.95000, 10.02000, 4.13000 },
    { 'C', 11.55000, 3.09000, 12.22000, 3.31000, 12.22000, 3.31000 },
    { 'C', 12.66000, 4.41000, 12.38000, 5.23000, 12.30000, 5.43000 },
    { 'C', 12.81000, 5.99000, 13.12000, 6.70000, 13.12000, 7.58000 },
    { 'C', 13.12000, 10.65000, 11.25000, 11.33000, 9.47000, 11.53000 },
    { 'C', 9.76000, 11.78000, 10.01000, 12.26000, 10.01000, 13.01000 },
    { 'C', 10.01000, 14.08000, 10.00000, 14.94000, 10.00000, 15.21000 },
    { 'C', 10.00000, 15.42000, 10.15000, 15.67000, 10.55000, 15.59000 },
    { 'C', 13.80645, 14.49066, 15.99912, 11.43700, 16.00000, 8.00000 },
    { 'C', 16.00000, 3.58000, 12.42000, 0.00000, 8.00000, 0.00000 },
    { 'Z' },
  }

  -- Current OpenRouter glyph from its 401.4×293.7 brand viewBox, converted
  -- to absolute Cairo curves. The second subpath preserves the central hole.
  local openrouter_mark_ops = {
    { 'M', 303.94750, 17.19926 },
    { 'C', 346.74484, 17.19926, 381.43683, 51.89253, 381.43683, 94.68859 },
    { 'C', 381.43683, 137.48465, 346.74484, 172.17792, 303.94750, 172.17792 },
    { 'L', 380.80916, 249.04036 },
    { 'C', 390.57283, 258.80349, 383.65819, 275.49703, 369.85219, 275.49703 },
    { 'L', 148.96884, 275.49703 },
    { 'C', 77.64198, 275.49703, 19.81995, 217.67501, 19.81995, 146.34814 },
    { 'C', 19.81995, 75.02127, 77.64197, 17.19926, 148.96884, 17.19926 },
    { 'L', 303.94750, 17.19926 },
    { 'Z' },
    { 'M', 148.96884, 68.85881 },
    { 'C', 106.17277, 68.85881, 71.47951, 103.55208, 71.47951, 146.34814 },
    { 'C', 71.47951, 189.14420, 106.17278, 223.83747, 148.96884, 223.83747 },
    { 'C', 191.76490, 223.83747, 226.45817, 189.14420, 226.45817, 146.34814 },
    { 'C', 226.45817, 103.55208, 191.76490, 68.85881, 148.96884, 68.85881 },
    { 'Z' },
  }

  -- Compact Azure "A" in a 50×50 viewBox. The crossbar is part of the outline
  -- so a winding fill stays solid at rail-marker size.
  local azure_mark_ops = {
    { 'M', 4, 44 },
    { 'L', 22, 8 },
    { 'L', 28, 8 },
    { 'L', 46, 44 },
    { 'L', 38, 44 },
    { 'L', 32, 30 },
    { 'L', 18, 30 },
    { 'L', 12, 44 },
    { 'Z' },
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
          color = fields[4] ~= '' and fields[4] or colors.violet,
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

  local function glow_segments(cr, segments, color, width, alpha)
    if #segments == 0 then
      return
    end
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    local function add_path()
      cairo_new_path(cr)
      for _, segment in ipairs(segments) do
        cairo_move_to(cr, segment[1], segment[2])
        cairo_line_to(cr, segment[3], segment[4])
      end
    end
    for _, layer in ipairs({ { width + 7, 0.08 }, { width + 3, 0.15 } }) do
      add_path()
      cairo_set_line_width(cr, layer[1])
      set_hex(cr, color, layer[2])
      cairo_stroke(cr)
    end
    add_path()
    cairo_set_line_width(cr, width)
    set_hex(cr, color, alpha)
    cairo_stroke(cr)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
  end

  local function glow_line(cr, x1, y1, x2, y2, color, width, alpha)
    glow_segments(cr, { { x1, y1, x2, y2 } }, color, width, alpha)
  end

  local function dotted_glow_line(cr, x1, y1, x2, y2, color, width, alpha)
    local dx, dy = x2 - x1, y2 - y1
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance <= 0 then
      return
    end
    local dash, gap = 2.4, 3.8
    local segments = {}
    local t = 0
    while t < distance do
      local t2 = math.min(t + dash, distance)
      local start_ratio = t / distance
      local end_ratio = t2 / distance
      table.insert(segments, {
        x1 + dx * start_ratio,
        y1 + dy * start_ratio,
        x1 + dx * end_ratio,
        y1 + dy * end_ratio,
      })
      t = t + dash + gap
    end
    glow_segments(cr, segments, color, width, alpha)
  end

  local function add_mark_path(cr, ops, x, y, size, view_width, view_height)
    local scale = size / view_width
    local left = x - view_width * scale / 2
    local top = y - view_height * scale / 2
    cairo_new_path(cr)
    for _, op in ipairs(ops) do
      if op[1] == 'M' then
        cairo_move_to(cr, left + op[2] * scale, top + op[3] * scale)
      elseif op[1] == 'L' then
        cairo_line_to(cr, left + op[2] * scale, top + op[3] * scale)
      elseif op[1] == 'C' then
        cairo_curve_to(
          cr,
          left + op[2] * scale,
          top + op[3] * scale,
          left + op[4] * scale,
          top + op[5] * scale,
          left + op[6] * scale,
          top + op[7] * scale
        )
      elseif op[1] == 'Z' then
        cairo_close_path(cr)
      end
    end
  end

  local function vector_mark(cr, ops, x, y, size, view_width, view_height, color, alpha)
    add_mark_path(cr, ops, x, y, size, view_width, view_height)
    set_hex(cr, color, 0.20 * alpha)
    cairo_set_line_width(cr, 4.2)
    cairo_stroke(cr)

    add_mark_path(cr, ops, x, y, size, view_width, view_height)
    set_hex(cr, color, 0.98 * alpha)
    cairo_fill_preserve(cr)
    set_hex(cr, colors.text, 0.64 * alpha)
    cairo_set_line_width(cr, 0.55)
    cairo_stroke(cr)
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

  local function provider_mark(cr, provider, x, y, alpha)
    if provider.id == 'github_actions' then
      vector_mark(cr, github_mark_ops, x, y, 13.0, 16, 16, provider.color, alpha)
    elseif provider.id == 'openrouter' then
      vector_mark(
        cr,
        openrouter_mark_ops,
        x,
        y,
        15.0,
        401.4,
        293.7,
        provider.color,
        alpha
      )
    elseif provider.id == 'azure' then
      vector_mark(cr, azure_mark_ops, x, y, 13.0, 50, 50, provider.color, alpha)
    else
      bead(cr, x, y, 4.3, provider.color, alpha)
    end
  end

  local function mark_clearance(provider)
    if provider.id == 'github_actions' then
      return 7.5
    elseif provider.id == 'openrouter' then
      return 8.8
    elseif provider.id == 'azure' then
      -- The A is wide at the base, which is the side the past trail approaches.
      return 10.5
    end
    return 5.5
  end

  local function trajectory_start_after_mark(provider, x1, y1, x2, y2)
    -- Inset the centerline by the glyph body plus the solid line's round cap.
    -- The solid trajectory then just meets the mark edge, while its wider glow
    -- blends behind the mark instead of creating either a gap or a piercing
    -- line through the logo.
    local clearance = mark_clearance(provider)
    local dx, dy = x2 - x1, y2 - y1
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance <= clearance then
      return nil, nil
    end
    local ratio = clearance / distance
    return x1 + dx * ratio, y1 + dy * ratio
  end

  local function clip_segment_outside_mark(x1, y1, x2, y2, mx, my, clearance)
    local r2 = clearance * clearance
    local function dist2(x, y)
      local dx, dy = x - mx, y - my
      return dx * dx + dy * dy
    end
    local d1 = dist2(x1, y1)
    local d2 = dist2(x2, y2)
    if d1 <= r2 and d2 <= r2 then
      return nil
    end
    if d1 > r2 and d2 > r2 then
      return x1, y1, x2, y2
    end
    local dx, dy = x2 - x1, y2 - y1
    local fx, fy = x1 - mx, y1 - my
    local a = dx * dx + dy * dy
    if a < 1e-9 then
      return nil
    end
    local b = 2 * (fx * dx + fy * dy)
    local c = fx * fx + fy * fy - r2
    local disc = b * b - 4 * a * c
    if disc < 0 then
      if d1 > r2 then
        return x1, y1, x2, y2
      end
      return nil
    end
    local root = math.sqrt(disc)
    local t_hit
    local t_a = (-b - root) / (2 * a)
    local t_b = (-b + root) / (2 * a)
    if t_a >= 0 and t_a <= 1 then
      t_hit = t_a
    elseif t_b >= 0 and t_b <= 1 then
      t_hit = t_b
    end
    if not t_hit then
      if d1 > r2 then
        return x1, y1, x2, y2
      end
      return nil
    end
    local ix, iy = x1 + dx * t_hit, y1 + dy * t_hit
    if d1 > r2 then
      return x1, y1, ix, iy
    end
    return ix, iy, x2, y2
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

  local function rounded_rectangle(cr, x, y, width, height, radius)
    local corner = math.min(radius, width / 2, height / 2)
    cairo_new_path(cr)
    cairo_arc(cr, x + width - corner, y + corner, corner, -math.pi / 2, 0)
    cairo_arc(cr, x + width - corner, y + height - corner, corner, 0, math.pi / 2)
    cairo_arc(cr, x + corner, y + height - corner, corner, math.pi / 2, math.pi)
    cairo_arc(cr, x + corner, y + corner, corner, math.pi, math.pi * 3 / 2)
    cairo_close_path(cr)
  end

  local function draw_no_data_alert(cr)
    -- Treat the empty state as a foreground error, not another annotation on
    -- the map. The veil preserves the affine context while the opaque red
    -- popup owns the center of the component and cannot be mistaken for data.
    domain_path(cr)
    set_hex(cr, '01030a', 0.58)
    cairo_fill(cr)

    local x, y, width, height = 42, 140, 196, 58
    rounded_rectangle(cr, x, y, width, height, 9)
    set_hex(cr, 'ef4444', 0.22)
    cairo_set_line_width(cr, 9)
    cairo_stroke(cr)

    rounded_rectangle(cr, x, y, width, height, 9)
    local background = cairo_pattern_create_linear(x, y, x + width, y + height)
    add_stop(background, 0.00, '7f1d1d', 0.99)
    add_stop(background, 0.48, '4c1018', 0.99)
    add_stop(background, 1.00, '25070d', 0.99)
    cairo_set_source(cr, background)
    cairo_fill_preserve(cr)
    set_hex(cr, 'fb7185', 0.96)
    cairo_set_line_width(cr, 1.6)
    cairo_stroke(cr)
    cairo_pattern_destroy(background)

    cairo_new_path(cr)
    cairo_move_to(cr, x + 9, y + 10)
    cairo_line_to(cr, x + 9, y + height - 10)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    cairo_set_line_width(cr, 2.5)
    set_hex(cr, 'f87171', 0.98)
    cairo_stroke(cr)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)

    local icon_x, icon_y = x + 25, y + height / 2
    cairo_new_path(cr)
    cairo_arc(cr, icon_x, icon_y, 10.5, 0, math.pi * 2)
    set_hex(cr, 'f87171', 0.98)
    cairo_fill(cr)
    text(cr, '!', icon_x, icon_y + 4, 11, '25070d', 1, 'center', true)

    text(cr, 'NO BILLING DATA', x + 44, y + 25, 8.2, colors.text, 1, 'left', true)
    text(cr, 'CHECK BILLING LOG', x + 44, y + 42, 6.7, 'fecaca', 0.92, 'left', true)
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
        local trail = {}
        local origin_x, origin_y = point(0, 0)
        table.insert(trail, { origin_x, origin_y })
        for _, sample in ipairs(provider.history or {}) do
          local day = sample.day or 0
          if day > 0 and day < status.day then
            local past_x, past_y = point(day / status.days_in_month, sample.pressure)
            table.insert(trail, { past_x, past_y })
          end
        end
        table.insert(trail, { current_x, current_y })
        local past_segments = {}
        local clearance = mark_clearance(provider)
        local entered_mark = false
        if #trail >= 2 then
          for index = 1, #trail - 1 do
            if entered_mark then
              break
            end
            local x1, y1 = trail[index][1], trail[index][2]
            local x2, y2 = trail[index + 1][1], trail[index + 1][2]
            local cx1, cy1, cx2, cy2 = clip_segment_outside_mark(
              x1, y1, x2, y2, current_x, current_y, clearance
            )
            if cx1 then
              table.insert(past_segments, { cx1, cy1, cx2, cy2 })
              local dx = x2 - current_x
              local dy = y2 - current_y
              if dx * dx + dy * dy <= clearance * clearance then
                entered_mark = true
              end
            else
              entered_mark = true
            end
          end
        end
        -- Only draw a past trail when there is observed history, not a lone
        -- origin-to-now diagonal for providers without daily samples.
        if #(provider.history or {}) > 0 then
          glow_segments(
            cr,
            past_segments,
            provider.color,
            provider.kind == 'prepaid' and 2.0 or 1.9,
            0.96 * alpha
          )
        end
        if provider.forecast_available then
          local line_x, line_y = trajectory_start_after_mark(
            provider, current_x, current_y, forecast_x, forecast_y
          )
          if line_x then
            dotted_glow_line(
              cr,
              line_x,
              line_y,
              forecast_x,
              forecast_y,
              provider.color,
              provider.kind == 'prepaid' and 2.0 or 1.9,
              0.96 * alpha
            )
          end
        end
        provider_mark(cr, provider, current_x, current_y, alpha)
        if provider.forecast_available then
          diamond(cr, forecast_x, forecast_y, provider.kind == 'prepaid' and 5.2 or 5.0, provider.color, alpha)
        end
      end
    end

    if drawn == 0 then
      draw_no_data_alert(cr)
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
