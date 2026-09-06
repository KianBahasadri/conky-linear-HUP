-- Local repository health and session presence share one bounded list.
local module_dir = (debug.getinfo(1, 'S').source:gsub('^@', '')):match('^(.*)/') or './conky'
return function(shared, repo_root)
  local status_path = repo_root .. '/cache/git-status.json'
  local presence = dofile(module_dir .. '/repository-presence.lua')(shared, repo_root)
  local ui = shared.ui
  local settled_pitch, busy_pitch = 18, 44
  -- Matches the fetcher's GIT_DEFAULT_BRANCHES: a settled repository names its
  -- branch only when being off the default is the reason to look.
  local default_branches = {}
  for name in (os.getenv('GIT_DEFAULT_BRANCHES') or 'main,master'):gmatch('[^,:%s]+') do
    default_branches[name] = true
  end

  local function json_string(content, key, fallback)
    local value = shared.json_string(content, key, nil)
    return value ~= nil and value or fallback or ''
  end

  local function json_number(content, key, fallback)
    local value = shared.json_number(content, key, nil)
    return value ~= nil and value or fallback or 0
  end

  local function json_bool(content, key)
    return shared.json_boolean(content, key, false)
  end

  local function parse_repo_object(object)
    return {
      name = json_string(object, 'name', 'repo'),
      path = json_string(object, 'path', ''),
      ok = json_bool(object, 'ok'),
      error = json_string(object, 'error', ''),
      branch = json_string(object, 'branch', ''),
      ahead = json_number(object, 'ahead', 0),
      behind = json_number(object, 'behind', 0),
      staged = json_number(object, 'staged', 0),
      modified = json_number(object, 'modified', 0),
      untracked = json_number(object, 'untracked', 0),
      conflicted = json_number(object, 'conflicted', 0),
      stash = json_number(object, 'stash', 0),
      state = json_string(object, 'state', 'error'),
      actions = json_string(object, 'actions', ''),
    }
  end

  local function read_status()
    local content = shared.read_file(status_path)
    if not content then
      return { ok = false, stale = false, error = 'Waiting for the first git status update', repos = {} }
    end
    local repos = {}
    for _, object in ipairs(shared.json_array_objects(content, 'repos')) do
      table.insert(repos, parse_repo_object(object))
    end
    return {
      ok = json_bool(content, 'ok'),
      stale = json_bool(content, 'stale'),
      error = json_string(content, 'error', ''),
      repos = repos,
    }
  end

  -- The worst thing true of a repository, as badge text and severity. The
  -- order follows the fetcher's own severity ranking with the Actions result
  -- folded in: a failed run outranks every working-tree state but a conflict.
  -- Nil means the repository is settled and collapses to a single line.
  local function verdict(repo)
    if not repo.ok or repo.state == 'error' then return 'Error', 'danger' end
    if repo.state == 'conflict' then return 'Conflicts', 'danger' end
    if repo.actions == 'fail' then return 'CI failed', 'danger' end
    if repo.state == 'detached' then return 'Detached', 'caution' end
    if repo.state == 'behind' then return 'Behind ' .. repo.behind, 'caution' end
    if repo.state == 'dirty' then return 'Dirty', 'caution' end
    if repo.state == 'stash' then return 'Stashed', 'caution' end
    if repo.state == 'ahead' then return 'Ahead ' .. repo.ahead, 'caution' end
    if repo.actions == 'run' then return 'CI running', 'caution' end
    return nil, nil
  end

  local function counts_of(repo)
    if not repo.ok then return {repo.error ~= '' and repo.error or 'Unavailable'} end
    local counts = {}
    for _, pair in ipairs({{'staged', 'S'}, {'modified', 'M'}, {'untracked', 'U'},
      {'conflicted', 'C'}, {'ahead', 'ahead '}, {'behind', 'behind '}, {'stash', 'stash '}}) do
      if repo[pair[1]] > 0 then counts[#counts + 1] = pair[2] .. repo[pair[1]] end
    end
    return counts
  end

  local function layout_row(cr, row, width)
    local layout = {branch = '', counts = '', tokens = {}, count_lines = {}, session_text = '', cv_text = '',
      presence_width = 0, branch_width = 0, counts_width = 0, pitch = settled_pitch}
    local function measure(text) return ui.width(cr, text, 12, true) end
    if row.repo then
      layout.label, layout.kind = verdict(row.repo)
      if row.repo.ok and (layout.label or not default_branches[row.repo.branch]) then
        layout.branch = row.repo.branch
      end
      layout.tokens = counts_of(row.repo)
    elseif row.login then
      if row.login.state == 'alert' then layout.label, layout.kind = 'Unknown remote', 'danger'
      else layout.session_text = 'login ' .. ui.ago(row.login.age) end
    elseif row.error then
      layout.label, layout.kind, layout.tokens = 'Unavailable', 'danger', {row.error}
    end
    if row.session_count > 0 then
      layout.session_text = (row.session_count > 1 and row.session_count .. '× ' or '') .. ui.ago(row.idle)
    end
    if row.cv and row.cv.running then layout.cv_text = ui.ago(row.cv.age) end
    local sw = measure(layout.session_text)
    local cw = row.cv and (row.cv.running and measure(layout.cv_text) + 18 or 14) or 0
    local dev_count = math.min(#row.devices, 3)
    local dw = 0
    if dev_count > 0 then
      dw = dev_count * 14 + (dev_count - 1) * 4
      if #row.devices > 3 then
        dw = dw + measure('+' .. (#row.devices - 3)) + 4
      end
    end
    local pw = 0
    local parts = 0
    if cw > 0 then pw = pw + cw; parts = parts + 1 end
    if dw > 0 then pw = pw + dw; parts = parts + 1 end
    if sw > 0 then pw = pw + sw; parts = parts + 1 end
    if parts > 1 then pw = pw + (parts - 1) * 6 end
    layout.presence_width = pw
    layout.counts = table.concat(layout.tokens or {}, '  ')
    layout.counts_width = measure(layout.counts)
    local available = width
    local quiet_branch_space = math.min(width * 0.5, available - 96) - pw - (pw > 0 and 8 or 0)
    layout.expanded = layout.label and not row.login
      or pw > available * 0.5 or (layout.branch ~= '' and quiet_branch_space < 48)
    if layout.expanded then
      layout.pitch = busy_pitch
      local branch_min = layout.branch ~= '' and 48 or 0
      layout.presence_below = pw > 0 and (pw > width * 0.46
        or layout.counts_width + pw + branch_min + 24 > available)
      local detail_width = available - (pw > 0 and not layout.presence_below and pw + 12 or 0)
      if layout.counts_width + branch_min + 12 > detail_width and #layout.tokens > 1 then
        -- Preserve complete counts when all of them cannot share the branch's
        -- line. Wrap count tokens, never the status badge or presence values.
        layout.presence_below = pw > 0
        local line = ''
        for _, token in ipairs(layout.tokens) do
          local next_line = line == '' and token or line .. '  ' .. token
          if line ~= '' and measure(next_line) > available then
            layout.count_lines[#layout.count_lines + 1] = line
            line = token
          else line = next_line end
        end
        if line ~= '' then layout.count_lines[#layout.count_lines + 1] = line end
        layout.counts = ''
        layout.counts_width = 0
        detail_width = available
        layout.pitch = layout.pitch + 18 * #layout.count_lines
      end
      layout.branch_width = math.max(0, math.min(width * 0.62,
        detail_width - layout.counts_width - (layout.counts_width > 0 and 12 or 0)))
      if layout.presence_below then layout.pitch = layout.pitch + 18 end
    else
      layout.branch_width = math.max(0, quiet_branch_space)
    end
    return layout
  end

  local function draw_presence(cr, row, layout, right, baseline)
    local icon_y = baseline - 11
    if row.cv then
      -- CodeView identity and state use neutral ink, including old indexes.
      ui.icon(cr, row.cv.running and 'eye' or 'eye-closed', right - 14, icon_y, 14, ui.muted)
      right = right - 14
      if layout.cv_text ~= '' then
        right = right - 4
        right = right - ui.text(cr, layout.cv_text, right, baseline,
          {size = 12, mono = true, color = ui.muted, align = 'right'})
      end
      if #row.devices > 0 or layout.session_text ~= '' then
        right = right - 6
      end
    end
    if #row.devices > 0 then
      for index = math.min(#row.devices, 3), 1, -1 do
        ui.icon(cr, row.devices[index].glyph, right - 14, icon_y, 14, ui.muted)
        right = right - 14
        if index > 1 then right = right - 4 end
      end
      if #row.devices > 3 then
        right = right - 4
        right = right - ui.text(cr, '+' .. (#row.devices - 3), right, baseline,
          {size = 11, mono = true, color = ui.muted, align = 'right'})
      end
      if layout.session_text ~= '' then
        right = right - 6
      end
    end
    if layout.session_text ~= '' then
      ui.text(cr, layout.session_text, right, baseline,
        {size = 12, mono = true, color = ui.muted, align = 'right'})
    end
  end

  local function draw_row(cr, row, layout, width, y)
    local name_right = width
    if layout.label then
      name_right = width - ui.badge(cr, layout.label, width, y + 1, layout.kind, {right = true}) - 12
    elseif not layout.expanded then
      draw_presence(cr, row, layout, width, y + 13)
      name_right = width - layout.presence_width - (layout.presence_width > 0 and 8 or 0)
      if layout.branch ~= '' then
        name_right = name_right - ui.text(cr, layout.branch, name_right, y + 13,
          {size = 12, mono = true, color = ui.faint, align = 'right', width = layout.branch_width}) - 8
      end
    end
    ui.text(cr, row.name, 0, y + 13, {size = 13.5, bold = 'medium',
      color = layout.label and ui.ink or ui.muted, width = name_right})
    if not layout.expanded then return end
    local detail_right = width
    if layout.presence_width > 0 and not layout.presence_below then
      draw_presence(cr, row, layout, width, y + 31)
      detail_right = width - layout.presence_width - 12
    end
    if layout.branch ~= '' then
      ui.text(cr, layout.branch, 0, y + 31,
        {size = 12, mono = true, color = ui.muted, width = layout.branch_width})
    end
    if layout.counts ~= '' then
      ui.text(cr, layout.counts, detail_right, y + 31,
        {size = 12, mono = true, color = ui.muted, align = 'right', width = detail_right})
    end
    local baseline = y + 31
    for _, line in ipairs(layout.count_lines) do
      baseline = baseline + 18
      ui.text(cr, line, 0, baseline, {size = 12, mono = true, color = ui.muted, width = width})
    end
    if layout.presence_below then draw_presence(cr, row, layout, width, baseline + 18) end
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local state = read_status()
      local sessions = presence.read()
      local rows = presence.join(state.repos, sessions)
      if #state.repos == 0 and not state.ok then
        table.insert(rows, 1, {name = 'Git', error = state.error, devices = {}, session_count = 0})
      end
      if not sessions.ok then
        rows[#rows + 1] = {name = 'Sessions', error = sessions.error, devices = {}, session_count = 0}
      end
      if #rows == 0 then
        ui.text(cr, 'No repositories or sessions', 0, 16, {size = 13.5, color = ui.muted})
        return
      end
      local heights, layouts = {}, {}
      for index, row in ipairs(rows) do
        layouts[index] = layout_row(cr, row, width)
        heights[index] = layouts[index].pitch + (row.gap or 0)
      end
      local first, last, page = ui.stack(heights, height, 0, state.stale)
      local y = 0
      for index = first, last do
        draw_row(cr, rows[index], layouts[index], width, y + (rows[index].gap or 0))
        y = y + heights[index]
      end
      local notes = {}
      if state.stale then notes[#notes + 1] = 'Stale cache' end
      if page ~= '' then notes[#notes + 1] = page end
      ui.footer(cr, table.concat(notes, ' · '), width, height, state.stale and ui.caution or nil)
    end)
  end
  return {draw = draw}
end
