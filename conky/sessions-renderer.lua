return function(shared, repo_root)
  local sessions_path = repo_root .. '/cache/sessions.json'
  local font = 'JetBrains Mono'

  local panel_width = 360
  local panel_min_height = 760

  local content_left = 22
  local content_right = panel_width - 22
  local slot_columns = 3
  local drift_top = 112
  local drift_nominal_height = 358
  local destination_row_height = 104
  local footer_height = 70

  local green = '39ff88'
  local red = 'f87171'
  local muted = '94a3b8'
  local dim = '334155'
  local text_color = 'f8fafc'

  local function json_objects(body)
    local objects = {}
    for object in body:gmatch('%b{}') do table.insert(objects, object) end
    return objects
  end

  local function json_array(content, key)
    local _, start = content:find('"' .. key .. '"%s*:%s*%[')
    if not start then return {} end
    local depth = 1
    local index = start + 1
    while index <= #content and depth > 0 do
      local character = content:sub(index, index)
      if character == '[' then depth = depth + 1
      elseif character == ']' then depth = depth - 1 end
      index = index + 1
    end
    return json_objects(content:sub(start + 1, index - 2))
  end

  local function field(object, key)
    local value = shared.match_json_string(object, key)
    if value then return shared.unescape_json_string(value) end
    return nil
  end

  local function number_field(object, key)
    return tonumber(object:match('"' .. key .. '"%s*:%s*(%-?%d+)')) or 0
  end

  local function read_state()
    local content = shared.read_file(sessions_path)
    if not content then
      return { ok = false, error = 'Waiting for the first session scan...' }
    end
    if content:match('"ok"%s*:%s*true') == nil then
      return { ok = false, error = field(content, 'error') or 'Session data unavailable' }
    end
    local devices = {}
    for _, object in ipairs(json_array(content, 'devices')) do
      table.insert(devices, {
        name = field(object, 'name') or '?',
        os = field(object, 'os') or '',
        glyph = field(object, 'glyph') or 'monitor',
        session = field(object, 'session'),
        age = field(object, 'age') or '',
        ageSeconds = number_field(object, 'ageSeconds'),
        state = field(object, 'state') or 'idle',
      })
    end
    local sessions = {}
    for _, object in ipairs(json_array(content, 'sessions')) do
      local attached = field(object, 'attached') or ''
      table.insert(sessions, {
        name = field(object, 'name') or '?',
        windows = number_field(object, 'windows'),
        panes = number_field(object, 'panes'),
        path = field(object, 'path') or '',
        attached = attached ~= '' and attached or nil,
        idle = field(object, 'idle') or '',
        idleSeconds = number_field(object, 'idleSeconds'),
      })
    end
    return { ok = true, devices = devices, sessions = sessions, sshd = content:match('"sshdListening"%s*:%s*true') ~= nil }
  end

  local function panel_height(state)
    local session_count = state and state.sessions and #state.sessions or 0
    local session_rows = 0
    if session_count > 0 then
      session_rows = math.ceil(session_count / slot_columns)
    end
    local content_height = drift_top + drift_nominal_height + session_rows * destination_row_height + footer_height
    return math.max(panel_min_height, content_height)
  end

  local function flat_text(cr, label, x, baseline, size, color, alpha, align)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, size)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    if align == 'right' then x = x - extents.x_advance
    elseif align == 'center' then x = x - extents.x_advance / 2 end
    shared.set_hex(cr, color, alpha or 1)
    cairo_move_to(cr, x, baseline)
    cairo_show_text(cr, label)
  end

  local function fit_text(cr, value, max_width, size)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, size)
    return shared.truncate_title(cr, value or '', max_width)
  end

  local function drift_fraction(age_seconds)
    age_seconds = age_seconds or 0
    if age_seconds <= 0 then return 0.03 end
    local max_seconds = 48 * 3600
    local f = age_seconds / max_seconds
    if f < 0 then f = 0 end
    if f > 1 then f = 1 end
    return 0.03 + f * 0.92
  end

  local function column_center(index, slot_width)
    local col = (index - 1) % slot_columns
    return content_left + (col + 0.5) * slot_width
  end

  local function session_idle_for(device, sessions_by_name)
    if device.session and sessions_by_name[device.session] then
      local s = sessions_by_name[device.session]
      if s.idleSeconds and s.idleSeconds > 0 then return s.idleSeconds end
    end
    return device.ageSeconds or 0
  end

  local function hex_rgb(hex)
    return tonumber(hex:sub(1,2),16)/255, tonumber(hex:sub(3,4),16)/255, tonumber(hex:sub(5,6),16)/255
  end

  local function radial_hex(cr, cx, cy, r0, r1, stops)
    if not cairo_pattern_create_radial then
      local _, _, _ = cx, cy, r0
      shared.set_hex(cr, stops[1][2], stops[1][3] * 0.18)
      cairo_arc(cr, cx, cy, r1, 0, math.pi * 2)
      cairo_fill(cr)
      return
    end
    local pat = cairo_pattern_create_radial(cx, cy, r0, cx, cy, r1)
    for _, s in ipairs(stops) do
      local r, g, b = hex_rgb(s[2])
      cairo_pattern_add_color_stop_rgba(pat, s[1], r, g, b, s[3])
    end
    cairo_set_source(cr, pat)
    cairo_arc(cr, cx, cy, r1, 0, math.pi * 2)
    cairo_fill(cr)
    if cairo_pattern_destroy then cairo_pattern_destroy(pat) end
  end

  local function device_icon_kind(device)
    local glyph = device.glyph or ""
    local name = (device.name or ""):lower()
    if glyph == "phone" or name:find("pixel") then return "phone" end
    if glyph == "laptop" or glyph == "monitor" or glyph == "terminal" or name:match("^tty%d*") then
      return "laptop"
    end
    return nil
  end

  local function draw_phone_icon(cr, cx, cy, color, filled)
    radial_hex(cr, cx, cy, 0, 19, {{0, color, filled and 0.16 or 0.07},{0.32, color, filled and 0.06 or 0.02},{1, color, 0}})
    local w, h, r = 9.0, 14.4, 1.7
    local x, y = cx - w / 2, cy - h / 2
    shared.rounded_rect(cr, x, y, w, h, r)
    if filled then
      shared.set_hex(cr, color, 1); cairo_set_line_width(cr, 1.25); cairo_stroke(cr)
    else
      shared.set_hex(cr, color, 0.92); cairo_set_line_width(cr, 1.12); cairo_stroke(cr)
    end
    shared.set_hex(cr, color, filled and 0.18 or 0.22)
    cairo_rectangle(cr, x + 1.1, y + 2.0, w - 2.2, h - 5.2); cairo_fill(cr)
    shared.set_hex(cr, color, filled and 1 or 0.82)
    cairo_arc(cr, cx, y + h - 1.95, 0.75, 0, math.pi * 2); cairo_fill(cr)
  end

  local function draw_laptop_icon(cr, cx, cy, color, filled)
    radial_hex(cr, cx, cy, 0, 19, {{0, color, filled and 0.16 or 0.07},{0.32, color, filled and 0.06 or 0.02},{1, color, 0}})
    local sw, sh = 14.4, 8.6
    local bw, bh = 16.8, 2.4
    local sx, sy = cx - sw / 2, cy - sh / 2 - 1.65
    local bx, by = cx - bw / 2, cy + sh / 2 + 0.25
    shared.rounded_rect(cr, sx, sy, sw, sh, 1.3)
    if filled then
      shared.set_hex(cr, color, 1); cairo_set_line_width(cr, 1.25); cairo_stroke(cr)
    else
      shared.set_hex(cr, color, 0.92); cairo_set_line_width(cr, 1.12); cairo_stroke(cr)
    end
    shared.set_hex(cr, color, filled and 0.18 or 0.22)
    cairo_rectangle(cr, sx + 1.1, sy + 1.15, sw - 2.2, sh - 2.1); cairo_fill(cr)
    shared.set_hex(cr, color, filled and 0.92 or 0.78)
    cairo_rectangle(cr, bx, by, bw, bh); cairo_fill(cr)
    shared.set_hex(cr, color, filled and 1 or 0.86)
    cairo_rectangle(cr, cx - 1.85, by + bh * 0.5 - 0.35, 3.8, 0.65); cairo_fill(cr)
  end

  local function draw_nebula(cr, x, y)
    -- very subtle washes — barely visible on transparent desktop, just depth
    radial_hex(cr, x + panel_width * 0.50, y + drift_top + 88, 0, 420, {
      {0,    'f8fafc', 0.022}, {0.30, '94a3b8', 0.010}, {0.62, '64748b', 0.004}, {1, '000000', 0},
    })
    radial_hex(cr, x + 108, y + drift_top + 52, 0, 170, {
      {0, '94a3b8', 0.014}, {1, '000000', 0},
    })
    radial_hex(cr, x + 190, y + drift_top + drift_nominal_height * 0.88, 0, 220, {
      {0, '39ff88', 0.007}, {1, '000000', 0},
    })
    -- soft vignette toward edges
    if cairo_pattern_create_radial then
      local cx, cy = x + panel_width / 2, y + drift_top + drift_nominal_height / 2
      local r0, r1 = drift_nominal_height * 0.40, drift_nominal_height * 0.90
      local pat = cairo_pattern_create_radial(cx, cy, r0, cx, cy, r1)
      cairo_pattern_add_color_stop_rgba(pat, 0, 0, 0, 0, 0)
      cairo_pattern_add_color_stop_rgba(pat, 1, 0, 0, 0, 0.07)
      cairo_set_source(cr, pat)
      cairo_rectangle(cr, x + content_left, y + drift_top, panel_width - 44, drift_nominal_height)
      cairo_fill(cr)
      if cairo_pattern_destroy then cairo_pattern_destroy(pat) end
    end
  end

  local function draw_field_stars(cr, x, y, layout, slot_width, star_pos, diamond_pos)
    -- deterministic micro-stars, seeded per frame count so they don't crawl
    local seed = 42
    local function rnd() seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296 end
    for _ = 1, 30 do
      local sx = x + 8 + rnd() * (panel_width - 16)
      local sy = y + 14 + rnd() * (layout.field_height + 34)
      local too_close = false
      for _, p in ipairs(star_pos) do
        local dx, dy = sx - p[1], sy - p[2]
        if dx*dx + dy*dy < 18*18 then too_close = true; break end
      end
      if not too_close then
        for _, p in ipairs(diamond_pos) do
          local dx, dy = sx - p[1], sy - p[2]
          if dx*dx + dy*dy < 18*18 then too_close = true; break end
        end
      end
      if not too_close then
        local r = 0.45 + rnd() * 0.50
        local a = rnd() * 0.14 + 0.06
        if rnd() < 0.16 then
          radial_hex(cr, sx, sy, 0, 3.2, {{0,'f8fafc', a * 0.35},{1,'000000',0}})
        end
        shared.set_hex(cr, rnd() < 0.18 and 'e2e8f0' or 'f8fafc', a)
        cairo_arc(cr, sx, sy, r, 0, math.pi * 2)
        cairo_fill(cr)
      end
    end
  end

  local function constellation_line(cr, x1, y1, x2, y2, col, alpha)
    alpha = alpha or 0.50
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    shared.set_hex(cr, col, 0.085 * alpha / 0.50)
    cairo_set_line_width(cr, 6.0)
    cairo_move_to(cr, x1, y1); cairo_line_to(cr, x2, y2); cairo_stroke(cr)
    shared.set_hex(cr, col, 0.16 * alpha / 0.50)
    cairo_set_line_width(cr, 2.8)
    cairo_move_to(cr, x1, y1); cairo_line_to(cr, x2, y2); cairo_stroke(cr)
    shared.set_hex(cr, col, alpha)
    cairo_set_line_width(cr, 1.0)
    cairo_move_to(cr, x1, y1); cairo_line_to(cr, x2, y2); cairo_stroke(cr)
    shared.set_hex(cr, 'f8fafc', 0.16)
    cairo_set_line_width(cr, 0.45)
    cairo_move_to(cr, x1, y1); cairo_line_to(cr, x2, y2); cairo_stroke(cr)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
  end

  local function idle_tail(cr, cx, cy)
    if cairo_pattern_create_linear then
      local pat = cairo_pattern_create_linear(cx, cy + 5, cx, cy + 32)
      local r, g, b = hex_rgb(dim)
      cairo_pattern_add_color_stop_rgba(pat, 0, r, g, b, 0.32)
      cairo_pattern_add_color_stop_rgba(pat, 0.45, r, g, b, 0.10)
      cairo_pattern_add_color_stop_rgba(pat, 1, r, g, b, 0)
      cairo_set_source(cr, pat)
      cairo_set_line_width(cr, 1.2)
      cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
      cairo_move_to(cr, cx, cy + 5); cairo_line_to(cr, cx, cy + 28); cairo_stroke(cr)
      if cairo_pattern_destroy then cairo_pattern_destroy(pat) end
    else
      shared.set_hex(cr, dim, 0.12)
      cairo_set_line_width(cr, 1.1)
      cairo_move_to(cr, cx, cy + 5); cairo_line_to(cr, cx, cy + 28); cairo_stroke(cr)
    end
    for _, t in ipairs({{10,0.14,0.85},{18,0.07,0.65},{26,0.03,0.45}}) do
      shared.set_hex(cr, dim, t[2])
      cairo_arc(cr, cx, cy + t[1], t[3], 0, math.pi * 2); cairo_fill(cr)
    end
  end

  local function draw_star(cr, cx, cy, state)
    if state == 'live' then
      radial_hex(cr, cx, cy, 0, 17, {{0, green, 0.18},{0.28, green, 0.07},{0.62, green, 0.018},{1, green, 0}})
      radial_hex(cr, cx, cy, 0, 7, {{0, green, 0.14},{1, green, 0}})
      shared.set_hex(cr, green, 0.18); cairo_arc(cr, cx, cy, 3.6, 0, math.pi*2); cairo_fill(cr)
      shared.set_hex(cr, green, 1.0); cairo_arc(cr, cx, cy, 2.05, 0, math.pi*2); cairo_fill(cr)
      shared.set_hex(cr, 'ffffff', 0.86); cairo_arc(cr, cx - 0.50, cy - 0.68, 0.72, 0, math.pi*2); cairo_fill(cr)
      shared.set_hex(cr, green, 0.42); cairo_set_line_width(cr, 0.60); cairo_arc(cr, cx, cy, 2.05, 0, math.pi*2); cairo_stroke(cr)
    elseif state == 'idle' then
      radial_hex(cr, cx, cy, 0, 11, {{0, dim, 0.13},{1, dim, 0}})
      shared.set_hex(cr, dim, 0.55); cairo_arc(cr, cx, cy, 1.65, 0, math.pi*2); cairo_fill(cr)
      shared.set_hex(cr, dim, 0.34); cairo_set_line_width(cr, 0.50); cairo_arc(cr, cx, cy, 1.65, 0, math.pi*2); cairo_stroke(cr)
    elseif state == 'alert' then
      radial_hex(cr, cx, cy, 0, 15, {{0, red, 0.22},{0.32, red, 0.07},{1, red, 0}})
      shared.set_hex(cr, red, 0.20); cairo_arc(cr, cx, cy, 3.8, 0, math.pi*2); cairo_fill(cr)
      shared.set_hex(cr, red, 1.0); cairo_arc(cr, cx, cy, 2.15, 0, math.pi*2); cairo_fill(cr)
      shared.set_hex(cr, 'ffffff', 0.86); cairo_arc(cr, cx - 0.46, cy - 0.58, 0.68, 0, math.pi*2); cairo_fill(cr)
      shared.set_hex(cr, red, 0.46); cairo_set_line_width(cr, 0.60); cairo_arc(cr, cx, cy, 2.15, 0, math.pi*2); cairo_stroke(cr)
      cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
      local s = 4.6
      shared.set_hex(cr, red, 0.14); cairo_set_line_width(cr, 3.0)
      cairo_move_to(cr, cx - s, cy - s); cairo_line_to(cr, cx + s, cy + s); cairo_stroke(cr)
      cairo_move_to(cr, cx + s, cy - s); cairo_line_to(cr, cx - s, cy + s); cairo_stroke(cr)
      shared.set_hex(cr, red, 0.92); cairo_set_line_width(cr, 1.05)
      cairo_move_to(cr, cx - s, cy - s); cairo_line_to(cr, cx + s, cy + s); cairo_stroke(cr)
      cairo_move_to(cr, cx + s, cy - s); cairo_line_to(cr, cx - s, cy + s); cairo_stroke(cr)
      cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
    end
  end

  local function draw_diamond(cr, cx, cy, state)
    local r = state == 'live' and 8.2 or 6.6
    local col = state == 'live' and green or dim
    local halo = state == 'live' and 20 or 13
    radial_hex(cr, cx, cy, 0, halo, {{0, col, state == 'live' and 0.16 or 0.09},{0.45, col, state == 'live' and 0.040 or 0.022},{1, col, 0}})
    cairo_move_to(cr, cx, cy - r); cairo_line_to(cr, cx + r, cy); cairo_line_to(cr, cx, cy + r); cairo_line_to(cr, cx - r, cy); cairo_close_path(cr)
    if state == 'live' then
      if cairo_pattern_create_linear then
        local pat = cairo_pattern_create_linear(cx, cy - r, cx, cy + r)
        local rr, gg, bb = hex_rgb(green)
        cairo_pattern_add_color_stop_rgba(pat, 0, rr, gg, bb, 0.88)
        cairo_pattern_add_color_stop_rgba(pat, 0.55, rr, gg, bb, 0.46)
        cairo_pattern_add_color_stop_rgba(pat, 1, rr, gg, bb, 0.14)
        cairo_set_source(cr, pat)
        cairo_fill_preserve(cr)
        if cairo_pattern_destroy then cairo_pattern_destroy(pat) end
      else
        shared.set_hex(cr, green, 0.72); cairo_fill_preserve(cr)
      end
      shared.set_hex(cr, green, 0.84); cairo_set_line_width(cr, 1.0); cairo_stroke(cr)
      shared.set_hex(cr, 'ffffff', 0.34); cairo_set_line_width(cr, 0.45)
      cairo_move_to(cr, cx - r * 0.38, cy - r * 0.38); cairo_line_to(cr, cx, cy - r + 0.55); cairo_line_to(cr, cx + r * 0.38, cy - r * 0.38); cairo_stroke(cr)
      shared.set_hex(cr, 'ffffff', 0.72); cairo_arc(cr, cx, cy - 0.9, 0.58, 0, math.pi*2); cairo_fill(cr)
    else
      shared.set_hex(cr, '020617', 0.58); cairo_fill_preserve(cr)
      shared.set_hex(cr, dim, 0.46); cairo_set_line_width(cr, 0.90); cairo_stroke(cr)
      shared.set_hex(cr, dim, 0.11)
      cairo_move_to(cr, cx, cy - r*0.56); cairo_line_to(cr, cx + r*0.56, cy); cairo_line_to(cr, cx, cy + r*0.56); cairo_line_to(cr, cx - r*0.56, cy); cairo_close_path(cr); cairo_fill(cr)
    end
  end

  local function draw_diamond_arc(cr, positions)
    if #positions < 2 then return end
    table.sort(positions, function(a,b) return a[1] < b[1] end)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    cairo_set_dash(cr, {2.2, 5.4}, 0)
    shared.set_hex(cr, muted, 0.045); cairo_set_line_width(cr, 3.0)
    cairo_move_to(cr, positions[1][1], positions[1][2])
    for i=2,#positions do cairo_line_to(cr, positions[i][1], positions[i][2]) end; cairo_stroke(cr)
    shared.set_hex(cr, muted, 0.11); cairo_set_line_width(cr, 0.62)
    cairo_move_to(cr, positions[1][1], positions[1][2])
    for i=2,#positions do cairo_line_to(cr, positions[i][1], positions[i][2]) end; cairo_stroke(cr)
    cairo_set_dash(cr, {}, 0)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
  end

  local function layout_for(state, height)
    local session_count = state and state.sessions and #state.sessions or 0
    local session_slots = session_count
    local session_rows = 0
    if session_count > 0 then
      session_rows = math.ceil(session_count / slot_columns)
    end
    height = height or panel_height(state)
    local destination_top = height - footer_height - session_rows * destination_row_height
    local field_top = drift_top
    local field_bottom = destination_top - 14
    if field_bottom - field_top < drift_nominal_height then
      field_bottom = field_top + drift_nominal_height
    end
    return {
      session_slots = session_slots,
      session_rows = session_rows,
      destination_top = destination_top,
      field_top = field_top,
      field_bottom = field_bottom,
      field_height = field_bottom - field_top,
      status_divider = height - footer_height,
      height = height,
    }
  end

  local function draw_panel(cr, state, x, y, height)
    local layout = layout_for(state, height)
    local slot_width = (content_right - content_left) / slot_columns
    local sessions_by_name = {}
    for _, s in ipairs(state.sessions) do sessions_by_name[s.name] = s end

    -- positions
    local star_pos = {}
    local star_list = {}
    local diamond_list = {}
    local session_positions = {}
    for index, session in ipairs(state.sessions) do
      local cx = x + column_center(index, slot_width)
      local cy = y + layout.destination_top + destination_row_height * math.floor((index - 1) / slot_columns) + 46
      session_positions[session.name] = { x = cx, y = cy }
      table.insert(diamond_list, {cx, cy})
    end
    for index, device in ipairs(state.devices) do
      local cx = x + column_center(index, slot_width)
      local age = session_idle_for(device, sessions_by_name)
      local frac = drift_fraction(age)
      local cy = y + layout.field_top + 16 + frac * (layout.field_height - 32)
      table.insert(star_pos, {cx, cy})
      table.insert(star_list, {device = device, cx = cx, cy = cy, index = index})
    end

    -- depth: nebula + field stars (behind everything)
    draw_nebula(cr, x, y)
    draw_field_stars(cr, x, y, layout, slot_width, star_pos, diamond_list)

    -- constellation arc linking diamonds (faint skeleton)
    if #diamond_list >= 2 then
      draw_diamond_arc(cr, diamond_list)
    end

    local function inset_line(x1, y1, x2, y2, a, b)
      local dx, dy = x2 - x1, y2 - y1
      local len = math.sqrt(dx*dx + dy*dy)
      if len < 1 then return x1, y1, x2, y2 end
      local nx, ny = dx/len, dy/len
      return x1 + nx*a, y1 + ny*a, x2 - nx*b, y2 - ny*b
    end
    local function icon_inset(kind, state, nx, ny)
      nx, ny = math.abs(nx), math.abs(ny)
      if kind == 'phone' then
        local hw, hh = 4.5 + 0.6, 7.2 + 0.6
        local d = 1e9
        if nx > 1e-6 then d = math.min(d, hw / nx) end
        if ny > 1e-6 then d = math.min(d, hh / ny) end
        return d + 0.65
      elseif kind == 'laptop' then
        local hw, hh = 8.4 + 0.6, 5.5 + 0.6
        local d = 1e9
        if nx > 1e-6 then d = math.min(d, hw / nx) end
        if ny > 1e-6 then d = math.min(d, hh / ny) end
        return d + 0.65
      else
        return (state == 'idle' and 1.85 or 2.25) + 0.55
      end
    end
    local function diamond_inset(live, nx, ny)
      local r = live and 8.2 or 6.6
      nx, ny = math.abs(nx), math.abs(ny)
      local denom = nx + ny
      if denom < 1e-6 then return r + 0.55 end
      return r / denom + 0.65
    end

    -- filaments — live links only, behind stars/diamonds (inset so they only touch icons)
    for _, entry in ipairs(star_list) do
      local device = entry.device
      local is_live = device.state == 'live' and device.state ~= 'alert'
      if is_live then
        local targets = {}
        if device.session and session_positions[device.session] then
          table.insert(targets, session_positions[device.session])
        end
        for _, sess in ipairs(state.sessions) do
          if sess.attached and sess.attached:find(device.name, 1, true) then
            local pos = session_positions[sess.name]
            if pos then
              local already = false
              for _, t in ipairs(targets) do if t == pos then already = true; break end end
              if not already then table.insert(targets, pos) end
            end
          end
        end
        for _, target in ipairs(targets) do
          local kind = device.state ~= 'alert' and device_icon_kind(device) or nil
          local dx, dy = target.x - entry.cx, target.y - entry.cy
          local len = math.sqrt(dx*dx + dy*dy)
          local nx, ny = len > 0 and dx/len or 0, len > 0 and dy/len or 0
          local a = icon_inset(kind, device.state, nx, ny)
          local live_target = false
          for _, s in ipairs(state.sessions) do
            if session_positions[s.name] == target then live_target = s.attached ~= nil; break end
          end
          local b = diamond_inset(live_target, nx, ny)
          local x1, y1, x2, y2 = inset_line(entry.cx, entry.cy, target.x, target.y, a, b)
          constellation_line(cr, x1, y1, x2, y2, green, 0.48)
        end
      end
    end

    -- idle tails (behind stars, above filaments)
    for _, entry in ipairs(star_list) do
      if entry.device.state == 'idle' then
        idle_tail(cr, entry.cx, entry.cy)
      end
    end

    -- alert X handled inside draw_star; idle tail above is for idle only

    -- stars/icons + labels (phone/laptop with glow, fallback dot star)
    for _, entry in ipairs(star_list) do
      local device = entry.device
      local cx, cy = entry.cx, entry.cy
      local color = device.state == 'alert' and red or (device.state == 'idle' and dim or green)
      local filled = device.state == 'live' or device.state == 'alert'
      local kind = device.state ~= 'alert' and device_icon_kind(device) or nil
      if kind == 'phone' then
        draw_phone_icon(cr, cx, cy, color, filled)
      elseif kind == 'laptop' then
        draw_laptop_icon(cr, cx, cy, color, filled)
      else
        draw_star(cr, cx, cy, device.state)
      end
      local label = fit_text(cr, device.name, slot_width - 10, 8)
      local lab_color, lab_alpha, lab_w = text_color, 0.92, CAIRO_FONT_WEIGHT_BOLD
      if device.state == 'idle' then lab_color, lab_alpha, lab_w = muted, 0.70, CAIRO_FONT_WEIGHT_NORMAL
      elseif device.state == 'alert' then lab_color, lab_alpha, lab_w = red, 0.90, CAIRO_FONT_WEIGHT_BOLD end
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, lab_w)
      cairo_set_font_size(cr, 8)
      local ext = cairo_text_extents_t:create(); cairo_text_extents(cr, label, ext)
      local lx = cx - ext.x_advance / 2
      if lx < x + 6 then lx = x + 6 end
      if lx + ext.x_advance > x + panel_width - 6 then lx = x + panel_width - 6 - ext.x_advance end
      shared.set_hex(cr, lab_color, lab_alpha)
      cairo_move_to(cr, lx, cy - 18)
      cairo_show_text(cr, label)
    end
    if #state.devices == 0 then
      flat_text(cr, 'no inbound', x + panel_width / 2, y + layout.field_top + layout.field_height / 2, 8, dim, 0.52, 'center')
    end

    -- diamonds + labels
    for index, session in ipairs(state.sessions) do
      local cx = x + column_center(index, slot_width)
      local row = math.floor((index - 1) / slot_columns)
      local cy = y + layout.destination_top + row * destination_row_height + 46
      local live = session.attached ~= nil
      draw_diamond(cr, cx, cy, live and 'live' or 'idle')
      local lab = fit_text(cr, session.name, slot_width - 12, 9)
      local r = live and 8.2 or 6.6
      flat_text(cr, lab, cx, cy + r + 13, live and 9 or 8.4, live and text_color or muted, live and 0.90 or 0.72, 'center')
      if not live then
        flat_text(cr, 'open', cx, cy + r + 22, 7.0, dim, 0.44, 'center')
      end
    end
  end

  local function draw_error(cr, state, x, y)
    shared.set_hex(cr, dim, 0.16)
    cairo_set_line_width(cr, 0.6)
    cairo_move_to(cr, x + content_left, y + 64)
    cairo_line_to(cr, x + content_right, y + 64)
    cairo_stroke(cr)
    flat_text(cr, 'PATCH BAY', x + content_left, y + 31, 11, muted, 0.56)
    flat_text(cr, fit_text(cr, state.error or 'error', panel_width - 48, 9), x + content_left, y + 88, 9, red, 0.90)
  end

  local function needed_height()
    local state = read_state()
    if not state.ok then return panel_min_height + 8 end
    return panel_height(state) + 8
  end

  local function height_spacer() return string.format('${voffset %d}', needed_height()) end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then return end
    local cr = cairo_create(surface)
    local state = read_state()
    local x = math.max(4, (conky_window.width - panel_width) / 2)
    if state.ok then
      local h = panel_height(state)
      draw_panel(cr, state, x, math.max(4, conky_window.height - h - 4), h)
    else
      local h = panel_min_height
      draw_error(cr, state, x, math.max(4, conky_window.height - h - 4))
    end
    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then cairo_surface_destroy(surface) end
  end

  return { draw = draw, height_spacer = height_spacer }
end
