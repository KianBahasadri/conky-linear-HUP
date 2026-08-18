return function(shared, repo_root)
  local codex_usage_path = repo_root .. '/cache/codex-usage.json'
  local codex_usage_tsv_path = repo_root .. '/cache/codex-usage-render.tsv'
  local claude_usage_tsv_path = repo_root .. '/cache/claude-usage-render.tsv'
  local cursor_usage_tsv_path = repo_root .. '/cache/cursor-usage-render.tsv'
  local gemini_usage_tsv_path = repo_root .. '/cache/gemini-usage-render.tsv'
  local grok_usage_tsv_path = repo_root .. '/cache/grok-usage-render.tsv'
  local opencode_usage_tsv_path = repo_root .. '/cache/opencode-usage-render.tsv'
  local commandcode_usage_tsv_path = repo_root .. '/cache/commandcode-usage-render.tsv'
  local font = 'JetBrains Mono'
  local panel_width = 1000
  local panel_height = 110
  local panel_auto_height = true
  local panel_radius = 18
  local account_row_x = 34
  local account_row_y = 8
  local account_row_gap = 19
  local panel_dynamic_height_padding = 30
  local panel_first_bar_x = 90
  -- Width of each usage progress bar.
  local bar_width = 230
  local bar_height = 8
  local bar_text_gap = 14
  local bar_countdown_width = 54
  local bar_pair_gap = 0
  -- Insets keep title chips (drawn at y-9) and the frame glow (y+7) inside the
  -- Conky window. Must stay in sync with fetch_common.rate_limit_panel_window_height.
  local panel_top_inset = 12
  local panel_bottom_inset = 12
  local title_chip_gap = 8
  local panel_window_floor = 320
  local five_hour_window_seconds = 18000
  local weekly_window_seconds = 604800
  local pace_threshold = 10
  -- Pace marker appearance; does not affect bar fill.
  local pace_marker_color = 'ff9f1c'
  local pace_marker_width = 1
  local pace_marker_opacity_neutral = 1.0
  local pace_marker_opacity = 0.96

  local function seconds_until_reset(window)
    if window.reset_at_epoch and window.reset_at_epoch > 0 then
      return math.max(0, window.reset_at_epoch - os.time())
    end
    return math.max(0, window.reset_after_seconds or 0)
  end

  local function normalized_window_label(window)
    local label = string.lower(window.label or '')
    if label == '5h' and seconds_until_reset(window) > 86400 then
      return 'weekly'
    end
    return label
  end

  local function window_duration(window)
    if window.window_seconds and window.window_seconds > 0 then
      return window.window_seconds
    end
    if normalized_window_label(window) == 'weekly' then
      return weekly_window_seconds
    end
    if normalized_window_label(window) == 'monthly' then
      if window.window_seconds and window.window_seconds > 0 then
        return window.window_seconds
      end
      return 31 * 86400
    end
    if normalized_window_label(window) == 'daily' then
      return 86400
    end
    return five_hour_window_seconds
  end

  local function unescape_tsv(value)
    local output = {}
    local index = 1

    while index <= #value do
      local character = value:sub(index, index)
      if character == '\\' and index < #value then
        local next_character = value:sub(index + 1, index + 1)
        if next_character == 't' then
          table.insert(output, '\t')
        elseif next_character == 'n' then
          table.insert(output, ' ')
        elseif next_character == '\\' then
          table.insert(output, '\\')
        else
          table.insert(output, next_character)
        end
        index = index + 2
      else
        table.insert(output, character)
        index = index + 1
      end
    end

    return table.concat(output)
  end

  local function split_tsv(line)
    local fields = {}
    for field in (line .. '\t'):gmatch('(.-)\t') do
      table.insert(fields, unescape_tsv(field))
    end
    return fields
  end

  local function read_usage_tsv(path, provider)
    local content = shared.read_file(path)
    if not content then
      return nil
    end

    local usage = {
      ok = false,
      error = '',
      accounts = {},
    }
    local account_index = {}

    for line in content:gmatch('[^\r\n]+') do
      local fields = split_tsv(line)
      local row_type = fields[1]

      if row_type == 'meta' then
        for index = 2, #fields, 2 do
          local key = fields[index]
          local value = fields[index + 1] or ''
          if key == 'ok' then
            usage.ok = value == '1'
          elseif key == 'error' then
            usage.error = value
          end
        end
      elseif row_type == 'account' then
        local label = fields[2] or ''
        if label ~= '' and not account_index[label] then
          account_index[label] = {
            label = label,
            provider = provider,
            plan_type = fields[3] or '',
            is_selected = fields[4] == '1',
            ok = fields[5] == '1',
            error = fields[6] or '',
            stale = fields[7] == '1',
            windows = {},
          }
          table.insert(usage.accounts, account_index[label])
        end
      elseif row_type == 'bar' then
        local label = fields[2] or ''
        if label ~= '' then
          if not account_index[label] then
            account_index[label] = {
              label = label,
              provider = provider,
              plan_type = fields[3] or '',
              is_selected = fields[4] == '1',
              ok = true,
              error = '',
              stale = false,
              windows = {},
            }
            table.insert(usage.accounts, account_index[label])
          end

          table.insert(account_index[label].windows, {
            label = normalized_window_label({
              label = fields[5] or '',
              reset_at_epoch = tonumber(fields[9]) or 0,
              reset_after_seconds = tonumber(fields[10]) or 0,
            }),
            used_percent = tonumber(fields[6]) or 0,
            remaining_percent = tonumber(fields[7]) or 0,
            resets_at = fields[8] or '',
            reset_at_epoch = tonumber(fields[9]) or 0,
            reset_after_seconds = tonumber(fields[10]) or 0,
            window_seconds = tonumber(fields[11]) or 0,
          })
        end
      end
    end

    return usage
  end

  local function read_codex_usage_tsv()
    return read_usage_tsv(codex_usage_tsv_path, 'Codex')
  end

  local function read_claude_usage_tsv()
    return read_usage_tsv(claude_usage_tsv_path, 'Claude')
  end

  local function read_cursor_usage_tsv()
    return read_usage_tsv(cursor_usage_tsv_path, 'Cursor')
  end

  local function read_gemini_usage_tsv()
    return read_usage_tsv(gemini_usage_tsv_path, 'Gemini')
  end

  local function read_grok_usage_tsv()
    return read_usage_tsv(grok_usage_tsv_path, 'Grok')
  end

  local function read_opencode_usage_tsv()
    return read_usage_tsv(opencode_usage_tsv_path, 'OpenCode')
  end

  local function read_commandcode_usage_tsv()
    return read_usage_tsv(commandcode_usage_tsv_path, 'CommandCode')
  end

  local function read_codex_usage_json()
    local content = shared.read_file(codex_usage_path)
    if not content then
      return nil
    end

    local ok = content:match('"ok"%s*:%s*true') ~= nil
    local error_message = content:match('"error"%s*:%s*"(.-)"')
    local accounts = {}
    local account_index = {}

    for object in content:gmatch('{%s-"account".-}') do
      local account = object:match('"account"%s*:%s*"(.-)"')
      local plan_type = object:match('"planType"%s*:%s*"(.-)"') or ''
      local is_selected = object:match('"isSelected"%s*:%s*true') ~= nil
      local window = object:match('"window"%s*:%s*"(.-)"')
      local used_percent = tonumber(object:match('"usedPercent"%s*:%s*([%d%.]+)')) or 0
      local remaining_percent = tonumber(object:match('"remainingPercent"%s*:%s*([%d%.]+)')) or math.max(0, 100 - used_percent)
      local resets_at = object:match('"resetsAt"%s*:%s*"(.-)"') or ''
      local reset_at_epoch = tonumber(object:match('"resetAtEpoch"%s*:%s*(%d+)')) or 0
      local reset_after_seconds = tonumber(object:match('"resetAfterSeconds"%s*:%s*(%d+)')) or 0
      local window_seconds = tonumber(object:match('"windowSeconds"%s*:%s*(%d+)')) or 0

      if account and window then
        if not account_index[account] then
          account_index[account] = {
            label = shared.unescape_json_string(account),
            provider = 'Codex',
            plan_type = shared.unescape_json_string(plan_type),
            is_selected = is_selected,
            windows = {},
          }
          table.insert(accounts, account_index[account])
        elseif is_selected then
          account_index[account].is_selected = true
        end

        table.insert(account_index[account].windows, {
          label = normalized_window_label({
            label = window,
            reset_at_epoch = reset_at_epoch,
            reset_after_seconds = reset_after_seconds,
          }),
          used_percent = used_percent,
          remaining_percent = remaining_percent,
          resets_at = resets_at,
          reset_at_epoch = reset_at_epoch,
          reset_after_seconds = reset_after_seconds,
          window_seconds = window_seconds,
        })
      end
    end

    return {
      ok = ok,
      error = error_message and shared.unescape_json_string(error_message) or '',
      accounts = accounts,
    }
  end

  local function plan_sort_rank(account)
    local provider = string.lower(account.provider or '')
    if provider == 'codex' then
      return 0
    elseif provider == 'claude' then
      return 10
    elseif provider == 'cursor' then
      return 20
    elseif provider == 'gemini' then
      return 30
    elseif provider == 'grok' then
      return 35
    elseif provider == 'opencode' then
      return 38
    elseif provider == 'commandcode' then
      return 39
    end

    return 40
  end

  local function plan_type_sort_rank(account)
    local plan_type = string.lower(account.plan_type or '')
    if plan_type == 'free' then
      return 0
    elseif plan_type == 'plus' or plan_type == 'pro' then
      return 2
    end
    return 1
  end

  local function is_free_account(account)
    return string.lower(account.plan_type or '') == 'free'
  end

  local function sort_accounts(accounts)
    for index, account in ipairs(accounts or {}) do
      account.original_index = index
    end

    table.sort(accounts, function(left, right)
      local left_rank = plan_sort_rank(left)
      local right_rank = plan_sort_rank(right)
      if left_rank == right_rank then
        local left_plan_rank = plan_type_sort_rank(left)
        local right_plan_rank = plan_type_sort_rank(right)
        if left_plan_rank ~= right_plan_rank then
          return left_plan_rank < right_plan_rank
        end
        return (left.original_index or 0) < (right.original_index or 0)
      end
      return left_rank < right_rank
    end)
  end

  local function read_ai_usage()
    local codex_usage = read_codex_usage_tsv() or read_codex_usage_json()
    local claude_usage = read_claude_usage_tsv()
    local cursor_usage = read_cursor_usage_tsv()
    local gemini_usage = read_gemini_usage_tsv()
    local grok_usage = read_grok_usage_tsv()
    local opencode_usage = read_opencode_usage_tsv()
    local commandcode_usage = read_commandcode_usage_tsv()
    local usage = {
      ok = false,
      error = '',
      accounts = {},
    }

    if codex_usage then
      usage.ok = usage.ok or codex_usage.ok
      usage.error = codex_usage.error or ''
      for _, account in ipairs(codex_usage.accounts or {}) do
        account.provider = account.provider or 'Codex'
        table.insert(usage.accounts, account)
      end
    end

    if claude_usage then
      usage.ok = usage.ok or claude_usage.ok
      if usage.error == '' then
        usage.error = claude_usage.error or ''
      end
      for _, account in ipairs(claude_usage.accounts or {}) do
        account.provider = account.provider or 'Claude'
        table.insert(usage.accounts, account)
      end
    end

    if cursor_usage then
      usage.ok = usage.ok or cursor_usage.ok
      if usage.error == '' then
        usage.error = cursor_usage.error or ''
      end
      for _, account in ipairs(cursor_usage.accounts or {}) do
        account.provider = account.provider or 'Cursor'
        table.insert(usage.accounts, account)
      end
    end

    if gemini_usage then
      usage.ok = usage.ok or gemini_usage.ok
      if usage.error == '' then
        usage.error = gemini_usage.error or ''
      end
      for _, account in ipairs(gemini_usage.accounts or {}) do
        account.provider = account.provider or 'Gemini'
        table.insert(usage.accounts, account)
      end
    end

    if grok_usage then
      usage.ok = usage.ok or grok_usage.ok
      if usage.error == '' then
        usage.error = grok_usage.error or ''
      end
      for _, account in ipairs(grok_usage.accounts or {}) do
        account.provider = account.provider or 'Grok'
        table.insert(usage.accounts, account)
      end
    end

    if opencode_usage then
      usage.ok = usage.ok or opencode_usage.ok
      if usage.error == '' then
        usage.error = opencode_usage.error or ''
      end
      for _, account in ipairs(opencode_usage.accounts or {}) do
        account.provider = account.provider or 'OpenCode'
        table.insert(usage.accounts, account)
      end
    end

    if commandcode_usage then
      usage.ok = usage.ok or commandcode_usage.ok
      if usage.error == '' then
        usage.error = commandcode_usage.error or ''
      end
      for _, account in ipairs(commandcode_usage.accounts or {}) do
        account.provider = account.provider or 'CommandCode'
        table.insert(usage.accounts, account)
      end
    end

    if usage then
      sort_accounts(usage.accounts)
    end
    return usage
  end

  local function format_reset(seconds)
    if seconds <= 0 then
      return 'wait'
    end

    local days = math.floor(seconds / 86400)
    local hours = math.floor((seconds % 86400) / 3600)
    local minutes = math.floor((seconds % 3600) / 60)

    if days > 0 then
      return string.format('%dd %dh', days, hours)
    end
    if hours > 0 then
      return string.format('%dh %02dm', hours, minutes)
    end
    return string.format('%dm', minutes)
  end

  local function format_window_countdown(window)
    local seconds = seconds_until_reset(window)
    if seconds <= 0 and (window.used_percent or 0) <= 0 then
      return 'ready'
    end
    return format_reset(seconds)
  end

  local function find_weekly_window(account)
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == 'weekly' then
        return window
      end
    end
    return nil
  end

  local function find_monthly_window(account)
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == 'monthly' then
        return window
      end
    end
    return nil
  end

  local function remaining_for_pace(window, window_seconds)
    -- Unused sliding resets report remaining == full duration at fetch time.
    -- Live epoch countdown would otherwise make expected > 0 a few seconds later
    -- and draw a left-edge tick on a window that has not actually started.
    local snapshot_remaining = tonumber(window.reset_after_seconds) or 0
    if snapshot_remaining >= window_seconds then
      return window_seconds
    end
    return seconds_until_reset(window)
  end

  local function calculate_window_pace(window, window_seconds)
    if not window or window_seconds <= 0 then
      return nil
    end

    local elapsed_seconds = window_seconds - remaining_for_pace(window, window_seconds)
    local expected = shared.clamp((elapsed_seconds / window_seconds) * 100, 0, 100)
    local actual = shared.clamp(window.used_percent, 0, 100)
    local delta = actual - expected
    local state = 'neutral'

    if delta >= pace_threshold then
      state = 'over'
    elseif expected >= pace_threshold and delta <= -pace_threshold then
      state = 'under'
    end

    return {
      expected = expected,
      actual = actual,
      delta = delta,
      state = state,
    }
  end

  local function find_selected_account(accounts, provider)
    for _, account in ipairs(accounts or {}) do
      if string.lower(account.provider or '') == string.lower(provider) and account.is_selected then
        return account
      end
    end
    for _, account in ipairs(accounts or {}) do
      if string.lower(account.provider or '') == string.lower(provider) then
        return account
      end
    end
    return nil
  end

  local function get_primary_pace_window(account)
    if not account then return nil end
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == 'weekly' then
        return window
      end
    end
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == 'auto' then
        return window
      end
    end
    if account.windows and #account.windows > 0 then
      return account.windows[1]
    end
    return nil
  end

  local function calculate_provider_average_pace(accounts, provider)
    local provider_lower = string.lower(provider)
    local delta_total = 0
    local delta_count = 0

    for _, account in ipairs(accounts or {}) do
      if string.lower(account.provider or '') == provider_lower then
        if not (provider_lower == 'codex' and is_free_account(account)) then
          if provider_lower == 'cursor' or provider_lower == 'gemini' or provider_lower == 'grok' then
            for _, window in ipairs(account.windows or {}) do
              local pace = calculate_window_pace(window, window_duration(window))
              if pace then
                delta_total = delta_total + pace.delta
                delta_count = delta_count + 1
              end
            end
          elseif provider_lower == 'opencode' or provider_lower == 'commandcode' then
            local monthly = find_monthly_window(account)
            if monthly then
              local pace = calculate_window_pace(monthly, window_duration(monthly))
              if pace then
                delta_total = delta_total + pace.delta
                delta_count = delta_count + 1
              end
            end
          else
            local weekly = find_weekly_window(account)
            if weekly then
              local pace = calculate_window_pace(weekly, window_duration(weekly))
              if pace then
                delta_total = delta_total + pace.delta
                delta_count = delta_count + 1
              end
            end
          end
        end
      end
    end

    if delta_count == 0 then
      return nil
    end

    return delta_total / delta_count
  end

  local function get_provider_label_from_delta(provider_name, avg_delta)
    if not avg_delta then
      return string.upper(provider_name)
    end
    local sign = avg_delta < 0 and '-' or '+'
    return string.format('%s: %s%.0f%%', string.upper(provider_name), sign, math.abs(avg_delta))
  end

  local function calculate_weekly_pace(accounts)
    local expected_total = 0
    local actual_total = 0
    local weekly_count = 0

    for _, account in ipairs(accounts or {}) do
      if not is_free_account(account) then
        local weekly = find_weekly_window(account)
        if weekly then
          local weekly_pace = calculate_window_pace(weekly, window_duration(weekly))

          if weekly_pace then
            expected_total = expected_total + weekly_pace.expected
            actual_total = actual_total + weekly_pace.actual
            weekly_count = weekly_count + 1
          end
        end
      end
    end

    if weekly_count == 0 then
      return nil
    end

    local expected = expected_total / weekly_count
    local actual = actual_total / weekly_count
    local delta = actual - expected
    local state = 'neutral'

    if delta >= pace_threshold then
      state = 'over'
    elseif expected >= pace_threshold and delta <= -pace_threshold then
      state = 'under'
    end

    return {
      expected = expected,
      actual = actual,
      delta = delta,
      state = state,
    }
  end

  local function pace_chip_color(pace)
    if pace and pace.state == 'over' then
      return 'f87171'
    end
    if pace and pace.state == 'under' then
      return '39ff88'
    end
    return '00e5ff'
  end

  local function draw_panel_frame(cr, x, y)
    shared.rounded_rect(cr, x + 4, y + 7, panel_width, panel_height, panel_radius)
    shared.set_hex(cr, '00e5ff', 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, panel_width, panel_height, panel_radius)
    shared.set_hex(cr, '00e5ff', 0.15)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, panel_width, panel_height, panel_radius)
    shared.set_hex(cr, '8b5cf6', 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, panel_width, panel_height, panel_radius)
    shared.set_hex(cr, '020617', 0.80)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, '00e5ff', 0.95)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 8, y + 8, panel_width - 16, panel_height - 16, panel_radius - 6)
    shared.set_hex(cr, '8b5cf6', 0.24)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)

  end

  local function draw_pace_marker(cr, pace, x, bar_y, bar_w)
    if not pace then
      return
    end
    -- Hide while none of the reset window has elapsed (expected <= 0), including
    -- unused sliding resets whose fetch remaining still equals the full duration.
    -- Show as soon as any time has elapsed, even at 0% fill or the left edge.
    -- Do not gate on usedPercent or on pixel/rounded display position.
    if (pace.expected or 0) <= 0 then
      return
    end

    local marker_x = math.floor(x + bar_w * (shared.clamp(pace.expected, 0, 100) / 100) + 0.5)
    local marker_left = marker_x - math.floor(pace_marker_width / 2)
    local is_neutral = pace.state == 'neutral'

    cairo_set_antialias(cr, CAIRO_ANTIALIAS_NONE)
    shared.set_hex(cr, pace_marker_color, is_neutral and pace_marker_opacity_neutral or pace_marker_opacity)
    cairo_rectangle(cr, marker_left, bar_y, pace_marker_width, bar_height)
    cairo_fill(cr)
    cairo_set_antialias(cr, CAIRO_ANTIALIAS_DEFAULT)

  end

  local function draw_bar_overlay_label(cr, label, x, bar_y, color)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 8)
    shared.set_hex(cr, color or 'f8fafc', 0.95)
    cairo_move_to(cr, x + 4, bar_y + 7)
    cairo_show_text(cr, label)
  end

  local function draw_usage_bar(cr, window, x, y, accent, accent_secondary, show_pace, refresh_mode, layout)
    if show_pace == nil then
      show_pace = true
    end

    local bw = layout and layout.bar_width or bar_width
    local btg = layout and layout.bar_text_gap or bar_text_gap
    local bcw = layout and layout.bar_countdown_width or bar_countdown_width

    local used = shared.clamp(window.used_percent, 0, 100)
    if refresh_mode then
      used = 0
    end
    local fill_width = bw * (used / 100)
    local countdown_label = format_window_countdown(window)
    if refresh_mode then
      -- The token is no longer fresh, so any cached number is stale: blank the
      -- countdown and prompt a re-auth instead.
      countdown_label = 'refresh'
    end

    local bar_y = y
    shared.rounded_rect(cr, x, bar_y, bw, bar_height, 4)
    shared.set_hex(cr, '020617', 0.68)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.52)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)

    if fill_width > 0 then
      local active_width = math.max(6, fill_width)

      shared.rounded_rect(cr, x - 1, bar_y - 2, active_width + 2, bar_height + 4, 5)
      shared.set_hex(cr, accent, 0.22)
      cairo_fill(cr)

      shared.rounded_rect(cr, x + 1, bar_y + 1, math.max(4, active_width - 2), bar_height - 2, 3)
      shared.set_hex(cr, accent, 0.92)
      cairo_fill(cr)

      shared.set_hex(cr, 'f8fafc', 0.20)
      cairo_set_line_width(cr, 1)
      if active_width > 10 then
        cairo_move_to(cr, x + 4, bar_y + 2)
        cairo_line_to(cr, x + active_width - 4, bar_y + 2)
        cairo_stroke(cr)
      end
    end

    shared.set_hex(cr, accent_secondary, 0.34)
    cairo_set_line_width(cr, 1)
    local tick_gap = bw / 4
    for tick = 1, 3 do
      local tick_x = x + tick * tick_gap
      cairo_move_to(cr, tick_x, bar_y + 1)
      cairo_line_to(cr, tick_x, bar_y + bar_height - 1)
    end
    cairo_stroke(cr)

    shared.set_hex(cr, 'f8fafc', 0.18)
    cairo_move_to(cr, x + 8, bar_y + 4)
    cairo_line_to(cr, x + bw - 8, bar_y + 4)
    cairo_stroke(cr)

    if show_pace and not refresh_mode then
      draw_pace_marker(cr, calculate_window_pace(window, window_duration(window)), x, bar_y, bw)
    end

    local text_x = x + bw + btg
    local font_size = 10

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, font_size)
    countdown_label = shared.truncate_title(cr, countdown_label, bcw)

    shared.set_hex(cr, accent, 0.95)
    cairo_move_to(cr, text_x, y + 8)
    cairo_show_text(cr, countdown_label)
  end

  local function draw_panel_error(cr, usage, x, y)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)
    shared.set_hex(cr, 'f87171', 1)
    cairo_move_to(cr, x + 34, y + 58)
    cairo_show_text(cr, 'AI QUOTA SIGNAL LOST')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 12)
    shared.set_hex(cr, 'f8fafc', 0.88)
    cairo_move_to(cr, x + 34, y + 82)
    cairo_show_text(cr, shared.truncate_title(cr, usage and usage.error or 'No usage cache found.', panel_width - 68))
  end

  local function provider_name(account)
    return string.lower(account.provider or 'codex')
  end

  local function window_reset_has_passed(window)
    -- Only absolute reset timestamps can prove a cached window is over.
    if window.reset_at_epoch and window.reset_at_epoch > 0 then
      return window.reset_at_epoch <= os.time()
    end
    return false
  end

  local function window_needs_refresh(account, window)
    -- Placeholder bars stand in for an account with no cached sample at all.
    if window.needs_refresh then
      return true
    end

    -- Every expired/stale account: keep cached fill and reset until that
    -- window's reset time has already passed.
    return account.stale and window_reset_has_passed(window)
  end

  local function provider_accents(account, is_free)
    if provider_name(account) == 'cursor' then
      return '94a3b8', '64748b', '475569', '334155'
    end

    if provider_name(account) == 'gemini' then
      -- Bright spring green Gemini, pine Other.
      return '4ade80', '86efac', '318f6a', '1f6b52'
    end

    if provider_name(account) == 'grok' then
      return '8b7ab0', 'a899c9', '5d4f78', '4a3f63'
    end

    if provider_name(account) == 'opencode' then
      -- Soft rose-crimson 5h, lighter rose weekly, deeper rose monthly.
      return 'f43f5e', 'fb7185', 'be123c', '881337', 'e11d48', 'be123c'
    end

    if provider_name(account) == 'commandcode' then
      -- Lime 5h, brighter lime weekly, forest monthly.
      return 'a3e635', 'd9f99d', '84cc16', 'bef264', '4d7c0f', '65a30d'
    end

    if is_free then
      if provider_name(account) == 'codex' then
        return '2563eb', '1e3a8a', '2563eb', '1e3a8a'
      end
      return '94a3b8', '64748b', '94a3b8', '64748b'
    end

    if provider_name(account) == 'claude' then
      -- Light coral/gold 5h, deeper coral weekly.
      return 'ff8f73', 'fcd34d', 'c85f49', '81392e'
    end

    -- Bright cyan 5h, rich navy weekly.
    return '00e5ff', '8b5cf6', '2563eb', '1e3a8a'
  end

  -- Match the left row inset so panel content has equal side padding.
  local bar_area_side_margin = account_row_x

  local function make_bar_layout(num_bars)
    local available = panel_width - account_row_x - panel_first_bar_x - bar_area_side_margin
    local btx = num_bars == 3 and 6 or 8
    local bcw = 54
    local text_total = btx + bcw
    local min_bw = num_bars == 1 and 40 or (num_bars == 3 and 40 or 30)
    local unit = available / num_bars
    local bw = math.max(min_bw, math.floor(unit - text_total))
    -- Fold floor remainder into the bar so unused width does not collect on the right.
    local used = num_bars * (bw + text_total)
    local leftover = available - used
    if leftover > 0 then
      bw = bw + math.floor(leftover / num_bars)
    end

    return {
      bar_width = bw,
      bar_text_gap = btx,
      bar_countdown_width = bcw,
      text_total = text_total,
      num_bars = num_bars,
    }
  end

  local function get_row_windows(account)
    local provider = provider_name(account)
    local windows = account.windows or {}

    if provider == 'grok' then
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'monthly' then return { w } end
      end
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'weekly' then return { w } end
      end
      if windows[1] then return { windows[1] } end
      return {}
    end

    if provider == 'opencode' or provider == 'commandcode' then
      local result = {}
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == '5h' then table.insert(result, w) end
      end
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'weekly' then table.insert(result, w) end
      end
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'monthly' then table.insert(result, w) end
      end
      return result
    end

    local first, second
    for _, window in ipairs(windows) do
      local window_label = normalized_window_label(window)
      if provider == 'cursor' and window_label == 'api' then
        second = window
      elseif provider == 'cursor' and window_label == 'auto' then
        first = window
      elseif provider == 'gemini' and window_label == 'other' then
        second = window
      elseif provider == 'gemini' and window_label == 'gemini' then
        first = window
      elseif window_label == 'weekly' then
        second = window
      elseif not first then
        first = window
      end
    end

    local result = {}
    if first then table.insert(result, first) end
    if second then table.insert(result, second) end
    return result
  end

  local function draw_account_row(cr, account, x, y)
    local name = string.upper(account.label)
    local label_x = x + 22
    local is_free = is_free_account(account)
    local first_accent, first_accent_secondary, second_accent, second_accent_secondary, third_accent, third_accent_secondary = provider_accents(account, is_free)
    local is_active = account.is_selected

    local row_windows = get_row_windows(account)

    -- A Claude account with no windows at all (no cached sample, or unreadable
    -- credentials) would drop off the panel entirely. Keep the row with an empty
    -- 5h bar labeled "refresh" to prompt a re-auth.
    local claude_has_no_data = provider_name(account) == 'claude' and (account.stale or not account.ok)
    if claude_has_no_data and #row_windows == 0 then
      row_windows = {
        {
          used_percent = 0,
          label = '5h',
          reset_at_epoch = 0,
          reset_after_seconds = 0,
          window_seconds = five_hour_window_seconds,
          needs_refresh = true,
        }
      }
    end

    if account.is_selected then
      local selection_color = provider_name(account) == 'codex' and '00e5ff'
        or provider_name(account) == 'cursor' and '94a3b8'
        or provider_name(account) == 'grok' and '9a86b3'
        or provider_name(account) == 'opencode' and 'ef4444'
        or provider_name(account) == 'commandcode' and 'a3e635'
        or first_accent

      shared.set_hex(cr, selection_color, 0.20)
      cairo_set_line_width(cr, 5)
      cairo_move_to(cr, label_x - 20, y + 11)
      cairo_line_to(cr, label_x - 12, y + 18)
      cairo_line_to(cr, label_x - 20, y + 25)
      cairo_stroke(cr)

      shared.set_hex(cr, selection_color, 0.94)
      cairo_set_line_width(cr, 2)
      cairo_move_to(cr, label_x - 20, y + 11)
      cairo_line_to(cr, label_x - 12, y + 18)
      cairo_line_to(cr, label_x - 20, y + 25)
      cairo_stroke(cr)
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 14)
    if is_active then
      shared.set_hex(cr, 'ffffff', 1)
    else
      shared.set_hex(cr, 'f8fafc', 0.72)
    end
    cairo_move_to(cr, label_x, y + 23)
    cairo_show_text(cr, shared.truncate_title(cr, name, 120))

    local num_bars = #row_windows
    if num_bars == 0 then return end

    local show_bar_pace = not (provider_name(account) == 'codex' and is_free)
    local bar_y = y + 15
    local layout = make_bar_layout(num_bars)
    local bar_unit_width = layout.bar_width + layout.text_total
    local bar_area_start = x + panel_first_bar_x

    local accent_list = { first_accent, second_accent, third_accent or second_accent }
    local accent_secondary_list = { first_accent_secondary, second_accent_secondary, third_accent_secondary or second_accent_secondary }
    local overlay_labels = {}
    if provider_name(account) == 'cursor' then
      overlay_labels = { 'AUTO', 'API' }
    elseif provider_name(account) == 'gemini' then
      overlay_labels = { 'Gemini', 'Other' }
    end

    for i, window in ipairs(row_windows) do
      local bar_x = bar_area_start + (i - 1) * bar_unit_width
      local accent = accent_list[i] or second_accent
      local accent_secondary = accent_secondary_list[i] or second_accent_secondary
      local refresh = window_needs_refresh(account, window)
      draw_usage_bar(cr, window, bar_x, bar_y, accent, accent_secondary, show_bar_pace, refresh, layout)

      if overlay_labels[i] then
        draw_bar_overlay_label(cr, overlay_labels[i], bar_x, bar_y, i == 1 and '000000' or nil)
      end
    end
  end

  local function title_chip_width(cr, label)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)

    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    return extents.width + 24
  end

  local function draw_title_chip(cr, label, color, x, y)
    local chip_width = title_chip_width(cr, label)

    shared.rounded_rect(cr, x, y - 9, chip_width, 20, 6)
    shared.set_hex(cr, '020617', 0.94)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, color, 0.82)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    shared.set_hex(cr, color, 1)
    cairo_move_to(cr, x + 12, y + 6)
    cairo_show_text(cr, label)

    return chip_width
  end

  local function draw_title_chips(cr, chips, x, y)
    local widths = {}
    local total_width = 0

    for i, chip in ipairs(chips) do
      widths[i] = title_chip_width(cr, chip.label)
      total_width = total_width + widths[i]
      if i > 1 then
        total_width = total_width + title_chip_gap
      end
    end

    local chip_x = x + (panel_width - total_width) / 2
    for i, chip in ipairs(chips) do
      draw_title_chip(cr, chip.label, chip.color, chip_x, y)
      chip_x = chip_x + widths[i] + title_chip_gap
    end
  end

  local function draw_pace_chip(cr, pace, x, y)
    if not pace then
      return
    end

    local color = pace_chip_color(pace)
    local sign = pace.delta < 0 and '-' or '+'
    local label = string.format('PACE: %s%.0f%%', sign, math.abs(pace.delta))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)

    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    local chip_width = extents.width + 24
    local chip_height = 20
    local chip_x = x + (panel_width - chip_width) / 2
    local chip_y = y - 9

    shared.rounded_rect(cr, chip_x, chip_y, chip_width, chip_height, 6)
    shared.set_hex(cr, '020617', 0.94)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, color, 0.82)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    shared.set_hex(cr, color, 1)
    cairo_move_to(cr, chip_x + 12, chip_y + 15)
    cairo_show_text(cr, label)
  end

  local function draw_rate_limit_panel(cr, usage, x, y)
    draw_panel_frame(cr, x, y)

    local codex_label = 'CODEX'
    local claude_label = 'CLAUDE'
    local cursor_label = 'CURSOR'
    local gemini_label = 'ANTIGRAVITY'
    local grok_label = 'GROK'
    local opencode_label = 'OPENCODE'
    local commandcode_label = 'CMD'

    local codex_color = '00e5ff'
    local claude_color = 'ff7a59'
    local cursor_color = '94a3b8'
    local gemini_color = '4ade80'
    local grok_color = '9a86b3'
    local opencode_color = 'ef4444'
    local commandcode_color = 'a3e635'

    if usage.ok and #usage.accounts > 0 then
      local codex_avg_delta = calculate_provider_average_pace(usage.accounts, 'Codex')
      local claude_avg_delta = calculate_provider_average_pace(usage.accounts, 'Claude')
      local cursor_avg_delta = calculate_provider_average_pace(usage.accounts, 'Cursor')
      local gemini_avg_delta = calculate_provider_average_pace(usage.accounts, 'Gemini')
      local grok_avg_delta = calculate_provider_average_pace(usage.accounts, 'Grok')
      local opencode_avg_delta = calculate_provider_average_pace(usage.accounts, 'OpenCode')
      local commandcode_avg_delta = calculate_provider_average_pace(usage.accounts, 'CommandCode')

      codex_label = get_provider_label_from_delta('Codex', codex_avg_delta)
      claude_label = get_provider_label_from_delta('Claude', claude_avg_delta)
      cursor_label = get_provider_label_from_delta('Cursor', cursor_avg_delta)
      gemini_label = get_provider_label_from_delta('Antigravity', gemini_avg_delta)
      grok_label = get_provider_label_from_delta('Grok', grok_avg_delta)
      opencode_label = get_provider_label_from_delta('OpenCode', opencode_avg_delta)
      commandcode_label = get_provider_label_from_delta('CMD', commandcode_avg_delta)
    end

    draw_title_chips(cr, {
      { label = codex_label, color = codex_color },
      { label = claude_label, color = claude_color },
      { label = cursor_label, color = cursor_color },
      { label = gemini_label, color = gemini_color },
      { label = grok_label, color = grok_color },
      { label = opencode_label, color = opencode_color },
      { label = commandcode_label, color = commandcode_color },
    }, x, y)

    if not usage.ok or #usage.accounts == 0 then
      draw_panel_error(cr, usage, x, y)
      return
    end

    for index, account in ipairs(usage.accounts) do
      draw_account_row(cr, account, x + account_row_x, y + account_row_y + (index - 1) * account_row_gap)
    end
  end

  local function account_count_from_usage(usage)
    if usage and usage.accounts then
      return math.max(1, #usage.accounts)
    end
    return 1
  end

  local function panel_height_for(account_count)
    local count = math.max(1, tonumber(account_count) or 1)
    if not panel_auto_height then
      return panel_height
    end
    return math.max(panel_height, panel_dynamic_height_padding + count * account_row_gap)
  end

  local function window_height_for(account_count)
    return math.max(
      panel_window_floor,
      panel_top_inset + panel_height_for(account_count) + panel_bottom_inset
    )
  end

  local function needed_height()
    return window_height_for(account_count_from_usage(read_ai_usage()))
  end

  -- Expand the Conky window to fit the current account list. Returned text is
  -- re-parsed via ${lua_parse} so the voffset becomes real vertical space.
  local function height_spacer()
    return string.format('${voffset %d}', needed_height())
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local usage = read_ai_usage()

    if not usage then
      usage = {
        ok = false,
        error = 'No AI usage cache found.',
        accounts = {},
      }
    end

    local dynamic_height = panel_height_for(account_count_from_usage(usage))
    local render_width = math.min(panel_width, conky_window.width - 40)
    local x = (conky_window.width - render_width) / 2
    local y = math.max(
      panel_top_inset,
      conky_window.height - dynamic_height - panel_bottom_inset
    )
    local previous_width = panel_width
    local previous_height = panel_height

    panel_width = render_width
    panel_height = dynamic_height
    draw_rate_limit_panel(cr, usage, x, y)
    panel_width = previous_width
    panel_height = previous_height

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
