-- Join session presence to the visible fleet without requiring another fetch.
-- Paths disambiguate equal repository names; unmatched records remain visible.
return function(shared, repo_root)
  local presence = {}
  local glyphs = {laptop = 'laptop-minimal', phone = 'smartphone',
    monitor = 'monitor', alert = 'triangle-alert'}

  local function names(value)
    local out = {}
    for name in (value or ''):gmatch('[^,]+') do
      name = name:match('^%s*(.-)%s*$')
      if name ~= '' then out[#out + 1] = name end
    end
    return out
  end

  local function path_of(path)
    path = path or ''
    if path == '~' or path:sub(1, 2) == '~/' then
      path = (os.getenv('HOME') or '') .. path:sub(2)
    end
    if path:sub(1, 1) ~= '/' then return nil end
    local parts = {}
    for part in path:gmatch('[^/]+') do
      if part == '..' then table.remove(parts)
      elseif part ~= '.' then parts[#parts + 1] = part end
    end
    return '/' .. table.concat(parts, '/')
  end

  function presence.read()
    local enabled = (os.getenv('SESSIONS_OVERLAY_ENABLED') or '1'):lower()
    if enabled == '0' or enabled == 'false' or enabled == 'no' or enabled == 'off' or enabled == 'disabled' then
      return {ok = true, disabled = true, devices = {}, sessions = {}}
    end
    local content = shared.read_file(repo_root .. '/cache/sessions.json')
    local state = {ok = false, devices = {}, sessions = {}}
    if not content then state.error = 'Waiting for the first session scan'; return state end
    state.ok = shared.json_boolean(content, 'ok', false)
    if not state.ok then
      state.error = shared.json_string(content, 'error', 'Session data unavailable')
      return state
    end
    for _, object in ipairs(shared.json_array_objects(content, 'devices')) do
      state.devices[#state.devices + 1] = {
        name = shared.json_string(object, 'name', '?'),
        glyph = glyphs[shared.json_string(object, 'glyph', '')] or 'terminal',
        session = shared.json_string(object, 'session', ''),
        state = shared.json_string(object, 'state', 'idle'),
        age = shared.json_number(object, 'ageSeconds', -1),
      }
    end
    for _, object in ipairs(shared.json_array_objects(content, 'sessions')) do
      state.sessions[#state.sessions + 1] = {
        name = shared.json_string(object, 'name', '?'),
        repo = shared.json_string(object, 'repo', ''),
        path = path_of(shared.json_string(object, 'path', '')),
        attached = names(shared.json_string(object, 'attached', '')),
        live = shared.json_number(object, 'windows', 0) > 0,
        idle = shared.json_number(object, 'idleSeconds', -1),
        cv_present = shared.json_boolean(object, 'codeviewPresent', false),
        cv_running = shared.json_boolean(object, 'codeviewRunning', false),
        cv_age = shared.json_number(object, 'codeviewIndexAgeSeconds', -1),
      }
    end
    return state
  end

  function presence.join(repos, state)
    local rows, residual, devices, active = {}, {}, {}, {}
    for _, device in ipairs(state.devices) do
      -- Several logins may share a host; an alert must never be overwritten.
      if not devices[device.name] or device.state == 'alert' then devices[device.name] = device end
    end
    for _, repo in ipairs(repos) do
      rows[#rows + 1] = {name = repo.name, repo = repo, path = path_of(repo.path),
        devices = {}, device_names = {}, session_count = 0, idle = -1}
    end
    local function target_for(session)
      local target, length, same_name, matches = nil, 0, nil, 0
      for _, row in ipairs(rows) do
        if session.path and row.path then
          if (session.path == row.path or session.path:sub(1, #row.path + 1) == row.path .. '/')
              and #row.path > length then target, length = row, #row.path end
        elseif session.repo ~= '' and session.repo == row.name then
          same_name, matches = row, matches + 1
        end
      end
      return target or (matches == 1 and same_name or nil)
    end
    for _, session in ipairs(state.sessions) do
      local row = target_for(session)
      if not row then
        row = {name = session.name, devices = {}, device_names = {}, session_count = 0, idle = -1}
        residual[#residual + 1] = row
      end
      if session.live then
        active[session.name] = true
        row.session_count = row.session_count + 1
        if session.idle >= 0 and (row.idle < 0 or session.idle < row.idle) then row.idle = session.idle end
        for _, name in ipairs(session.attached) do
          if not row.device_names[name] then
            row.device_names[name] = true
            row.devices[#row.devices + 1] = devices[name] or {name = name, glyph = 'terminal'}
          end
        end
      end
      if session.cv_present then
        -- A dashboard-only record contributes no session or device. A serving
        -- record wins over a stopped one; known ages win over unknown ages.
        if not row.cv or (session.cv_running and not row.cv.running)
            or (session.cv_running == row.cv.running and session.cv_age >= 0
              and (row.cv.age < 0 or session.cv_age < row.cv.age)) then
          row.cv = {running = session.cv_running, age = session.cv_age}
        end
      end
    end
    local extra = {}
    for _, device in ipairs(state.devices) do
      local attached = false
      for _, name in ipairs(names(device.session)) do if active[name] then attached = true end end
      if device.state == 'alert' or not attached then
        extra[#extra + 1] = {name = device.name, devices = {device}, login = device,
          session_count = 0, idle = -1}
      end
    end
    table.sort(extra, function(a, b)
      if (a.login.state == 'alert') ~= (b.login.state == 'alert') then return a.login.state == 'alert' end
      return a.name < b.name
    end)
    for _, row in ipairs(residual) do extra[#extra + 1] = row end
    for index, row in ipairs(extra) do
      row.gap = index == 1 and #rows > 0 and 8 or 0
      rows[#rows + 1] = row
    end
    for _, row in ipairs(rows) do
      if row.session_count > 0 and #row.devices == 0 then row.devices[1] = {glyph = 'terminal'} end
    end
    return rows
  end

  return presence
end
