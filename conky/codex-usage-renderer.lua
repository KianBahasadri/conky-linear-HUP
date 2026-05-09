return function(shared, repo_root)
  local codex_usage_path = repo_root .. '/cache/codex-usage.json'
  local font = 'JetBrains Mono'
  local codex_width = 1000
  local codex_height = 110
  local codex_auto_height = false
  local codex_radius = 18
  local codex_account_row_x = 34
  local codex_account_row_y = 8
  local codex_account_row_gap = 19
  local codex_dynamic_height_padding = 46
  local codex_first_bar_x = 113
  -- Width of each Codex usage progress bar.
  local codex_bar_width = 230
  local codex_bar_height = 8
  local codex_bar_text_gap = 14
  local codex_bar_countdown_width = 54
  local codex_bar_reset_gap = 0
  local codex_bar_reset_width = 96
  local codex_bar_pair_gap = 0
  local bottom_padding = 4
  local five_hour_window_seconds = 18000
  local weekly_window_seconds = 604800
  local pace_threshold = 10

  local function read_codex_usage()
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
      local reset_after_seconds = tonumber(object:match('"resetAfterSeconds"%s*:%s*(%d+)')) or 0

      if account and window then
        if not account_index[account] then
          account_index[account] = {
            label = shared.unescape_json_string(account),
            plan_type = shared.unescape_json_string(plan_type),
            is_selected = is_selected,
            windows = {},
          }
          table.insert(accounts, account_index[account])
        elseif is_selected then
          account_index[account].is_selected = true
        end

        table.insert(account_index[account].windows, {
          label = window,
          used_percent = used_percent,
          remaining_percent = remaining_percent,
          resets_at = resets_at,
          reset_after_seconds = reset_after_seconds,
        })
      end
    end

    return {
      ok = ok,
      error = error_message and shared.unescape_json_string(error_message) or '',
      accounts = accounts,
    }
  end

  local function format_reset(seconds)
    if seconds <= 0 then
      return 'reset pending'
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

  local function format_reset_at(window)
    if window.reset_after_seconds <= 0 then
      return format_reset(window.reset_after_seconds)
    end

    local reset_time = os.time() + window.reset_after_seconds
    local local_time = os.date('*t', reset_time)
    local label = string.lower(window.label or '')
    local hour = local_time.hour % 12
    if hour == 0 then
      hour = 12
    end
    local meridiem = local_time.hour >= 12 and 'PM' or 'AM'
    local time_label = string.format('%d:%02d %s', hour, local_time.min, meridiem)

    if label == 'weekly' then
      return string.format('%s %02d %s', os.date('%b', reset_time), local_time.day, time_label)
    end

    return time_label
  end

  local function format_reset_label(window)
    local countdown = format_reset(window.reset_after_seconds)
    local reset_at = format_reset_at(window)

    if reset_at == countdown then
      return countdown
    end

    return string.format('%s    %s', countdown, reset_at)
  end

  local function find_weekly_window(account)
    for _, window in ipairs(account.windows or {}) do
      if string.lower(window.label or '') == 'weekly' then
        return window
      end
    end
    return nil
  end

  local function calculate_window_pace(window, window_seconds)
    if not window or window_seconds <= 0 then
      return nil
    end

    local elapsed_seconds = window_seconds - window.reset_after_seconds
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

  local function calculate_weekly_pace(accounts)
    local expected_total = 0
    local actual_total = 0
    local weekly_count = 0

    for _, account in ipairs(accounts or {}) do
      local weekly = find_weekly_window(account)
      if weekly then
        local weekly_pace = calculate_window_pace(weekly, weekly_window_seconds)

        if weekly_pace then
          expected_total = expected_total + weekly_pace.expected
          actual_total = actual_total + weekly_pace.actual
          weekly_count = weekly_count + 1
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

  local function draw_codex_bar(cr, window, x, y, accent, accent_secondary, pace)
    local used = shared.clamp(window.used_percent, 0, 100)
    local fill_width = codex_bar_width * (used / 100)
    local window_label = string.lower(window.label or '')
    local is_weekly = window_label == 'weekly'
    local is_five_hour = window_label == '5h'
    local countdown_label = format_reset(window.reset_after_seconds)
    local reset_at_label = format_reset_at(window)

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

    if is_weekly then
      draw_pace_marker(cr, pace, x, bar_y)
    elseif is_five_hour then
      draw_pace_marker(cr, calculate_window_pace(window, five_hour_window_seconds), x, bar_y)
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 11)
    local text_x = x + codex_bar_width + codex_bar_text_gap
    local reset_x = text_x + codex_bar_countdown_width + codex_bar_reset_gap
    countdown_label = shared.truncate_title(cr, countdown_label, codex_bar_countdown_width)
    reset_at_label = shared.truncate_title(cr, reset_at_label, codex_bar_reset_width)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.95)
    cairo_move_to(cr, text_x, y + 8)
    cairo_show_text(cr, countdown_label)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.82)
    cairo_move_to(cr, reset_x, y + 8)
    cairo_show_text(cr, reset_at_label)
  end

  local function draw_codex_error(cr, usage, x, y)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)
    shared.set_hex(cr, 'f87171', 1)
    cairo_move_to(cr, x + 34, y + 58)
    cairo_show_text(cr, 'CODEX SIGNAL LOST')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 12)
    shared.set_hex(cr, 'f8fafc', 0.88)
    cairo_move_to(cr, x + 34, y + 82)
    cairo_show_text(cr, shared.truncate_title(cr, usage and usage.error or 'No usage cache found.', codex_width - 68))
  end

  local function draw_codex_account_row(cr, account, x, y, pace)
    local name = string.upper(account.label)
    local first = account.windows[1]
    local second = account.windows[2] or account.windows[1]
    local label_x = x + 22

    if account.is_selected then
      shared.set_hex(cr, 'ff9f1c', 0.20)
      cairo_set_line_width(cr, 5)
      cairo_move_to(cr, label_x - 20, y + 11)
      cairo_line_to(cr, label_x - 12, y + 18)
      cairo_line_to(cr, label_x - 20, y + 25)
      cairo_stroke(cr)

      shared.set_hex(cr, 'ff9f1c', 0.94)
      cairo_set_line_width(cr, 2)
      cairo_move_to(cr, label_x - 20, y + 11)
      cairo_line_to(cr, label_x - 12, y + 18)
      cairo_line_to(cr, label_x - 20, y + 25)
      cairo_stroke(cr)
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 14)
    if account.is_selected then
      shared.set_hex(cr, 'ffffff', 1)
    else
      shared.set_hex(cr, 'f8fafc', 0.72)
    end
    cairo_move_to(cr, label_x, y + 23)
    cairo_show_text(cr, shared.truncate_title(cr, name, 120))

    if first then
      draw_codex_bar(cr, first, x + codex_first_bar_x, y + 15, '00e5ff', '8b5cf6', pace)
    end
    if second then
      draw_codex_bar(cr, second, x + codex_first_bar_x + codex_bar_width + codex_bar_countdown_width + codex_bar_reset_width + codex_bar_pair_gap, y + 15, '39ff88', '00f5d4', pace)
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

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)

    shared.rounded_rect(cr, x + 48, y - 9, 74, 20, 6)
    shared.set_hex(cr, '020617', 0.94)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, '00e5ff', 0.82)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    shared.set_hex(cr, '00e5ff', 1)
    cairo_move_to(cr, x + 60, y + 6)
    cairo_show_text(cr, 'CODEX')

    if not usage.ok or #usage.accounts == 0 then
      draw_codex_error(cr, usage, x, y)
      return
    end

    local pace = calculate_weekly_pace(usage.accounts)
    draw_pace_chip(cr, pace, x, y)

    for index, account in ipairs(usage.accounts) do
      draw_codex_account_row(cr, account, x + codex_account_row_x, y + codex_account_row_y + (index - 1) * codex_account_row_gap, pace)
    end
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local usage = read_codex_usage()

    if not usage then
      usage = {
        ok = false,
        error = 'No codex-usage.json cache found.',
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
