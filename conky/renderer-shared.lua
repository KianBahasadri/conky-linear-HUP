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

-- Encode a Unicode code point as UTF-8 (Lua 5.1–compatible; no utf8 lib required).
function shared.utf8_char(codepoint)
  if not codepoint or codepoint < 0 then
    return ''
  end
  -- UTF-16 surrogate code points are not Unicode scalar values.  Encoding a
  -- lone surrogate would produce invalid UTF-8 and can make Cairo reject the
  -- rest of a label, so use the replacement character instead.
  if codepoint >= 0xD800 and codepoint <= 0xDFFF then
    return '\xef\xbf\xbd'
  end
  if codepoint < 0x80 then
    return string.char(codepoint)
  end
  if codepoint < 0x800 then
    return string.char(
      0xC0 + math.floor(codepoint / 0x40),
      0x80 + (codepoint % 0x40)
    )
  end
  if codepoint < 0x10000 then
    return string.char(
      0xE0 + math.floor(codepoint / 0x1000),
      0x80 + (math.floor(codepoint / 0x40) % 0x40),
      0x80 + (codepoint % 0x40)
    )
  end
  if codepoint <= 0x10FFFF then
    return string.char(
      0xF0 + math.floor(codepoint / 0x40000),
      0x80 + (math.floor(codepoint / 0x1000) % 0x40),
      0x80 + (math.floor(codepoint / 0x40) % 0x40),
      0x80 + (codepoint % 0x40)
    )
  end
  return ''
end

function shared.unescape_json_string(value)
  if not value then
    return value
  end

  -- Single-pass unescape so sequences like \\n stay as backslash + n.
  -- Also decodes \uXXXX (and UTF-16 surrogate pairs) so em dashes etc. render.
  local parts = {}
  local index = 1
  while index <= #value do
    local character = value:sub(index, index)
    if character == '\\' and index < #value then
      local next_character = value:sub(index + 1, index + 1)
      if next_character == 'n' or next_character == 't' or next_character == 'r'
          or next_character == 'b' or next_character == 'f' then
        table.insert(parts, ' ')
        index = index + 2
      elseif next_character == '"' then
        table.insert(parts, '"')
        index = index + 2
      elseif next_character == '/' then
        table.insert(parts, '/')
        index = index + 2
      elseif next_character == '\\' then
        table.insert(parts, '\\')
        index = index + 2
      elseif next_character == 'u' then
        local hex = value:sub(index + 2, index + 5)
        if hex:match('^%x%x%x%x$') then
          local codepoint = tonumber(hex, 16)
          index = index + 6
          -- UTF-16 surrogate pair: high + low → one supplementary code point
          if codepoint >= 0xD800 and codepoint <= 0xDBFF then
            local low_escape = value:sub(index, index + 5)
            local low_hex = value:sub(index + 2, index + 5)
            if low_escape:match('^\\u%x%x%x%x$') then
              local low = tonumber(low_hex, 16)
              if low >= 0xDC00 and low <= 0xDFFF then
                codepoint = 0x10000 + (codepoint - 0xD800) * 0x400 + (low - 0xDC00)
                index = index + 6
              end
            end
          end
          table.insert(parts, shared.utf8_char(codepoint))
        else
          table.insert(parts, next_character)
          index = index + 2
        end
      else
        table.insert(parts, next_character)
        index = index + 2
      end
    else
      table.insert(parts, character)
      index = index + 1
    end
  end
  return table.concat(parts)
end

-- The render caches are JSON, but Conky does not ship a JSON module on every
-- supported Lua build.  Keep the parser deliberately small: it only exposes
-- direct object-field lookup plus arrays of objects/strings, which is all the
-- renderers need.  Unlike the old Lua patterns, the scanner understands nested
-- containers and ignores braces, brackets, and escaped quotes inside strings.
local function skip_json_whitespace(text, index)
  while index <= #text and text:sub(index, index):match('%s') do
    index = index + 1
  end
  return index
end

local function json_string_end(text, start_index)
  if text:sub(start_index, start_index) ~= '"' then
    return nil
  end

  local index = start_index + 1
  while index <= #text do
    local character = text:sub(index, index)
    if character == '\\' then
      local escape = text:sub(index + 1, index + 1)
      if escape == 'u' then
        if not text:sub(index + 2, index + 5):match('^%x%x%x%x$') then
          return nil
        end
        index = index + 6
      elseif escape:match('^["\\/bfnrt]$') then
        index = index + 2
      else
        return nil
      end
    elseif character == '"' then
      return index
    elseif character:byte() < 0x20 then
      return nil
    else
      index = index + 1
    end
  end
  return nil
