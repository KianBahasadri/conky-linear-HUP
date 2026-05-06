local shared = {}

function shared.read_file(path)
  local file = io.open(path, 'r')
  if not file then
    return nil
  end

  local content = file:read('*a')
  file:close()
  return content
end

function shared.unescape_json_string(value)
  value = value:gsub('\\n', ' ')
  value = value:gsub('\\"', '"')
  value = value:gsub('\\/', '/')
  value = value:gsub('\\\\', '\\')
  return value
end

function shared.set_hex(cr, hex, alpha)
  local r = tonumber(hex:sub(1, 2), 16) / 255
  local g = tonumber(hex:sub(3, 4), 16) / 255
  local b = tonumber(hex:sub(5, 6), 16) / 255
  cairo_set_source_rgba(cr, r, g, b, alpha or 1)
end

function shared.clamp(value, min_value, max_value)
  if value < min_value then
    return min_value
  end
  if value > max_value then
    return max_value
  end
  return value
end

function shared.rounded_rect(cr, x, y, width, height, corner_radius)
  local degrees = math.pi / 180

  cairo_new_sub_path(cr)
  cairo_arc(cr, x + width - corner_radius, y + corner_radius, corner_radius, -90 * degrees, 0 * degrees)
  cairo_arc(cr, x + width - corner_radius, y + height - corner_radius, corner_radius, 0 * degrees, 90 * degrees)
  cairo_arc(cr, x + corner_radius, y + height - corner_radius, corner_radius, 90 * degrees, 180 * degrees)
  cairo_arc(cr, x + corner_radius, y + corner_radius, corner_radius, 180 * degrees, 270 * degrees)
  cairo_close_path(cr)
end

function shared.truncate_title(cr, title, max_width)
  local extents = cairo_text_extents_t:create()
  cairo_text_extents(cr, title, extents)

  if extents.width <= max_width then
    return title
  end

  local suffix = '...'
  local truncated = title
  while #truncated > 0 do
    truncated = truncated:sub(1, -2)
    cairo_text_extents(cr, truncated .. suffix, extents)
    if extents.width <= max_width then
      return truncated .. suffix
    end
  end

  return suffix
end

function shared.wrap_title(cr, title, max_width)
  local words = {}
  for word in title:gmatch('%S+') do
    table.insert(words, word)
  end

  local lines = {}
  local current = ''
  local extents = cairo_text_extents_t:create()

  for _, word in ipairs(words) do
    local candidate = current == '' and word or current .. ' ' .. word
    cairo_text_extents(cr, candidate, extents)

    if extents.width <= max_width then
      current = candidate
    else
      if current ~= '' then
        table.insert(lines, current)
      end
      current = word
    end
  end

  if current ~= '' then
    table.insert(lines, current)
  end

  if #lines == 0 then
    return { '' }
  end

  if #lines > 2 then
    lines[2] = shared.truncate_title(cr, lines[2] .. ' ' .. table.concat(lines, ' ', 3), max_width)
    return { lines[1], lines[2] }
  end

  for index, line in ipairs(lines) do
    lines[index] = shared.truncate_title(cr, line, max_width)
  end

  return lines
end

function shared.create_surface()
  if not conky_window then
    return nil, false
  end

  if conky_surface then
    return conky_surface(), false
  end

  if cairo_xlib_surface_create then
    return cairo_xlib_surface_create(conky_window.display, conky_window.drawable, conky_window.visual, conky_window.width, conky_window.height), true
  end

  return nil, false
end

return shared
