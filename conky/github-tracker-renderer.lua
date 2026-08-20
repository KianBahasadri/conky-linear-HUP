return function(shared, repo_root)
  local github_path = repo_root .. '/cache/github-contributions.json'
  local git_status_path = repo_root .. '/cache/git-status.json'
  local log_path = repo_root .. '/cache/conky-github.log'
  local square = 7
  local gap = 4
  local columns = 7
  local weeks = 53
  local radius = 2
  -- Inset used when the rail is pinned by gap_y instead of centered in a band.
  local top_padding = 4
  local colors = {
    '1f2937',
    '0e4429',
    '006d32',
    '26a641',
    '39d353',
  }

  -- Screen-space band published by start_conky_overlays.sh when it auto-places
  -- the rail: this window's top edge, the git panel window's top edge (empty when
  -- that overlay is off) and where the Minecraft panel starts. All absent when
  -- GITHUB_GAP_Y pins the rail or Conky was started by hand.
  local function read_band()
    local window_top = tonumber(os.getenv('GITHUB_RAIL_WINDOW_TOP') or '')
    local bottom = tonumber(os.getenv('GITHUB_RAIL_BAND_BOTTOM') or '')
    if not window_top or not bottom then
      return nil
    end

    return {
      window_top = window_top,
      bottom = bottom,
      git_top = tonumber(os.getenv('GITHUB_RAIL_GIT_TOP') or ''),
      nudge_up = tonumber(os.getenv('GITHUB_RAIL_NUDGE_UP') or '') or 0,
    }
  end

  local band = read_band()
  local logged_start_y = nil

  local function parse_entries()
    local content = shared.read_file(github_path)
    if not content or content:match('"ok"%s*:%s*true') == nil then
      return {}
    end

    local entries = {}
    for object in content:gmatch('{%s-"date".-}') do
      local level = tonumber(object:match('"level"%s*:%s*(%d+)')) or 0
      table.insert(entries, shared.clamp(level, 0, 4))
    end

    while #entries > weeks * columns do
      table.remove(entries, 1)
    end

    return entries
  end

  -- Rows the git panel is drawing right now. A missing cache means it is drawing
  -- its empty state, which is what a zero count measures.
  local function git_repo_count()
    local content = shared.read_file(git_status_path)
    if not content then
      return 0
    end

    local array_body = content:match('"repos"%s*:%s*%[(.*)%]%s*}%s*$')
    if not array_body then
      array_body = content:match('"repos"%s*:%s*%[(.*)%]')
    end
    if not array_body then
      return 0
    end

    local count = 0
    for _ in array_body:gmatch('%b{}') do
      count = count + 1
    end
    return count
  end

  -- Center the calendar in the band, measuring the git panel from its live row
  -- count so gaining or losing a repo row keeps the gap above and below equal.
  local function rail_placement(grid_height)
    if not band then
      return { y = top_padding, repos = 0, band_top = nil }
    end

    local repos = git_repo_count()
    local band_top = band.window_top
    if band.git_top then
      band_top = math.max(band_top, band.git_top + shared.git_panel_occupied_height(repos))
    end

    local start_y
    local free = band.bottom - band_top
    if free > grid_height then
      start_y = band_top + (free - grid_height) / 2 - band.nudge_up
      if start_y < band_top then
        start_y = band_top
      end
    else
      -- Band too short to center in: sit just under the panel and let it clip.
      start_y = band_top + top_padding
    end

    start_y = start_y - band.window_top
    local window_height = tonumber(conky_window and conky_window.height) or 0
    if window_height > grid_height then
      start_y = shared.clamp(start_y, 0, window_height - grid_height)
    elseif start_y < 0 then
      start_y = 0
    end

    return { y = math.floor(start_y + 0.5), repos = repos, band_top = band_top }
  end

  -- Only log when the rail actually moves, so the log tracks placement changes.
  local function log_placement(placement, grid_height)
    if placement.y == logged_start_y then
      return
    end
    logged_start_y = placement.y

    local log_file = io.open(log_path, 'a')
    if not log_file then
      return
    end
    log_file:write(
      string.format(
        '[%s] github-tracker-renderer: rail y=%s height=%s repos=%s band=%s..%s window_top=%s\n',
        os.date('!%Y-%m-%dT%H:%M:%SZ'),
        tostring(placement.y),
        tostring(grid_height),
        tostring(placement.repos),
        tostring(placement.band_top or 'pinned'),
        tostring(band and band.bottom or 'pinned'),
        tostring(band and band.window_top or 'pinned')
      )
    )
    log_file:close()
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local entries = parse_entries()
    if #entries == 0 then
      cairo_destroy(cr)
      if should_destroy_surface and cairo_surface_destroy then
        cairo_surface_destroy(surface)
      end
      return
    end

    local cell = square + gap
    local grid_width = columns * square + (columns - 1) * gap
    local rows = math.ceil(#entries / columns)
    local grid_height = rows * square + math.max(0, rows - 1) * gap
    local start_x = math.floor((conky_window.width - grid_width) / 2)
    local placement = rail_placement(grid_height)
    local start_y = placement.y

    for index, level in ipairs(entries) do
      local draw_index = #entries - index + 1
      local row = math.floor((index - 1) / columns)
      local column = (index - 1) % columns
      local x = start_x + column * cell
      local y = start_y + row * cell
      level = entries[draw_index]
      local alpha = level == 0 and 0.42 or 0.96

      shared.rounded_rect(cr, x, y, square, square, radius)
      shared.set_hex(cr, colors[level + 1], alpha)
      cairo_fill(cr)
    end

    log_placement(placement, grid_height)

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