end

local function json_number_end(text, start_index)
  local index = start_index
  if text:sub(index, index) == '-' then
    index = index + 1
  end

  local first_digit = text:sub(index, index)
  if first_digit == '0' then
    index = index + 1
    if text:sub(index, index):match('%d') then
      return nil
    end
  elseif first_digit:match('[1-9]') then
    repeat
      index = index + 1
    until not text:sub(index, index):match('%d')
  else
    return nil
  end

  if text:sub(index, index) == '.' then
    index = index + 1
    if not text:sub(index, index):match('%d') then
      return nil
    end
    repeat
      index = index + 1
    until not text:sub(index, index):match('%d')
  end

  if text:sub(index, index):match('[eE]') then
    index = index + 1
    if text:sub(index, index):match('[+-]') then
      index = index + 1
    end
    if not text:sub(index, index):match('%d') then
      return nil
    end
    repeat
      index = index + 1
    until not text:sub(index, index):match('%d')
  end

  return index - 1
end

local json_value_end

local function json_object_end(text, start_index, on_member)
  if text:sub(start_index, start_index) ~= '{' then
    return nil
  end

  local index = skip_json_whitespace(text, start_index + 1)
  if text:sub(index, index) == '}' then
    return index
  end

  while index <= #text do
    local key_start = index
    local key_end = json_string_end(text, key_start)
    if not key_end then
      return nil
    end
    local key = shared.unescape_json_string(text:sub(key_start + 1, key_end - 1))

    index = skip_json_whitespace(text, key_end + 1)
    if text:sub(index, index) ~= ':' then
      return nil
    end

    local value_start = skip_json_whitespace(text, index + 1)
    local value_end = json_value_end(text, value_start)
    if not value_end then
      return nil
    end
    if on_member then
      on_member(key, value_start, value_end)
    end

    index = skip_json_whitespace(text, value_end + 1)
    local delimiter = text:sub(index, index)
    if delimiter == '}' then
      return index
    end
    if delimiter ~= ',' then
      return nil
    end
    index = skip_json_whitespace(text, index + 1)
    if text:sub(index, index) == '}' then
      return nil
    end
  end
  return nil
end

local function json_array_end(text, start_index, on_value)
  if text:sub(start_index, start_index) ~= '[' then
    return nil
  end

  local index = skip_json_whitespace(text, start_index + 1)
  if text:sub(index, index) == ']' then
    return index
  end

  while index <= #text do
    local value_start = index
    local value_end = json_value_end(text, value_start)
    if not value_end then
      return nil
    end
    if on_value then
      on_value(value_start, value_end)
    end

    index = skip_json_whitespace(text, value_end + 1)
    local delimiter = text:sub(index, index)
    if delimiter == ']' then
      return index
    end
    if delimiter ~= ',' then
      return nil
    end
    index = skip_json_whitespace(text, index + 1)
    if text:sub(index, index) == ']' then
      return nil
    end
  end
  return nil
end

