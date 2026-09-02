return function(shared, repo_root)
  local status_path = repo_root .. '/cache/minecraft-status.json'
  local font = 'JetBrains Mono'
  local configured_panel_width = 360
  local panel_width = configured_panel_width
  local panel_height = 110
  local radius = 18
  local bottom_padding = 4
  local info_x = 26
  local names_x = 168
  local divider_x = 148

  local function parse_string_array(content, key)
    return shared.json_array_strings(content, key)
  end

  local function format_memory(value_mb, limit_mb)
    if limit_mb and limit_mb > 0 then
      if limit_mb >= 1024 then
        return string.format('%.1f/%.0f GB', value_mb / 1024, limit_mb / 1024)
      end
      return string.format('%.0f/%d MB', value_mb, limit_mb)
    end

    if value_mb >= 1024 then
      return string.format('%.1f GB', value_mb / 1024)
    end
    return string.format('%.0f MB', value_mb)
  end

  local function usage_color(percent)
    if percent >= 85 then
      return 'f87171'
    end
    if percent >= 65 then
      return 'facc15'
    end
    return '39ff88'
  end

  local function ping_color(latency_ms)
    if latency_ms >= 180 then
      return 'f87171'
    end
    if latency_ms >= 100 then
      return 'facc15'
    end
    return '39ff88'
  end

  local function format_ago(seconds)
    if not seconds or seconds < 0 then
      seconds = 0
    end
    if seconds < 60 then
      return string.format('%ds', math.floor(seconds))
    end
    if seconds < 3600 then
      return string.format('%dm', math.floor(seconds / 60))
    end
    if seconds < 86400 then
      local hours = math.floor(seconds / 3600)
      local minutes = math.floor((seconds % 3600) / 60)
      if minutes > 0 then
        return string.format('%dh %dm', hours, minutes)
      end
      return string.format('%dh', hours)
    end
    local days = math.floor(seconds / 86400)
    local hours = math.floor((seconds % 86400) / 3600)
    if hours > 0 then
      return string.format('%dd %dh', days, hours)
    end
    return string.format('%dd', days)
  end

  local function empty_players_label(status)
    if status.last_player_seen_epoch and status.last_player_seen_epoch > 0 then
      local ago = os.time() - status.last_player_seen_epoch
      return 'Last player ' .. format_ago(ago) .. ' ago'
    end
    return 'No players online'
  end

  local function draw_info_row(cr, label, value, x, y, color)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, 'f8fafc', 0.50)
    cairo_move_to(cr, x, y)
    cairo_show_text(cr, label)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 11)
    shared.set_hex(cr, color, 0.92)
    cairo_move_to(cr, x + 40, y)
    cairo_show_text(cr, shared.truncate_title(cr, value, 82))
  end

  local function draw_metric_value(cr, value, x, y, color)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 11)
    shared.set_hex(cr, color, 0.92)
    cairo_move_to(cr, x, y)
    cairo_show_text(cr, value)
  end

  local function draw_chip(cr, label, x, y, width, color)
    shared.rounded_rect(cr, x, y, width, 20, 6)
    shared.set_hex(cr, '020617', 0.94)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, color, 0.82)
    cairo_set_line_width(cr, 1.5)
    cairo_stroke(cr)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 12)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    local text_x = x + (width - extents.width) / 2 - extents.x_bearing
    shared.set_hex(cr, color, 1)
    cairo_move_to(cr, text_x, y + 15)
    cairo_show_text(cr, label)
  end

  local function read_status()
    local content = shared.read_file(status_path)
    if not content then
      return {
        ok = false,
        error = 'No minecraft-status.json cache found.',
      }
    end

    local ok = shared.json_boolean(content, 'ok', false)
    local error_message = shared.json_string(content, 'error', '')
    local online = shared.json_number(content, 'onlinePlayers', 0)
    local latency_ms = shared.json_number(content, 'latencyMs', 0)
    local server_info_ok = shared.json_boolean(content, 'serverInfoOk', false)
    local cpu_percent = shared.json_number(content, 'cpuPercent', 0)
    local memory_mb = shared.json_number(content, 'memoryMb', 0)
    local memory_limit_mb = shared.json_number(content, 'memoryLimitMb', 0)
    local player_names = parse_string_array(content, 'playerNames')
    local last_player_seen_epoch = shared.json_number(content, 'lastPlayerSeenAtEpoch', nil)

    return {
      ok = ok,
      error = error_message,
      online = online,
      latency_ms = latency_ms,
      server_info_ok = server_info_ok,
      cpu_percent = cpu_percent,
      memory_mb = memory_mb,
      memory_limit_mb = memory_limit_mb,
      player_names = player_names,
      last_player_seen_epoch = last_player_seen_epoch,
    }
  end

  local function draw_frame(cr, x, y, accent, secondary)
    shared.rounded_rect(cr, x + 4, y + 7, panel_width, panel_height, radius)
    shared.set_hex(cr, accent, 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, panel_width, panel_height, radius)
    shared.set_hex(cr, accent, 0.16)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, panel_width, panel_height, radius)
    shared.set_hex(cr, secondary, 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, panel_width, panel_height, radius)
    shared.set_hex(cr, '020617', 0.59)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.70)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 8, y + 8, panel_width - 16, panel_height - 16, radius - 6)
    shared.set_hex(cr, secondary, 0.24)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
  end

  local function draw_status(cr, status, x, y)
    local accent = status.ok and '39ff88' or 'f87171'
    local secondary = status.ok and '00e5ff' or 'ff4d00'
    local content_x = status.server_info_ok and names_x or info_x
    local ping_x = status.server_info_ok and info_x or info_x + 64
    local online_value_offset = status.server_info_ok and 52 or 42
    local summary_y = y + 36

    draw_frame(cr, x, y, accent, secondary)
    draw_chip(cr, 'MINECRAFT', x + 28, y - 9, 112, accent)
    draw_chip(cr, status.ok and 'ONLINE' or 'OFFLINE', x + panel_width - 102, y - 9, 74, status.ok and secondary or accent)

    if not status.ok then
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
      cairo_set_font_size(cr, 28)
      shared.set_hex(cr, 'f87171', 1)
      cairo_move_to(cr, x + 26, y + 66)
      cairo_show_text(cr, 'OFFLINE')

      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
      cairo_set_font_size(cr, 10)
      shared.set_hex(cr, 'f8fafc', 0.78)
      cairo_move_to(cr, x + 26, y + 92)
      cairo_show_text(cr, shared.truncate_title(cr, status.error, panel_width - 52))
      return
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.72)
    cairo_move_to(cr, x + content_x, summary_y)
    cairo_show_text(cr, 'ONLINE')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 10)
    shared.set_hex(cr, accent, 0.72)
    cairo_move_to(cr, x + content_x + online_value_offset, summary_y)
    cairo_show_text(cr, string.format('%d', status.online))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 11)
    if #status.player_names > 0 then
      for index = 1, math.min(3, #status.player_names) do
        shared.set_hex(cr, 'f8fafc', index == 1 and 0.86 or 0.62)
        cairo_move_to(cr, x + content_x, y + 56 + (index - 1) * 15)
        cairo_show_text(cr, shared.truncate_title(cr, status.player_names[index], 160))
      end
    else
      shared.set_hex(cr, 'f8fafc', 0.52)
      cairo_move_to(cr, x + content_x, y + 64)
      local empty_label = status.online > 0 and 'Names unavailable' or empty_players_label(status)
      cairo_show_text(cr, shared.truncate_title(cr, empty_label, 160))
    end

    if status.server_info_ok then
      draw_metric_value(cr, string.format('%dms', status.latency_ms), x + info_x, summary_y, ping_color(status.latency_ms))
      local memory_percent = 0
      if status.memory_limit_mb > 0 then
        memory_percent = (status.memory_mb / status.memory_limit_mb) * 100
      end
      draw_info_row(cr, 'CPU', string.format('%.1f%%', status.cpu_percent), x + info_x, y + 64, usage_color(status.cpu_percent))
      draw_info_row(cr, 'RAM', format_memory(status.memory_mb, status.memory_limit_mb), x + info_x, y + 86, usage_color(memory_percent))
    else
      draw_metric_value(cr, string.format('%dms', status.latency_ms), x + ping_x, summary_y, ping_color(status.latency_ms))
    end

    if status.server_info_ok then
      shared.set_hex(cr, secondary, 0.42)
      cairo_set_line_width(cr, 1)
      cairo_move_to(cr, x + divider_x, y + 32)
      cairo_line_to(cr, x + divider_x, y + 96)
      cairo_stroke(cr)
    end
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local status = read_status()
    local window_width = tonumber(conky_window and conky_window.width) or 0
    if window_width > 24 then
      panel_width = math.min(configured_panel_width, window_width - 24)
    else
      panel_width = configured_panel_width
    end
    local y = math.max(bottom_padding, conky_window.height - panel_height - bottom_padding)
    draw_status(cr, status, 8, y)

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
