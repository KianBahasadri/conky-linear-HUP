return function(shared, repo_root)
  local sessions_path = repo_root .. '/cache/sessions.json'
  local font = 'JetBrains Mono'

  local panel_width = 360
  local panel_min_height = 760

  -- The HUD keeps inbound sources in a top row and tmux sockets in a bottom
  -- row. Three columns remain visible even when the live state is sparse.
  local content_left = 22
  local content_right = panel_width - 22
  local slot_columns = 3
  local source_top = 112
  local source_row_height = 88
  local source_jack_offset = 76
  local route_gap = 350
  local destination_row_height = 104
  local destination_socket_offset = 10
  local footer_height = 70

  local violet = 'a78bfa'
  local cyan = '00e5ff'
  local teal = '00f5d4'
  local green = '39ff88'
  local red = 'f87171'
  local muted = '94a3b8'
  local dim = '334155'
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

  local function row_count(item_count)
    return math.max(1, math.ceil(math.max(1, item_count or 0) / slot_columns))
  end

  local function panel_height(state)
    local device_count = state and state.devices and #state.devices or 0
    local session_count = state and state.sessions and #state.sessions or 0
    local source_rows = row_count(device_count)
    local session_slots = math.max(slot_columns, session_count)
    local session_rows = row_count(session_slots)
    local content_height = source_top
      + source_rows * source_row_height
      + route_gap
      + session_rows * destination_row_height
      + footer_height
    return math.max(panel_min_height, content_height)
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

  local function fit_text(cr, value, max_width, size)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, size)
    return shared.truncate_title(cr, value or '', max_width)
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
    local lift = math.max(24, math.abs(y2 - y1) * 0.36)
    local c1x, c1y = x1, y1 + lift
    local c2x, c2y = x2, y2 - lift
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

  local function slot_position(index, top, row_height, slot_width)
    local zero_index = index - 1
    local column = zero_index % slot_columns
    local row = math.floor(zero_index / slot_columns)
    return content_left + (column + 0.5) * slot_width,
      top + row * row_height
  end

  local function draw_session_card(cr, state, session, center_x, y, width, index)
    local live = session and session.attached ~= nil
    local tone = live and green or dim
    local socket_y = y + destination_socket_offset
    local text_width = width - 14

    jack(cr, center_x, socket_y, tone, live)
    status_dot(cr, center_x + 10, socket_y, live and 'live' or 'idle')
    flat_text(cr, string.format('SOCKET %02d', index), center_x - width / 2 + 7, y + 25,
      6.2, violet, 0.80)
    flat_text(cr, live and 'ATTACHED' or (session and 'DETACHED' or 'AVAILABLE'),
      center_x + width / 2 - 7, y + 25, 6.2, tone, live and 0.92 or 0.62, 'right')

    if session then
      flat_text(cr, fit_text(cr, session.name, text_width, 8.8), center_x, y + 46,
        8.8, live and text_color or muted, live and 1.0 or 0.72, 'center')
      flat_text(cr, fit_text(cr, session.path, text_width, 6.5), center_x, y + 61,
        6.5, muted, 0.68, 'center')
      flat_text(cr, string.format('%dw / %dp', session.windows, session.panes), center_x,
        y + 76, 6.4, dim, 0.78, 'center')
      local via = session_source(state, session.name) or session.attached
      flat_text(cr, fit_text(cr, via and ('via ' .. via) or 'no inbound route', text_width, 6.2),
        center_x, y + 91, 6.2, via and teal or dim, 0.78, 'center')
    else
      flat_text(cr, 'OPEN SOCKET', center_x, y + 46, 8.4, muted, 0.62, 'center')
      flat_text(cr, 'waiting for tmux', center_x, y + 61, 6.4, muted, 0.52, 'center')
      flat_text(cr, 'no inbound route', center_x, y + 76, 6.2, dim, 0.62, 'center')
    end

    shared.set_hex(cr, tone, live and 0.78 or 0.24)
    cairo_set_line_width(cr, live and 1.5 or 0.8)
    cairo_move_to(cr, center_x - width / 2 + 10, y + 99)
    cairo_line_to(cr, center_x + width / 2 - 10, y + 99)
    cairo_stroke(cr)
  end

  local function draw_source_row(cr, device, center_x, y, width, index)
    local tone = green
    if device.state == 'alert' then
      tone = red
    elseif device.state == 'idle' then
      tone = dim
    end
    local active = device.state ~= 'idle'
    local text_width = width - 14
    local origin = device.os or ''
    if device.age and device.age ~= '' then
      origin = origin .. '  ' .. device.age
    end

    flat_text(cr, string.format('IN %02d', index), center_x, y + 3, 6.2, violet, 0.72, 'center')
    device_glyph(cr, device.glyph, center_x, y + 17, tone, active and 0.95 or 0.48)
    flat_text(cr, fit_text(cr, device.name, text_width, 8.2), center_x, y + 35,
      8.2, active and text_color or muted, active and 1.0 or 0.72, 'center')
    flat_text(cr, fit_text(cr, origin, text_width, 6.2), center_x, y + 49,
      6.2, muted, 0.62, 'center')
    flat_text(cr, fit_text(cr, device.session and ('route ' .. device.session) or 'unpatched',
      text_width, 6.1), center_x, y + 63, 6.1, active and tone or dim,
      active and 0.82 or 0.58, 'center')
    jack(cr, center_x, y + source_jack_offset, tone, device.session ~= nil)
    status_dot(cr, center_x + 10, y + source_jack_offset, device.state)

    shared.set_hex(cr, dim, 0.34)
    cairo_set_line_width(cr, 0.8)
    cairo_move_to(cr, center_x - width / 2 + 10, y + 84)
    cairo_line_to(cr, center_x + width / 2 - 10, y + 84)
    cairo_stroke(cr)
  end

  local function layout_for(state)
    local device_count = state and state.devices and #state.devices or 0
    local session_count = state and state.sessions and #state.sessions or 0
    local source_rows = row_count(device_count)
    local session_slots = math.max(slot_columns, session_count)
    local session_rows = row_count(session_slots)
    local height = panel_height(state)
    local destination_top = height - footer_height - session_rows * destination_row_height
    return {
      source_rows = source_rows,
      session_slots = session_slots,
      session_rows = session_rows,
      source_area_bottom = source_top + source_rows * source_row_height,
      destination_top = destination_top,
      route_top = source_top + source_rows * source_row_height,
      route_bottom = destination_top + destination_socket_offset,
      status_divider = height - footer_height,
      height = height,
    }
  end

  local function draw_panel(cr, state, x, y, height)
    local layout = layout_for(state)
    local slot_width = (content_right - content_left) / slot_columns
    local alert = false
    local live_count = 0
    local idle_count = 0
    for _, device in ipairs(state.devices) do
      if device.state == 'alert' then alert = true end
      if device.state == 'live' then live_count = live_count + 1 end
      if device.state == 'idle' then idle_count = idle_count + 1 end
    end

    -- The sessions window is intentionally transparent, like the resource HUD:
    -- only labels, glyphs, traces and status lines are painted.
    flat_text(cr, 'PATCH BAY', x + content_left, y + 31, 11, 'dbeafe', 0.92)
    flat_text(cr, 'TMUX / INBOUND ROUTING', x + content_left, y + 48, 7, muted, 0.66)
    flat_text(cr, string.format('%02d IN / %02d TMUX', #state.devices, #state.sessions),
      x + content_right, y + 31, 7, muted, 0.72, 'right')
    flat_text(cr, 'VERTICAL ROUTE', x + content_right, y + 48, 6.4,
      violet, 0.78, 'right')
    shared.set_hex(cr, cyan, 0.24)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + content_left, y + 67)
    cairo_line_to(cr, x + content_right, y + 67)
    cairo_stroke(cr)

    flat_text(cr, 'INBOUND SOURCES', x + content_left, y + 91, 7, violet, 0.84)
    flat_text(cr, 'TOP PATCH ROW', x + content_right, y + 91, 6.2, dim, 0.72, 'right')
    flat_text(cr, 'DEVICE / ORIGIN', x + content_left, y + 107, 6.1, dim, 0.74)

    for column = 0, slot_columns - 1 do
      local center_x = content_left + (column + 0.5) * slot_width
      shared.set_hex(cr, dim, 0.22)
      cairo_set_line_width(cr, 0.7)
      cairo_move_to(cr, x + center_x, y + layout.route_top)
      cairo_line_to(cr, x + center_x, y + layout.route_bottom)
      cairo_stroke(cr)
    end

    local session_positions = {}
    for index, session in ipairs(state.sessions) do
      local center_x, row_top = slot_position(index, layout.destination_top,
        destination_row_height, slot_width)
      session_positions[session.name] = {
        x = x + center_x,
        y = y + row_top + destination_socket_offset,
      }
    end

    for index, device in ipairs(state.devices) do
      local center_x, row_top = slot_position(index, source_top, source_row_height, slot_width)
      local source_x = x + center_x
      local source_y = y + row_top + source_jack_offset
      local target = device.session and session_positions[device.session] or nil
      if target then
        local tone = device.state == 'alert' and red or green
        cable(cr, source_x, source_y + 3, target.x, target.y, tone)
      elseif device.state == 'alert' then
        local stub_y = source_y + math.max(30, (y + layout.route_bottom - source_y) * 0.32)
        cable(cr, source_x, source_y + 3, source_x, stub_y, red)
        shared.set_hex(cr, red, 0.9)
        cairo_set_line_width(cr, 1.4)
        cairo_move_to(cr, source_x - 3, stub_y - 3.5)
        cairo_line_to(cr, source_x + 3, stub_y + 3.5)
        cairo_move_to(cr, source_x + 3, stub_y - 3.5)
        cairo_line_to(cr, source_x - 3, stub_y + 3.5)
        cairo_stroke(cr)
      end
    end

    for index, device in ipairs(state.devices) do
      local center_x, row_top = slot_position(index, source_top, source_row_height, slot_width)
      draw_source_row(cr, device, x + center_x, y + row_top, slot_width, index)
    end
    if #state.devices == 0 then
      flat_text(cr, 'no inbound sources', x + content_left, y + source_top + 35,
        7, dim, 0.62)
    end

    shared.set_hex(cr, violet, 0.28)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + content_left, y + layout.destination_top - 22)
    cairo_line_to(cr, x + content_right, y + layout.destination_top - 22)
    cairo_stroke(cr)
    flat_text(cr, 'TMUX DESTINATIONS', x + content_left, y + layout.destination_top - 6,
      7, violet, 0.84)
    flat_text(cr, 'BOTTOM PATCH ROW', x + content_right, y + layout.destination_top - 6,
      6.2, dim, 0.72, 'right')

    for index = 1, layout.session_slots do
      local session = state.sessions[index]
      local center_x, row_top = slot_position(index, layout.destination_top,
        destination_row_height, slot_width)
      draw_session_card(cr, state, session, x + center_x, y + row_top, slot_width, index)
    end

    shared.set_hex(cr, violet, 0.24)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + content_left, y + layout.status_divider)
    cairo_line_to(cr, x + content_right, y + layout.status_divider)
    cairo_stroke(cr)
    flat_text(cr, 'ROUTING STATUS', x + content_left, y + height - 46, 6.6, violet, 0.78)
    flat_text(cr, string.format('%02d LIVE', live_count), x + content_left, y + height - 25,
      8, green, 0.92)
    flat_text(cr, string.format('%02d IDLE', idle_count), x + content_left + 76,
      y + height - 25, 8, dim, 0.84)
    if alert then
      flat_text(cr, 'UNKNOWN', x + content_left + 152, y + height - 25, 6.6, red, 0.95)
    end
    flat_text(cr, 'TAILSCALE SSH', x + content_right, y + height - 46, 6.6,
      muted, 0.58, 'right')
    flat_text(cr, state.sshd and 'SSHD:22 OPEN' or 'SSHD:22 CLOSED',
      x + content_right, y + height - 25, 6.6, dim, 0.74, 'right')
  end

  local function draw_error(cr, state, x, y)
    flat_text(cr, 'PATCH BAY', x + content_left, y + 31, 11, 'dbeafe', 0.92)
    flat_text(cr, 'SESSION DATA UNAVAILABLE', x + content_left, y + 48, 7, muted, 0.66)
    shared.set_hex(cr, red, 0.24)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + content_left, y + 67)
    cairo_line_to(cr, x + content_right, y + 67)
    cairo_stroke(cr)
    device_glyph(cr, 'alert', x + content_left + 9, y + 104, red, 0.9)
    flat_text(cr, fit_text(cr, state.error or 'error', panel_width - 70, 8),
      x + content_left + 26, y + 108, 8, muted, 0.76)
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
