-- Realtime resource readings: 132x132 270° arc gauges with a 24px history
-- directly beneath, on a fixed zero-based scale.
return function(shared, repo_root)
  local ui = shared.ui
  local interval = 2
  local history_limit = math.floor(shared.clamp(tonumber(os.getenv('RESOURCE_HISTORY_SAMPLES')) or 90, 30, 180))
  local network_max = (tonumber(os.getenv('RESOURCE_NETWORK_MAX_MBPS')) or 12.5) * 1048576
  if network_max <= 0 then network_max = 12.5 * 1048576 end
  local history = {}

  local net_week_seconds = 7 * 24 * 3600
  local net_week_flush_interval = 30
  local net_peaks_path = repo_root .. '/cache/resource-net-peaks.tsv'
  local net_week_peaks = {}
  local net_week_peaks_loaded = false
  local net_week_peaks_dirty = false
  local net_week_peaks_last_flush = 0

  local function hour_bucket(timestamp)
    return math.floor((timestamp or 0) / 3600) * 3600
  end

  local function parse_net_peaks_line(line)
    if line:match('^%s*#') then return nil end
    local hour_str, rx_str, tx_str, net_id = line:match('^%s*(%d+)%s+([%d%.]+)%s+([%d%.]+)%s*(%S*)')
    if not hour_str then return nil end
    local hour = tonumber(hour_str)
    local rx = tonumber(rx_str) or 0
    local tx = tonumber(tx_str) or 0
    -- Discard anomalous corruption/spikes (> 10 GB/s)
    local max_plausible = 10 * 1024 * 1024 * 1024
    if rx > max_plausible or tx > max_plausible then
      return nil
    end
    if not net_id or net_id == '' then
      net_id = 'default'
    end
    return hour, rx, tx, net_id
  end

  local function prune_net_week_peaks(now)
    local cutoff = (now or os.time()) - net_week_seconds
    for key, entry in pairs(net_week_peaks) do
      if entry.hour < cutoff then
        net_week_peaks[key] = nil
        net_week_peaks_dirty = true
      end
    end
  end

  local function merge_net_week_peak(hour, net_id, rx_rate, tx_rate)
    if not hour then return end
    net_id = (net_id and net_id ~= '') and net_id or 'default'
    local key = string.format('%d:%s', hour, net_id)
    local entry = net_week_peaks[key]
    local rx = math.max(0, rx_rate or 0)
    local tx = math.max(0, tx_rate or 0)
    if not entry then
      net_week_peaks[key] = {
        hour = hour,
        net_id = net_id,
        rx = rx,
        tx = tx,
      }
      net_week_peaks_dirty = true
      return
    end
    if rx > (entry.rx or 0) then
      entry.rx = rx
      net_week_peaks_dirty = true
    end
    if tx > (entry.tx or 0) then
      entry.tx = tx
      net_week_peaks_dirty = true
    end
  end

  local function write_net_week_peaks()
    local entries = {}
    for _, entry in pairs(net_week_peaks) do
      table.insert(entries, entry)
    end
    table.sort(entries, function(a, b)
      if a.hour ~= b.hour then
        return a.hour < b.hour
      end
      return (a.net_id or '') < (b.net_id or '')
    end)

    local lines = { '# hour_epoch rx_peak_bps tx_peak_bps network_id' }
    for _, entry in ipairs(entries) do
      table.insert(
        lines,
        string.format('%d %.0f %.0f %s', entry.hour, entry.rx or 0, entry.tx or 0, entry.net_id or 'default')
      )
    end

    local tmp_path = string.format(
      '%s.tmp.%d',
      net_peaks_path,
      math.floor((os.clock() % 1) * 1e9) + (os.time() % 100000)
    )
    local file = io.open(tmp_path, 'w')
    if not file then return end
    local wrote = file:write(table.concat(lines, '\n'))
    wrote = wrote and file:write('\n')
    local closed = file:close()
    if not wrote or not closed or not os.rename(tmp_path, net_peaks_path) then
      os.remove(tmp_path)
      return
    end
    net_week_peaks_dirty = false
    net_week_peaks_last_flush = os.time()
  end

  local function load_net_week_peaks()
    local content = shared.read_file(net_peaks_path)
    if content then
      for line in content:gmatch('[^\r\n]+') do
        local hour, rx, tx, net_id = parse_net_peaks_line(line)
        if hour then
          merge_net_week_peak(hour, net_id, rx, tx)
        end
      end
    end
    net_week_peaks_dirty = false
    net_week_peaks_loaded = true
    prune_net_week_peaks(os.time())
    if net_week_peaks_dirty then
      write_net_week_peaks()
    end
  end

  local function flush_net_week_peaks(now, force)
    now = now or os.time()
    if not net_week_peaks_dirty then return end
    if not force and (now - net_week_peaks_last_flush) < net_week_flush_interval then return end

    local content = shared.read_file(net_peaks_path)
    if content then
      for line in content:gmatch('[^\r\n]+') do
        local hour, rx, tx, net_id = parse_net_peaks_line(line)
        if hour then
          merge_net_week_peak(hour, net_id, rx, tx)
        end
      end
    end
    prune_net_week_peaks(now)
    write_net_week_peaks()
  end

  local function record_net_week_peaks(status)
    if not status or not status.measured then return end
    if not net_week_peaks_loaded then
      load_net_week_peaks()
    end
    local now = status.timestamp or os.time()
    local max_plausible = 10 * 1024 * 1024 * 1024
    local rx = math.min(status.rx_rate or 0, max_plausible)
    local tx = math.min(status.tx_rate or 0, max_plausible)
    merge_net_week_peak(hour_bucket(now), status.network_id, rx, tx)
    prune_net_week_peaks(now)
    flush_net_week_peaks(now, false)
  end

  local function get_network_week_peaks(net_id)
    if not net_week_peaks_loaded then
      load_net_week_peaks()
    end
    prune_net_week_peaks(os.time())
    local rx_peak = 0
    local tx_peak = 0
    local found = false
    if net_id and net_id ~= 'default' then
      for _, entry in pairs(net_week_peaks) do
        if entry.net_id == net_id or entry.net_id == 'default' then
          rx_peak = math.max(rx_peak, entry.rx or 0)
          tx_peak = math.max(tx_peak, entry.tx or 0)
          found = true
        end
      end
    end
    if not found then
      for _, entry in pairs(net_week_peaks) do
        rx_peak = math.max(rx_peak, entry.rx or 0)
        tx_peak = math.max(tx_peak, entry.tx or 0)
      end
    end
    return rx_peak, tx_peak
  end

  local function read_proc(path)
    return shared.read_file(path) or ''
  end

  local function hex_to_ip(hex)
    if not hex or #hex ~= 8 then return nil end
    local b1 = tonumber(hex:sub(7, 8), 16) or 0
    local b2 = tonumber(hex:sub(5, 6), 16) or 0
    local b3 = tonumber(hex:sub(3, 4), 16) or 0
    local b4 = tonumber(hex:sub(1, 2), 16) or 0
    return string.format('%d.%d.%d.%d', b1, b2, b3, b4)
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

  local function default_network_route()
    local best_interface, best_gateway, best_metric = nil, nil, nil
    for line in read_proc('/proc/net/route'):gmatch('[^\r\n]+') do
      local interface, destination, gateway, flags, ref_count, use_count, metric = line:match(
        '^%s*(%S+)%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)'
      )
      if interface and destination == '00000000' and interface ~= 'lo' then
        local numeric_metric = tonumber(metric) or 0
        if not best_metric or numeric_metric < best_metric then
          best_interface = interface
          best_gateway = gateway
          best_metric = numeric_metric
        end
      end
    end
    return best_interface, hex_to_ip(best_gateway)
  end

  local cached_net_check = 0
  local cached_net_id = 'default'

  local function get_current_network_id(interface, gateway_ip)
    local now = os.time()
    if now - cached_net_check < 15 and cached_net_id then
      return cached_net_id
    end
    cached_net_check = now
    if not interface then
      cached_net_id = 'default'
      return cached_net_id
    end

    if interface:match('^wl') or read_proc('/sys/class/net/' .. interface .. '/wireless') ~= '' then
      if io.popen then
        local ok, p = pcall(io.popen, 'iwgetid -r ' .. interface .. ' 2>/dev/null')
        if ok and p then
          local ssid = p:read('*l')
          p:close()
          if ssid and ssid:match('%S') then
            cached_net_id = ssid:gsub('%s+', '_')
            return cached_net_id
          end
        end
      end
    end

    if gateway_ip and gateway_ip ~= '' and gateway_ip ~= '0.0.0.0' then
      cached_net_id = interface .. '@' .. gateway_ip
    else
      cached_net_id = interface
    end
    return cached_net_id
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
    local selected_interface, gateway_ip = default_network_route()
    local network_id = get_current_network_id(selected_interface, gateway_ip)
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
        network_id = network_id,
        rx_bytes = selected_rx,
        tx_bytes = selected_tx,
      }
    end

    return {
      interface = selected_interface or 'all interfaces',
      network_id = network_id or 'default',
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
    local same_network = previous and previous.interface == network.interface and previous.network_id == network.network_id

    if previous and delta_seconds > 0 and delta_seconds <= 30 then
      local total_delta = cpu.total - (previous.cpu_total or 0)
      local idle_delta = cpu.idle - (previous.cpu_idle or 0)
      if total_delta > 0 then
        cpu_percent = shared.clamp(((total_delta - idle_delta) / total_delta) * 100, 0, 100)
      end

      if same_network then
        local rx_delta = network.rx_bytes - (previous.rx_bytes or 0)
        local tx_delta = network.tx_bytes - (previous.tx_bytes or 0)
        if rx_delta >= 0 then
          rx_rate = rx_delta / delta_seconds
        end
        if tx_delta >= 0 then
          tx_rate = tx_delta / delta_seconds
        end
      end
    elseif previous and delta_seconds <= 0 then
      cpu_percent = previous.cpu or 0
      rx_rate = previous.rx_rate or 0
      tx_rate = previous.tx_rate or 0
    end

    return {
      measured = previous ~= nil and delta_seconds >= 0 and delta_seconds <= 30 and (same_network or previous == nil),
      timestamp = now,
      cpu = cpu_percent,
      cpu_total = cpu.total,
      cpu_idle = cpu.idle,
      ram = memory.percent,
      rx_rate = rx_rate,
      tx_rate = tx_rate,
      rx_bytes = network.rx_bytes,
      tx_bytes = network.tx_bytes,
      interface = network.interface,
      network_id = network.network_id,
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

  -- Positions come from elapsed time inside the fixed window; a delivery gap
  -- longer than 1.5 intervals breaks the trace instead of being bridged.
  local function plot(cr, channel, x, y, width, current_reading)
    local now = os.time()
    local window = history_limit * interval
    local bottom = y + 20
    local scale_h = 16
    local function sx(timestamp) return x + shared.clamp((timestamp - (now - window)) / window, 0, 1) * width end
    local function sy(value) return bottom - math.min(1, value / channel.max) * scale_h end
    ui.line_between(cr, x, bottom, x + width, bottom, ui.line, 1)
    if channel.warning and channel.warning <= channel.max then
      ui.dash(cr, x, sy(channel.warning), x + width, sy(channel.warning), ui.caution, 1, 3, 4, 0.45)
    end
    local trace_color, trace_alpha, area_alpha = ui.accent, 1.0, 0.12
    if channel.warning or channel.critical then
      if channel.critical and current_reading and current_reading >= channel.critical then
        trace_color, trace_alpha, area_alpha = ui.danger, 1.0, 0.20
      elseif channel.warning and current_reading and current_reading >= channel.warning then
        trace_color, trace_alpha, area_alpha = ui.caution, 1.0, 0.20
      else
        trace_color, trace_alpha, area_alpha = ui.good, 0.50, 0.12
      end
    end
    local segment, previous = {}, nil
    local function flush()
      if #segment > 1 then
        local area = {}
        for _, p in ipairs(segment) do area[#area + 1] = p end
        area[#area + 1] = {segment[#segment][1], bottom}
        area[#area + 1] = {segment[1][1], bottom}
        ui.polygon(cr, area, trace_color, area_alpha)
        ui.polyline(cr, segment, trace_color, 1.5, trace_alpha)
      elseif #segment == 1 then
        ui.circle(cr, segment[1][1], segment[1][2], 2, trace_color, trace_alpha)
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
      record_net_week_peaks(status)

      local rx_week_peak, tx_week_peak = get_network_week_peaks(status.network_id)
      local default_ceiling = network_max
      local rx_max = math.max((rx_week_peak and rx_week_peak > 0) and rx_week_peak or default_ceiling, status.rx_rate or 0, 1024)
      local tx_max = math.max((tx_week_peak and tx_week_peak > 0) and tx_week_peak or default_ceiling, status.tx_rate or 0, 1024)

      local channels = {
        {field = 'cpu', icon = 'cpu', max = 100, warning = 80, critical = 95},
        {field = 'ram', icon = 'memory-stick', max = 100, warning = 80, critical = 95},
        {
          field = 'rx_rate',
          icon = 'download',
          max = rx_max,
          warning = rx_max * 0.80,
          critical = rx_max * 0.95,
          bytes = true,
        },
        {
          field = 'tx_rate',
          icon = 'upload',
          max = tx_max,
          warning = tx_max * 0.80,
          critical = tx_max * 0.95,
          bytes = true,
        },
      }

      local columns = #channels
      local gap = 6
      local column_width = math.floor((width - (columns - 1) * gap) / columns)
      local dial_size = math.min(column_width, 88)
      local show_sparkline = height >= dial_size + 24
      local y = show_sparkline and 0 or math.max(0, math.floor((height - dial_size) / 2))

      for index, channel in ipairs(channels) do
        local x = (index - 1) * (column_width + gap)
        local value, unit, color = '—', '', ui.muted
        local reading = nil
        local measured = false
        if channel.bytes then
          if status.measured then
            measured = true
            reading = status[channel.field]
            value, unit = rate(reading)
          end
        elseif channel.field ~= 'cpu' or status.measured then
          measured = true
          reading = status[channel.field]
          value, unit = string.format('%.0f', reading), '%'
        end

        if measured and reading then
          if channel.critical and reading >= channel.critical then
            color = ui.danger
          elseif channel.warning and reading >= channel.warning then
            color = ui.caution
          end
        end

        ui.arc_gauge(cr, channel.icon, value, unit, x, y, column_width, {
          size = dial_size,
          max = channel.max,
          warning = channel.warning,
          critical = channel.critical,
          color = color,
          reading = reading,
          measured = measured,
        })
        if show_sparkline then
          plot(cr, channel, x, y + dial_size + 2, column_width, reading)
        end
      end
    end)
  end
  return {draw = draw}
end
