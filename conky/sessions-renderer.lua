return function(shared, repo_root)
  local sessions_path = repo_root .. '/cache/sessions.json'
  local font = 'JetBrains Mono'

  local panel_width = 360
  local panel_min_height = 760

  -- The tall rail keeps a generous source field above a roomy destination
  -- field. Three slots remain visible even when the live state is sparse.
  local card_height = 82
  local card_gap = 14
  local device_row = 72
  local source_top = 132
  local card_x = 208
  local jack_x = 178
  local minimum_source_rows = 3
  local minimum_session_slots = 3
  local destination_gap = 45
  local status_gap = 22
  local footer_height = 70

  local violet = '8b5cf6'
  local cyan = '00e5ff'
  local teal = '00f5d4'
  local green = '39ff88'
  local red = 'f87171'
  local muted = '94a3b8'
  local dim = '64748b'
  local text_color = 'f8fafc'

  local function json_objects(body)
    local objects = {}
    for object in body:gmatch('%b{}') do
      table.insert(objects, object)
    end
    return objects
  end

  local function json_array(content, key)
    local _, start = content:find('"' .. key .. '"%s*:%s*%[')
    if not start then
      return {}
    end
    local depth = 1
    local index = start + 1
    while index <= #content and depth > 0 do
      local character = content:sub(index, index)
      if character == '[' then
        depth = depth + 1
      elseif character == ']' then
        depth = depth - 1
      end
      index = index + 1
    end
    return json_objects(content:sub(start + 1, index - 2))
  end

  local function field(object, key)
    local value = shared.match_json_string(object, key)
    if value then
      return shared.unescape_json_string(value)
    end
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
      })
    end

    return {
      ok = true,
      devices = devices,
      sessions = sessions,
      sshd = content:match('"sshdListening"%s*:%s*true') ~= nil,
    }
  end

  local function panel_height(state)
    local device_count = state and state.devices and #state.devices or 0
    local session_count = state and state.sessions and #state.sessions or 0
    local source_rows = math.max(minimum_source_rows, device_count)
    local session_slots = math.max(minimum_session_slots, session_count)
    local destination_divider = source_top + source_rows * device_row + 1
    local card_top = destination_divider + destination_gap
    local cards_bottom = card_top + session_slots * (card_height + card_gap) - card_gap
    local status_divider = cards_bottom + status_gap
    return math.max(panel_min_height, status_divider + footer_height)
  end

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
    shared.set_hex(cr, '000000', 0.44)
    cairo_move_to(cr, x, baseline + 1.5)
    cairo_show_text(cr, label)
    shared.set_hex_shaded(cr, color, alpha or 1, 0.22)
    cairo_move_to(cr, x, baseline)
    cairo_show_text(cr, label)
  end

  local function fill_gradient(cr, x0, y0, x1, y1, stops)
    local pattern = cairo_pattern_create_linear(x0, y0, x1, y1)
    for _, stop in ipairs(stops) do
      local r, g, b = shared.shade_rgb(stop[2], stop[4])
      cairo_pattern_add_color_stop_rgba(pattern, stop[1], r, g, b, stop[3])
    end
    cairo_set_source(cr, pattern)
    cairo_fill_preserve(cr)
    cairo_pattern_destroy(pattern)
  end

  local function draw_frame(cr, x, y, width, height, accent, secondary)
    shared.rounded_rect(cr, x + 4, y + 7, width, height, 18)
    shared.set_hex(cr, accent, 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, width, height, 18)
    shared.set_hex(cr, accent, 0.15)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, width, height, 18)
    shared.set_hex(cr, secondary, 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, width, height, 18)
    fill_gradient(cr, x, y, x, y + height, {
      { 0.00, '0d1a30', 0.88 },
      { 0.06, '050d1c', 0.82 },
      { 0.80, '020617', 0.80 },
      { 1.00, '08111f', 0.85 },
    })
    shared.set_hex(cr, accent, 0.88)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 8, y + 8, width - 16, height - 16, 12)
    shared.set_hex(cr, secondary, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
  end

  local function bead(cr, x, y, size, color, alpha)
    alpha = alpha or 1
    shared.set_hex(cr, color, 0.22 * alpha)
    cairo_arc(cr, x, y, size * 2.1, 0, math.pi * 2)
    cairo_fill(cr)
    shared.set_hex_shaded(cr, color, alpha, 0.35)
    cairo_arc(cr, x, y, size, 0, math.pi * 2)
    cairo_fill(cr)
  end

  local function device_glyph(cr, kind, x, y, color, alpha)
    cairo_new_path(cr)
    shared.set_hex(cr, color, alpha or 1)
    cairo_set_line_width(cr, 1.2)
    if kind == 'phone' then
      shared.rounded_rect(cr, x - 4.5, y - 7, 9, 14, 2)
      cairo_stroke(cr)
      cairo_move_to(cr, x - 2, y - 4.6)
      cairo_line_to(cr, x + 2, y - 4.6)
      cairo_stroke(cr)
      bead(cr, x, y + 4.6, 1.0, color, alpha)
    elseif kind == 'laptop' then
      shared.rounded_rect(cr, x - 6.5, y - 6.5, 13, 9, 1.6)
      cairo_stroke(cr)
      cairo_move_to(cr, x - 9, y + 4.5)
      cairo_line_to(cr, x + 9, y + 4.5)
      cairo_stroke(cr)
    elseif kind == 'terminal' then
      shared.rounded_rect(cr, x - 8, y - 6, 16, 12, 2)
      cairo_stroke(cr)
      cairo_set_line_width(cr, 1.4)
      cairo_move_to(cr, x - 4.5, y - 2.4)
      cairo_line_to(cr, x - 1.6, y + 0.2)
      cairo_line_to(cr, x - 4.5, y + 2.8)
      cairo_stroke(cr)
      cairo_move_to(cr, x + 0.6, y + 3)
      cairo_line_to(cr, x + 4.6, y + 3)
      cairo_stroke(cr)
    elseif kind == 'alert' then
      cairo_move_to(cr, x, y - 7.5)
      cairo_line_to(cr, x + 8, y + 6)
      cairo_line_to(cr, x - 8, y + 6)
      cairo_close_path(cr)
      cairo_stroke(cr)
      cairo_set_line_width(cr, 1.6)
      cairo_move_to(cr, x, y - 3)
      cairo_line_to(cr, x, y + 1.6)
      cairo_stroke(cr)
      bead(cr, x, y + 4, 1.0, color, alpha)
    else
      shared.rounded_rect(cr, x - 8, y - 6.5, 16, 11, 1.8)
      cairo_stroke(cr)
      cairo_move_to(cr, x - 3.5, y + 7)
      cairo_line_to(cr, x + 3.5, y + 7)
      cairo_stroke(cr)
      cairo_move_to(cr, x, y + 4.5)
      cairo_line_to(cr, x, y + 7)
      cairo_stroke(cr)
    end
  end

  local function jack(cr, x, y, color, live)
    cairo_new_path(cr)
    shared.set_hex(cr, color, live and 0.16 or 0.08)
    cairo_set_line_width(cr, 4.2)
    cairo_arc(cr, x, y, 5, 0, math.pi * 2)
    cairo_stroke(cr)
    shared.set_hex(cr, color, live and 0.95 or 0.34)
    cairo_set_line_width(cr, 1.2)
    cairo_arc(cr, x, y, 5, 0, math.pi * 2)
    cairo_stroke(cr)
    if live then
      bead(cr, x, y, 2.2, color, 1)
    else
      shared.set_hex(cr, '020617', 0.9)
      cairo_arc(cr, x, y, 2.2, 0, math.pi * 2)
      cairo_fill(cr)
    end
  end

  local function cable(cr, x1, y1, x2, y2, color)
    local lift = math.max(26, math.abs(x2 - x1) * 0.42)
    local c1x, c1y = x1 + lift, y1
    local c2x, c2y = x2 - lift, y2
    local function path()
      cairo_new_path(cr)
      cairo_move_to(cr, x1, y1)
      cairo_curve_to(cr, c1x, c1y, c2x, c2y, x2, y2)
    end
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    shared.set_hex(cr, color, 0.13)
    cairo_set_line_width(cr, 5)
    path()
    cairo_stroke(cr)
    local pattern = cairo_pattern_create_linear(x1, y1, x2, y2)
    local r0, g0, b0 = shared.shade_rgb(color, -0.10)
    local r1, g1, b1 = shared.shade_rgb(color, 0.30)
    cairo_pattern_add_color_stop_rgba(pattern, 0, r0, g0, b0, 0.50)
    cairo_pattern_add_color_stop_rgba(pattern, 1, r1, g1, b1, 0.90)
    cairo_set_source(cr, pattern)
    cairo_set_line_width(cr, 1.6)
    path()
    cairo_stroke(cr)
    cairo_pattern_destroy(pattern)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
    for index = 0, 1 do
      local t = 0.34 + index * 0.24
      local mt = 1 - t
      local bx = mt ^ 3 * x1 + 3 * mt ^ 2 * t * c1x + 3 * mt * t ^ 2 * c2x + t ^ 3 * x2
      local by = mt ^ 3 * y1 + 3 * mt ^ 2 * t * c1y + 3 * mt * t ^ 2 * c2y + t ^ 3 * y2
      bead(cr, bx, by, 1.9, color, 0.9 - index * 0.22)
    end
  end

  local function status_dot(cr, x, y, state)
    cairo_new_path(cr)
    local color = green
    if state == 'alert' then color = red
    elseif state == 'idle' then color = dim end
    if state == 'alert' then
      shared.set_hex(cr, color, 0.22)
      cairo_arc(cr, x, y, 5.5, 0, math.pi * 2)
      cairo_fill(cr)
    end
    bead(cr, x, y, 2.6, color, state == 'idle' and 0.6 or 1.0)
  end

  local function session_source(state, session_name)
    for _, device in ipairs(state.devices) do
      if device.session == session_name then
        return device.name
      end
    end
    return nil
  end

  local function draw_session_card(cr, state, session, x, y, width, index)
    local live = session and session.attached ~= nil
    local tone = live and green or dim
    shared.rounded_rect(cr, x, y, width, card_height, 8)
    fill_gradient(cr, x, y, x, y + card_height, {
      { 0.00, '0d1a30', live and 0.86 or 0.58 },
      { 1.00, '020617', live and 0.78 or 0.50 },
    })
    shared.set_hex(cr, tone, live and 0.66 or 0.28)
    cairo_set_line_width(cr, 1.2)
    cairo_stroke(cr)

    shared.set_hex(cr, tone, live and 0.90 or 0.30)
    cairo_rectangle(cr, x + 1, y + 8, 2.6, card_height - 16)
    cairo_fill(cr)

    flat_text(cr, string.format('SOCKET %02d', index), x + 12, y + 16, 6.3,
      violet, 0.80)
    flat_text(cr, live and 'ATTACHED' or (session and 'DETACHED' or 'AVAILABLE'),
      x + width - 10, y + 16, 6.4, tone, live and 0.92 or 0.62, 'right')

    if session then
      lit_text(cr, session.name, x + 12, y + 37, 11,
        live and text_color or muted, live and 1.0 or 0.72)
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
      cairo_set_font_size(cr, 6.8)
      flat_text(cr, shared.truncate_title(cr, session.path, width - 24),
        x + 12, y + 53, 6.8, muted, 0.68)
      flat_text(cr, string.format('%dw / %dp', session.windows, session.panes),
        x + 12, y + 68, 6.6, dim, 0.78)
      local via = session_source(state, session.name) or session.attached
      if via then
        flat_text(cr, shared.truncate_title(cr, 'via ' .. via, width - 24),
          x + width - 10, y + 68, 6.4, teal, 0.78, 'right')
      else
        flat_text(cr, 'no inbound route', x + width - 10, y + 68, 6.4,
          dim, 0.62, 'right')
      end
    else
      flat_text(cr, 'OPEN SOCKET', x + 12, y + 37, 9.0, muted, 0.62)
      flat_text(cr, 'waiting for tmux', x + 12, y + 53, 6.8, muted, 0.52)
      flat_text(cr, 'no inbound route', x + width - 10, y + 68, 6.4,
        dim, 0.62, 'right')
    end
  end

  local function draw_source_row(cr, device, x, y, index)
    local tone = green
    if device.state == 'alert' then
      tone = red
    elseif device.state == 'idle' then
      tone = dim
    end
    local active = device.state ~= 'idle'

    shared.set_hex(cr, 'cbd5e1', 0.075)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 22, y + 50)
    cairo_line_to(cr, x + panel_width - 22, y + 50)
    cairo_stroke(cr)

    device_glyph(cr, device.glyph, x + 30, y + 14, tone, active and 0.95 or 0.48)
    flat_text(cr, string.format('IN %02d', index), x + 48, y - 1, 6.2, violet, 0.72)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 8.7)
    lit_text(cr, shared.truncate_title(cr, device.name, 96), x + 48, y + 16,
      8.7, active and text_color or muted, active and 1.0 or 0.72)
    flat_text(cr, device.os, x + 48, y + 31, 6.5, muted, 0.62)
    flat_text(cr, device.age, x + 154, y + 31, 6.5, dim, 0.68, 'right')

    jack(cr, x + jack_x, y + 14, tone, device.session ~= nil)
    status_dot(cr, x + jack_x + 16, y + 6, device.state)
    flat_text(cr, device.session and ('route ' .. device.session) or 'unpatched',
      x + 48, y + 45, 6.4, active and tone or dim, active and 0.82 or 0.58)
  end

  local function layout_for(state)
    local device_count = state and state.devices and #state.devices or 0
    local session_count = state and state.sessions and #state.sessions or 0
    local source_rows = math.max(minimum_source_rows, device_count)
    local session_slots = math.max(minimum_session_slots, session_count)
    local destination_divider = source_top + source_rows * device_row + 1
    local card_top = destination_divider + destination_gap
    local cards_bottom = card_top + session_slots * (card_height + card_gap) - card_gap
    local status_divider = cards_bottom + status_gap
    return {
      source_rows = source_rows,
      session_slots = session_slots,
      destination_divider = destination_divider,
      card_top = card_top,
      status_divider = status_divider,
      height = math.max(panel_min_height, status_divider + footer_height),
    }
  end

  local function draw_panel(cr, state, x, y, height)
    local layout = layout_for(state)
    local card_width = panel_width - card_x - 20
    local alert = false
    local live_count = 0
    local idle_count = 0
    for _, device in ipairs(state.devices) do
      if device.state == 'alert' then alert = true end
      if device.state == 'live' then live_count = live_count + 1 end
      if device.state == 'idle' then idle_count = idle_count + 1 end
    end

    draw_frame(cr, x, y, panel_width, height, alert and red or cyan, violet)

    -- Quiet vertical rails make the extra height feel intentional instead of
    -- leaving a large empty rounded rectangle.
    shared.set_hex(cr, cyan, 0.16)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 14, y + 22)
    cairo_line_to(cr, x + 14, y + height - 22)
    cairo_stroke(cr)
    shared.set_hex(cr, violet, 0.22)
    cairo_move_to(cr, x + 18, y + 22)
    cairo_line_to(cr, x + 18, y + height - 22)
    cairo_stroke(cr)

    flat_text(cr, 'PATCH BAY', x + 30, y + 31, 11, 'dbeafe', 0.92)
    flat_text(cr, 'TMUX / INBOUND ROUTING', x + 30, y + 48, 7, muted, 0.66)
    flat_text(cr, string.format('%02d IN / %02d TMUX', #state.devices, #state.sessions),
      x + panel_width - 22, y + 31, 7, muted, 0.72, 'right')
    flat_text(cr, 'LEFT RAIL', x + panel_width - 22, y + 48, 6.4,
      violet, 0.78, 'right')
    shared.set_hex(cr, cyan, 0.24)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 22, y + 67)
    cairo_line_to(cr, x + panel_width - 22, y + 67)
    cairo_stroke(cr)

    flat_text(cr, 'INBOUND SOURCES', x + 30, y + 91, 7, violet, 0.84)
    flat_text(cr, 'SOURCE / ORIGIN', x + 48, y + 108, 6.1, dim, 0.74)
    flat_text(cr, 'AGE', x + 154, y + 108, 6.1, dim, 0.74, 'right')
    flat_text(cr, 'JACK', x + jack_x + 4, y + 108, 6.1, dim, 0.74, 'center')

    local card_tops = {}
    for index = 1, layout.session_slots do
      local session = state.sessions[index]
      local cy = y + layout.card_top + (index - 1) * (card_height + card_gap)
      if session then card_tops[session.name] = cy end
      draw_session_card(cr, state, session, x + card_x, cy, card_width, index)
      jack(cr, x + card_x + 1, cy + card_height / 2,
        session and session.attached and green or dim,
        session and session.attached ~= nil)
    end

    local device_jacks = {}
    for index, device in ipairs(state.devices) do
      local sy = y + source_top + (index - 1) * device_row + 14
      device_jacks[device.name] = { x = x + jack_x, y = sy }
      if device.session and card_tops[device.session] then
        local tone = device.state == 'alert' and red or green
        cable(cr, x + jack_x + 6, sy, x + card_x + 1,
          card_tops[device.session] + card_height / 2, tone)
      elseif device.state == 'alert' then
        local stub_x = x + card_x - 12
        cable(cr, x + jack_x + 6, sy, stub_x, sy, red)
        shared.set_hex(cr, red, 0.9)
        cairo_set_line_width(cr, 1.4)
        cairo_move_to(cr, stub_x - 3, sy - 3.5)
        cairo_line_to(cr, stub_x + 3, sy + 3.5)
        cairo_move_to(cr, stub_x + 3, sy - 3.5)
        cairo_line_to(cr, stub_x - 3, sy + 3.5)
        cairo_stroke(cr)
      end
    end

    for index, device in ipairs(state.devices) do
      draw_source_row(cr, device, x, y + source_top + (index - 1) * device_row, index)
    end
    if #state.devices == 0 then
      flat_text(cr, 'no inbound sources', x + 30, y + source_top + 20, 7, dim, 0.62)
    end

    shared.set_hex(cr, violet, 0.28)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 22, y + layout.destination_divider)
    cairo_line_to(cr, x + panel_width - 22, y + layout.destination_divider)
    cairo_stroke(cr)
    flat_text(cr, 'TMUX DESTINATIONS', x + 30, y + layout.destination_divider + 24,
      7, violet, 0.84)
    flat_text(cr, 'SOCKETS / WORKTREES', x + panel_width - 22,
      y + layout.destination_divider + 24, 6.2, dim, 0.72, 'right')

    shared.set_hex(cr, violet, 0.24)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 22, y + layout.status_divider)
    cairo_line_to(cr, x + panel_width - 22, y + layout.status_divider)
    cairo_stroke(cr)
    flat_text(cr, 'ROUTING STATUS', x + 30, y + height - 46, 6.6, violet, 0.78)
    flat_text(cr, string.format('%02d LIVE', live_count), x + 30, y + height - 25,
      8, green, 0.92)
    flat_text(cr, string.format('%02d IDLE', idle_count), x + 106, y + height - 25,
      8, dim, 0.84)
    if alert then
      flat_text(cr, 'UNKNOWN', x + 182, y + height - 25, 6.6, red, 0.95)
    end
    flat_text(cr, 'TAILSCALE SSH', x + panel_width - 22, y + height - 46, 6.6,
      muted, 0.58, 'right')
    flat_text(cr, state.sshd and 'SSHD:22 OPEN' or 'SSHD:22 CLOSED',
      x + panel_width - 22, y + height - 25, 6.6, dim, 0.74, 'right')
  end

  local function draw_error(cr, state, x, y)
    draw_frame(cr, x, y, panel_width, panel_min_height, red, violet)
    flat_text(cr, 'PATCH BAY', x + 30, y + 31, 11, 'dbeafe', 0.92)
    flat_text(cr, 'SESSION DATA UNAVAILABLE', x + 30, y + 48, 7, muted, 0.66)
    shared.set_hex(cr, red, 0.24)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 22, y + 67)
    cairo_line_to(cr, x + panel_width - 22, y + 67)
    cairo_stroke(cr)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 8)
    flat_text(cr, shared.truncate_title(cr, state.error or 'error', panel_width - 60),
      x + 30, y + 112, 8, muted, 0.76)
  end

  local function needed_height()
    local state = read_state()
    if not state.ok then return panel_min_height + 8 end
    return panel_height(state) + 8
  end

  local function height_spacer()
    return string.format('${voffset %d}', needed_height())
  end

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
