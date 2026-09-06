-- Local repository fleet. A settled repository is one quiet line; only a
-- repository with something to answer for earns a second line and a badge.
return function(shared, repo_root)
  local status_path = repo_root .. '/cache/git-status.json'
  local ui = shared.ui
  local settled_pitch, busy_pitch = 26, 44
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
    if not repo.ok then return repo.error end
    local counts = {}
    for _, pair in ipairs({{'staged', 'S'}, {'modified', 'M'}, {'untracked', 'U'},
      {'conflicted', 'C'}, {'ahead', 'ahead '}, {'behind', 'behind '}, {'stash', 'stash '}}) do
      if repo[pair[1]] > 0 then counts[#counts + 1] = pair[2] .. repo[pair[1]] end
    end
    return table.concat(counts, '  ')
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
      local heights, labels, kinds = {}, {}, {}
      for index, repo in ipairs(repos) do
        labels[index], kinds[index] = verdict(repo)
        heights[index] = labels[index] and busy_pitch or settled_pitch
      end
      local first, last, page = ui.stack(heights, height, 0, state.stale)
      local y = 0
      for index = first, last do
        local repo, label = repos[index], labels[index]
        if not label then
          -- Settled: the name alone, and the branch only when it is not the
          -- default, since that is the whole reason to read the line.
          local branch_width = 0
          if not default_branches[repo.branch] and repo.branch ~= '' then
            branch_width = ui.text(cr, repo.branch, width, y + 15,
              {size = 12, mono = true, color = ui.faint, align = 'right', width = width * 0.5}) + 12
          end
          ui.text(cr, repo.name, 0, y + 15,
            {size = 13.5, bold = 'medium', color = ui.muted, width = width - branch_width})
        else
          local badge_width = ui.badge(cr, label, width, y + 1, kinds[index], {right = true})
          ui.text(cr, repo.name, 0, y + 15,
            {size = 13.5, bold = 'medium', width = width - badge_width - 12})
          local branch_width = ui.text(cr, repo.branch ~= '' and repo.branch or 'Unavailable', 0, y + 33,
            {size = 12, mono = true, color = ui.muted, width = width * 0.62})
          ui.text(cr, counts_of(repo), branch_width + 12, y + 33,
            {size = 12, mono = true, color = ui.muted, width = width - branch_width - 12})
        end
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
