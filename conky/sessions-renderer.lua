return function(shared, repo_root)
  local sessions_path = repo_root .. '/cache/sessions.json'
  local font = 'JetBrains Mono'

  local panel_width = 360
  local panel_min_height = 760

  -- Drift: ingress origins float at a height that *is* time. Fresh at the
  -- top, stale sunk near the bottom. Destinations are a fixed bottom row.
  local content_left = 22
  local content_right = panel_width - 22
  local slot_columns = 3
  local drift_top = 112
  local drift_nominal_height = 358
  local destination_row_height = 104
  local footer_height = 70

  local violet = 'a78bfa'
  local cyan = '00e5ff'
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
    local minutes = age_seconds / 60
    local max_minutes = 48 * 60
    local f = math.log(1 + minutes) / math.log(1 + max_minutes)
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

  local function device_icon_kind(device)
    -- Prefer the glyph from fetch_sessions (phone/laptop/monitor/terminal/alert) but
    -- also handle the two names the user cares about explicitly: any tty* and
    -- the Pixel 8. Anything else falls back to a plain dot so the panel stays
    -- quiet until a known device appears.
    local glyph = device.glyph or ""
    local name = (device.name or ""):lower()
    if glyph == "phone" or name:find("pixel") then return "phone" end
    if glyph == "laptop" or glyph == "monitor" or glyph == "terminal" or name:match("^tty%d*") then
      return "laptop"
    end
    return nil
  end

  local function draw_phone_icon(cr, cx, cy, color, filled, alpha)
    local w, h, r = 7.5, 12, 1.4
    local x, y = cx - w / 2, cy - h / 2
    shared.rounded_rect(cr, x, y, w, h, r)
    if filled then
      shared.set_hex(cr, color, alpha or 1)
      cairo_fill_preserve(cr)
      shared.set_hex(cr, color, 1)
      cairo_set_line_width(cr, 0.9)
      cairo_stroke(cr)
    else
      shared.set_hex(cr, color, 0.96)
      cairo_set_line_width(cr, 1.15)
      cairo_stroke(cr)
    end
    -- screen
    shared.set_hex(cr, color, filled and 0.18 or 0.28)
    cairo_rectangle(cr, x + 1, y + 1.7, w - 2, h - 4.4)
    cairo_fill(cr)
    -- home indicator
    shared.set_hex(cr, color, filled and 1 or 0.85)
    cairo_arc(cr, cx, y + h - 1.3, 0.7, 0, math.pi * 2)
    cairo_fill(cr)
  end

  local function draw_laptop_icon(cr, cx, cy, color, filled, alpha)
    local sw, sh = 12, 7.2
    local bw, bh = 14, 2.0
    local sx, sy = cx - sw / 2, cy - sh / 2 - 1.4
    local bx, by = cx - bw / 2, cy + sh / 2 + 0.2
    -- screen
    shared.rounded_rect(cr, sx, sy, sw, sh, 1.1)
    if filled then
      shared.set_hex(cr, color, alpha or 1)
      cairo_fill_preserve(cr)
      shared.set_hex(cr, color, 1)
      cairo_set_line_width(cr, 0.9)
      cairo_stroke(cr)
    else
      shared.set_hex(cr, color, 0.96)
      cairo_set_line_width(cr, 1.15)
      cairo_stroke(cr)
    end
    -- inner screen
    shared.set_hex(cr, color, filled and 0.16 or 0.26)
    cairo_rectangle(cr, sx + 1, sy + 1, sw - 2, sh - 1.8)
    cairo_fill(cr)
    -- base
    shared.set_hex(cr, color, filled and 0.95 or 0.82)
    cairo_rectangle(cr, bx, by, bw, bh)
    cairo_fill(cr)
    -- notch/base line
    shared.set_hex(cr, color, filled and 1 or 0.9)
    cairo_rectangle(cr, cx - 1.6, by + bh * 0.5 - 0.3, 3.2, 0.6)
    cairo_fill(cr)
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

    local live_count, idle_count = 0, 0
    local alert = false
    for _, d in ipairs(state.devices) do
      if d.state == 'alert' then alert = true end
      if d.state == 'live' then live_count = live_count + 1 end
      if d.state == 'idle' then idle_count = idle_count + 1 end
    end

    -- faint depth hairlines
    shared.set_hex(cr, dim, 0.07)
    cairo_set_line_width(cr, 0.6)
    for i = 1, 3 do
      local fy = y + layout.field_top + layout.field_height * i / 4
      cairo_move_to(cr, x + content_left + 6, fy)
      cairo_line_to(cr, x + content_right - 6, fy)
      cairo_stroke(cr)
    end

    -- destinations: only real sessions, no empty placeholder sockets
    local session_positions = {}
    for index, session in ipairs(state.sessions) do
      local cx = x + column_center(index, slot_width)
      local cy = y + layout.destination_top + destination_row_height * math.floor((index - 1) / slot_columns) + 46
      session_positions[session.name] = { x = cx, y = cy }
    end

    -- threads: height is time
    for index, device in ipairs(state.devices) do
      local cx = x + column_center(index, slot_width)
      local age = session_idle_for(device, sessions_by_name)
      local frac = drift_fraction(age)
      local cy = y + layout.field_top + 16 + frac * (layout.field_height - 32)
      local target = device.session and session_positions[device.session] or nil
      if target and device.state ~= 'alert' then
        shared.set_hex(cr, green, 0.85)
        cairo_set_line_width(cr, 1.15)
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
        cairo_move_to(cr, cx, cy + 5)
        cairo_line_to(cr, target.x, target.y - 7)
        cairo_stroke(cr)
      elseif device.state == 'alert' then
        local stub_len = math.min(86, layout.field_bottom - cy - 8)
        if stub_len < 16 then stub_len = 16 end
        local sy = cy + 5 + stub_len
        if sy > y + layout.field_bottom - 6 then sy = y + layout.field_bottom - 6 end
        shared.set_hex(cr, red, 0.62)
        cairo_set_line_width(cr, 1.15)
        cairo_move_to(cr, cx, cy + 5)
        cairo_line_to(cr, cx, sy)
        cairo_stroke(cr)
        shared.set_hex(cr, red, 0.85)
        cairo_set_line_width(cr, 0.9)
        cairo_move_to(cr, cx - 3.2, sy - 3.2)
        cairo_line_to(cr, cx + 3.2, sy + 3.2)
        cairo_move_to(cr, cx + 3.2, sy - 3.2)
        cairo_line_to(cr, cx - 3.2, sy + 3.2)
        cairo_stroke(cr)
      else
        local stub = 26 + (index % 3) * 6
        local sx = cx + 4
        local sy = cy + 5 + stub
        if sy > y + layout.field_bottom - 10 then sy = y + layout.field_bottom - 10 end
        shared.set_hex(cr, dim, 0.32)
        cairo_set_line_width(cr, 1)
        cairo_move_to(cr, cx, cy + 5)
        cairo_curve_to(cr, cx + 3, cy + 12, cx - 3, sy - 8, sx, sy)
        cairo_stroke(cr)
      end
    end

    -- ingress icons/dots + labels: phone/laptop for known devices, dot fallback
    for index, device in ipairs(state.devices) do
      local cx = x + column_center(index, slot_width)
      local age = session_idle_for(device, sessions_by_name)
      local frac = drift_fraction(age)
      local cy = y + layout.field_top + 16 + frac * (layout.field_height - 32)
      local color = green
      if device.state == 'alert' then color = red
      elseif device.state == 'idle' then color = dim end
      local filled = device.state == 'live' or device.state == 'alert'
      local icon = device_icon_kind(device)
      -- Alerts always keep the red dot + X stub language, never an icon.
      if device.state == 'alert' then icon = nil end
      if icon == "phone" then
        draw_phone_icon(cr, cx, cy, color, filled, filled and 1 or 0.92)
      elseif icon == "laptop" then
        draw_laptop_icon(cr, cx, cy, color, filled, filled and 1 or 0.92)
      else
        if filled then
          shared.set_hex(cr, color, 1)
          cairo_new_path(cr)
          cairo_arc(cr, cx, cy, 4.7, 0, math.pi * 2)
          cairo_fill(cr)
        else
          shared.set_hex(cr, color, 0.95)
          cairo_set_line_width(cr, 1.2)
          cairo_new_path(cr)
          cairo_arc(cr, cx, cy, 4.7, 0, math.pi * 2)
          cairo_stroke(cr)
          shared.set_hex(cr, dim, 0.28)
          cairo_new_path(cr)
          cairo_arc(cr, cx, cy, 7.2, 0, math.pi * 2)
          cairo_stroke(cr)
        end
      end
      local label = fit_text(cr, device.name, slot_width - 10, 9)
      local lab_color = device.state == 'alert' and red or (device.state == 'live' and text_color or muted)
      local lab_alpha = device.state == 'idle' and 0.62 or 0.96
      flat_text(cr, label, cx, cy + 17, 9, lab_color, lab_alpha, 'center')
    end
    if #state.devices == 0 then
      flat_text(cr, 'no inbound', x + panel_width / 2, y + layout.field_top + layout.field_height / 2, 9, dim, 0.62, 'center')
    end

    -- destination diamonds + labels (no empty sockets)
    for index, session in ipairs(state.sessions) do
      local cx = x + column_center(index, slot_width)
      local row = math.floor((index - 1) / slot_columns)
      local cy = y + layout.destination_top + row * destination_row_height + 46
      local live = session.attached ~= nil
      local col = live and green or dim
      cairo_new_path(cr)
      cairo_move_to(cr, cx, cy - 7)
      cairo_line_to(cr, cx + 7, cy)
      cairo_line_to(cr, cx, cy + 7)
      cairo_line_to(cr, cx - 7, cy)
      cairo_close_path(cr)
      if live then
        shared.set_hex(cr, col, 1)
        cairo_fill(cr)
      else
        shared.set_hex(cr, col, 0.92)
        cairo_set_line_width(cr, 1.15)
        cairo_stroke(cr)
      end
      local lab = fit_text(cr, session.name, slot_width - 12, 9)
      flat_text(cr, lab, cx, cy + 22, 9, live and text_color or dim, live and 0.96 or 0.62, 'center')
      if live then
        flat_text(cr, string.format('%dw', session.windows), cx, cy + 34, 8, dim, 0.62, 'center')
      else
        flat_text(cr, 'open', cx, cy + 34, 8, dim, 0.48, 'center')
      end
    end

    -- footer hidden for minimal Drift (like billing map)
  end

  local function draw_error(cr, state, x, y)
    shared.set_hex(cr, dim, 0.18)
    cairo_set_line_width(cr, 0.7)
    cairo_move_to(cr, x + content_left, y + 64)
    cairo_line_to(cr, x + content_right, y + 64)
    cairo_stroke(cr)
    flat_text(cr, 'PATCH BAY', x + content_left, y + 31, 11, muted, 0.62)
    flat_text(cr, fit_text(cr, state.error or 'error', panel_width - 48, 9), x + content_left, y + 88, 9, red, 0.92)
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
