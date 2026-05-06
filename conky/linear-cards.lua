local cairo = require('cairo')
pcall(require, 'cairo_xlib')

local script_path = debug.getinfo(1, 'S').source:gsub('^@', '')
local repo_root = script_path:match('^(.*)/conky/linear%-cards%.lua$') or '.'
local cards_path = repo_root .. '/linear-cards.json'
local codex_usage_path = repo_root .. '/codex-usage.json'

local card_width = 318
local card_height = 130
local card_gap = 24
local row_gap = 20
local top_padding = 30
local radius = 18
local font = 'JetBrains Mono'
local font_size = 16
local line_height = 22
local codex_width = 1120
local codex_height = 132
local codex_radius = 18
local codex_bar_width = 388
local codex_bar_height = 24

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

local function read_codex_usage()
  local content = read_file(codex_usage_path)
  if not content then
    return nil
  end

  local ok = content:match('"ok"%s*:%s*true') ~= nil
  local error_message = content:match('"error"%s*:%s*"(.-)"')
  local accounts = {}
  local account_index = {}

  for object in content:gmatch('{%s-"account".-}') do
    local account = object:match('"account"%s*:%s*"(.-)"')
    local plan_type = object:match('"planType"%s*:%s*"(.-)"') or ''
    local window = object:match('"window"%s*:%s*"(.-)"')
    local used_percent = tonumber(object:match('"usedPercent"%s*:%s*([%d%.]+)')) or 0
    local remaining_percent = tonumber(object:match('"remainingPercent"%s*:%s*([%d%.]+)')) or math.max(0, 100 - used_percent)
    local resets_at = object:match('"resetsAt"%s*:%s*"(.-)"') or ''
    local reset_after_seconds = tonumber(object:match('"resetAfterSeconds"%s*:%s*(%d+)')) or 0

    if account and window then
      if not account_index[account] then
        account_index[account] = {
          label = unescape_json_string(account),
          plan_type = unescape_json_string(plan_type),
          windows = {},
        }
        table.insert(accounts, account_index[account])
      end

      table.insert(account_index[account].windows, {
        label = window,
        used_percent = used_percent,
        remaining_percent = remaining_percent,
        resets_at = resets_at,
        reset_after_seconds = reset_after_seconds,
      })
    end
  end

  return {
    ok = ok,
    error = error_message and unescape_json_string(error_message) or '',
    accounts = accounts,
  }
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

local function clamp(value, min_value, max_value)
  if value < min_value then
    return min_value
  end
  if value > max_value then
    return max_value
  end
  return value
end

local function format_reset(seconds)
  if seconds <= 0 then
    return 'reset pending'
  end

  local days = math.floor(seconds / 86400)
  local hours = math.floor((seconds % 86400) / 3600)
  local minutes = math.floor((seconds % 3600) / 60)

  if days > 0 then
    return string.format('%dd %dh', days, hours)
  end
  if hours > 0 then
    return string.format('%dh %02dm', hours, minutes)
  end
  return string.format('%dm', minutes)
end

local function format_reset_at(window)
  local value = window.resets_at or ''
  local year, month, day, hour, minute = value:match('^(%d%d%d%d)%-(%d%d)%-(%d%d)T(%d%d):(%d%d)')

  if not year then
    return format_reset(window.reset_after_seconds)
  end

  local reset_time = os.time({
    year = tonumber(year),
    month = tonumber(month),
    day = tonumber(day),
    hour = tonumber(hour),
    min = tonumber(minute),
    sec = 0,
    isdst = false,
  })

  local local_time = os.date('*t', reset_time)
  local label = string.lower(window.label or '')
  local hour = local_time.hour % 12
  if hour == 0 then
    hour = 12
  end
  local meridiem = local_time.hour >= 12 and 'PM' or 'AM'
  local time_label = string.format('%d:%02d %s', hour, local_time.min, meridiem)

  if label == 'weekly' then
    return string.format('%s %02d %s', os.date('%b', reset_time), local_time.day, time_label)
  end

  return time_label
end

