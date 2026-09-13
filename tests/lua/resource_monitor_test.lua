-- Drive the real sampler and renderer with counter snapshots and GPU query
-- results, keeping this harness independent of the host's hardware.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')
local ui = shared.ui
local files = {
  ['/proc/stat'] = 'cpu 1000 0 0 4000 0 0 0 0\n',
  ['/proc/meminfo'] = 'MemTotal: 100000 kB\nMemAvailable: 60000 kB\n',
  ['/proc/net/route'] = 'eth0 00000000 0102A8C0 0003 0 0 100\n',
  ['/proc/net/dev'] = 'eth0: 1000 0 0 0 0 0 0 0 500 0 0 0 0 0 0 0\n',
  ['/sys/block/nvme0n1/device/uevent'] = 'DRIVER=nvme\n',
  ['/sys/block/sda/device/uevent'] = 'DEVTYPE=scsi_device\n',
}
shared.read_file = function(path) return files[path] end
local now, width, height = 1000, 400, 176
local intel_counter, nvidia_percent, gpu_success, query_count = 100000000000, '0', true, 0
local function gpu_output()
  return string.format('sample\t%d\ngpu\t0000:00:02.0\tIntel\t\ngpu\t0000:01:00.0\tNVIDIA\t%s\n'
    .. 'engine\t0000:00:02.0\t30\trender\t%.0f\t1\n', now, nvidia_percent, intel_counter)
end
local original_time, original_popen, original_getenv = os.time, io.popen, os.getenv
os.time = function() return now end
os.getenv = function(name)
  if name:match('^RESOURCE_') then return nil end
  return original_getenv(name)
end
io.popen = function()
  query_count = query_count + 1
  return {
    read = function() return gpu_output() end,
    close = function() return gpu_success end,
  }
end

