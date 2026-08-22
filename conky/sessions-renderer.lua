return function(shared, repo_root)
  local sessions_path = repo_root .. '/cache/sessions.json'
  local font = 'JetBrains Mono'

  local panel_width = 456
  local radius = 18

  -- Layout. Must match scripts/fetch_sessions.py overlay_height().
  local row_height = 52       -- one inbound device row
  local card_height = 40      -- one tmux session card
  local card_gap = 12
  local chrome_height = 78    -- header + divider + footer around the rows
  local content_top = 62      -- panel top -> first row
  local jack_x = 164          -- panel-mount jack the cable leaves from
  local socket_x = 196        -- left edge of the session cards

  local cyan = '00e5ff'
  local violet = '8b5cf6'
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
      -- `sshdListening` is a JSON bool, so it needs its own match.
      sshd = content:match('"sshdListening"%s*:%s*true') ~= nil,
    }
  end

  local function panel_height(state)
    local rows = math.max(1, #state.devices, #state.sessions)
    return chrome_height + rows * row_height
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

  local function bead(cr, x, y, size, color, alpha)
    alpha = alpha or 1
    shared.set_hex(cr, color, 0.22 * alpha)
    cairo_arc(cr, x, y, size * 2.1, 0, math.pi * 2)
    cairo_fill(cr)
    shared.set_hex_shaded(cr, color, alpha, 0.35)
    cairo_arc(cr, x, y, size, 0, math.pi * 2)
    cairo_fill(cr)
  end

  local function draw_frame(cr, x, y, height, accent)
    shared.rounded_rect(cr, x + 4, y + 7, panel_width, height, radius)
    shared.set_hex(cr, accent, 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, panel_width, height, radius)
    shared.set_hex(cr, accent, 0.16)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, panel_width, height, radius)
    shared.set_hex(cr, violet, 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, panel_width, height, radius)
    shared.set_hex(cr, '020617', 0.59)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.70)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 8, y + 8, panel_width - 16, height - 16, radius - 6)
    shared.set_hex(cr, violet, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
  end

  -- A ~13px icon for what is on the other end of the wire.
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
    cairo_set_line_width(cr, 4.5)
    cairo_arc(cr, x, y, 5.4, 0, math.pi * 2)
    cairo_stroke(cr)

    shared.set_hex(cr, color, live and 0.95 or 0.34)
    cairo_set_line_width(cr, 1.4)
    cairo_arc(cr, x, y, 5.4, 0, math.pi * 2)
    cairo_stroke(cr)

    if live then
      bead(cr, x, y, 2.4, color, 1)
    else
      shared.set_hex(cr, '020617', 0.9)
      cairo_arc(cr, x, y, 2.4, 0, math.pi * 2)
      cairo_fill(cr)
    end
  end

  -- A patch cable: slack bezier from a jack to a session card, with flow beads
  -- so a live link reads as carrying something.
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
    cairo_set_line_width(cr, 5.5)
    path()
    cairo_stroke(cr)

    local pattern = cairo_pattern_create_linear(x1, y1, x2, y2)
    local r0, g0, b0 = shared.shade_rgb(color, -0.10)
    local r1, g1, b1 = shared.shade_rgb(color, 0.30)
    cairo_pattern_add_color_stop_rgba(pattern, 0, r0, g0, b0, 0.50)
    cairo_pattern_add_color_stop_rgba(pattern, 1, r1, g1, b1, 0.90)
    cairo_set_source(cr, pattern)
    cairo_set_line_width(cr, 1.7)
    path()
    cairo_stroke(cr)
    cairo_pattern_destroy(pattern)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)

    for index = 0, 1 do
      local t = 0.34 + index * 0.24
      local mt = 1 - t
      local bx = mt ^ 3 * x1 + 3 * mt ^ 2 * t * c1x + 3 * mt * t ^ 2 * c2x + t ^ 3 * x2
      local by = mt ^ 3 * y1 + 3 * mt ^ 2 * t * c1y + 3 * mt * t ^ 2 * c2y + t ^ 3 * y2
      bead(cr, bx, by, 2.1, color, 0.9 - index * 0.22)
    end
  end

  local function status_dot(cr, x, y, state)
    cairo_new_path(cr)
    local color = green
    if state == 'alert' then
      color = red
    elseif state == 'idle' then
      color = dim
    end

    if state == 'alert' then
      shared.set_hex(cr, color, 0.22)
      cairo_arc(cr, x, y, 6.5, 0, math.pi * 2)
      cairo_fill(cr)
    end
    bead(cr, x, y, 3.0, color, state == 'idle' and 0.6 or 1.0)
  end

  local function draw_session_card(cr, session, x, y, width)
    local live = session.attached ~= nil
    local tone = live and green or dim

    shared.rounded_rect(cr, x, y, width, card_height, 8)
    fill_gradient(cr, x, y, x, y + card_height, {
      { 0.00, '0d1a30', live and 0.80 or 0.55 },
      { 1.00, '020617', live and 0.72 or 0.50 },
    })
    shared.set_hex(cr, tone, live and 0.55 or 0.24)
    cairo_set_line_width(cr, 1.1)
    cairo_stroke(cr)

    shared.set_hex(cr, tone, live and 0.85 or 0.30)
    cairo_rectangle(cr, x + 1, y + 6, 2.4, card_height - 12)
    cairo_fill(cr)

    lit_text(cr, session.name, x + 12, y + 16, 10.5,
      live and text_color or muted, live and 1.0 or 0.7)
    flat_text(cr, live and 'attached' or 'detached', x + width - 10, y + 16, 7,
      tone, live and 0.9 or 0.6, 'right')

    local detail = string.format('%dw · %dp  %s', session.windows, session.panes, session.path)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 6.8)
    flat_text(cr, shared.truncate_title(cr, detail, width - 20), x + 12, y + 28, 6.8, muted, 0.62)
  end

  local function draw_device_row(cr, device, x, y)
    local tone = green
    if device.state == 'alert' then
      tone = red
    elseif device.state == 'idle' then
      tone = dim
    end
    local strong = device.state ~= 'idle'

    device_glyph(cr, device.glyph, x + 32, y, tone, strong and 0.95 or 0.5)
    lit_text(cr, device.name, x + 48, y - 1, 9,
      device.state == 'live' and text_color or muted, strong and 1.0 or 0.7)
    flat_text(cr, device.os, x + 48, y + 10, 6.6, muted, 0.58)
    flat_text(cr, device.age, x + 138, y + 10, 6.6, dim, 0.6, 'right')
    jack(cr, x + jack_x, y, tone, device.session ~= nil)
    status_dot(cr, x + 150, y - 4, device.state)
  end

  local function draw_panel(cr, state, x, y, height)
    local alert = false
    for _, device in ipairs(state.devices) do
      if device.state == 'alert' then
        alert = true
      end
    end

    draw_frame(cr, x, y, height, alert and red or cyan)
    flat_text(cr, 'SESSIONS', x + 22, y + 30, 10, 'dbeafe', 0.85)
    flat_text(cr, string.format('%d IN · %d TMUX', #state.devices, #state.sessions),
      x + panel_width - 22, y + 30, 8, muted, 0.62, 'right')

    shared.set_hex(cr, violet, 0.28)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 20, y + 42)
    cairo_line_to(cr, x + panel_width - 20, y + 42)
    cairo_stroke(cr)

    local top = y + content_top
    local card_w = panel_width - socket_x - 24

    flat_text(cr, 'INBOUND', x + 24, top - 4, 7, violet, 0.72)
    flat_text(cr, 'TMUX', x + socket_x, top - 4, 7, violet, 0.72)

    -- Cards first, so the cables land on top of their edges.
    local card_tops = {}
    for index, session in ipairs(state.sessions) do
      local cy = top + (index - 1) * (card_height + card_gap)
      card_tops[session.name] = cy
      draw_session_card(cr, session, x + socket_x, cy, card_w)
    end

    if #state.sessions == 0 then
      flat_text(cr, 'no tmux server', x + socket_x, top + 18, 8, dim, 0.55)
    end

    for index, device in ipairs(state.devices) do
      local dy = top + (index - 1) * row_height + 14
      draw_device_row(cr, device, x, dy)
      if device.session and card_tops[device.session] then
        local tone = device.state == 'alert' and red or green
        cable(cr, x + jack_x + 6, dy, x + socket_x - 1,
          card_tops[device.session] + card_height / 2, tone)
      end
    end

    if #state.devices == 0 then
      flat_text(cr, 'no logins', x + 32, top + 18, 8, dim, 0.55)
    end

    local footer = state.sshd and 'tailscale ssh · sshd:22 open'
      or 'tailscale ssh · sshd:22 closed'
    flat_text(cr, footer, x + 22, y + height - 14, 6.8, dim, 0.55)
  end

  local function draw_error(cr, state, x, y)
    local height = chrome_height + row_height
    draw_frame(cr, x, y, height, red)
    flat_text(cr, 'SESSIONS', x + 22, y + 30, 10, 'dbeafe', 0.85)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 8)
    flat_text(cr, shared.truncate_title(cr, state.error, panel_width - 48),
      x + 24, y + 70, 8, muted, 0.7)
  end

  -- Conky grows the window to this; the panel is bottom-anchored, so it grows
  -- upward and the baseline it shares with the skyline's plinth stays put.
  local function needed_height()
    local state = read_state()
    if not state.ok then
      return chrome_height + row_height + 8
    end
    return panel_height(state) + 8
  end

  local function height_spacer()
    return string.format('${voffset %d}', needed_height())
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local state = read_state()

    -- The launcher puts this window's bottom edge on the same line as the
    -- skyline's plinth, so the panel is drawn flush with it.
    local x = math.max(4, (conky_window.width - panel_width) / 2)
    if state.ok then
      local height = panel_height(state)
      draw_panel(cr, state, x, math.max(4, conky_window.height - height - 4), height)
    else
      draw_error(cr, state, x, 4)
    end

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
    height_spacer = height_spacer,
  }
end
