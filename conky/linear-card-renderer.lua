return function(shared, repo_root)
  local cards_path = repo_root .. '/cache/linear-cards.json'
  local card_width = 318
  local card_height = 110
  local card_gap = 24
  local row_gap = 20
  local top_padding = 12
  -- Extra space below the last row for soft glow / In Progress outline.
  local bottom_padding = 16
  local empty_height = 100
  local radius = 18
  local font = 'JetBrains Mono'
  local font_size = 16
  local line_height = 22
  local title_offset_y = 7
  local default_window_width = 1540

  local function read_cards()
    local content = shared.read_file(cards_path)
    if not content then
      return { cards = {}, error = '' }
    end

    local error_message = content:match('"error"%s*:%s*"(.-)"')
    local cards = {}
    for object in content:gmatch('{%s-"identifier".-}') do
      local identifier = object:match('"identifier"%s*:%s*"(.-)"')
      local state = object:match('"state"%s*:%s*"(.-)"')
      local title = object:match('"title"%s*:%s*"(.-)"')
      local done = object:match('"done"%s*:%s*(true)') ~= nil
      local due_today = object:match('"dueToday"%s*:%s*(true)') ~= nil
      local due_date = object:match('"dueDate"%s*:%s*"(.-)"')
      local competition_upcoming = object:match('"competitionUpcoming"%s*:%s*(true)') ~= nil
      local competition_due_date = object:match('"competitionDueDate"%s*:%s*"(.-)"')

      if title then
        table.insert(cards, {
          identifier = identifier and shared.unescape_json_string(identifier) or '',
          state = state and shared.unescape_json_string(state) or '',
          title = shared.unescape_json_string(title),
          done = done,
          due_today = due_today,
          due_date = due_date and shared.unescape_json_string(due_date) or '',
          competition_upcoming = competition_upcoming,
          competition_due_date = competition_due_date and shared.unescape_json_string(competition_due_date) or '',
        })
      end
    end

    return {
      cards = cards,
      error = error_message and shared.unescape_json_string(error_message) or '',
    }
  end

  local function visible_cards(cards)
    local has_red_cards = false
    for _, card in ipairs(cards) do
      if card.due_today and not card.done then
        has_red_cards = true
        break
      end
    end

    if not has_red_cards then
      return cards
    end

    local filtered_cards = {}
    for _, card in ipairs(cards) do
      if card.done or card.due_today or card.competition_upcoming then
        table.insert(filtered_cards, card)
      end
    end
    return filtered_cards
  end

  local function window_width()
    if conky_window and conky_window.width and conky_window.width > 0 then
      return conky_window.width
    end
    return default_window_width
  end

  local function cards_per_row_for(width)
    return math.max(1, math.floor((width + card_gap) / (card_width + card_gap)))
  end

  local function row_count_for(card_count, width)
    if card_count <= 0 then
      return 0
    end
    local per_row = cards_per_row_for(width)
    return math.ceil(card_count / per_row)
  end

  local function height_for_rows(rows)
    if rows <= 0 then
      return empty_height
    end
    return top_padding + rows * card_height + math.max(0, rows - 1) * row_gap + bottom_padding
  end

  local function needed_height()
    local state = read_cards()
    local cards = visible_cards(state.cards)
    if #cards == 0 then
      return empty_height
    end
    return height_for_rows(row_count_for(#cards, window_width()))
  end

  -- Expand the Conky window to fit the current card grid. Returned text is
  -- re-parsed via ${lua_parse} so the voffset becomes real vertical space.
  local function height_spacer()
    return string.format('${voffset %d}', needed_height())
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

    if card.state == 'In Progress' and not card.done then
      shared.rounded_rect(cr, x - 6, y - 6, card_width + 12, card_height + 12, radius + 6)
      shared.set_hex(cr, 'facc15', 0.18)
      cairo_set_line_width(cr, 4)
      cairo_stroke(cr)

      shared.rounded_rect(cr, x - 5, y - 5, card_width + 10, card_height + 10, radius + 5)
      shared.set_hex(cr, 'facc15', 0.84)
      cairo_set_line_width(cr, 2)
      cairo_stroke(cr)
    end

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
    cairo_set_font_size(cr, 11)
    shared.set_hex(cr, accent, 0.88)

    local identifier_max_width = card_width - 44
    local visible_due_date = ''
    if not card.done and not card.due_today then
      visible_due_date = card.due_date ~= '' and card.due_date or card.competition_due_date
    end

    if visible_due_date ~= '' then
      local due_extents = cairo_text_extents_t:create()
      cairo_text_extents(cr, visible_due_date, due_extents)
      shared.set_hex(cr, accent, 0.88)
      cairo_move_to(cr, x + card_width - 22 - due_extents.width - due_extents.x_bearing, y + 31)
      cairo_show_text(cr, visible_due_date)
      identifier_max_width = math.max(40, card_width - 62 - due_extents.width)
    end

    shared.set_hex(cr, accent, 0.88)
    cairo_move_to(cr, x + 22, y + 31)
    cairo_show_text(cr, shared.truncate_title(cr, card.identifier, identifier_max_width))

    cairo_set_font_size(cr, font_size)

    local lines = shared.wrap_title(cr, card.title, card_width - 36)
    local extents = cairo_text_extents_t:create()
    local total_text_height = #lines * line_height
    local first_baseline = y + (card_height - total_text_height) / 2 + font_size + title_offset_y

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
    local cards = visible_cards(state.cards)

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

    local per_row = cards_per_row_for(conky_window.width)

    for index, card in ipairs(cards) do
      local row = math.floor((index - 1) / per_row)
      local column = (index - 1) % per_row
      local items_in_row = math.min(per_row, #cards - row * per_row)
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
    height_spacer = height_spacer,
  }
end
