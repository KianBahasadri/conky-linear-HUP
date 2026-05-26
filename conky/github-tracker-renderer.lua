return function(shared, repo_root)
  local github_path = repo_root .. '/cache/github-contributions.json'
  local square = 7
  local gap = 4
  local columns = 7
  local weeks = 53
  local radius = 2
  local colors = {
    '1f2937',
    '0e4429',
    '006d32',
    '26a641',
    '39d353',
  }

  local function parse_entries()
    local content = shared.read_file(github_path)
    if not content or content:match('"ok"%s*:%s*true') == nil then
      return {}
    end

    local entries = {}
    for object in content:gmatch('{%s-"date".-}') do
      local level = tonumber(object:match('"level"%s*:%s*(%d+)')) or 0
      table.insert(entries, shared.clamp(level, 0, 4))
    end

    while #entries > weeks * columns do
      table.remove(entries, 1)
    end

    return entries
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local entries = parse_entries()
    if #entries == 0 then
      cairo_destroy(cr)
      if should_destroy_surface and cairo_surface_destroy then
        cairo_surface_destroy(surface)
      end
      return
    end

    local cell = square + gap
    local grid_width = columns * square + (columns - 1) * gap
    local rows = math.ceil(#entries / columns)
    local grid_height = rows * square + math.max(0, rows - 1) * gap
    local start_x = math.floor((conky_window.width - grid_width) / 2)
    local start_y = math.floor((conky_window.height - grid_height) / 2)

    for index, level in ipairs(entries) do
      local draw_index = #entries - index + 1
      local row = math.floor((index - 1) / columns)
      local column = (index - 1) % columns
      local x = start_x + column * cell
      local y = start_y + row * cell
      level = entries[draw_index]
      local alpha = level == 0 and 0.42 or 0.96

      shared.rounded_rect(cr, x, y, square, square, radius)
      shared.set_hex(cr, colors[level + 1], alpha)
      cairo_fill(cr)
    end

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
