return function(shared, repo_root)
  local cards_path = repo_root .. '/cache/linear-cards.json'
  local card_width = 318
  local card_height = 130
  local card_gap = 24
  local row_gap = 20
  local top_padding = 30
  local radius = 18
  local font = 'JetBrains Mono'
  local font_size = 16
  local line_height = 22

  local function read_cards()
    local content = shared.read_file(cards_path)
    if not content then
      return { cards = {}, error = '' }
    end

    local error_message = content:match('"error"%s*:%s*"(.-)"')
    local cards = {}
    for object in content:gmatch('{%s-"title".-}') do
      local title = object:match('"title"%s*:%s*"(.-)"')
      local done = object:match('"done"%s*:%s*(true)') ~= nil
      local due_today = object:match('"dueToday"%s*:%s*(true)') ~= nil

      if title then
        table.insert(cards, {
          title = shared.unescape_json_string(title),
          done = done,
          due_today = due_today,
        })
      end
    end

    return {
      cards = cards,
      error = error_message and shared.unescape_json_string(error_message) or '',
    }
  end

  local function draw_error(cr, message)
    local width = math.min(620, conky_window.width - 40)
    local height = 86
    local x = (conky_window.width - width) / 2
    local y = top_padding

    shared.rounded_rect(cr, x, y, width, height, radius)
    shared.set_hex(cr, '020617', 0.82)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, 'f87171', 0.92)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)
    shared.set_hex(cr, 'f87171', 1)
    cairo_move_to(cr, x + 24, y + 34)
    cairo_show_text(cr, 'LINEAR SIGNAL LOST')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 12)
    shared.set_hex(cr, 'f8fafc', 0.88)
    cairo_move_to(cr, x + 24, y + 58)
    cairo_show_text(cr, shared.truncate_title(cr, message, width - 48))
  end

  local function draw_card(cr, card, x, y)
    local accent = card.done and '39ff88' or card.due_today and 'ff1a1a' or '00e5ff'
    local accent_secondary = card.done and '00f5d4' or card.due_today and 'ff4d00' or '8b5cf6'

    shared.rounded_rect(cr, x + 4, y + 7, card_width, card_height, radius)
    shared.set_hex(cr, accent, 0.12)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, card_width, card_height, radius)
    shared.set_hex(cr, accent, 0.16)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, card_width, card_height, radius)
    shared.set_hex(cr, accent, 0.26)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x, y, card_width, card_height, radius)
    shared.set_hex(cr, '020617', 0.78)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.95)
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 7, y + 7, card_width - 14, card_height - 14, radius - 6)
    shared.set_hex(cr, accent_secondary, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)

    shared.set_hex(cr, accent, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_move_to(cr, x + 22, y + 18)
    cairo_line_to(cr, x + 48, y + 18)
    cairo_line_to(cr, x + 58, y + 28)
    cairo_stroke(cr)

    shared.set_hex(cr, accent_secondary, 0.18)
    cairo_move_to(cr, x + card_width - 22, y + card_height - 18)
    cairo_line_to(cr, x + card_width - 48, y + card_height - 18)
    cairo_line_to(cr, x + card_width - 58, y + card_height - 28)
    cairo_stroke(cr)

    shared.set_hex(cr, accent, 0.34)
    cairo_arc(cr, x + 58, y + 28, 2, 0, math.pi * 2)
    cairo_fill(cr)
    shared.set_hex(cr, accent_secondary, 0.28)
    cairo_arc(cr, x + card_width - 58, y + card_height - 28, 2, 0, math.pi * 2)
    cairo_fill(cr)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, font_size)

    local lines = shared.wrap_title(cr, card.title, card_width - 36)
    local extents = cairo_text_extents_t:create()
    local total_text_height = #lines * line_height
    local first_baseline = y + (card_height - total_text_height) / 2 + font_size

    for index, line in ipairs(lines) do
      cairo_text_extents(cr, line, extents)
      local text_x = x + (card_width - extents.width) / 2 - extents.x_bearing
      local text_y = first_baseline + (index - 1) * line_height

      shared.set_hex(cr, accent, 0.24)
      cairo_move_to(cr, text_x - 1, text_y)
      cairo_show_text(cr, line)
      cairo_move_to(cr, text_x + 1, text_y)
      cairo_show_text(cr, line)

      shared.set_hex(cr, 'f8fafc', 1)
      cairo_move_to(cr, text_x, text_y)
      cairo_show_text(cr, line)
    end
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local state = read_cards()
    local cards = state.cards

    if #cards == 0 then
      if state.error ~= '' then
        draw_error(cr, state.error)
      end
      cairo_destroy(cr)
      if should_destroy_surface and cairo_surface_destroy then
        cairo_surface_destroy(surface)
      end
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
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
