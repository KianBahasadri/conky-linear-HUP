-- Inbound logins and tmux sessions: two aligned lines per record with an
-- explicit connection, idle, or codeview state.
return function(shared, repo_root)
  local sessions_path = repo_root .. '/cache/sessions.json'
  local ui = shared.ui
  local pitch = 44
  local function field(object, key)
    return shared.json_string(object, key, nil)
  end

  local function number_field(object, key)
    return shared.json_number(object, key, 0)
  end

  local function bool_field(object, key)
    return shared.json_boolean(object, key, false)
  end

  local function read_state()
    local content = shared.read_file(sessions_path)
    if not content then
      return { ok = false, error = 'Waiting for the first session scan' }
    end
    if not bool_field(content, 'ok') then
      return { ok = false, error = field(content, 'error') or 'Session data unavailable' }
    end
    local devices = {}
    for _, object in ipairs(shared.json_array_objects(content, 'devices')) do
      table.insert(devices, {
        name = field(object, 'name') or '?',
        os = field(object, 'os') or '',
        session = field(object, 'session'),
        age = field(object, 'age') or '',
        state = field(object, 'state') or 'idle',
      })
    end
    local sessions = {}
    for _, object in ipairs(shared.json_array_objects(content, 'sessions')) do
      local attached = field(object, 'attached') or ''
      local cv_age = number_field(object, 'codeviewIndexAgeSeconds')
      if cv_age == 0 and shared.json_field(object, 'codeviewIndexAgeSeconds') == nil then
        cv_age = number_field(object, 'codeviewIndexAge')
      end
      table.insert(sessions, {
        name = field(object, 'name') or '?',
        path = field(object, 'path') or '',
        attached = attached ~= '' and attached or nil,
        windows = number_field(object, 'windows'), panes = number_field(object, 'panes'),
        port = number_field(object, 'codeviewPort'),
        -- Keep missing distinct from a real zero: zero means the tmux session
        -- is active now, while missing falls back to the device login age.
        idleSeconds = shared.json_number(object, 'idleSeconds', nil),
        codeviewPresent = bool_field(object, 'codeviewPresent'),
        codeviewRunning = bool_field(object, 'codeviewRunning'),
        codeviewIndexAge = cv_age,
      })
    end
    return { ok = true, devices = devices, sessions = sessions }
  end

  local function rows_for(state)
    local rows = {}
    for _, device in ipairs(state.devices or {}) do rows[#rows + 1] = {device = device} end
    for _, session in ipairs(state.sessions or {}) do rows[#rows + 1] = {session = session} end
    return rows
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local state = read_state()
      if not state.ok then ui.callout(cr, 'Unavailable', state.error, 0, 0, width, 'danger'); return end
      local rows = rows_for(state)
      if #rows == 0 then ui.text(cr, 'No tmux sessions', 0, 16, {size = 13.5, color = ui.muted}); return end
      local first, last, page = ui.rows(#rows, height, pitch, 0)
      for index = first, last do
        local y = (index - first) * pitch
        local row = rows[index]
        if row.device then
          local device = row.device
          local label = device.state == 'alert' and 'Unknown remote' or device.state == 'live' and 'Connected' or 'Idle'
          local kind = device.state == 'alert' and 'danger' or device.state == 'live' and 'good' or 'neutral'
          local badge_width = ui.badge(cr, label, width, y + 1, kind, {right = true})
          ui.text(cr, device.name, 0, y + 15, {size = 13.5, bold = 'medium', width = width - badge_width - 12})
          local age_width = ui.text(cr, device.age, width, y + 33,
            {size = 12, mono = true, color = ui.muted, align = 'right'})
          local origin = device.os == 'local' and 'Local login' or ('Remote login · ' .. device.os)
          local target = device.session and ('To ' .. device.session) or 'No attached session'
          ui.text(cr, origin .. ' · ' .. target, 0, y + 33,
            {size = 12, mono = true, color = ui.muted, width = width - age_width - 12})
        else
          local session = row.session
          local dashboard = session.windows == 0 and session.codeviewPresent
          local status = dashboard and 'Dashboard' or session.attached and 'Attached' or 'Detached'
          local badge_width = ui.badge(cr, status, width, y + 1, session.attached and 'good' or 'neutral', {right = true})
          ui.text(cr, session.name, 0, y + 15, {size = 13.5, bold = 'medium', width = width - badge_width - 12})
          local note, color = session.attached or session.path, ui.muted
          if session.codeviewPresent then
            if session.codeviewRunning then
              note = 'Codeview serving · index ' .. ui.ago(session.codeviewIndexAge)
              color = session.codeviewIndexAge >= 7200 and ui.caution or ui.good
            else note, color = 'Codeview stopped', ui.danger end
          end
          local note_width = ui.text(cr, note, width, y + 33,
            {size = 12, color = color, align = 'right', width = width * 0.6})
          local context = dashboard and ('Port ' .. session.port) or
            string.format('%dw / %dp · idle %s', session.windows, session.panes, ui.ago(session.idleSeconds))
          ui.text(cr, context, 0, y + 33,
            {size = 12, mono = true, color = ui.muted, width = width - note_width - 12})
        end
      end
      ui.footer(cr, page, width, height)
    end)
  end

  local function height_spacer()
    return string.format('${voffset %d}', math.max(100, 16 + #rows_for(read_state()) * pitch))
  end
  return {draw = draw, height_spacer = height_spacer}
end
