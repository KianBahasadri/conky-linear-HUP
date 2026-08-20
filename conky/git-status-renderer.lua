return function(shared, repo_root)
  local status_path = repo_root .. '/cache/git-status.json'
  local font = 'JetBrains Mono'
  -- Fixed design width. Never permanently clamp this from a 0-sized first frame
  -- (Conky often reports width=0 on the first draw hook).
  local configured_panel_width = 272
  local panel_width = configured_panel_width
  local radius = 18
  -- Row and padding geometry lives in renderer-shared: the GitHub rail measures
  -- this panel from there so it can center itself in the band underneath.
  local geometry = shared.git_panel
  -- Two-line rows: repo name on top, branch underneath.
  local row_height = geometry.row_height
  -- Inside the frame: tight top/bottom padding around repo rows (no header bar).
  local content_top = geometry.content_top
  local content_bottom = geometry.content_bottom
  -- Outside the frame: octocat + refresh age sit bottom-right below the box.
  local footer_gap = geometry.footer_gap
  local footer_height = geometry.footer_height
  -- Small inset so the frame glow is not clipped by the window edge.
  local top_padding = geometry.top_padding
  local side_padding = 14
  -- Official GitHub mark path in a 16×16 viewBox (absolute M/C/Z ops).
  local github_mark_ops = {
    { 'M', 8.00000, 0.00000 },
    { 'C', 3.58000, 0.00000, 0.00000, 3.58000, 0.00000, 8.00000 },
    { 'C', 0.00000, 11.54000, 2.29000, 14.53000, 5.47000, 15.59000 },
    { 'C', 5.87000, 15.66000, 6.02000, 15.42000, 6.02000, 15.21000 },
    { 'C', 6.02000, 15.02000, 6.01000, 14.39000, 6.01000, 13.72000 },
    { 'C', 4.00000, 14.09000, 3.48000, 13.23000, 3.32000, 12.78000 },
    { 'C', 3.23000, 12.55000, 2.84000, 11.84000, 2.50000, 11.65000 },
    { 'C', 2.22000, 11.50000, 1.82000, 11.13000, 2.49000, 11.12000 },
    { 'C', 3.12000, 11.11000, 3.57000, 11.70000, 3.72000, 11.94000 },
    { 'C', 4.44000, 13.15000, 5.59000, 12.81000, 6.05000, 12.60000 },
    { 'C', 6.12000, 12.08000, 6.33000, 11.73000, 6.56000, 11.53000 },
    { 'C', 4.78000, 11.33000, 2.92000, 10.64000, 2.92000, 7.58000 },
    { 'C', 2.92000, 6.71000, 3.23000, 5.99000, 3.74000, 5.43000 },
    { 'C', 3.66000, 5.23000, 3.38000, 4.41000, 3.82000, 3.31000 },
    { 'C', 3.82000, 3.31000, 4.49000, 3.10000, 6.02000, 4.13000 },
    { 'C', 6.66000, 3.95000, 7.34000, 3.86000, 8.02000, 3.86000 },
    { 'C', 8.70000, 3.86000, 9.38000, 3.95000, 10.02000, 4.13000 },
    { 'C', 11.55000, 3.09000, 12.22000, 3.31000, 12.22000, 3.31000 },
    { 'C', 12.66000, 4.41000, 12.38000, 5.23000, 12.30000, 5.43000 },
    { 'C', 12.81000, 5.99000, 13.12000, 6.70000, 13.12000, 7.58000 },
    { 'C', 13.12000, 10.65000, 11.25000, 11.33000, 9.47000, 11.53000 },
    { 'C', 9.76000, 11.78000, 10.01000, 12.26000, 10.01000, 13.01000 },
    { 'C', 10.01000, 14.08000, 10.00000, 14.94000, 10.00000, 15.21000 },
    { 'C', 10.00000, 15.42000, 10.15000, 15.67000, 10.55000, 15.59000 },
    { 'C', 13.80645, 14.49066, 15.99912, 11.43700, 16.00000, 8.00000 },
    { 'C', 16.00000, 3.58000, 12.42000, 0.00000, 8.00000, 0.00000 },
    { 'Z' },
  }

  local colors = {
    text = 'f8fafc',
    muted = '94a3b8',
    dim = '64748b',
    frame = '00e5ff',
    frame_secondary = '8b5cf6',
    clean = '39ff88',
    dirty = 'ffb454',
    behind = 'a78bfa',
    ahead = '00e5ff',
    conflict = 'f87171',
    stash = 'a78bfa',
    error = 'f87171',
    detached = 'f472b6',
    staged = '00e5ff',
    modified = 'ffb454',
    untracked = '94a3b8',
  }

  local function json_string(content, key, fallback)
    local value = content:match('"' .. key .. '"%s*:%s*"(.-)"')
    if not value then
      return fallback or ''
    end
    return shared.unescape_json_string(value)
  end

  local function json_number(content, key, fallback)
    return tonumber(content:match('"' .. key .. '"%s*:%s*([%d%.%-]+)')) or fallback or 0
  end

  local function json_bool(content, key)
    return content:match('"' .. key .. '"%s*:%s*true') ~= nil
  end

  local function parse_summary(content)
    local body = content:match('"summary"%s*:%s*{([^}]*)}') or ''
    return {
      total = json_number(body, 'total', 0),
      dirty = json_number(body, 'dirty', 0),
      behind = json_number(body, 'behind', 0),
      ahead = json_number(body, 'ahead', 0),
      conflict = json_number(body, 'conflict', 0),
      stash = json_number(body, 'stash', 0),
      clean = json_number(body, 'clean', 0),
      error = json_number(body, 'error', 0),
      detached = json_number(body, 'detached', 0),
    }
  end

  local function parse_repo_object(object)
    return {
      name = json_string(object, 'name', 'repo'),
      path = json_string(object, 'path', ''),
      ok = json_bool(object, 'ok'),
      error = json_string(object, 'error', ''),
      branch = json_string(object, 'branch', ''),
      upstream = json_string(object, 'upstream', ''),
      detached = json_bool(object, 'detached'),
      ahead = json_number(object, 'ahead', 0),
      behind = json_number(object, 'behind', 0),
      staged = json_number(object, 'staged', 0),
      modified = json_number(object, 'modified', 0),
      untracked = json_number(object, 'untracked', 0),
      conflicted = json_number(object, 'conflicted', 0),
      stash = json_number(object, 'stash', 0),
      clean = json_bool(object, 'clean'),
      state = json_string(object, 'state', 'error'),
      severity = json_number(object, 'severity', 0),
      actions = json_string(object, 'actions', ''),
    }
  end

  local function parse_repos(content)
    local repos = {}
    local array_body = content:match('"repos"%s*:%s*%[(.*)%]%s*}%s*$')
    if not array_body then
      array_body = content:match('"repos"%s*:%s*%[(.*)%]')
    end
    if not array_body then
      return repos
    end

    for object in array_body:gmatch('%b{}') do
      table.insert(repos, parse_repo_object(object))
    end
    return repos
  end

  local function read_status()
    local content = shared.read_file(status_path)
    if not content then
      return {
        ok = false,
        stale = false,
        error = 'Waiting for the first git status update...',
        updated_at_epoch = 0,
        summary = {
          total = 0,
          dirty = 0,
          behind = 0,
          ahead = 0,
          conflict = 0,
          stash = 0,
          clean = 0,
          error = 0,
          detached = 0,
        },
        repos = {},
      }
    end

    return {
      ok = content:match('"ok"%s*:%s*true') ~= nil,
      stale = content:match('"stale"%s*:%s*true') ~= nil,
      error = json_string(content, 'error', ''),
      updated_at_epoch = json_number(content, 'updatedAtEpoch', 0),
      summary = parse_summary(content),
      repos = parse_repos(content),
    }
  end

  local function state_style(state)
    if state == 'conflict' then
      return { color = colors.conflict, glyph = '!', alpha = 1.0 }
    end
    if state == 'error' then
      return { color = colors.error, glyph = 'x', alpha = 1.0 }
    end
    if state == 'detached' then
      return { color = colors.detached, glyph = 'D', alpha = 1.0 }
    end
    if state == 'behind' then
      return { color = colors.behind, glyph = 'v', alpha = 1.0 }
    end
    if state == 'dirty' then
      return { color = colors.dirty, glyph = 'o', alpha = 1.0 }
    end
    if state == 'stash' then
      return { color = colors.stash, glyph = '$', alpha = 0.95 }
    end
    if state == 'ahead' then
      return { color = colors.ahead, glyph = '^', alpha = 0.95 }
    end
    return { color = colors.clean, glyph = '+', alpha = 0.52 }
  end

  local function format_ago(seconds)
    if not seconds or seconds < 0 then
      seconds = 0
    end
    -- Always two digits so the label shape is stable; layout still reserves a
    -- fixed slot measured from "99s ago" (not the live string).
    if seconds < 60 then
      return string.format('%02ds ago', math.floor(seconds))
    end
    if seconds < 3600 then
      return string.format('%02dm ago', math.floor(seconds / 60))
    end
    if seconds < 86400 then
      return string.format('%02dh ago', math.floor(seconds / 3600))
    end
    return string.format('%02dd ago', math.floor(seconds / 86400))
  end

  local function text_width(cr, value)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, value, extents)
    return extents.width
  end

  local function draw_frame(cr, x, y, width, height, accent, secondary)
    shared.rounded_rect(cr, x + 4, y + 7, width, height, radius)
    shared.set_hex(cr, accent, 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, width, height, radius)
    shared.set_hex(cr, accent, 0.16)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, width, height, radius)
    shared.set_hex(cr, secondary, 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, width, height, radius)
    shared.set_hex(cr, '020617', 0.59)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.70)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 8, y + 8, width - 16, height - 16, radius - 6)
    shared.set_hex(cr, secondary, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
  end

  local function draw_chip(cr, label, x, y, width, color)
    shared.rounded_rect(cr, x, y, width, 18, 6)
    shared.set_hex(cr, '020617', 0.96)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, color, 0.84)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    shared.set_hex(cr, color, 1)
    cairo_move_to(cr, x + (width - extents.width) / 2 - extents.x_bearing, y + 13)
    cairo_show_text(cr, label)
  end

  local function chip_width_for(cr, label)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    return math.max(52, text_width(cr, label) + 16)
  end

  local function draw_right_text(cr, value, right_x, y, color, alpha)
    local width = text_width(cr, value)
    shared.set_hex(cr, color, alpha or 1)
    cairo_move_to(cr, right_x - width, y)
    cairo_show_text(cr, value)
    return width
  end

  local function build_counts(repo)
    local parts = {}
    if repo.conflicted > 0 then
      table.insert(parts, { text = 'C' .. repo.conflicted, color = colors.conflict })
    end
    if repo.staged > 0 then
      table.insert(parts, { text = 'S' .. repo.staged, color = colors.staged })
    end
    if repo.modified > 0 then
      table.insert(parts, { text = 'M' .. repo.modified, color = colors.modified })
    end
    if repo.untracked > 0 then
      table.insert(parts, { text = 'U' .. repo.untracked, color = colors.untracked })
    end
    return parts
  end

  local function build_sync(repo)
    if repo.ahead <= 0 and repo.behind <= 0 then
      return ''
    end
    local parts = {}
    if repo.ahead > 0 then
      table.insert(parts, '^' .. repo.ahead)
    end
    if repo.behind > 0 then
      table.insert(parts, 'v' .. repo.behind)
    end
    return table.concat(parts, ' ')
  end

  local function panel_height_for(repo_count)
    -- Frame only: top inset + rows + bottom inset (footer draws outside).
    return shared.git_panel_frame_height(repo_count)
  end

  local function draw_github_mark(cr, x, y, size, color, alpha)
    -- Draw the official GitHub mark scaled from a 16×16 viewBox into size×size.
    local scale = size / 16
    cairo_new_path(cr)
    for _, op in ipairs(github_mark_ops) do
      local kind = op[1]
      if kind == 'M' then
        cairo_move_to(cr, x + op[2] * scale, y + op[3] * scale)
      elseif kind == 'C' then
        cairo_curve_to(
          cr,
          x + op[2] * scale,
          y + op[3] * scale,
          x + op[4] * scale,
          y + op[5] * scale,
          x + op[6] * scale,
          y + op[7] * scale
        )
      elseif kind == 'Z' then
        cairo_close_path(cr)
      end
    end
    shared.set_hex(cr, color, alpha or 1)
    cairo_fill(cr)
  end

  local function prepare_footer(cr, status)
    local logo_size = 11
    local pad_x = 8
    local logo_timer_gap = 5
    local timer_font_size = 10
    local chip_height = footer_height

    local ago = '—'
    if status.updated_at_epoch and status.updated_at_epoch > 0 then
      ago = format_ago(os.time() - status.updated_at_epoch)
    end
    if status.stale then
      ago = 'STALE · ' .. ago
    end

    -- Reserve a fixed timer slot so the chip width does not jitter as digits change.
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, timer_font_size)
    local slot = status.stale and ('STALE · ' .. '99s ago') or '99s ago'
    local timer_slot_width = math.max(text_width(cr, slot), text_width(cr, ago))
    local chip_width = pad_x + logo_size + logo_timer_gap + timer_slot_width + pad_x

    return {
      ago = ago,
      logo_size = logo_size,
      pad_x = pad_x,
      logo_timer_gap = logo_timer_gap,
      timer_font_size = timer_font_size,
      timer_slot_width = timer_slot_width,
      chip_width = chip_width,
      chip_height = chip_height,
    }
  end

  local function draw_footer(cr, footer, frame_x, frame_y, frame_width, frame_height, accent)
    -- Sit just under the frame, right-aligned chip: [octocat] [timer]
    local chip_color = accent or colors.frame
    local chip_x = frame_x + frame_width - footer.chip_width - side_padding + 2
    local chip_y = frame_y + frame_height + footer_gap
    local chip_h = footer.chip_height

    shared.rounded_rect(cr, chip_x, chip_y, footer.chip_width, chip_h, 6)
    shared.set_hex(cr, '020617', 0.96)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, chip_color, 0.84)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    local logo_x = chip_x + footer.pad_x
    local logo_y = chip_y + (chip_h - footer.logo_size) / 2
    draw_github_mark(cr, logo_x, logo_y, footer.logo_size, chip_color, 0.96)

    local text_x = logo_x + footer.logo_size + footer.logo_timer_gap
    local baseline_y = chip_y + chip_h * 0.68
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, footer.timer_font_size)
    shared.set_hex(cr, colors.dim, 0.95)
    cairo_move_to(cr, text_x, baseline_y)
    cairo_show_text(cr, footer.ago)
  end

  -- Compact badge font (counts/tags/sync sit on the branch line).
  local badge_font_size = 8

  -- Width needed for the right-side counts/tags so branch truncation can use the rest.
  local function right_block_width(cr, repo)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, badge_font_size)
    local parts = {}
    if repo.state == 'conflict' then
      table.insert(parts, 'CONFLICT')
    elseif repo.state == 'stash' and repo.stash > 0 then
      table.insert(parts, 'STASH×' .. repo.stash)
    elseif repo.state == 'error' then
      table.insert(parts, 'ERR')
    elseif repo.state == 'detached' then
      table.insert(parts, 'DETACHED')
    end
    for _, part in ipairs(build_counts(repo)) do
      table.insert(parts, part.text)
    end
    local sync = build_sync(repo)
    if sync ~= '' then
      table.insert(parts, sync)
    end
    if #parts == 0 then
      return 8
    end
    local total = 0
    for index, label in ipairs(parts) do
      total = total + text_width(cr, label)
      if index < #parts then
        total = total + 5
      end
    end
    -- Gap between branch text and the right block.
    return total + 10
  end

  local function actions_pip_color(actions)
    if actions == 'run' then
      return colors.dirty, 1.0
    end
    if actions == 'fail' then
      return colors.error, 1.0
    end
    if actions == 'ok' then
      return colors.clean, 0.70
    end
    return nil, 0
  end

  local function draw_actions_pip(cr, actions, right_x, center_y)
    local color, alpha = actions_pip_color(actions)
    if not color then
      return
    end
    local radius = 3.5
    local cx = right_x - radius
    local cy = center_y
    if actions == 'run' then
      cairo_new_path(cr)
      cairo_arc(cr, cx, cy, radius + 2.5, 0, 2 * math.pi)
      shared.set_hex(cr, color, 0.28)
      cairo_fill(cr)
    end
    cairo_new_path(cr)
    cairo_arc(cr, cx, cy, radius, 0, 2 * math.pi)
    shared.set_hex(cr, color, alpha)
    cairo_fill(cr)
  end

  local function draw_row(cr, repo, x, y, width)
    local style = state_style(repo.state)
    local alpha = style.alpha
    local row_y = y

    -- Soft background for non-clean rows
    if repo.state ~= 'clean' then
      shared.rounded_rect(cr, x + 10, row_y + 2, width - 20, row_height - 4, 8)
      shared.set_hex(cr, style.color, 0.07)
      cairo_fill(cr)
    end

    -- Left accent bar spans both name + branch lines
    shared.rounded_rect(cr, x + 12, row_y + 6, 3, row_height - 12, 2)
    shared.set_hex(cr, style.color, repo.state == 'clean' and 0.35 or 0.95)
    cairo_fill(cr)

    local name_y = row_y + 16
    local branch_y = row_y + 31
    -- Text starts just after the left accent bar (no status glyph/icon).
    local name_x = x + 22
    local right_edge = x + width - side_padding - 6
    local pip_size = 7
    local pip_gap = 8
    local actions = repo.actions or ''
    local name_right = right_edge
    if actions == 'run' or actions == 'fail' or actions == 'ok' then
      name_right = right_edge - pip_size - pip_gap
    end
    -- Repo name uses the name line; Actions pip sits on the far right of that line.
    local name_max = name_right - name_x
    if name_max < 48 then
      name_max = 48
    end
    local branch_max = right_edge - right_block_width(cr, repo) - name_x
    if branch_max < 40 then
      branch_max = 40
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 12)
    shared.set_hex(cr, colors.text, alpha)
    local name = shared.truncate_title(cr, repo.name, name_max)
    cairo_move_to(cr, name_x, name_y)
    cairo_show_text(cr, name)
    -- Full-alpha pip so a fail/run still reads on a dimmed clean row.
    draw_actions_pip(cr, actions, right_edge, row_y + 12)

    local branch_color = colors.muted
    if repo.state == 'detached' or repo.branch == 'DETACHED' then
      branch_color = colors.detached
    elseif repo.branch ~= 'main' and repo.branch ~= 'master' and repo.branch ~= '' then
      branch_color = colors.text
    end
    local branch_label = repo.branch
    if not repo.ok and repo.error ~= '' then
      branch_label = repo.error
      branch_color = colors.error
    end
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, branch_color, alpha * 0.9)
    cairo_move_to(cr, name_x, branch_y)
    cairo_show_text(cr, shared.truncate_title(cr, branch_label, branch_max))

    -- Right side of the branch line: compact counts + tags + sync
    local right = right_edge
    local counts_y = branch_y
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, badge_font_size)

    if repo.state == 'conflict' then
      right = right - draw_right_text(cr, 'CONFLICT', right, counts_y, colors.conflict, 1) - 6
    elseif repo.state == 'stash' and repo.stash > 0 then
      right = right - draw_right_text(cr, 'STASH×' .. repo.stash, right, counts_y, colors.stash, 1) - 6
    elseif repo.state == 'error' then
      right = right - draw_right_text(cr, 'ERR', right, counts_y, colors.error, 1) - 6
    elseif repo.state == 'detached' then
      right = right - draw_right_text(cr, 'DETACHED', right, counts_y, colors.detached, 1) - 6
    end

    local counts = build_counts(repo)
    for index = #counts, 1, -1 do
      local part = counts[index]
      right = right - draw_right_text(cr, part.text, right, counts_y, part.color, alpha) - 5
    end

    local sync = build_sync(repo)
    if sync ~= '' then
      local sync_color = colors.ahead
      if repo.behind > 0 and repo.ahead > 0 then
        sync_color = colors.detached
      elseif repo.behind > 0 then
        sync_color = colors.behind
      end
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
      cairo_set_font_size(cr, badge_font_size)
      draw_right_text(cr, sync, right, counts_y, sync_color, alpha)
    end
  end

  local function status_accent(status)
    local accent = colors.frame
    if status.summary.conflict > 0 or status.summary.error > 0 then
      accent = colors.conflict
    elseif status.summary.behind > 0 then
      accent = colors.behind
    elseif status.summary.dirty > 0 then
      accent = colors.dirty
    elseif status.summary.clean == status.summary.total and status.summary.total > 0 then
      accent = colors.clean
    end
    return accent
  end

  local function draw_empty(cr, status, x, y, height, footer)
    local accent = colors.frame
    draw_frame(cr, x, y, panel_width, height, accent, colors.frame_secondary)
    draw_footer(cr, footer, x, y, panel_width, height, accent)

    local content_y = y + content_top
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 14)
    shared.set_hex(cr, colors.dirty, 1)
    cairo_move_to(cr, x + side_padding + 8, content_y + 24)
    cairo_show_text(cr, status.ok and 'No repos to show' or 'No git data')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 11)
    shared.set_hex(cr, colors.muted, 0.9)
    cairo_move_to(cr, x + side_padding + 8, content_y + 46)
    local message = status.error
    if message == '' then
      message = 'No recent repos (or set GIT_REPO_PATHS)'
    end
    cairo_show_text(cr, shared.truncate_title(cr, message, panel_width - 40))
  end

  local function draw_status(cr, status, x, y)
    local repos = status.repos or {}
    local footer = prepare_footer(cr, status)
    local height = panel_height_for(#repos)
    if #repos == 0 then
      draw_empty(cr, status, x, y, height, footer)
      return
    end

    local accent = status_accent(status)

    draw_frame(cr, x, y, panel_width, height, accent, colors.frame_secondary)
    draw_footer(cr, footer, x, y, panel_width, height, accent)

    local row_y = y + content_top
    for _, repo in ipairs(repos) do
      draw_row(cr, repo, x, row_y, panel_width)
      row_y = row_y + row_height
    end
  end

  local draw_log_counter = 0

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local ok, err = pcall(function()
      local status = read_status()
      local window_width = tonumber(conky_window and conky_window.width) or 0
      local window_height = tonumber(conky_window and conky_window.height) or 0
      -- Only shrink to the live window when Conky has a real size; never let a
      -- zero-width first frame permanently lock panel_width.
      if window_width > 32 then
        panel_width = math.min(configured_panel_width, window_width)
      else
        panel_width = configured_panel_width
      end
      -- 4px left inset keeps the outer glow inside the window.
      draw_status(cr, status, 4, top_padding)

      -- Sparse heartbeat so we can confirm the hook runs on every head.
      draw_log_counter = draw_log_counter + 1
      if draw_log_counter == 1 or draw_log_counter % 40 == 0 then
        local log_file = io.open(repo_root .. '/cache/conky-git.log', 'a')
        if log_file then
          local repo_count = status.repos and #status.repos or 0
          log_file:write(
            string.format(
              '[%s] git-status-renderer: draw ok window=%sx%s panel=%s repos=%s\n',
              os.date('!%Y-%m-%dT%H:%M:%SZ'),
              tostring(window_width),
              tostring(window_height),
              tostring(panel_width),
              tostring(repo_count)
            )
          )
          log_file:close()
        end
      end
    end)
    if not ok then
      local log_path = repo_root .. '/cache/conky-git.log'
      local log_file = io.open(log_path, 'a')
      if log_file then
        log_file:write(string.format('[%s] git-status-renderer: draw error: %s\n', os.date('!%Y-%m-%dT%H:%M:%SZ'), tostring(err)))
        log_file:close()
      end
    end

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
