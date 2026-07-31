return function(shared, repo_root)
  local font = 'JetBrains Mono'
  local hud_width = 268
  -- Gauge arc tops sit at y=12, matching Linear card top_padding.
  local gauge_center_y = 45
  local history_limit = tonumber(os.getenv('RESOURCE_HISTORY_SAMPLES') or '') or 90
  history_limit = math.floor(shared.clamp(history_limit, 30, 180))
  -- NET gauge arcs use a short moving average so bursty traffic does not make
  -- the needles jump every refresh. Readouts and sparklines stay on raw rates.
  local net_gauge_window = math.floor(
    shared.clamp(tonumber(os.getenv('RESOURCE_NET_GAUGE_WINDOW') or '') or 6, 2, 30)
  )
  -- Each Conky window keeps its own samples. This makes the HUD safe to show on
  -- every display without several renderers contending for one cache file.
  local history = {}

  local colors = {
    text = 'f8fafc',
    muted = '94a3b8',
    dim = '334155',
    cyan = '00e5ff',
    green = '39ff88',
    violet = 'a78bfa',
    amber = 'ffb454',
    magenta = 'f472b6',
    red = 'f87171',
  }

  local function read_proc(path)
    return shared.read_file(path) or ''
  end

  local function parse_cpu()
    local content = read_proc('/proc/stat')
    local user, nice, system, idle, iowait, irq, softirq, steal = content:match(
      'cpu%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)'
    )
    if not user then
      return { total = 0, idle = 0, cores = 1 }
    end

    local cpuinfo = read_proc('/proc/cpuinfo')
    local _, core_count = cpuinfo:gsub('processor%s*:%s*%d+', '')
    return {
      total = tonumber(user) + tonumber(nice) + tonumber(system) + tonumber(idle)
        + tonumber(iowait) + tonumber(irq) + tonumber(softirq) + tonumber(steal),
      idle = tonumber(idle) + tonumber(iowait),
      cores = math.max(1, core_count),
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
    return {
      total = total,
      used = used,
      percent = total > 0 and (used / total) * 100 or 0,
    }
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

  local function parse_mount(path)
    local pipe = io.popen('df -Pk ' .. path .. ' 2>/dev/null')
    if not pipe then
      return { total = 0, used = 0, percent = 0 }
    end

    local output = pipe:read('*a') or ''
    pipe:close()
    local total_kb, used_kb, _available_kb, percent = output:match(
      '\n%S+%s+(%d+)%s+(%d+)%s+(%d+)%s+(%d+)%%'
    )
    if not total_kb then
      return { total = 0, used = 0, percent = 0 }
    end

    return {
      total = tonumber(total_kb) * 1024,
      used = tonumber(used_kb) * 1024,
      percent = tonumber(percent) or 0,
    }
  end

  local function parse_disks()
    return {
      root = parse_mount('/'),
      home = parse_mount('/home'),
    }
  end

  local function parse_system_state()
    local uptime = tonumber(read_proc('/proc/uptime'):match('^([%d%.]+)')) or 0
    local load_content = read_proc('/proc/loadavg')
    local load_one, load_five, load_fifteen = load_content:match('^([%d%.]+)%s+([%d%.]+)%s+([%d%.]+)')
    return {
      uptime = uptime,
      load_one = tonumber(load_one) or 0,
      load_five = tonumber(load_five) or 0,
      load_fifteen = tonumber(load_fifteen) or 0,
    }
  end

  local function collect_status(previous)
    local now = os.time()
    local cpu = parse_cpu()
    local memory = parse_memory()
    local network = parse_network()
    local disks = parse_disks()
    local system = parse_system_state()
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
      timestamp = now,
      cpu = cpu_percent,
      cpu_total = cpu.total,
      cpu_idle = cpu.idle,
      cores = cpu.cores,
      ram = memory.percent,
      memory_used = memory.used,
      memory_total = memory.total,
      net = rx_rate + tx_rate,
      rx_rate = rx_rate,
      tx_rate = tx_rate,
      rx_bytes = network.rx_bytes,
      tx_bytes = network.tx_bytes,
      network_interface = network.interface,
      root_disk = disks.root.percent,
      root_disk_used = disks.root.used,
      root_disk_total = disks.root.total,
      home_disk = disks.home.percent,
      home_disk_used = disks.home.used,
      home_disk_total = disks.home.total,
      uptime = system.uptime,
      load_one = system.load_one,
      load_five = system.load_five,
      load_fifteen = system.load_fifteen,
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

  local function average_history_field(field, window)
    if #history == 0 then
      return 0
    end
    local start = math.max(1, #history - window + 1)
    local sum = 0
    local count = 0
    for index = start, #history do
      sum = sum + (history[index][field] or 0)
      count = count + 1
    end
    return count > 0 and sum / count or 0
  end

  local function format_rate_compact(bytes)
    if not bytes or bytes <= 0 then
      return '0'
    end
    if bytes >= 1024 * 1024 then
      return string.format('%.1fM', bytes / (1024 * 1024))
    end
    if bytes >= 1024 then
      return string.format('%.0fK', bytes / 1024)
    end
    return string.format('%.0fB', bytes)
  end

  local function format_duration(seconds)
    if not seconds or seconds <= 0 then
      return '--'
    end
    local days = math.floor(seconds / 86400)
    local hours = math.floor((seconds % 86400) / 3600)
    local minutes = math.floor((seconds % 3600) / 60)
    if days > 0 then
      return string.format('%dd %02dh', days, hours)
    end
    if hours > 0 then
      return string.format('%dh %02dm', hours, minutes)
    end
    return string.format('%dm', minutes)
  end

  local function format_gib_fraction(used, total)
    local gib = 1024 * 1024 * 1024
    if not total or total <= 0 then
      return '--'
    end
    return string.format('%.0f/%.0fG', (used or 0) / gib, total / gib)
  end

  local function usage_color(percent, normal_color)
    if percent >= 85 then
      return colors.red
    end
    if percent >= 65 then
      return colors.amber
    end
    return normal_color
  end

  local function draw_text(cr, value, x, y, size, color, alpha, weight)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, weight or CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, size)
    shared.set_hex(cr, color, alpha or 1)
    cairo_move_to(cr, x, y)
    cairo_show_text(cr, value or '')
  end

  local function draw_centered_text(cr, value, center_x, y, size, color, alpha, weight)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, weight or CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, size)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, value, extents)
    shared.set_hex(cr, color, alpha or 1)
    cairo_move_to(cr, center_x - extents.width / 2 - extents.x_bearing, y)
    cairo_show_text(cr, value)
  end

  local function draw_gauge(cr, metric, center_x, center_y, radius)
    local start_angle = math.pi * 0.75
    local end_angle = math.pi * 2.25
    local sweep = end_angle - start_angle
    local value = shared.clamp(metric.percent or 0, 0, 100)
    local active_angle = start_angle + sweep * value / 100

    -- A faint halo makes the readings legible without turning the HUD into a box.
    shared.set_hex(cr, metric.color, 0.055)
    cairo_arc(cr, center_x, center_y, radius - 7, 0, math.pi * 2)
    cairo_fill(cr)

    cairo_new_path(cr)
    shared.set_hex(cr, colors.dim, 0.72)
    cairo_set_line_width(cr, 4)
    cairo_arc(cr, center_x, center_y, radius, start_angle, end_angle)
    cairo_stroke(cr)

    cairo_new_path(cr)
    for tick = 0, 12 do
      local tick_angle = start_angle + sweep * tick / 12
      local outer_radius = radius + 4
      local inner_radius = outer_radius - (tick % 3 == 0 and 5 or 3)
      local active = tick / 12 <= value / 100
      shared.set_hex(cr, active and metric.color or colors.dim, active and 0.84 or 0.42)
      cairo_set_line_width(cr, tick % 3 == 0 and 1.2 or 0.8)
      cairo_move_to(
        cr,
        center_x + math.cos(tick_angle) * outer_radius,
        center_y + math.sin(tick_angle) * outer_radius
      )
      cairo_line_to(
        cr,
        center_x + math.cos(tick_angle) * inner_radius,
        center_y + math.sin(tick_angle) * inner_radius
      )
      cairo_stroke(cr)
    end

    if value > 0.2 then
      cairo_new_path(cr)
      shared.set_hex(cr, metric.color, 0.13)
      cairo_set_line_width(cr, 11)
      cairo_arc(cr, center_x, center_y, radius, start_angle, active_angle)
      cairo_stroke(cr)

      cairo_new_path(cr)
      shared.set_hex(cr, metric.color, 0.98)
      cairo_set_line_width(cr, 3.4)
      if cairo_set_line_cap and CAIRO_LINE_CAP_ROUND then
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
      end
      cairo_arc(cr, center_x, center_y, radius, start_angle, active_angle)
      cairo_stroke(cr)
    end

    local needle_outer = radius - 6
    local needle_inner = math.max(12, radius * 0.42)
    local needle_cos = math.cos(active_angle)
    local needle_sin = math.sin(active_angle)
    cairo_new_path(cr)
    shared.set_hex(cr, metric.color, 0.88)
    cairo_set_line_width(cr, 1.25)
    if cairo_set_line_cap and CAIRO_LINE_CAP_ROUND then
      cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    end
    cairo_move_to(
      cr,
      center_x + needle_cos * needle_inner,
      center_y + needle_sin * needle_inner
    )
    cairo_line_to(
      cr,
      center_x + needle_cos * needle_outer,
      center_y + needle_sin * needle_outer
    )
    cairo_stroke(cr)

    draw_centered_text(
      cr,
      metric.value,
      center_x,
      center_y + 5,
      metric.value_size or 13,
      colors.text,
      0.98,
      CAIRO_FONT_WEIGHT_BOLD
    )
    draw_centered_text(
      cr,
      metric.label,
      center_x,
      center_y + radius + 3,
      7,
      metric.color,
      0.94,
      CAIRO_FONT_WEIGHT_BOLD
    )
  end

  local function draw_gauge_arc(cr, center_x, center_y, radius, percent, color, line_width, glow_width)
    local start_angle = math.pi * 0.75
    local end_angle = math.pi * 2.25
    local sweep = end_angle - start_angle
    local value = shared.clamp(percent or 0, 0, 100)

    cairo_new_path(cr)
    shared.set_hex(cr, colors.dim, 0.72)
    cairo_set_line_width(cr, line_width + 0.6)
    cairo_arc(cr, center_x, center_y, radius, start_angle, end_angle)
    cairo_stroke(cr)

    if value <= 0.2 then
      return
    end

    local active_angle = start_angle + sweep * value / 100
    if glow_width and glow_width > 0 then
      cairo_new_path(cr)
      shared.set_hex(cr, color, 0.12)
      cairo_set_line_width(cr, glow_width)
      cairo_arc(cr, center_x, center_y, radius, start_angle, active_angle)
      cairo_stroke(cr)
    end

    cairo_new_path(cr)
    shared.set_hex(cr, color, 0.98)
    cairo_set_line_width(cr, line_width)
    if cairo_set_line_cap and CAIRO_LINE_CAP_ROUND then
      cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    end
    cairo_arc(cr, center_x, center_y, radius, start_angle, active_angle)
    cairo_stroke(cr)
  end

  -- Outer ring = download, inner ring = upload; center still shows combined rate.
  local function draw_net_gauge(cr, metric, center_x, center_y, radius)
    local down_radius = radius
    local up_radius = math.max(12, radius - 11)

    shared.set_hex(cr, metric.down_color, 0.055)
    cairo_arc(cr, center_x, center_y, radius - 7, 0, math.pi * 2)
    cairo_fill(cr)

    local start_angle = math.pi * 0.75
    local end_angle = math.pi * 2.25
    local sweep = end_angle - start_angle
    local down_value = shared.clamp(metric.down_percent or 0, 0, 100)
    for tick = 0, 12 do
      local tick_angle = start_angle + sweep * tick / 12
      local outer_radius = radius + 4
      local inner_radius = outer_radius - (tick % 3 == 0 and 5 or 3)
      local active = tick / 12 <= down_value / 100
      shared.set_hex(cr, active and metric.down_color or colors.dim, active and 0.84 or 0.42)
      cairo_set_line_width(cr, tick % 3 == 0 and 1.2 or 0.8)
      cairo_move_to(
        cr,
        center_x + math.cos(tick_angle) * outer_radius,
        center_y + math.sin(tick_angle) * outer_radius
      )
      cairo_line_to(
        cr,
        center_x + math.cos(tick_angle) * inner_radius,
        center_y + math.sin(tick_angle) * inner_radius
      )
      cairo_stroke(cr)
    end

    draw_gauge_arc(cr, center_x, center_y, down_radius, metric.down_percent, metric.down_color, 3.2, 9)
    draw_gauge_arc(cr, center_x, center_y, up_radius, metric.up_percent, metric.up_color, 2.4, 6)

    shared.set_hex(cr, colors.dim, 0.9)
    cairo_arc(cr, center_x, center_y, 2.0, 0, math.pi * 2)
    cairo_fill(cr)

    draw_centered_text(
      cr,
      metric.value,
      center_x,
      center_y + 5,
      metric.value_size or 12,
      colors.text,
      0.98,
      CAIRO_FONT_WEIGHT_BOLD
    )
    draw_centered_text(
      cr,
      metric.label,
      center_x,
      center_y + radius + 3,
      7,
      metric.down_color,
      0.94,
      CAIRO_FONT_WEIGHT_BOLD
    )
  end

  local function draw_trace(cr, values, x, y, width, height, color, maximum)
    local scale = math.max(maximum or 1, 1)

    shared.set_hex(cr, colors.dim, 0.45)
    cairo_set_line_width(cr, 0.7)
    cairo_move_to(cr, x, y + height)
    cairo_line_to(cr, x + width, y + height)
    cairo_stroke(cr)

    if #values == 0 then
      return
    end

    cairo_new_path(cr)
    for index, value in ipairs(values) do
      local progress = #values == 1 and 1 or (index - 1) / (#values - 1)
      local normalized = shared.clamp((value or 0) / scale, 0, 1)
      local point_x = x + progress * width
      local point_y = y + height - normalized * height
      if index == 1 then
        cairo_move_to(cr, point_x, point_y)
      else
        cairo_line_to(cr, point_x, point_y)
      end
    end
    shared.set_hex(cr, color, 0.94)
    cairo_set_line_width(cr, 1.1)
    cairo_stroke(cr)

    local last_value = values[#values] or 0
    local last_y = y + height - shared.clamp(last_value / scale, 0, 1) * height
    shared.set_hex(cr, color, 1)
    cairo_arc(cr, x + width, last_y, 1.5, 0, math.pi * 2)
    cairo_fill(cr)
  end

  local function draw_readout(cr, label, value, x, y, color, cell_width)
    local label_size = 8
    local value_size = 11
    local text_value = value or ''

    draw_text(cr, label, x, y, label_size, colors.muted, 0.86, CAIRO_FONT_WEIGHT_BOLD)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, value_size)
    local value_extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, text_value, value_extents)

    -- Right-align within the cell so long values cannot spill into the next column.
    local value_x = x + cell_width - value_extents.width - value_extents.x_bearing
    if value_x < x then
      value_x = x
    end

    draw_text(cr, text_value, value_x, y, value_size, color or colors.text, 0.98, CAIRO_FONT_WEIGHT_BOLD)
  end

  -- Fill readouts in column-major order so paired metrics stack vertically
  -- under the gauges (LOAD/UP, //home, IN/OUT). Middle column is wider for
  -- long disk fractions so they do not collide with IN/OUT.
  local function draw_readout_grid(cr, items, origin_x, origin_y, grid_width, cols, row_height)
    cols = cols or 3
    local rows = math.max(1, math.ceil(#items / cols))
    local weights = { 0.30, 0.40, 0.30 }
    local weight_sum = 0
    for col = 1, cols do
      weight_sum = weight_sum + (weights[col] or (1 / cols))
    end
    local col_widths = {}
    local col_origins = {}
    local cursor = origin_x
    for col = 0, cols - 1 do
      local width = grid_width * ((weights[col + 1] or (1 / cols)) / weight_sum)
      col_widths[col] = width
      col_origins[col] = cursor
      cursor = cursor + width
    end
    local cell_pad = 3
    for index, item in ipairs(items) do
      local col = math.floor((index - 1) / rows)
      local row = (index - 1) % rows
      draw_readout(
        cr,
        item.label,
        item.value,
        col_origins[col] + cell_pad,
        origin_y + row * row_height,
        item.color,
        col_widths[col] - cell_pad * 2
      )
    end
  end

  local function draw_hud(cr, status, x, y)
    local cpu_color = usage_color(status.cpu, colors.green)
    local ram_color = usage_color(status.ram, colors.violet)
    local disk_color = usage_color(math.max(status.root_disk or 0, status.home_disk or 0), colors.amber)
    local rx_peak, tx_peak, net_peak = 1024, 1024, 1024
    for _, sample in ipairs(history) do
      rx_peak = math.max(rx_peak, sample.rx_rate or 0)
      tx_peak = math.max(tx_peak, sample.tx_rate or 0)
      net_peak = math.max(net_peak, sample.net or 0)
    end
    local rx_ceiling = math.max(1024, rx_peak * 1.12)
    local tx_ceiling = math.max(1024, tx_peak * 1.12)
    local net_ceiling = math.max(1024, net_peak * 1.12)
    local smooth_rx = average_history_field('rx_rate', net_gauge_window)
    local smooth_tx = average_history_field('tx_rate', net_gauge_window)
    local smooth_net = smooth_rx + smooth_tx
    local down_percent = shared.clamp((smooth_rx / rx_ceiling) * 100, 0, 100)
    local up_percent = shared.clamp((smooth_tx / tx_ceiling) * 100, 0, 100)

    draw_gauge(cr, {
      label = 'CPU',
      value = string.format('%.0f%%', status.cpu),
      percent = status.cpu,
      color = cpu_color,
    }, x + 38, y + gauge_center_y, 33)
    draw_gauge(cr, {
      label = 'RAM',
      value = string.format('%.0f%%', status.ram),
      percent = status.ram,
      color = ram_color,
    }, x + 134, y + gauge_center_y, 33)
    draw_net_gauge(cr, {
      label = 'NET',
      value = format_rate_compact(smooth_net),
      down_percent = down_percent,
      up_percent = up_percent,
      down_color = colors.cyan,
      up_color = colors.magenta,
      value_size = #format_rate_compact(smooth_net) > 4 and 10 or 12,
    }, x + 230, y + gauge_center_y, 33)

    local cpu_trace, ram_trace, net_trace = {}, {}, {}
    for _, sample in ipairs(history) do
      table.insert(cpu_trace, sample.cpu or 0)
      table.insert(ram_trace, sample.ram or 0)
      table.insert(net_trace, sample.net or 0)
    end
    draw_trace(cr, cpu_trace, x + 12, y + 90, hud_width - 24, 8, cpu_color, 100)
    draw_trace(cr, ram_trace, x + 12, y + 103, hud_width - 24, 8, ram_color, 100)
    draw_trace(cr, net_trace, x + 12, y + 116, hud_width - 24, 8, colors.cyan, net_ceiling)

    draw_readout_grid(cr, {
      { label = 'LOAD', value = string.format('%.2f', status.load_one), color = cpu_color },
      { label = 'UP', value = format_duration(status.uptime), color = colors.green },
      {
        label = '/',
        value = format_gib_fraction(status.root_disk_used, status.root_disk_total),
        color = disk_color,
      },
      {
        label = '/home',
        value = format_gib_fraction(status.home_disk_used, status.home_disk_total),
        color = disk_color,
      },
      { label = 'IN', value = format_rate_compact(status.rx_rate) .. '/s', color = colors.cyan },
      { label = 'OUT', value = format_rate_compact(status.tx_rate) .. '/s', color = colors.magenta },
    }, x + 13, y + 157, hud_width - 26, 3, 19)
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local status = collect_status(history[#history])
    record_status(status)
    local x = math.max(6, math.floor((conky_window.width - hud_width) / 2))
    draw_hud(cr, status, x, 0)

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
