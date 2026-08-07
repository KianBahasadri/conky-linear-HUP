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
  if not value then
    return value
  end

  -- Single-pass unescape so sequences like \\n stay as backslash + n.
  local parts = {}
  local index = 1
  while index <= #value do
    local character = value:sub(index, index)
    if character == '\\' and index < #value then
      local next_character = value:sub(index + 1, index + 1)
      if next_character == 'n' or next_character == 't' or next_character == 'r' then
        table.insert(parts, ' ')
      elseif next_character == '"' then
        table.insert(parts, '"')
      elseif next_character == '/' then
        table.insert(parts, '/')
      elseif next_character == '\\' then
        table.insert(parts, '\\')
      else
        table.insert(parts, next_character)
      end
      index = index + 2
    else
      table.insert(parts, character)
      index = index + 1
    end
  end
  return table.concat(parts)
end

-- Extract a JSON string field value, respecting escaped quotes and backslashes.
-- Non-greedy Lua patterns like "(.-)" stop at the first ", which breaks titles
-- such as: "add \"create new property\" button..."
function shared.match_json_string(text, key)
  if not text or not key then
    return nil
  end

  local escaped_key = key:gsub('(%W)', '%%%1')
  local _, value_start = text:find('"' .. escaped_key .. '"%s*:%s*"')
  if not value_start then
    return nil
  end

  local parts = {}
  local index = value_start + 1
  while index <= #text do
    local character = text:sub(index, index)
    if character == '\\' then
      local next_character = text:sub(index + 1, index + 1)
      if next_character == '' then
        table.insert(parts, character)
        break
      end
      table.insert(parts, character)
      table.insert(parts, next_character)
      index = index + 2
    elseif character == '"' then
      break
    else
      table.insert(parts, character)
      index = index + 1
    end
  end

  return table.concat(parts)
end

function shared.set_hex(cr, hex, alpha)
  local r = tonumber(hex:sub(1, 2), 16) / 255
  local g = tonumber(hex:sub(3, 4), 16) / 255
  local b = tonumber(hex:sub(5, 6), 16) / 255
  cairo_set_source_rgba(cr, r, g, b, alpha or 1)
end

function shared.darken_hex(hex, factor)
  local r = math.floor(tonumber(hex:sub(1, 2), 16) * factor + 0.5)
  local g = math.floor(tonumber(hex:sub(3, 4), 16) * factor + 0.5)
  local b = math.floor(tonumber(hex:sub(5, 6), 16) * factor + 0.5)
  return string.format(
    '%02x%02x%02x',
    shared.clamp(r, 0, 255),
    shared.clamp(g, 0, 255),
    shared.clamp(b, 0, 255)
  )
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

function shared.wrap_title(cr, title, max_width, max_lines)
  max_lines = max_lines or 2

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

  if #lines > max_lines then
    local overflow = {}
    for index = max_lines, #lines do
      table.insert(overflow, lines[index])
    end
    lines[max_lines] = shared.truncate_title(cr, table.concat(overflow, ' '), max_width)
    for index = #lines, max_lines + 1, -1 do
      table.remove(lines, index)
    end
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