local function format_reset_label(window)
  local countdown = format_reset(window.reset_after_seconds)
  local reset_at = format_reset_at(window)

  if reset_at == countdown then
    return countdown
  end

  return string.format('%s    %s', countdown, reset_at)
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
  local accent = card.done and '39ff88' or card.due_today and 'ff1a1a' or '00e5ff'
  local accent_secondary = card.done and '00f5d4' or card.due_today and 'ff4d00' or '8b5cf6'

  rounded_rect(cr, x + 4, y + 7, card_width, card_height, radius)
  set_hex(cr, accent, 0.12)
  cairo_fill(cr)

  rounded_rect(cr, x + 2, y + 3, card_width, card_height, radius)
  set_hex(cr, accent, 0.16)
  cairo_set_line_width(cr, 8)
  cairo_stroke(cr)

  rounded_rect(cr, x + 1, y + 2, card_width, card_height, radius)
  set_hex(cr, accent, 0.26)
  cairo_set_line_width(cr, 4)
  cairo_stroke(cr)

  rounded_rect(cr, x, y, card_width, card_height, radius)
  set_hex(cr, '020617', 0.78)
  cairo_fill_preserve(cr)
  set_hex(cr, accent, 0.95)
  cairo_set_line_width(cr, 2)
  cairo_stroke(cr)

  rounded_rect(cr, x + 7, y + 7, card_width - 14, card_height - 14, radius - 6)
  set_hex(cr, accent_secondary, 0.22)
  cairo_set_line_width(cr, 1)
  cairo_stroke(cr)

  set_hex(cr, accent, 0.22)
  cairo_set_line_width(cr, 1)
  cairo_move_to(cr, x + 22, y + 18)
  cairo_line_to(cr, x + 48, y + 18)
  cairo_line_to(cr, x + 58, y + 28)
  cairo_stroke(cr)

  set_hex(cr, accent_secondary, 0.18)
  cairo_move_to(cr, x + card_width - 22, y + card_height - 18)
  cairo_line_to(cr, x + card_width - 48, y + card_height - 18)
  cairo_line_to(cr, x + card_width - 58, y + card_height - 28)
  cairo_stroke(cr)

  set_hex(cr, accent, 0.34)
  cairo_arc(cr, x + 58, y + 28, 2, 0, math.pi * 2)
  cairo_fill(cr)
  set_hex(cr, accent_secondary, 0.28)
  cairo_arc(cr, x + card_width - 58, y + card_height - 28, 2, 0, math.pi * 2)
  cairo_fill(cr)

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
  cairo_set_font_size(cr, font_size)

  local lines = wrap_title(cr, card.title, card_width - 36)
  local extents = cairo_text_extents_t:create()
  local total_text_height = #lines * line_height
  local first_baseline = y + (card_height - total_text_height) / 2 + font_size

  for index, line in ipairs(lines) do
    cairo_text_extents(cr, line, extents)
    local text_x = x + (card_width - extents.width) / 2 - extents.x_bearing
    local text_y = first_baseline + (index - 1) * line_height

    set_hex(cr, accent, 0.24)
    cairo_move_to(cr, text_x - 1, text_y)
    cairo_show_text(cr, line)
    cairo_move_to(cr, text_x + 1, text_y)
    cairo_show_text(cr, line)

    set_hex(cr, 'f8fafc', 1)
    cairo_move_to(cr, text_x, text_y)
    cairo_show_text(cr, line)
  end
end

local function draw_codex_frame(cr, x, y)
  rounded_rect(cr, x + 4, y + 7, codex_width, codex_height, codex_radius)
  set_hex(cr, '00e5ff', 0.10)
  cairo_fill(cr)

  rounded_rect(cr, x + 2, y + 3, codex_width, codex_height, codex_radius)
  set_hex(cr, '00e5ff', 0.15)
  cairo_set_line_width(cr, 8)
  cairo_stroke(cr)

  rounded_rect(cr, x + 1, y + 2, codex_width, codex_height, codex_radius)
  set_hex(cr, '8b5cf6', 0.22)
  cairo_set_line_width(cr, 4)
  cairo_stroke(cr)

  rounded_rect(cr, x, y, codex_width, codex_height, codex_radius)
  set_hex(cr, '020617', 0.80)
  cairo_fill_preserve(cr)
  set_hex(cr, '00e5ff', 0.95)
  cairo_set_line_width(cr, 2)
  cairo_stroke(cr)

  rounded_rect(cr, x + 8, y + 8, codex_width - 16, codex_height - 16, codex_radius - 6)
  set_hex(cr, '8b5cf6', 0.24)
  cairo_set_line_width(cr, 1)
  cairo_stroke(cr)

  set_hex(cr, '00e5ff', 0.24)
  cairo_set_line_width(cr, 1)
  cairo_move_to(cr, x + 26, y + 20)
  cairo_line_to(cr, x + 62, y + 20)
  cairo_line_to(cr, x + 75, y + 33)
  cairo_stroke(cr)

  set_hex(cr, '8b5cf6', 0.20)
  cairo_move_to(cr, x + codex_width - 26, y + codex_height - 20)
  cairo_line_to(cr, x + codex_width - 62, y + codex_height - 20)
  cairo_line_to(cr, x + codex_width - 75, y + codex_height - 33)
  cairo_stroke(cr)
end

