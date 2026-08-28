return function(shared, repo_root)
  local data_path = repo_root .. '/cache/billing-usage-render.tsv'
  local font = 'JetBrains Mono'
  local pressure_max = 1.12

  -- This is the production port of docs/billing-mockups/affine-map-only.py.
  -- The affine object is intentionally the whole component: no enclosing card,
  -- title bar, legend box, or footer is drawn around it.
  -- Scale the 420×300 mockup so the diamond is a hair under the weather
  -- card's 424px width, then tuck the vertical 18% for a flatter map read.
  -- Centered in the 456×300 window, which matches weather and leaves stroke room.
  local scale = (424 * 0.97) / 305
  local height_tuck = 0.82
  local base_x = 232 - 7.5 * scale
  local base_y = 268
  local time_x, time_y = 160 * scale, -94 * scale * height_tuck
  local pressure_x, pressure_y = -145 * scale, -94 * scale * height_tuck

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

  -- Official Microsoft Azure folded A from the 96×96 brand SVG. Left ribbon,
  -- center arrow, fold shadow, then the light right ribbon.
  local azure_left_ops = {
    { 'M', 33.33800, 6.54400 },
    { 'L', 59.37600, 6.54400 },
    { 'L', 32.34600, 86.63100 },
    { 'C', 31.77636, 88.31843, 30.19399, 89.45462, 28.41300, 89.45500 },
    { 'L', 8.14900, 89.45500 },
    { 'C', 6.81388, 89.45516, 5.56043, 88.81220, 4.78168, 87.72773 },
    { 'C', 4.00292, 86.64326, 3.79421, 85.25006, 4.22100, 83.98500 },
    { 'L', 29.40400, 9.36800 },
    { 'C', 29.97341, 7.67982, 31.55638, 6.54310, 33.33800, 6.54300 },
    { 'Z' },
  }
  local azure_arrow_ops = {
    { 'M', 71.17500, 60.26100 },
    { 'L', 29.88500, 60.26100 },
    { 'C', 29.09943, 60.26013, 28.39335, 60.74010, 28.10514, 61.47089 },
    { 'C', 27.81693, 62.20169, 28.00531, 63.03441, 28.58000, 63.57000 },
    { 'L', 55.11200, 88.33400 },
    { 'C', 55.88448, 89.05459, 56.90160, 89.45522, 57.95800, 89.45500 },
    { 'L', 81.33800, 89.45500 },
    { 'Z' },
  }
  local azure_shadow_ops = {
    { 'M', 33.33800, 6.54400 },
    { 'C', 31.53516, 6.53708, 29.93742, 7.70368, 29.39500, 9.42300 },
    { 'L', 4.25200, 83.91700 },
    { 'C', 3.79635, 85.18708, 3.98824, 86.59953, 4.76623, 87.70200 },
    { 'C', 5.54421, 88.80448, 6.81066, 89.45865, 8.16000, 89.45500 },
    { 'L', 28.94700, 89.45500 },
    { 'C', 30.52317, 89.17338, 31.82591, 88.06549, 32.35700, 86.55500 },
    { 'L', 37.37100, 71.77800 },
    { 'L', 55.28100, 88.48300 },
    { 'C', 56.03153, 89.10380, 56.97303, 89.44706, 57.94700, 89.45500 },
    { 'L', 81.24000, 89.45500 },
    { 'L', 71.02400, 60.26100 },
    { 'L', 41.24300, 60.26800 },
    { 'L', 59.47000, 6.54400 },
    { 'Z' },
  }
  local azure_right_ops = {
    { 'M', 66.59500, 9.36400 },
    { 'C', 66.02639, 7.67854, 64.44579, 6.54379, 62.66700, 6.54400 },
    { 'L', 33.64800, 6.54400 },
    { 'C', 35.42669, 6.54410, 37.00713, 7.67874, 37.57600, 9.36400 },
    { 'L', 62.76000, 83.98400 },
    { 'C', 63.18711, 85.24930, 62.97859, 86.64286, 62.19984, 87.72773 },
    { 'C', 61.42108, 88.81259, 60.16744, 89.45592, 58.83200, 89.45600 },
    { 'L', 87.85200, 89.45600 },
    { 'C', 89.18726, 89.45560, 90.44061, 88.81214, 91.21913, 87.72732 },
    { 'C', 91.99765, 86.64250, 92.20605, 85.24913, 91.77900, 83.98400 },
    { 'Z' },
  }

  -- Official AWS smile + arrowhead from the 304×182 brand SVG
  -- (Wikimedia Amazon_Web_Services_Logo.svg). The dark wordmark is omitted.
  -- Coordinates are shifted so y=108 in the original file is the top of
  -- this 306×76 view of the orange artwork only.
  local aws_smile_ops = {
    { 'M', 273.50000, 35.70000 },
    { 'C', 240.60000, 60.00000, 192.80000, 72.90000, 151.70000, 72.90000 },
    { 'C', 94.10000, 72.90000, 42.20000, 51.60000, 3.00000, 16.20000 },
    { 'C', -0.10000, 13.40000, 2.70000, 9.60000, 6.40000, 11.80000 },
    { 'C', 48.80000, 36.40000, 101.10000, 51.30000, 155.20000, 51.30000 },
    { 'C', 191.70000, 51.30000, 231.80000, 43.70000, 268.70000, 28.10000 },
    { 'C', 274.20000, 25.60000, 278.90000, 31.70000, 273.50000, 35.70000 },
    { 'Z' },
  }
  local aws_arrow_ops = {
    { 'M', 287.20000, 20.10000 },
    { 'C', 283.00000, 14.70000, 259.40000, 17.50000, 248.70000, 18.80000 },
    { 'C', 245.50000, 19.20000, 245.00000, 16.40000, 247.90000, 14.30000 },
    { 'C', 266.70000, 1.10000, 297.60000, 4.90000, 301.20000, 9.30000 },
    { 'C', 304.80000, 13.80000, 300.20000, 44.70000, 282.60000, 59.50000 },
    { 'C', 279.90000, 61.80000, 277.30000, 60.60000, 278.50000, 57.60000 },
    { 'C', 282.50000, 47.70000, 291.40000, 25.40000, 287.20000, 20.10000 },
    { 'Z' },
  }

  -- Official Blacksmith C-block in its 144×96 brand viewBox. The inner
  -- quarter-circle is the same cubic as the wordmark icon.
  local blacksmith_mark_ops = {
    { 'M', 144.00000, 0.00000 },
    { 'L', 0.00000, 0.00000 },
    { 'L', 0.00000, 48.00000 },
    { 'C', 26.50970, 48.00000, 48.00000, 69.49030, 48.00000, 96.00000 },
    { 'L', 144.00000, 96.00000 },
    { 'L', 144.00000, 0.00000 },
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

  local function domain_corners()
    local x0, y0 = point(0, 0)
    local x1, y1 = point(1, 0)
    local x2, y2 = point(1, pressure_max)
    local x3, y3 = point(0, pressure_max)
    return x0, y0, x1, y1, x2, y2, x3, y3
  end

  local function domain_path(cr)
    local x0, y0, x1, y1, x2, y2, x3, y3 = domain_corners()
    cairo_new_path(cr)
    cairo_move_to(cr, x0, y0)
    cairo_line_to(cr, x1, y1)
    cairo_line_to(cr, x2, y2)
    cairo_line_to(cr, x3, y3)
    cairo_close_path(cr)
  end

  local function fill_quad(cr, x1, y1, x2, y2, x3, y3, x4, y4, color, alpha)
    cairo_new_path(cr)
    cairo_move_to(cr, x1, y1)
    cairo_line_to(cr, x2, y2)
    cairo_line_to(cr, x3, y3)
    cairo_line_to(cr, x4, y4)
    cairo_close_path(cr)
    set_hex(cr, color, alpha)
    cairo_fill(cr)
  end

  -- Straight-down extrusion: the bottom face is the diamond translated in Y
  -- only, so the walls are vertical in screen space like a true isometric tile.
  local extrude_x, extrude_y = 0, 12

  local function draw_slab(cr)
    local ax, ay, bx, by, cx, cy, dx, dy = domain_corners()
    local ax2, ay2 = ax + extrude_x, ay + extrude_y
    local bx2, by2 = bx + extrude_x, by + extrude_y
    local cx2, cy2 = cx + extrude_x, cy + extrude_y
    local dx2, dy2 = dx + extrude_x, dy + extrude_y

    -- Soft contact shadow sits a little down-right of the tile, not sheared
    -- with a sideways extrusion.
    fill_quad(
      cr,
      ax + 4, ay + 16,
      bx + 4, by + 16,
      cx + 4, cy + 16,
      dx + 4, dy + 16,
      '000000',
      0.32
    )

    -- Painter's order: far faces first. Lit from the upper-left, so the
    -- time-axis face is the darkest and the start-of-month face is lighter.
    fill_quad(cr, dx, dy, cx, cy, cx2, cy2, dx2, dy2, '07101c', 0.94)
    fill_quad(cr, bx, by, cx, cy, cx2, cy2, bx2, by2, '152a4a', 0.96)
    fill_quad(cr, dx, dy, ax, ay, ax2, ay2, dx2, dy2, '2a3f63', 0.97)
    fill_quad(cr, ax, ay, bx, by, bx2, by2, ax2, ay2, '03060c', 0.98)

    cairo_new_path(cr)
    cairo_move_to(cr, ax2, ay2)
    cairo_line_to(cr, bx2, by2)
    set_hex(cr, '6366f1', 0.28)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
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

  local function dotted_glow_line(cr, x1, y1, x2, y2, color, width, alpha)
    local dx, dy = x2 - x1, y2 - y1
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance <= 0 then
      return
    end
    -- First dash is long enough to clear the mark glow (a 4.2px stroke around
    -- the glyph) so the forecast reads as attached instead of starting after
    -- a hole where the opening dash was painted over.
    local first_dash, dash, gap = 5.0, 2.4, 3.8
    local segments = {}
    local t = 0
    local used_first = false
    while t < distance do
      local this_dash = dash
      if not used_first then
        this_dash = first_dash
        used_first = true
      end
      local t2 = math.min(t + this_dash, distance)
      local start_ratio = t / distance
      local end_ratio = t2 / distance
      table.insert(segments, {
        x1 + dx * start_ratio,
        y1 + dy * start_ratio,
        x1 + dx * end_ratio,
        y1 + dy * end_ratio,
      })
      t = t2 + gap
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

  -- Map a brand path into pixel offsets from the mark center, sampling cubics
  -- so the convex hull follows the curve instead of cutting the control polygon.
  local function ops_local_points(ops, map_point)
    local points = {}
    local cx, cy = 0, 0
    local function add(vx, vy)
      local px, py = map_point(vx, vy)
      table.insert(points, { px, py })
    end
    for _, op in ipairs(ops) do
      if op[1] == 'M' then
        cx, cy = op[2], op[3]
        add(cx, cy)
      elseif op[1] == 'L' then
        cx, cy = op[2], op[3]
        add(cx, cy)
      elseif op[1] == 'C' then
        local x1, y1, x2, y2, x3, y3 = op[2], op[3], op[4], op[5], op[6], op[7]
        for step = 1, 4 do
          local t = step / 4
          local u = 1 - t
          add(
            u * u * u * cx + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3,
            u * u * u * cy + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3
          )
        end
        cx, cy = x3, y3
      end
    end
    return points
  end

  local function uniform_local_map(size, view_width, view_height)
    local scale = size / view_width
    local left = -view_width * scale / 2
    local top = -view_height * scale / 2
    return function(vx, vy)
      return left + vx * scale, top + vy * scale
    end
  end

  local function convex_hull(points)
    if #points <= 2 then
      return points
    end
    table.sort(points, function(left, right)
      if left[1] ~= right[1] then
        return left[1] < right[1]
      end
      return left[2] < right[2]
    end)
    local unique = { points[1] }
    for index = 2, #points do
      local previous = unique[#unique]
      local point = points[index]
      if math.abs(point[1] - previous[1]) > 1e-6 or math.abs(point[2] - previous[2]) > 1e-6 then
        table.insert(unique, point)
      end
    end
    if #unique <= 2 then
      return unique
    end
    local function cross(origin, a, b)
      return (a[1] - origin[1]) * (b[2] - origin[2]) - (a[2] - origin[2]) * (b[1] - origin[1])
    end
    local lower = {}
    for index = 1, #unique do
      while #lower >= 2 and cross(lower[#lower - 1], lower[#lower], unique[index]) <= 0 do
        table.remove(lower)
      end
      table.insert(lower, unique[index])
    end
    local upper = {}
    for index = #unique, 1, -1 do
      while #upper >= 2 and cross(upper[#upper - 1], upper[#upper], unique[index]) <= 0 do
        table.remove(upper)
      end
      table.insert(upper, unique[index])
    end
    table.remove(lower)
    table.remove(upper)
    for _, point in ipairs(upper) do
      table.insert(lower, point)
    end
    return lower
  end

  local function append_ops_points(points, ops, map_point)
    for _, point in ipairs(ops_local_points(ops, map_point)) do
      table.insert(points, point)
    end
  end

  -- AWS uses a squashed smile plus a uniformly scaled arrow, then recenters.
  -- Keep this mapping identical to aws_mark so the collider matches the ink.
  local function aws_local_maps()
    local view_h, height = 76, 10.0
    local s = height / view_h
    local smile_k = 0.55
    local pivot = 270.0
    local smile_left = 3.0
    local arrow_right = 305.0
    local left_span = pivot - smile_left
    local combined_left = pivot - left_span * smile_k
    local combined_right = arrow_right
    local ox_arrow = -s * (combined_left + combined_right) / 2
    local oy = -view_h * s / 2
    local ox_smile = ox_arrow + pivot * s * (1 - smile_k) + 1.6
    local sx_smile = s * smile_k
    return function(vx, vy)
      return ox_smile + vx * sx_smile, oy + vy * s
    end, function(vx, vy)
      return ox_arrow + vx * s, oy + vy * s
    end
  end

  local function hull_from_ops_list(pairs)
    local points = {}
    for _, item in ipairs(pairs) do
      append_ops_points(points, item[1], item[2])
    end
    return convex_hull(points)
  end

  local github_hull = hull_from_ops_list({
    { github_mark_ops, uniform_local_map(13.0, 16, 16) },
  })
  local openrouter_hull = hull_from_ops_list({
    { openrouter_mark_ops, uniform_local_map(15.0, 401.4, 293.7) },
  })
  local azure_map = uniform_local_map(14.0, 96, 96)
  local azure_hull = hull_from_ops_list({
    { azure_left_ops, azure_map },
    { azure_arrow_ops, azure_map },
    { azure_right_ops, azure_map },
  })
  local blacksmith_hull = hull_from_ops_list({
    { blacksmith_mark_ops, uniform_local_map(14.0, 144, 96) },
  })
  local aws_smile_map, aws_arrow_map = aws_local_maps()
  local aws_hull = hull_from_ops_list({
    { aws_smile_ops, aws_smile_map },
    { aws_arrow_ops, aws_arrow_map },
  })

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

  local function azure_mark(cr, x, y, alpha)
    local size, view = 14.0, 96
    local function mapped(vx, vy)
      local scale = size / view
      return x - view * scale / 2 + vx * scale,
        y - view * scale / 2 + vy * scale
    end
    local function glow_piece(ops)
      add_mark_path(cr, ops, x, y, size, view, view)
      set_hex(cr, '2892df', 0.18 * alpha)
      cairo_set_line_width(cr, 3.6)
      cairo_stroke(cr)
    end
    glow_piece(azure_left_ops)
    glow_piece(azure_arrow_ops)
    glow_piece(azure_right_ops)

    add_mark_path(cr, azure_left_ops, x, y, size, view, view)
    local lx0, ly0 = mapped(42.828, 12.688)
    local lx1, ly1 = mapped(15.787, 92.574)
    local left_g = cairo_pattern_create_linear(lx0, ly0, lx1, ly1)
    add_stop(left_g, 0, '114a8b', alpha)
    add_stop(left_g, 1, '0669bc', alpha)
    cairo_set_source(cr, left_g)
    cairo_fill(cr)
    cairo_pattern_destroy(left_g)

    add_mark_path(cr, azure_arrow_ops, x, y, size, view, view)
    set_hex(cr, '0078d4', alpha)
    cairo_fill(cr)

    add_mark_path(cr, azure_shadow_ops, x, y, size, view, view)
    local sx0, sy0 = mapped(51.275, 49.917)
    local sx1, sy1 = mapped(45.020, 52.032)
    local shadow_g = cairo_pattern_create_linear(sx0, sy0, sx1, sy1)
    add_stop(shadow_g, 0.000, '000000', 0.30 * alpha)
    add_stop(shadow_g, 0.071, '000000', 0.20 * alpha)
    add_stop(shadow_g, 0.321, '000000', 0.10 * alpha)
    add_stop(shadow_g, 0.623, '000000', 0.05 * alpha)
    add_stop(shadow_g, 1.000, '000000', 0)
    cairo_set_source(cr, shadow_g)
    cairo_fill(cr)
    cairo_pattern_destroy(shadow_g)

    add_mark_path(cr, azure_right_ops, x, y, size, view, view)
    local rx0, ry0 = mapped(47.835, 10.358)
    local rx1, ry1 = mapped(77.518, 89.439)
    local right_g = cairo_pattern_create_linear(rx0, ry0, rx1, ry1)
    add_stop(right_g, 0, '3ccbf4', alpha)
    add_stop(right_g, 1, '2892df', alpha)
    cairo_set_source(cr, right_g)
    cairo_fill(cr)
    cairo_pattern_destroy(right_g)
  end

  local function blacksmith_mark(cr, x, y, alpha)
    add_mark_path(cr, blacksmith_mark_ops, x, y, 14.0, 144, 96)
    set_hex(cr, '202020', 0.98 * alpha)
    cairo_fill(cr)
    add_mark_path(cr, blacksmith_mark_ops, x, y, 14.0, 144, 96)
    set_hex(cr, 'f0fb29', 0.98 * alpha)
    cairo_set_line_width(cr, 1.0)
    cairo_stroke(cr)
  end

  local function aws_mark(cr, x, y, alpha)
    -- Arrowhead keeps the uniform scale; the smile is squashed toward the
    -- join so the mark is less wide. Then the pair is recentered on (x, y).
    local view_h, height = 76, 10.0
    local s = height / view_h
    local smile_k = 0.55
    local pivot = 270.0
    local smile_left = 3.0
    local arrow_right = 305.0
    local left_span = pivot - smile_left
    local combined_left = pivot - left_span * smile_k
    local combined_right = arrow_right
    local ox_arrow = x - s * (combined_left + combined_right) / 2
    local oy = y - view_h * s / 2
    -- Nudge the squashed smile into the arrow so the join does not gap.
    local ox_smile = ox_arrow + pivot * s * (1 - smile_k) + 1.6
    local sx_smile = s * smile_k

    local function add_aws_path(ops, origin_x, scale_x)
      cairo_new_path(cr)
      for _, op in ipairs(ops) do
        if op[1] == 'M' then
          cairo_move_to(cr, origin_x + op[2] * scale_x, oy + op[3] * s)
        elseif op[1] == 'C' then
          cairo_curve_to(
            cr,
            origin_x + op[2] * scale_x,
            oy + op[3] * s,
            origin_x + op[4] * scale_x,
            oy + op[5] * s,
            origin_x + op[6] * scale_x,
            oy + op[7] * s
          )
        elseif op[1] == 'Z' then
          cairo_close_path(cr)
        end
      end
    end

    local function paint(ops, origin_x, scale_x, fill_it)
      add_aws_path(ops, origin_x, scale_x)
      set_hex(cr, 'ff9900', 0.18 * alpha)
      cairo_set_line_width(cr, 2.4)
      cairo_stroke(cr)
      add_aws_path(ops, origin_x, scale_x)
      set_hex(cr, 'ff9900', alpha)
      if fill_it then
        cairo_fill(cr)
      end
    end

    paint(aws_smile_ops, ox_smile, sx_smile, true)
    paint(aws_arrow_ops, ox_arrow, s, true)
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
      azure_mark(cr, x, y, alpha)
    elseif provider.id == 'blacksmith' then
      blacksmith_mark(cr, x, y, alpha)
    elseif provider.id == 'aws' then
      aws_mark(cr, x, y, alpha)
    else
      bead(cr, x, y, 4.3, provider.color, alpha)
    end
  end

  -- Outline half-width plus a hair of AA. Dilates the fill for hit-testing
  -- and backs the hull fallback off the raw envelope.
  local function mark_outline_pad(provider)
    if provider.id == 'github_actions' or provider.id == 'openrouter' then
      return 0.45
    elseif provider.id == 'blacksmith' then
      return 0.70
    elseif provider.id == 'azure' or provider.id == 'aws' then
      return 0.30
    end
    return 0.70
  end

  local function mark_collider(provider)
    local pad = mark_outline_pad(provider)
    if provider.id == 'github_actions' then
      return { hull = github_hull, pad = pad }
    elseif provider.id == 'openrouter' then
      return { hull = openrouter_hull, pad = pad }
    elseif provider.id == 'azure' then
      return { hull = azure_hull, pad = pad }
    elseif provider.id == 'blacksmith' then
      return { hull = blacksmith_hull, pad = pad }
    elseif provider.id == 'aws' then
      return { hull = aws_hull, pad = pad }
    end
    return { radius = 4.3 + pad }
  end

  local function point_in_hull(lx, ly, hull)
    local count = #hull
    if count < 3 then
      return false
    end
    for index = 1, count do
      local a = hull[index]
      local b = hull[index % count + 1]
      if (b[1] - a[1]) * (ly - a[2]) - (b[2] - a[2]) * (lx - a[1]) < -1e-6 then
        return false
      end
    end
    return true
  end

  local function mark_contains(collider, mx, my, px, py)
    if collider.hull then
      return point_in_hull(px - mx, py - my, collider.hull)
    end
    local dx, dy = px - mx, py - my
    return dx * dx + dy * dy <= collider.radius * collider.radius
  end

  local function segment_edge_t(x1, y1, x2, y2, x3, y3, x4, y4)
    local denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if math.abs(denominator) < 1e-12 then
      return nil
    end
    local t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    local u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denominator
    if t >= 0 and t <= 1 and u >= 0 and u <= 1 then
      return t
    end
    return nil
  end

  local function first_hull_hit_t(x1, y1, x2, y2, mx, my, hull)
    local best
    local count = #hull
    for index = 1, count do
      local a = hull[index]
      local b = hull[index % count + 1]
      local t = segment_edge_t(
        x1, y1, x2, y2,
        mx + a[1], my + a[2],
        mx + b[1], my + b[2]
      )
      if t and (not best or t < best) then
        best = t
      end
    end
    return best
  end

  local function add_ops_world_path(cr, ops, local_map, mx, my, reset)
    if reset then
      cairo_new_path(cr)
    else
      cairo_new_sub_path(cr)
    end
    local function to_world(vx, vy)
      local lx, ly = local_map(vx, vy)
      return mx + lx, my + ly
    end
    for _, op in ipairs(ops) do
      if op[1] == 'M' then
        cairo_move_to(cr, to_world(op[2], op[3]))
      elseif op[1] == 'L' then
        cairo_line_to(cr, to_world(op[2], op[3]))
      elseif op[1] == 'C' then
        local x1, y1 = to_world(op[2], op[3])
        local x2, y2 = to_world(op[4], op[5])
        local x3, y3 = to_world(op[6], op[7])
        cairo_curve_to(cr, x1, y1, x2, y2, x3, y3)
      elseif op[1] == 'Z' then
        cairo_close_path(cr)
      end
    end
  end

  local function add_mark_fill_path(cr, provider, mx, my)
    if provider.id == 'github_actions' then
      add_ops_world_path(
        cr, github_mark_ops, uniform_local_map(13.0, 16, 16), mx, my, true
      )
    elseif provider.id == 'openrouter' then
      add_ops_world_path(
        cr, openrouter_mark_ops, uniform_local_map(15.0, 401.4, 293.7), mx, my, true
      )
    elseif provider.id == 'azure' then
      local azure_local = uniform_local_map(14.0, 96, 96)
      add_ops_world_path(cr, azure_left_ops, azure_local, mx, my, true)
      add_ops_world_path(cr, azure_arrow_ops, azure_local, mx, my, false)
      add_ops_world_path(cr, azure_right_ops, azure_local, mx, my, false)
    elseif provider.id == 'blacksmith' then
      add_ops_world_path(
        cr, blacksmith_mark_ops, uniform_local_map(14.0, 144, 96), mx, my, true
      )
    elseif provider.id == 'aws' then
      add_ops_world_path(cr, aws_smile_ops, aws_smile_map, mx, my, true)
      add_ops_world_path(cr, aws_arrow_ops, aws_arrow_map, mx, my, false)
    else
      cairo_new_path(cr)
      cairo_arc(cr, mx, my, 4.3, 0, math.pi * 2)
      cairo_close_path(cr)
    end
  end

  local function mark_ink_contains(cr, provider, mx, my, px, py)
    cairo_save(cr)
    add_mark_fill_path(cr, provider, mx, my)
    local hit = cairo_in_fill(cr, px, py) ~= 0
    if not hit then
      cairo_set_line_width(cr, mark_outline_pad(provider) * 2)
      cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
      cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND)
      hit = cairo_in_stroke(cr, px, py) ~= 0
    end
    cairo_new_path(cr)
    cairo_restore(cr)
    return hit
  end

  -- First filled-ink crossing from (x1,y1) toward (x2,y2), as a t in [0,1].
  -- Starts near the hull so thin strokes are not missed; nil if the ray
  -- never hits paint (holes, AWS negative space).
  local function first_ink_t(cr, provider, x1, y1, x2, y2, mx, my, hull_t, distance)
    local dx, dy = x2 - x1, y2 - y1
    local start_t = 0
    if hull_t then
      start_t = math.max(0, hull_t - 2.5 / distance)
    end
    local step = 0.35 / distance
    local limit_t = 1
    if hull_t then
      limit_t = math.min(1, hull_t + 12.0 / distance)
    end
    local found
    local t = start_t
    while t <= limit_t do
      if mark_ink_contains(cr, provider, mx, my, x1 + dx * t, y1 + dy * t) then
        found = t
        break
      end
      t = t + step
    end
    if not found then
      return nil
    end
    local lo, hi = math.max(start_t, found - step), found
    for _ = 1, 12 do
      local mid = (lo + hi) / 2
      if mark_ink_contains(cr, provider, mx, my, x1 + dx * mid, y1 + dy * mid) then
        hi = mid
      else
        lo = mid
      end
    end
    return lo
  end

  -- t along outside->inside where the stroke should stop. Prefers the real
  -- ink edge; falls back to the convex hull when the ray would dive into a
  -- concavity or hole (more than a couple of pixels of empty hull).
  local function contact_t_from_outside(cr, provider, x1, y1, x2, y2, mx, my)
    local collider = mark_collider(provider)
    local dx, dy = x2 - x1, y2 - y1
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance < 1e-9 then
      return nil
    end
    local hull_t
    if collider.hull then
      hull_t = first_hull_hit_t(x1, y1, x2, y2, mx, my, collider.hull)
    end
    local ink_t = first_ink_t(
      cr, provider, x1, y1, x2, y2, mx, my, hull_t, distance
    )
    -- Ink t is already just outside the dilated fill (outline included).
    -- Hull t is the raw fill envelope, so back up by the outline pad.
    -- Prefer ink so the stroke meets the painted edge; hull is only the
    -- fallback when the ray misses the artwork (holes, AWS negative space).
    local pad_t = collider.pad / distance
    if ink_t then
      return ink_t
    end
    if hull_t then
      return hull_t - pad_t
    end
    return nil
  end

  local function clip_circle_outside_mark(x1, y1, x2, y2, mx, my, radius)
    local r2 = radius * radius
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

  local function clip_segment_outside_mark(cr, provider, x1, y1, x2, y2, mx, my, collider)
    if not collider.hull then
      return clip_circle_outside_mark(x1, y1, x2, y2, mx, my, collider.radius)
    end
    local inside1 = point_in_hull(x1 - mx, y1 - my, collider.hull)
    local inside2 = point_in_hull(x2 - mx, y2 - my, collider.hull)
    if inside1 and inside2 then
      return nil
    end
    local dx, dy = x2 - x1, y2 - y1
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance < 1e-9 then
      return nil
    end
    if not inside1 and not inside2 then
      return x1, y1, x2, y2
    end
    if not inside1 then
      local stop = contact_t_from_outside(cr, provider, x1, y1, x2, y2, mx, my)
      if not stop or stop <= 0.0 then
        return nil
      end
      return x1, y1, x1 + dx * stop, y1 + dy * stop
    end
    local start = contact_t_from_outside(cr, provider, x2, y2, x1, y1, mx, my)
    if not start then
      return nil
    end
    -- start is t along (x2 -> x1); convert to t along (x1 -> x2).
    start = 1 - start
    if start >= 1.0 then
      return nil
    end
    return x1 + dx * start, y1 + dy * start, x2, y2
  end

  local function trajectory_start_after_mark(cr, provider, mx, my, forecast_x, forecast_y)
    -- Walk from the EOM point back toward the glyph and start the dotted
    -- forecast just outside the ink.
    local collider = mark_collider(provider)
    local dx, dy = mx - forecast_x, my - forecast_y
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance <= 1e-9 then
      return nil, nil
    end
    if collider.hull then
      local t = contact_t_from_outside(
        cr, provider, forecast_x, forecast_y, mx, my, mx, my
      )
      if not t or t <= 0.0 then
        return nil, nil
      end
      return forecast_x + dx * t, forecast_y + dy * t
    end
    local clearance = collider.radius
    if distance <= clearance then
      return nil, nil
    end
    local ratio = 1 - clearance / distance
    return forecast_x + dx * ratio, forecast_y + dy * ratio
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

    local x, y, width, height = 134, 132, 196, 58
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
    draw_slab(cr)

    domain_path(cr)
    set_hex(cr, '8b5cf6', 0.10)
    cairo_set_line_width(cr, 12)
    cairo_stroke(cr)

    domain_path(cr)
    local gx0, gy0 = point(0, pressure_max)
    local gx1, gy1 = point(1, 0)
    local background = cairo_pattern_create_linear(gx0, gy0, gx1, gy1)
    add_stop(background, 0.00, '243044', 0.94)
    add_stop(background, 0.42, '0c1424', 0.90)
    add_stop(background, 1.00, '02050e', 0.86)
    cairo_set_source(cr, background)
    cairo_fill_preserve(cr)
    set_hex(cr, colors.violet, 0.30)
    cairo_set_line_width(cr, 1.1)
    cairo_stroke(cr)
    cairo_pattern_destroy(background)

    -- Lit rim along the two near edges so the top plane separates from the slab.
    local ax, ay, bx, by, _, _, dx, dy = domain_corners()
    cairo_new_path(cr)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    set_hex(cr, 'c4b5fd', 0.42)
    cairo_set_line_width(cr, 1.6)
    cairo_move_to(cr, dx, dy)
    cairo_line_to(cr, ax, ay)
    cairo_line_to(cr, bx, by)
    cairo_stroke(cr)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)

    local cap_start_x, cap_start_y = point(0, 1)
    local cap_end_x, cap_end_y = point(1, 1)
    local top_start_x, top_start_y = point(0, pressure_max)
    local top_end_x, top_end_y = point(1, pressure_max)
    cairo_new_path(cr)
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
        -- Observed days only. Anchoring the trail at the month origin drew a
        -- straight full-month diagonal for a provider holding a single sample,
        -- claiming a history the store does not have.
        local trail = {}
        for _, sample in ipairs(provider.history or {}) do
          local day = sample.day or 0
          if day > 0 and day < status.day then
            local past_x, past_y = point(day / status.days_in_month, sample.pressure)
            table.insert(trail, { past_x, past_y })
          end
        end
        local has_past_samples = #trail > 0
        table.insert(trail, { current_x, current_y })
        local past_segments = {}
        local collider = mark_collider(provider)
        local entered_mark = false
        if #trail >= 2 then
          for index = 1, #trail - 1 do
            if entered_mark then
              break
            end
            local x1, y1 = trail[index][1], trail[index][2]
            local x2, y2 = trail[index + 1][1], trail[index + 1][2]
            local cx1, cy1, cx2, cy2 = clip_segment_outside_mark(
              cr, provider, x1, y1, x2, y2, current_x, current_y, collider
            )
            if cx1 then
              table.insert(past_segments, { cx1, cy1, cx2, cy2 })
              if mark_contains(collider, current_x, current_y, x2, y2) then
                entered_mark = true
              end
            else
              entered_mark = true
            end
          end
        end
        -- Only draw a past trail when there is observed history, not a lone
        -- origin-to-now diagonal for providers without daily samples.
        if has_past_samples then
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
            cr, provider, current_x, current_y, forecast_x, forecast_y
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
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    draw_map(cr, read_status())
    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return renderer
end