json_value_end = function(text, start_index)
  local character = text:sub(start_index, start_index)
  if character == '"' then
    return json_string_end(text, start_index)
  end
  if character == '{' then
    return json_object_end(text, start_index)
  end
  if character == '[' then
    return json_array_end(text, start_index)
  end
  if character == '-' or character:match('%d') then
    return json_number_end(text, start_index)
  end

  for _, literal in ipairs({ 'true', 'false', 'null' }) do
    if text:sub(start_index, start_index + #literal - 1) == literal then
      return start_index + #literal - 1
    end
  end
  return nil
end

-- Return one direct object's field as JSON source, or nil for missing/malformed
-- input.  Nested fields with the same name are intentionally ignored.
function shared.json_field(text, key)
  if not text or not key then
    return nil
  end

  local object_start = skip_json_whitespace(text, 1)
  if text:sub(object_start, object_start) ~= '{' then
    return nil
  end

  local found
  local object_end = json_object_end(text, object_start, function(candidate, value_start, value_end)
    if candidate == key and found == nil then
      found = text:sub(value_start, value_end)
    end
  end)
  if not object_end then
    return nil
  end
  if skip_json_whitespace(text, object_end + 1) <= #text then
    return nil
  end
  return found
end

function shared.json_string(text, key, fallback)
  local value = shared.json_field(text, key)
  if not value or value:sub(1, 1) ~= '"' then
    return fallback
  end
  local value_end = json_string_end(value, 1)
  if value_end ~= #value then
    return fallback
  end
  return shared.unescape_json_string(value:sub(2, -2))
end

function shared.json_number(text, key, fallback)
  local value = shared.json_field(text, key)
  if not value or value == 'null' then
    return fallback
  end
  local number = tonumber(value)
  if not number or number ~= number or number == math.huge or number == -math.huge then
    return fallback
  end
  return number
end

function shared.json_boolean(text, key, fallback)
  local value = shared.json_field(text, key)
  if value == 'true' then
    return true
  end
  if value == 'false' then
    return false
  end
  return fallback
end

local function json_array_values(text, key)
  local array = shared.json_field(text, key)
  if not array or array:sub(1, 1) ~= '[' then
    return {}
  end

  local values = {}
  local array_end = json_array_end(array, 1, function(value_start, value_end)
    table.insert(values, array:sub(value_start, value_end))
  end)
  if array_end ~= #array then
    return {}
  end
  return values
end

function shared.json_array_objects(text, key)
  local objects = {}
  for _, value in ipairs(json_array_values(text, key)) do
    if value:sub(1, 1) == '{' then
      table.insert(objects, value)
    end
  end
  return objects
end

function shared.json_array_strings(text, key)
  local strings = {}
  for _, value in ipairs(json_array_values(text, key)) do
    if value:sub(1, 1) == '"' and json_string_end(value, 1) == #value then
      table.insert(strings, shared.unescape_json_string(value:sub(2, -2)))
    end
  end
  return strings
end

function shared.set_hex(cr, hex, alpha)
  local r = tonumber(hex:sub(1, 2), 16) / 255
  local g = tonumber(hex:sub(3, 4), 16) / 255
  local b = tonumber(hex:sub(5, 6), 16) / 255
  cairo_set_source_rgba(cr, r, g, b, alpha or 1)
end

-- Hex to rgb with a lightness shade: >0 lifts toward white, <0 toward black.
-- Face shading on the contribution skyline's towers, and the gradient stops in
-- the sessions panel, are both built from this.
function shared.shade_rgb(hex, shade)
  local r = tonumber(hex:sub(1, 2), 16) / 255
  local g = tonumber(hex:sub(3, 4), 16) / 255
  local b = tonumber(hex:sub(5, 6), 16) / 255
  shade = shade or 0

  if shade > 0 then
    return r + (1 - r) * shade, g + (1 - g) * shade, b + (1 - b) * shade
  end
  if shade < 0 then
    return r * (1 + shade), g * (1 + shade), b * (1 + shade)
  end
  return r, g, b
end

function shared.set_hex_shaded(cr, hex, alpha, shade)
  local r, g, b = shared.shade_rgb(hex, shade)
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
    -- Lua's string slicing is byte-based.  Remove one whole UTF-8 code point so
    -- truncating emoji or non-ASCII names never hands Cairo invalid text.
    local index = #truncated
    while index > 1 do
      local byte = truncated:byte(index)
      if not byte or byte < 0x80 or byte >= 0xC0 then
        break
      end
      index = index - 1
    end
    truncated = truncated:sub(1, index - 1)
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

-- Git status panel geometry. The GitHub rail centers itself in the band under
-- this panel, so both renderers have to measure the panel the same way.
shared.git_panel = {
  top_padding = 4,      -- window top -> frame top (keeps the frame glow unclipped)
  content_top = 8,      -- frame top -> first repo row
  content_bottom = 10,  -- last repo row -> frame bottom
  row_height = 40,      -- two-line repo row: name over branch
  empty_height = 120,   -- frame height when there is nothing to list
  footer_gap = 4,       -- frame bottom -> footer chip
  footer_height = 20,   -- octocat + refresh age chip under the frame
}

-- Frame height for a repo count; the footer chip hangs below this.
function shared.git_panel_frame_height(repo_count)
  local panel = shared.git_panel
  local count = repo_count or 0
  local height = panel.content_top + math.max(1, count) * panel.row_height + panel.content_bottom
  if count == 0 then
    return math.max(height, panel.empty_height)
  end
  return height
end

-- Window top -> bottom of the footer chip: everything the git panel occupies.
function shared.git_panel_occupied_height(repo_count)
  local panel = shared.git_panel
  return panel.top_padding
    + shared.git_panel_frame_height(repo_count)
    + panel.footer_gap
    + panel.footer_height
end

function shared.create_surface()
  if not conky_window
      or (tonumber(conky_window.width) or 0) <= 0
      or (tonumber(conky_window.height) or 0) <= 0 then
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
