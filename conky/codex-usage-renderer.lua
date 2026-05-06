return function(shared, repo_root)
  local codex_usage_path = repo_root .. '/cache/codex-usage.json'
  local font = 'JetBrains Mono'
  local codex_width = 1120
  local codex_height = 132
  local codex_radius = 18
  local codex_bar_width = 388
  local codex_bar_height = 24

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

    shared.set_hex(cr, '00e5ff', 0.24)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 26, y + 20)
    cairo_line_to(cr, x + 62, y + 20)
    cairo_line_to(cr, x + 75, y + 33)
    cairo_stroke(cr)

    shared.set_hex(cr, '8b5cf6', 0.20)
    cairo_move_to(cr, x + codex_width - 26, y + codex_height - 20)
    cairo_line_to(cr, x + codex_width - 62, y + codex_height - 20)
    cairo_line_to(cr, x + codex_width - 75, y + codex_height - 33)
    cairo_stroke(cr)
  end

  local function draw_codex_bar(cr, window, x, y, accent, accent_secondary)
    local used = shared.clamp(window.used_percent, 0, 100)
    local fill_width = codex_bar_width * (used / 100)
    local label = string.upper(window.label)
    local percent_label = string.format('%.0f%% used', used)
    local reset_label = format_reset_label(window)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 13)
    shared.set_hex(cr, 'f8fafc', 1)
    cairo_move_to(cr, x, y)
    cairo_show_text(cr, label)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 12)
    shared.set_hex(cr, '94a3b8', 1)
    cairo_move_to(cr, x + 94, y)
    cairo_show_text(cr, percent_label)

    local extents = cairo_text_extents_t:create()
    local reset_max_width = codex_bar_width - 162
    reset_label = shared.truncate_title(cr, reset_label, reset_max_width)
    cairo_text_extents(cr, reset_label, extents)

    shared.set_hex(cr, accent, 0.84)
    cairo_move_to(cr, x + codex_bar_width - extents.width - extents.x_bearing, y)
    cairo_show_text(cr, reset_label)

    local bar_y = y + 14
    shared.rounded_rect(cr, x, bar_y, codex_bar_width, codex_bar_height, 8)
    shared.set_hex(cr, '020617', 0.92)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.72)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    if fill_width > 0 then
      shared.rounded_rect(cr, x + 3, bar_y + 3, math.max(8, fill_width - 6), codex_bar_height - 6, 6)
      shared.set_hex(cr, accent, 0.68)
      cairo_fill(cr)
    end

    shared.set_hex(cr, accent_secondary, 0.26)
    cairo_set_line_width(cr, 1)
    local tick_gap = codex_bar_width / 10
    for tick = 1, 9 do
      local tick_x = x + tick * tick_gap
      cairo_move_to(cr, tick_x, bar_y + 4)
      cairo_line_to(cr, tick_x, bar_y + codex_bar_height - 4)
    end
    cairo_stroke(cr)

    shared.set_hex(cr, 'f8fafc', 0.22)
    cairo_move_to(cr, x + 8, bar_y + 8)
    cairo_line_to(cr, x + codex_bar_width - 8, bar_y + 8)
    cairo_stroke(cr)
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

  local function draw_codex_account_row(cr, account, x, y)
    local name = string.upper(account.label)
    local first = account.windows[1]
    local second = account.windows[2] or account.windows[1]
    local label_x = x + 22

    if account.is_selected then
      shared.set_hex(cr, 'ff9f1c', 0.20)
      cairo_set_line_width(cr, 5)
      cairo_move_to(cr, label_x - 20, y + 29)
      cairo_line_to(cr, label_x - 12, y + 36)
      cairo_line_to(cr, label_x - 20, y + 43)
      cairo_stroke(cr)

      shared.set_hex(cr, 'ff9f1c', 0.94)
      cairo_set_line_width(cr, 2)
      cairo_move_to(cr, label_x - 20, y + 29)
      cairo_line_to(cr, label_x - 12, y + 36)
      cairo_line_to(cr, label_x - 20, y + 43)
      cairo_stroke(cr)
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 14)
    if account.is_selected then
      shared.set_hex(cr, 'ffffff', 1)
    else
      shared.set_hex(cr, 'f8fafc', 0.90)
    end
    cairo_move_to(cr, label_x, y + 42)
    cairo_show_text(cr, shared.truncate_title(cr, name, 120))

    if first then
      draw_codex_bar(cr, first, x + 156, y + 18, '00e5ff', '8b5cf6')
    end
    if second then
      draw_codex_bar(cr, second, x + 156 + codex_bar_width + 42, y + 18, '39ff88', '00f5d4')
    end
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

    for index, account in ipairs(usage.accounts) do
      draw_codex_account_row(cr, account, x + 56, y + 38 + (index - 1) * 58)
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
    local dynamic_height = math.max(132, 72 + account_count * 58)
    local panel_width = math.min(codex_width, conky_window.width - 40)
    local x = (conky_window.width - panel_width) / 2
    local y = math.max(18, conky_window.height - dynamic_height - 18)
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
