-- Realtime resource readings: a symbol over each current value with a 64px
-- history directly beneath, on a fixed zero-based scale.
return function(shared, repo_root)
  local ui = shared.ui
  local interval = 2
  local history_limit = math.floor(shared.clamp(tonumber(os.getenv('RESOURCE_HISTORY_SAMPLES')) or 90, 30, 180))
  local network_max = (tonumber(os.getenv('RESOURCE_NETWORK_MAX_MBPS')) or 12.5) * 1048576
  if network_max <= 0 then network_max = 12.5 * 1048576 end
  local history = {}
  local function read_proc(path)
    return shared.read_file(path) or ''
  end

  local function parse_cpu()
    local content = read_proc('/proc/stat')
    local user, nice, system, idle, iowait, irq, softirq, steal = content:match(
      'cpu%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)'
    )
    if not user then
      return { total = 0, idle = 0 }
    end

    return {
      total = tonumber(user) + tonumber(nice) + tonumber(system) + tonumber(idle)
        + tonumber(iowait) + tonumber(irq) + tonumber(softirq) + tonumber(steal),
      idle = tonumber(idle) + tonumber(iowait),
    }
  end

  local function parse_memory()
    local values = {}
    for key, value in read_proc('/proc/meminfo'):gmatch('([%w_]+):%s+(%d+)') do
      values[key] = tonumber(value) * 1024
    end

    local total = values.MemTotal or 0
    local available = values.MemAvailable
    if not available then
      available = (values.MemFree or 0) + (values.Buffers or 0) + (values.Cached or 0)
    end

    local used = math.max(0, total - available)
    return { percent = total > 0 and (used / total) * 100 or 0 }
  end

  local function default_network_interface()
    local best_interface = nil
    local best_metric = nil
    for line in read_proc('/proc/net/route'):gmatch('[^\r\n]+') do
      local interface, destination, gateway, flags, ref_count, use_count, metric = line:match(
        '^%s*(%S+)%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)'
      )
      if interface and destination == '00000000' and interface ~= 'lo' then
        local numeric_metric = tonumber(metric) or 0
        if not best_metric or numeric_metric < best_metric then
          best_interface = interface
          best_metric = numeric_metric
        end
      end
    end
    return best_interface
  end

  local function is_virtual_interface(interface)
    return interface == 'lo'
      or interface:match('^docker')
      or interface:match('^br%-')
      or interface:match('^veth')
      or interface:match('^virbr')
      or interface:match('^lxdbr')
      or interface:match('^incusbr')
  end

  local function parse_network()
    local selected_interface = default_network_interface()
    local selected_rx, selected_tx = 0, 0
    local selected_found = false
    local aggregate_rx, aggregate_tx = 0, 0

    for line in read_proc('/proc/net/dev'):gmatch('[^\r\n]+') do
      local interface, data = line:match('^%s*([^:]+):%s*(.*)$')
      if interface and data then
        interface = interface:gsub('%s+$', '')
        local fields = {}
        for field in data:gmatch('%S+') do
          table.insert(fields, field)
        end

        local rx_bytes = tonumber(fields[1]) or 0
        local tx_bytes = tonumber(fields[9]) or 0
        if not is_virtual_interface(interface) then
          aggregate_rx = aggregate_rx + rx_bytes
          aggregate_tx = aggregate_tx + tx_bytes
        end
        if selected_interface and interface == selected_interface then
          selected_rx = rx_bytes
          selected_tx = tx_bytes
          selected_found = true
        end
      end
    end

    if selected_found then
      return {
        interface = selected_interface,
        rx_bytes = selected_rx,
        tx_bytes = selected_tx,
      }
    end

    return {
      interface = selected_interface or 'all interfaces',
      rx_bytes = aggregate_rx,
      tx_bytes = aggregate_tx,
    }
  end

  local function collect_status(previous)
    local now = os.time()
    local cpu = parse_cpu()
    local memory = parse_memory()
    local network = parse_network()
    local delta_seconds = previous and now - previous.timestamp or 0
    local cpu_percent = 0
    local rx_rate, tx_rate = 0, 0

    if previous and delta_seconds > 0 and delta_seconds <= 30 then
      local total_delta = cpu.total - (previous.cpu_total or 0)
      local idle_delta = cpu.idle - (previous.cpu_idle or 0)
      if total_delta > 0 then
        cpu_percent = shared.clamp(((total_delta - idle_delta) / total_delta) * 100, 0, 100)
      end

      local rx_delta = network.rx_bytes - (previous.rx_bytes or 0)
      local tx_delta = network.tx_bytes - (previous.tx_bytes or 0)
      if rx_delta >= 0 then
        rx_rate = rx_delta / delta_seconds
      end
      if tx_delta >= 0 then
        tx_rate = tx_delta / delta_seconds
      end
    elseif previous and delta_seconds <= 0 then
      cpu_percent = previous.cpu or 0
      rx_rate = previous.rx_rate or 0
      tx_rate = previous.tx_rate or 0
    end

    return {
      measured = previous ~= nil and delta_seconds >= 0 and delta_seconds <= 30,
      timestamp = now,
      cpu = cpu_percent,
      cpu_total = cpu.total,
      cpu_idle = cpu.idle,
      ram = memory.percent,
      rx_rate = rx_rate,
      tx_rate = tx_rate,
      rx_bytes = network.rx_bytes,
      tx_bytes = network.tx_bytes,
    }
  end

  local function record_status(status)
    if #history > 0 and history[#history].timestamp == status.timestamp then
      history[#history] = status
    else
      table.insert(history, status)
    end
    while #history > history_limit do
      table.remove(history, 1)
    end
  end

  local function rate(bytes)
    if bytes >= 1048576 then return string.format('%.1f', bytes / 1048576), 'MB/s' end
    if bytes >= 1024 then return string.format('%.0f', bytes / 1024), 'KB/s' end
    return string.format('%.0f', bytes), 'B/s'
  end

  local channels = {
    {field = 'cpu', icon = 'cpu', max = 100, warning = 80, critical = 95},
    {field = 'ram', icon = 'memory-stick', max = 100, warning = 80, critical = 95},
    {field = 'rx_rate', icon = 'download', max = network_max, bytes = true},
    {field = 'tx_rate', icon = 'upload', max = network_max, bytes = true},
  }

  -- Positions come from elapsed time inside the fixed window; a delivery gap
  -- longer than 1.5 intervals breaks the trace instead of being bridged.
  local function plot(cr, channel, x, y, width)
    local now = os.time()
    local window = history_limit * interval
    local baseline = y + 60
    local function sx(timestamp) return x + shared.clamp((timestamp - (now - window)) / window, 0, 1) * width end
    local function sy(value) return baseline - math.min(1, value / channel.max) * 56 end
    ui.line_between(cr, x, baseline, x + width, baseline)
    if channel.warning then
      ui.dash(cr, x, sy(channel.warning), x + width, sy(channel.warning), ui.caution, 1, 3, 4, 0.45)
    end
    local segment, previous = {}, nil
    local function flush()
      if #segment > 1 then
        local area = {}
        for _, p in ipairs(segment) do area[#area + 1] = p end
        area[#area + 1] = {segment[#segment][1], baseline}
        area[#area + 1] = {segment[1][1], baseline}
        ui.polygon(cr, area, ui.accent, 0.12)
        ui.polyline(cr, segment, ui.accent, 1.5)
      elseif #segment == 1 then
        ui.circle(cr, segment[1][1], segment[1][2], 2, ui.accent)
      end
      segment = {}
    end
    for _, sample in ipairs(history) do
      local available = channel.field ~= 'cpu' or sample.measured
      if not available or (previous and sample.timestamp - previous > interval * 1.5) then flush() end
      if available then segment[#segment + 1] = {sx(sample.timestamp), sy(sample[channel.field])} end
      previous = sample.timestamp
    end
    flush()
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local status = collect_status(history[#history])
      record_status(status)
      local columns = math.max(1, math.floor((width + 16) / 172))
      local column_width = (width - (columns - 1) * 16) / columns
      for index, channel in ipairs(channels) do
        local x = ((index - 1) % columns) * (column_width + 16)
        local y = math.floor((index - 1) / columns) * 132
        if y + 116 > height then break end
        local value, unit, color = '—', '', ui.muted
        if channel.bytes then
          if status.measured then value, unit = rate(status[channel.field]) end
        elseif channel.field ~= 'cpu' or status.measured then
          value, unit = string.format('%.0f', status[channel.field]), '%'
          local reading = status[channel.field]
          if channel.critical and reading >= channel.critical then color = ui.danger
          elseif channel.warning and reading >= channel.warning then color = ui.caution end
        end
        ui.reading(cr, channel.icon, value, unit, x, y, column_width, color)
        plot(cr, channel, x, y + 52, column_width)
      end
    end)
  end
  return {draw = draw}
end
