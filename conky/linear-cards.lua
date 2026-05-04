local cairo = require('cairo')
pcall(require, 'cairo_xlib')

local script_path = debug.getinfo(1, 'S').source:gsub('^@', '')
local repo_root = script_path:match('^(.*)/conky/linear%-cards%.lua$') or '.'
local cards_path = repo_root .. '/linear-cards.json'

local card_width = 290
local card_height = 118
local card_gap = 22
local row_gap = 18
local top_padding = 30
local radius = 16
local font = 'JetBrains Mono'
local font_size = 15
local line_height = 21

local function read_file(path)
  local file = io.open(path, 'r')
  if not file then
    return nil
  end

  local content = file:read('*a')
  file:close()
  return content
end

local function unescape_json_string(value)
  value = value:gsub('\\n', ' ')
  value = value:gsub('\\"', '"')
  value = value:gsub('\\/', '/')
  value = value:gsub('\\\\', '\\')
  return value
end

local function read_cards()
  local content = read_file(cards_path)
  if not content then
    return {}
  end

  local cards = {}
  for object in content:gmatch('{%s-"title".-}') do
    local title = object:match('"title"%s*:%s*"(.-)"')
    local done = object:match('"done"%s*:%s*(true)') ~= nil
    local due_today = object:match('"dueToday"%s*:%s*(true)') ~= nil

    if title then
      table.insert(cards, {
        title = unescape_json_string(title),
        done = done,
        due_today = due_today,
      })
    end
  end

  return cards
end

local function hex_to_rgba(hex, alpha)
  local r = tonumber(hex:sub(1, 2), 16) / 255
  local g = tonumber(hex:sub(3, 4), 16) / 255
  local b = tonumber(hex:sub(5, 6), 16) / 255
  return r, g, b, alpha
end

local function set_hex(cr, hex, alpha)
  cairo_set_source_rgba(cr, hex_to_rgba(hex, alpha or 1))
end

local function rounded_rect(cr, x, y, width, height, corner_radius)
  local degrees = math.pi / 180

  cairo_new_sub_path(cr)
  cairo_arc(cr, x + width - corner_radius, y + corner_radius, corner_radius, -90 * degrees, 0 * degrees)
  cairo_arc(cr, x + width - corner_radius, y + height - corner_radius, corner_radius, 0 * degrees, 90 * degrees)
  cairo_arc(cr, x + corner_radius, y + height - corner_radius, corner_radius, 90 * degrees, 180 * degrees)
  cairo_arc(cr, x + corner_radius, y + corner_radius, corner_radius, 180 * degrees, 270 * degrees)
  cairo_close_path(cr)
end

local function truncate_title(cr, title, max_width)
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

local function wrap_title(cr, title, max_width)
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
    lines[2] = truncate_title(cr, lines[2] .. ' ' .. table.concat(lines, ' ', 3), max_width)
    return { lines[1], lines[2] }
  end

  for index, line in ipairs(lines) do
    lines[index] = truncate_title(cr, line, max_width)
  end

  return lines
end

local function draw_card(cr, card, x, y)
  local fill = card.done and '166534' or card.due_today and '991b1b' or 'a16207'
  local stroke = card.done and '22c55e' or card.due_today and 'ef4444' or 'facc15'

  rounded_rect(cr, x + 3, y + 5, card_width, card_height, radius)
  set_hex(cr, '020617', 0.34)
  cairo_fill(cr)

  rounded_rect(cr, x, y, card_width, card_height, radius)
  set_hex(cr, fill, 0.96)
  cairo_fill_preserve(cr)
  set_hex(cr, stroke, 0.95)
  cairo_set_line_width(cr, 2)
  cairo_stroke(cr)

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
  cairo_set_font_size(cr, font_size)
  set_hex(cr, 'f8fafc', 1)

  local lines = wrap_title(cr, card.title, card_width - 36)
  local extents = cairo_text_extents_t:create()
  local total_text_height = #lines * line_height
  local first_baseline = y + (card_height - total_text_height) / 2 + font_size

  for index, line in ipairs(lines) do
    cairo_text_extents(cr, line, extents)
    local text_x = x + (card_width - extents.width) / 2 - extents.x_bearing
    local text_y = first_baseline + (index - 1) * line_height

    cairo_move_to(cr, text_x, text_y)
    cairo_show_text(cr, line)
  end
end

function conky_draw_linear_cards()
  if not conky_window then
    return
  end

  local surface = nil
  if conky_surface then
    surface = conky_surface()
  elseif cairo_xlib_surface_create then
    surface = cairo_xlib_surface_create(conky_window.display, conky_window.drawable, conky_window.visual, conky_window.width, conky_window.height)
  end

  if not surface then
    return
  end

  local cr = cairo_create(surface)
  local cards = read_cards()

  if #cards == 0 then
    cairo_destroy(cr)
    return
  end

  local cards_per_row = math.max(1, math.floor((conky_window.width + card_gap) / (card_width + card_gap)))

  for index, card in ipairs(cards) do
    local row = math.floor((index - 1) / cards_per_row)
    local column = (index - 1) % cards_per_row
    local items_in_row = math.min(cards_per_row, #cards - row * cards_per_row)
    local row_width = items_in_row * card_width + (items_in_row - 1) * card_gap
    local start_x = (conky_window.width - row_width) / 2
    local x = start_x + column * (card_width + card_gap)
    local y = top_padding + row * (card_height + row_gap)

    draw_card(cr, card, x, y)
  end

  cairo_destroy(cr)
  if not conky_surface and cairo_surface_destroy then
    cairo_surface_destroy(surface)
  end
end