local function draw_codex_bar(cr, window, x, y, accent, accent_secondary)
  local used = clamp(window.used_percent, 0, 100)
  local fill_width = codex_bar_width * (used / 100)
  local label = string.upper(window.label)
  local percent_label = string.format('%.0f%% used', used)
  local reset_label = format_reset_label(window)

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
  cairo_set_font_size(cr, 13)
  set_hex(cr, 'f8fafc', 1)
  cairo_move_to(cr, x, y)
  cairo_show_text(cr, label)

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
  cairo_set_font_size(cr, 12)
  set_hex(cr, '94a3b8', 1)
  cairo_move_to(cr, x + 94, y)
  cairo_show_text(cr, percent_label)

  local extents = cairo_text_extents_t:create()
  local reset_max_width = codex_bar_width - 162
  reset_label = truncate_title(cr, reset_label, reset_max_width)
  cairo_text_extents(cr, reset_label, extents)

  set_hex(cr, accent, 0.84)
  cairo_move_to(cr, x + codex_bar_width - extents.width - extents.x_bearing, y)
  cairo_show_text(cr, reset_label)

  local bar_y = y + 14
  rounded_rect(cr, x, bar_y, codex_bar_width, codex_bar_height, 8)
  set_hex(cr, '020617', 0.92)
  cairo_fill_preserve(cr)
  set_hex(cr, accent, 0.72)
  cairo_set_line_width(cr, 1.5)
  cairo_stroke(cr)

  if fill_width > 0 then
    rounded_rect(cr, x + 3, bar_y + 3, math.max(8, fill_width - 6), codex_bar_height - 6, 6)
    set_hex(cr, accent, 0.68)
    cairo_fill(cr)
  end

  set_hex(cr, accent_secondary, 0.26)
  cairo_set_line_width(cr, 1)
  local tick_gap = codex_bar_width / 10
  for tick = 1, 9 do
    local tick_x = x + tick * tick_gap
    cairo_move_to(cr, tick_x, bar_y + 4)
    cairo_line_to(cr, tick_x, bar_y + codex_bar_height - 4)
  end
  cairo_stroke(cr)

  set_hex(cr, 'f8fafc', 0.22)
  cairo_move_to(cr, x + 8, bar_y + 8)
  cairo_line_to(cr, x + codex_bar_width - 8, bar_y + 8)
  cairo_stroke(cr)
end

local function draw_codex_error(cr, usage, x, y)
  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
  cairo_set_font_size(cr, 15)
  set_hex(cr, 'f87171', 1)
  cairo_move_to(cr, x + 34, y + 58)
  cairo_show_text(cr, 'CODEX SIGNAL LOST')

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
  cairo_set_font_size(cr, 12)
  set_hex(cr, 'f8fafc', 0.88)
  cairo_move_to(cr, x + 34, y + 82)
  cairo_show_text(cr, truncate_title(cr, usage and usage.error or 'No usage cache found.', codex_width - 68))
end

local function draw_codex_account_row(cr, account, x, y)
  local name = string.upper(account.label)
  local plan = account.plan_type ~= '' and string.upper(account.plan_type) or 'PLAN UNKNOWN'
  local first = account.windows[1]
  local second = account.windows[2] or account.windows[1]

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
  cairo_set_font_size(cr, 14)
  set_hex(cr, 'f8fafc', 1)
  cairo_move_to(cr, x, y + 22)
  cairo_show_text(cr, truncate_title(cr, name, 120))

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
  cairo_set_font_size(cr, 11)
  set_hex(cr, '94a3b8', 1)
  cairo_move_to(cr, x, y + 42)
  cairo_show_text(cr, truncate_title(cr, plan, 120))

  if first then
    draw_codex_bar(cr, first, x + 156, y + 18, '00e5ff', '8b5cf6')
  end
  if second then
    draw_codex_bar(cr, second, x + 156 + codex_bar_width + 42, y + 18, '39ff88', '00f5d4')
  end
end

local function draw_codex_panel(cr, usage, x, y)
  draw_codex_frame(cr, x, y)

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
  cairo_set_font_size(cr, 15)
  set_hex(cr, '00e5ff', 1)
  cairo_move_to(cr, x + 34, y + 38)
  cairo_show_text(cr, 'CODEX')

  if not usage.ok or #usage.accounts == 0 then
    draw_codex_error(cr, usage, x, y)
    return
  end

  cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
  cairo_set_font_size(cr, 12)
  set_hex(cr, '94a3b8', 1)
  cairo_move_to(cr, x + 104, y + 38)
  cairo_show_text(cr, string.format('%d ACCOUNTS', #usage.accounts))

  for index, account in ipairs(usage.accounts) do
    draw_codex_account_row(cr, account, x + 34, y + 58 + (index - 1) * 58)
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

function conky_draw_codex_usage()
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
  local usage = read_codex_usage()

  if not usage then
    usage = {
      ok = false,
      error = 'No codex-usage.json cache found.',
      accounts = {},
    }
  end

  local account_count = math.max(1, #(usage.accounts or {}))
  local dynamic_height = math.max(132, 72 + account_count * 58)
  local panel_width = math.min(codex_width, conky_window.width - 40)
  local x = (conky_window.width - panel_width) / 2
  local y = math.max(18, conky_window.height - dynamic_height - 18)
  local previous_width = codex_width
  local previous_height = codex_height

  codex_width = panel_width
  codex_height = dynamic_height
  draw_codex_panel(cr, usage, x, y)
  codex_width = previous_width
  codex_height = previous_height

  cairo_destroy(cr)
  if not conky_surface and cairo_surface_destroy then
    cairo_surface_destroy(surface)
  end
end
