-- Minecraft server status: an explicit availability badge beside player and
-- latency metrics, then the player list and host resources.
return function(shared, repo_root)
  local status_path = repo_root .. '/cache/minecraft-status.json'
  local ui = shared.ui
  local function read_status()
    local content = shared.read_file(status_path)
    if not content then
      return { ok = false, error = 'No minecraft-status.json cache found' }
    end
    return {
      ok = shared.json_boolean(content, 'ok', false),
      error = shared.json_string(content, 'error', ''),
      online = shared.json_number(content, 'onlinePlayers', 0),
      latency_ms = shared.json_number(content, 'latencyMs', 0),
      server_info_ok = shared.json_boolean(content, 'serverInfoOk', false),
      cpu_percent = shared.json_number(content, 'cpuPercent', 0),
      memory_mb = shared.json_number(content, 'memoryMb', 0),
      memory_limit_mb = shared.json_number(content, 'memoryLimitMb', 0),
      player_names = shared.json_array_strings(content, 'playerNames'),
      last_player_seen_epoch = shared.json_number(content, 'lastPlayerSeenAtEpoch', nil),
    }
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local state = read_status()
      -- The callout already carries the unavailable status, so the badge is
      -- only drawn for a server that answered.
      if not state.ok then ui.callout(cr, 'Unavailable', state.error, 0, 0, width, 'danger'); return end
      local badge_width = ui.badge(cr, 'Online', width, 0, 'good', {right = true})
      local half = (width - badge_width - 24) / 2
      ui.metric(cr, 'Players', tostring(state.online), 0, 0, half)
      ui.metric(cr, 'Ping ms', string.format('%.0f', state.latency_ms), half + 8, 0, half)
      local players = state.online == 0 and (state.last_player_seen_epoch and
        ('Last player ' .. ui.ago(os.time() - state.last_player_seen_epoch) .. ' ago') or 'No players online')
        or table.concat(state.player_names, ', ')
      ui.text(cr, players, 0, 68, {size = 13.5, color = ui.muted, width = width})
      if state.server_info_ok then
        ui.text(cr, string.format('CPU %.0f%%', state.cpu_percent), 0, 88, {size = 12, mono = true})
        ui.text(cr, string.format('RAM %.0f / %.0f MB', state.memory_mb, state.memory_limit_mb),
          width, 88, {size = 12, mono = true, align = 'right'})
      end
    end)
  end
  return {draw = draw}
end