local gauges, traces, current_icon = {}, {}, nil
ui.draw = function(callback) callback({}, width, height) end
ui.arc_gauge = function(_, icon, value, unit, x, y, w, opts)
  current_icon = opts.label or icon
  gauges[#gauges + 1] = {icon = icon, value = value, unit = unit, x = x, y = y, width = w, opts = opts}
end
ui.line_between, ui.dash, ui.polygon, ui.circle = function() end, function() end, function() end, function() end
ui.polyline = function(_, points)
  traces[current_icon] = traces[current_icon] or {}
  table.insert(traces[current_icon], points)
end

local function disk(major, minor, name, reads, writes)
  return string.format('%d %d %s 10 0 %d 0 20 0 %d 0 0 0 0\n', major, minor, name, reads, writes)
end
local function snapshot(nvme_reads, nvme_writes, sda_reads, sda_writes)
  files['/proc/diskstats'] = disk(259, 0, 'nvme0n1', nvme_reads, nvme_writes)
    .. disk(8, 0, 'sda', sda_reads, sda_writes)
    .. disk(259, 1, 'nvme0n1p1', nvme_reads * 10, nvme_writes * 10)
    .. disk(253, 0, 'dm-0', nvme_reads * 10, nvme_writes * 10)
    .. disk(7, 0, 'loop0', nvme_reads * 10, nvme_writes * 10)
end
local function module()
  return dofile(root .. '/conky/resource-monitor-renderer.lua')(shared, '/fixture')
end
local function draw(renderer)
  gauges, traces = {}, {}
  renderer.draw()
end
local function unavailable(gauge)
  assert(gauge.value == '—' and gauge.unit == '' and not gauge.opts.measured,
    gauge.icon .. ' must show missing data as an unmeasured dash')
  assert(gauge.opts.reading == nil and gauge.opts.peak == nil,
    'missing data must not leave an active fill or peak')
end

snapshot(10000, 20000, 1000, 2000)
local renderer = module()
draw(renderer)
assert(#gauges == 8, 'both GPUs and disk I/O must fill the second row')
assert(gauges[5].opts.label == 'Intel' and gauges[6].opts.label == 'NVIDIA',
  'each physical GPU needs its own identified gauge')
unavailable(gauges[5])
assert(gauges[6].icon == 'gpu' and gauges[6].value == '0' and gauges[6].unit == '%',
  'a measured idle GPU is zero, including on the first update')
unavailable(gauges[1])
unavailable(gauges[3])
unavailable(gauges[4])
unavailable(gauges[7])
unavailable(gauges[8])
for index, gauge in ipairs(gauges) do
  assert(gauge.x >= 0 and gauge.x + gauge.width <= width and gauge.y >= 0
    and gauge.y + gauge.opts.size <= height, 'gauges must fit inside their window')
  if index > 4 then
    assert(gauge.x == gauges[index - 4].x and gauge.y > gauges[index - 4].y + gauge.opts.size,
      'the second row must clear the first and share its column positions')
  end
end

now = 1002
intel_counter, nvidia_percent = 100700000000, '64'
snapshot(14096, 28192, 3048, 2000)
draw(renderer)
assert(gauges[5].value == '35' and gauges[6].value == '64',
  'Intel engine-time deltas and NVIDIA utilization must remain separate')
assert(gauges[7].icon == 'hard-drive-upload' and gauges[7].opts.reading == 1.5 * 1048576,
  'reads must sum physical disk byte deltas once, using 512-byte sectors and elapsed seconds')
assert(gauges[7].value == '1.5' and gauges[7].unit == 'MB/s', 'read rate must retain useful precision')
assert(gauges[8].icon == 'hard-drive-download' and gauges[8].opts.reading == 2 * 1048576,
  'writes must use their own counter and exclude partitions and virtual devices')
assert(gauges[6].opts.peak == 64 and gauges[7].opts.peak == 1.5 * 1048576,
  'new channels must retain the existing peak behavior')
local sampled_queries = query_count
draw(renderer)
assert(query_count == sampled_queries, 'redrawing the same update must reuse the GPU sample')

now = 1004
nvidia_percent = '90'
gpu_success = nil -- a timed-out command may still have emitted partial stdout
files['/proc/net/route'] = 'eth1 00000000 0103A8C0 0003 0 0 100\n'
files['/proc/net/dev'] = 'eth1: 1000 0 0 0 0 0 0 0 500 0 0 0 0 0 0 0\n'
snapshot(18192, 36384, 3048, 2000)
draw(renderer)
unavailable(gauges[6])
unavailable(gauges[5])
unavailable(gauges[3])
assert(gauges[7].opts.reading == 1048576 and gauges[8].opts.reading == 2 * 1048576,
  'GPU failure and network changes must not suppress disk measurements')

now = 1006
gpu_success, intel_counter, nvidia_percent = true, 0, 'N/A'
snapshot(0, 0, 0, 0)
draw(renderer)
unavailable(gauges[6])
unavailable(gauges[7])
unavailable(gauges[8])

now = 1008
nvidia_percent = '0'
snapshot(0, 0, 0, 0)
files['/sys/block/sdb/device/uevent'] = 'DEVTYPE=scsi_device\n'
files['/proc/diskstats'] = files['/proc/diskstats'] .. disk(8, 16, 'sdb', 999999999, 999999999)
draw(renderer)
assert(gauges[5].opts.reading == 0 and gauges[6].opts.reading == 0
  and gauges[7].opts.reading == 0 and gauges[8].opts.reading == 0,
  'idle readings must recover, and attaching a disk must not turn its lifetime counters into a spike')

now = 1010
files['/proc/diskstats'] = disk(259, 0, 'nvme0n1', 4096, 8192)
draw(renderer)
assert(gauges[7].opts.reading == 1048576 and gauges[8].opts.reading == 2 * 1048576,
  'removing disks must not subtract their old counters from remaining disk activity')

now = 1042
draw(renderer)
unavailable(gauges[7])
unavailable(gauges[8])
now = 1044
files['/proc/diskstats'] = disk(259, 0, 'nvme0n1', 4096 + 4194304, 8192)
draw(renderer)
assert(gauges[7].value == '1.0' and gauges[7].unit == 'GB/s'
  and gauges[7].opts.reading > gauges[7].opts.max,
  'rates above the scale must keep their real value and fit using larger units')

-- Taller windows exercise the optional traces, including missing GPU/disk
-- readings and gaps that must not become a line through an invented zero.
now, height, width = 2000, 240, 360
renderer = module()
for _, sample in ipairs({{2000, '20'}, {2002, '30'}, {2004, 'N/A'}, {2006, '40'}, {2008, '50'}}) do
  now, nvidia_percent = sample[1], sample[2]
  draw(renderer)
end
assert(#traces.NVIDIA == 2 and #traces.NVIDIA[1] == 2 and #traces.NVIDIA[2] == 2,
  'GPU history must break on unavailable readings and resume with fresh samples')

-- A driver may briefly report a smaller busy counter, then catch up. Only
-- time beyond the previous high value may contribute to a later sample.
now, intel_counter = 3000, 10000000000
renderer = module()
draw(renderer)
now, intel_counter = 3002, 11000000000
draw(renderer)
assert(gauges[5].opts.reading == 50)
now, intel_counter = 3004, 10500000000
draw(renderer)
assert(gauges[5].opts.reading == 0, 'a regressing DRM counter must not yield negative utilization')
now, intel_counter = 3006, 11500000000
draw(renderer)
assert(gauges[5].opts.reading == 25, 'DRM counter recovery must not count the same work twice')

os.time, io.popen, os.getenv = original_time, original_popen, original_getenv
print('resource sampling, availability, peaks, and two-row geometry OK')
