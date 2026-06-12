return function(shared, repo_root)
  local codex_usage_path = repo_root .. '/cache/codex-usage.json'
  local codex_usage_tsv_path = repo_root .. '/cache/codex-usage-render.tsv'
  local claude_usage_tsv_path = repo_root .. '/cache/claude-usage-render.tsv'
  local cursor_usage_tsv_path = repo_root .. '/cache/cursor-usage-render.tsv'
  local font = 'JetBrains Mono'
  local codex_width = 1000
  local codex_height = 110
  local codex_auto_height = true
  local codex_radius = 18
  local codex_account_row_x = 34
  local codex_account_row_y = 8
  local codex_account_row_gap = 19
  local codex_dynamic_height_padding = 30
  local codex_first_bar_x = 90
  -- Width of each Codex usage progress bar.
  local codex_bar_width = 230
  local codex_bar_height = 8
  local codex_bar_text_gap = 14
  local codex_bar_countdown_width = 54
  local codex_bar_reset_gap = 0
  local codex_bar_reset_width = 116
  local codex_bar_reset_date_width = 48
  local codex_bar_pair_gap = 0
  local bottom_padding = 4
  local five_hour_window_seconds = 18000
  local weekly_window_seconds = 604800
  local pace_threshold = 10

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
    end

    return 30
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

  local function format_reset_at(window)
    if seconds_until_reset(window) <= 0 and (window.used_percent or 0) <= 0 then
      return '', ''
    end

    local reset_time = 0
    if window.reset_at_epoch and window.reset_at_epoch > 0 then
      reset_time = window.reset_at_epoch
    elseif window.reset_after_seconds and window.reset_after_seconds > 0 then
      reset_time = os.time() + window.reset_after_seconds
    end

    if reset_time <= 0 then
      return '', format_window_countdown(window)
    end

    local local_time = os.date('*t', reset_time)
    local label = normalized_window_label(window)
    local hour = local_time.hour % 12
    if hour == 0 then
      hour = 12
    end
    local meridiem = local_time.hour >= 12 and 'PM' or 'AM'
    local time_label = string.format('%d:%02d %s', hour, local_time.min, meridiem)

    if label == 'weekly' or seconds_until_reset(window) > 86400 then
      return string.format('%s %02d', os.date('%b', reset_time), local_time.day), time_label
    end

    return '', time_label
  end

  local function find_weekly_window(account)
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == 'weekly' then
        return window
      end
    end
    return nil
  end

  local function calculate_window_pace(window, window_seconds)
    if not window or window_seconds <= 0 then
      return nil
    end

    local elapsed_seconds = window_seconds - seconds_until_reset(window)
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
          if provider_lower == 'cursor' then
            for _, window in ipairs(account.windows or {}) do
              local pace = calculate_window_pace(window, window_duration(window))
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

  local function pace_color(pace)
    if pace and pace.state == 'over' then
      return 'f87171'
    end
    if pace and pace.state == 'under' then
      return 'ff9f1c'
    end
    return 'ff9f1c'
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

  local function draw_codex_frame(cr, x, y)
    shared.rounded_rect(cr, x + 4, y + 7, codex_width, codex_height, codex_radius)
    shared.set_hex(cr, '00e5ff', 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, codex_width, codex_height, codex_radius)
    shared.set_hex(cr, '00e5ff', 0.15)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, codex_width, codex_height, codex_radius)
    shared.set_hex(cr, '8b5cf6', 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, codex_width, codex_height, codex_radius)
    shared.set_hex(cr, '020617', 0.80)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, '00e5ff', 0.95)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 8, y + 8, codex_width - 16, codex_height - 16, codex_radius - 6)
    shared.set_hex(cr, '8b5cf6', 0.24)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)

  end

  local function draw_pace_marker(cr, pace, x, bar_y)
    if not pace then
      return
    end

    local marker_x = x + codex_bar_width * (shared.clamp(pace.expected, 0, 100) / 100)
    local color = pace_color(pace)

    shared.set_hex(cr, color, pace.state == 'neutral' and 0.30 or 0.18)
    cairo_set_line_width(cr, pace.state == 'neutral' and 6 or 5)
    cairo_move_to(cr, marker_x, bar_y)
    cairo_line_to(cr, marker_x, bar_y + codex_bar_height)
    cairo_stroke(cr)

    shared.set_hex(cr, color, pace.state == 'neutral' and 1.0 or 0.96)
    cairo_set_line_width(cr, pace.state == 'neutral' and 2.5 or 2)
    cairo_move_to(cr, marker_x, bar_y + 1)
    cairo_line_to(cr, marker_x, bar_y + codex_bar_height - 1)
    cairo_stroke(cr)

  end

  local function draw_codex_bar(cr, window, x, y, accent, accent_secondary, show_pace)
    if show_pace == nil then
      show_pace = true
    end

    local used = shared.clamp(window.used_percent, 0, 100)
    local fill_width = codex_bar_width * (used / 100)
    local window_label = normalized_window_label(window)
    local is_weekly = window_label == 'weekly'
    local is_five_hour = window_label == '5h'
    local countdown_label = format_window_countdown(window)
    local reset_date_label, reset_time_label = format_reset_at(window)

    local bar_y = y
    shared.rounded_rect(cr, x, bar_y, codex_bar_width, codex_bar_height, 4)
    shared.set_hex(cr, '020617', 0.68)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.52)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)

    if fill_width > 0 then
      local active_width = math.max(6, fill_width)

      shared.rounded_rect(cr, x - 1, bar_y - 2, active_width + 2, codex_bar_height + 4, 5)
      shared.set_hex(cr, accent, 0.22)
      cairo_fill(cr)

      shared.rounded_rect(cr, x + 1, bar_y + 1, math.max(4, active_width - 2), codex_bar_height - 2, 3)
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
    local tick_gap = codex_bar_width / 4
    for tick = 1, 3 do
      local tick_x = x + tick * tick_gap
      cairo_move_to(cr, tick_x, bar_y + 1)
      cairo_line_to(cr, tick_x, bar_y + codex_bar_height - 1)
    end
    cairo_stroke(cr)

    shared.set_hex(cr, 'f8fafc', 0.18)
    cairo_move_to(cr, x + 8, bar_y + 4)
    cairo_line_to(cr, x + codex_bar_width - 8, bar_y + 4)
    cairo_stroke(cr)

    if show_pace then
      draw_pace_marker(cr, calculate_window_pace(window, window_duration(window)), x, bar_y)
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 11)
    local text_x = x + codex_bar_width + codex_bar_text_gap
    local reset_x = text_x + codex_bar_countdown_width + codex_bar_reset_gap
    countdown_label = shared.truncate_title(cr, countdown_label, codex_bar_countdown_width)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.95)
    cairo_move_to(cr, text_x, y + 8)
    cairo_show_text(cr, countdown_label)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.82)
    if reset_date_label and reset_date_label ~= '' then
      cairo_move_to(cr, reset_x, y + 8)
      cairo_show_text(cr, reset_date_label)
      cairo_move_to(cr, reset_x + codex_bar_reset_date_width, y + 8)
      cairo_show_text(cr, reset_time_label or '')
    else
      cairo_move_to(cr, reset_x, y + 8)
      cairo_show_text(cr, reset_time_label or '')
    end
  end

  local function draw_codex_error(cr, usage, x, y)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)
    shared.set_hex(cr, 'f87171', 1)
    cairo_move_to(cr, x + 34, y + 58)
    cairo_show_text(cr, 'AI QUOTA SIGNAL LOST')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 12)
    shared.set_hex(cr, 'f8fafc', 0.88)
    cairo_move_to(cr, x + 34, y + 82)
    cairo_show_text(cr, shared.truncate_title(cr, usage and usage.error or 'No usage cache found.', codex_width - 68))
  end

  local function provider_name(account)
    return string.lower(account.provider or 'codex')
  end

  local function provider_accents(account, is_free)
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
    if provider_name(account) == 'cursor' then
      return '94a3b8', '64748b', '94a3b8', '64748b'
    end

    -- Bright cyan 5h, rich navy weekly.
    return '00e5ff', '8b5cf6', '2563eb', '1e3a8a'
  end

  local function draw_codex_account_row(cr, account, x, y)
    local name = string.upper(account.label)
    local first = nil
    local second = nil
    local label_x = x + 22
    local is_free = is_free_account(account)
    local first_accent, first_accent_secondary, second_accent, second_accent_secondary = provider_accents(account, is_free)
    local is_active = account.is_selected

    for _, window in ipairs(account.windows or {}) do
      local window_label = normalized_window_label(window)
      if provider_name(account) == 'cursor' and window_label == 'api' then
        second = window
      elseif provider_name(account) == 'cursor' and window_label == 'auto' then
        first = window
      elseif window_label == 'weekly' then
        second = window
      elseif not first then
        first = window
      end
    end

    if account.is_selected then
      local selection_color = provider_name(account) == 'codex' and '00e5ff' or provider_name(account) == 'cursor' and '94a3b8' or 'ff9f1c'

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

    local show_bar_pace = not (provider_name(account) == 'codex' and is_free)
    if first then
      draw_codex_bar(cr, first, x + codex_first_bar_x, y + 15, first_accent, first_accent_secondary, show_bar_pace)
    end
    if second then
      draw_codex_bar(cr, second, x + codex_first_bar_x + codex_bar_width + codex_bar_countdown_width + codex_bar_reset_width + codex_bar_pair_gap, y + 15, second_accent, second_accent_secondary, show_bar_pace)
    end
  end

  local function draw_title_chip(cr, label, color, x, y)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)

    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    local chip_width = extents.width + 24

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
    local chip_x = x + (codex_width - chip_width) / 2
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

  local function draw_codex_panel(cr, usage, x, y)
    draw_codex_frame(cr, x, y)

    local codex_label = 'CODEX'
    local claude_label = 'CLAUDE'
    local cursor_label = 'CURSOR'

    local codex_color = '00e5ff'
    local claude_color = 'ff7a59'
    local cursor_color = '94a3b8'

    if usage.ok and #usage.accounts > 0 then
      local codex_avg_delta = calculate_provider_average_pace(usage.accounts, 'Codex')
      local claude_avg_delta = calculate_provider_average_pace(usage.accounts, 'Claude')
      local cursor_avg_delta = calculate_provider_average_pace(usage.accounts, 'Cursor')

      codex_label = get_provider_label_from_delta('Codex', codex_avg_delta)
      claude_label = get_provider_label_from_delta('Claude', claude_avg_delta)
      cursor_label = get_provider_label_from_delta('Cursor', cursor_avg_delta)
    end

    local chip_x = x + 48
    local codex_chip_width = draw_title_chip(cr, codex_label, codex_color, chip_x, y)
    local claude_chip_width = draw_title_chip(cr, claude_label, claude_color, chip_x + codex_chip_width + 8, y)
    draw_title_chip(cr, cursor_label, cursor_color, chip_x + codex_chip_width + claude_chip_width + 16, y)

    if not usage.ok or #usage.accounts == 0 then
      draw_codex_error(cr, usage, x, y)
      return
    end

    for index, account in ipairs(usage.accounts) do
      draw_codex_account_row(cr, account, x + codex_account_row_x, y + codex_account_row_y + (index - 1) * codex_account_row_gap)
    end
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

    local account_count = math.max(1, #(usage.accounts or {}))
    local dynamic_height = codex_height
    if codex_auto_height then
      dynamic_height = math.max(codex_height, codex_dynamic_height_padding + account_count * codex_account_row_gap)
    end
    local panel_width = math.min(codex_width, conky_window.width - 40)
    local x = (conky_window.width - panel_width) / 2
    local y = math.max(bottom_padding, conky_window.height - dynamic_height - bottom_padding)
    local previous_width = codex_width
    local previous_height = codex_height

    codex_width = panel_width
    codex_height = dynamic_height
    draw_codex_panel(cr, usage, x, y)
    codex_width = previous_width
    codex_height = previous_height

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
