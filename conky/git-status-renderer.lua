-- Local repository fleet: two aligned lines per repository with an explicit
-- working-tree state and a GitHub Actions status badge.
return function(shared, repo_root)
  local status_path = repo_root .. '/cache/git-status.json'
  local ui = shared.ui
  local pitch = 44
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

  local function draw()
    ui.draw(function(cr, width, height)
      local state = read_status()
      local repos = state.repos or {}
      if #repos == 0 then
        if not state.ok then ui.callout(cr, 'Unavailable', state.error, 0, 0, width, 'danger')
        else ui.text(cr, 'No repositories to show', 0, 16, {size = 13.5, color = ui.muted}) end
        return
      end
      local first, last, page = ui.rows(#repos, height, pitch, 0, state.stale)
      for index = first, last do
        local repo = repos[index]
        local y = (index - first) * pitch
        local action = repo.actions == 'ok' and 'Passed' or repo.actions == 'run' and 'Running'
          or repo.actions == 'fail' and 'Failed' or ''
        local action_kind = repo.actions == 'ok' and 'good' or repo.actions == 'run' and 'caution' or 'danger'
        local badge_width = action ~= '' and ui.badge(cr, action, width, y + 1, action_kind, {right = true}) or 0
        ui.text(cr, repo.name, 0, y + 15, {size = 13.5, bold = 'medium', width = width - badge_width - 12})
        local kind = (repo.state == 'error' or repo.conflicted > 0) and 'danger'
          or (repo.behind > 0 or repo.state == 'dirty') and 'caution' or nil
        local label = repo.state == 'clean' and 'Clean' or (repo.state:gsub('^%l', string.upper))
        local state_width = ui.text(cr, label, width, y + 33,
          {size = 12, bold = 'medium', color = ui[kind] or ui.muted, align = 'right'})
        local counts = {}
        for _, pair in ipairs({{'staged', 'S'}, {'modified', 'M'}, {'untracked', 'U'},
          {'conflicted', 'C'}, {'ahead', 'ahead '}, {'behind', 'behind '}, {'stash', 'stash '}}) do
          if repo[pair[1]] > 0 then counts[#counts + 1] = pair[2] .. repo[pair[1]] end
        end
        if not repo.ok then counts = {repo.error} end
        local branch_width = ui.text(cr, repo.branch ~= '' and repo.branch or 'Unavailable', 0, y + 33,
          {size = 12, mono = true, color = ui.muted, width = (width - state_width - 12) / 2})
        ui.text(cr, table.concat(counts, '  '), branch_width + 8, y + 33,
          {size = 11, mono = true, color = kind == 'danger' and ui.danger or ui.muted,
            width = width - branch_width - state_width - 20})
      end
      local notes = {}
      if state.stale then notes[#notes + 1] = 'Stale cache' end
      if page ~= '' then notes[#notes + 1] = page end
      ui.footer(cr, table.concat(notes, ' · '), width, height, state.stale and ui.caution or nil)
    end)
  end
  return {draw = draw}
end
