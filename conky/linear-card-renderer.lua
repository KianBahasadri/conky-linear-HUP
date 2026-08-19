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
  -- JetBrains Mono has no emoji glyphs, and the cairo toy text API does not fall
  -- back per glyph, so project icons need their own family.
  local emoji_font = 'Noto Color Emoji'
  local font_size = 16
  local line_height = 22
  local project_font_size = 11
  -- Emoji glyphs are taller than their nominal size, so run them a step smaller
  -- than the project name to keep both inside the card's inner border.
  local project_icon_size = 10
  local project_icon_gap = 5
  local compact_font_size = 14
  local compact_line_height = 19
  -- Baseline of the header row that carries the project icon and name.
  local project_offset_y = 19
  -- Identifier and due date share a footer row, mirroring the project row's inset.
  local meta_font_size = 9
  local meta_offset_y = card_height - 15
  -- Linear marks urgent issues with an orange rounded square carrying a knocked
  -- out exclamation mark; it rides the footer row's right edge.
  local urgent_color = 'ff7236'
  local urgent_badge_size = 14
  local urgent_badge_gap = 8
  -- The header baseline and the footer row are inset by roughly the same amount
  -- from their edges, so centring the title on the card leaves even gaps either
  -- side. Retune this if project_offset_y or meta_offset_y moves.
  local title_offset_y = 0
  local default_window_width = 1540

  local function read_cards()
    local content = shared.read_file(cards_path)
    if not content then
      return { cards = {}, error = '' }
    end

    local error_message = shared.match_json_string(content, 'error')
    local cards = {}
    for object in content:gmatch('{%s-"identifier".-}') do
      local identifier = shared.match_json_string(object, 'identifier')
      local project_name = shared.match_json_string(object, 'projectName')
      local project_icon = shared.match_json_string(object, 'projectIcon')
      local state = shared.match_json_string(object, 'state')
      local title = shared.match_json_string(object, 'title')
      local done = object:match('"done"%s*:%s*(true)') ~= nil
      local due_today = object:match('"dueToday"%s*:%s*(true)') ~= nil
      local due_date = shared.match_json_string(object, 'dueDate')
      local competition_upcoming = object:match('"competitionUpcoming"%s*:%s*(true)') ~= nil
      local competition_due_date = shared.match_json_string(object, 'competitionDueDate')
      local backlog_due_soon = object:match('"backlogDueSoon"%s*:%s*(true)') ~= nil
      local urgent = object:match('"urgent"%s*:%s*(true)') ~= nil

      if title then
        table.insert(cards, {
          identifier = identifier and shared.unescape_json_string(identifier) or '',
          project_name = project_name and shared.unescape_json_string(project_name) or '',
          project_icon = project_icon and shared.unescape_json_string(project_icon) or '',
          state = state and shared.unescape_json_string(state) or '',
          title = shared.unescape_json_string(title),
          done = done,
          due_today = due_today,
          due_date = due_date and shared.unescape_json_string(due_date) or '',
          competition_upcoming = competition_upcoming,
          competition_due_date = competition_due_date and shared.unescape_json_string(competition_due_date) or '',
          backlog_due_soon = backlog_due_soon,
          urgent = urgent,
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
      if card.done or card.due_today or card.competition_upcoming or card.backlog_due_soon then
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
    shared.set_hex(cr, '020617', 0.59)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, 'f87171', 0.70)
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

  local function draw_urgent_badge(cr, x, y)
    shared.rounded_rect(cr, x, y, urgent_badge_size, urgent_badge_size, 3)
    shared.set_hex(cr, urgent_color, 0.96)
    cairo_fill(cr)

    -- Bar and dot are cut in the card's body color, the way Linear's icon shows
    -- the surface through the mark.
    local stem_width = 2.4
    local stem_x = x + (urgent_badge_size - stem_width) / 2
    shared.set_hex(cr, '020617', 0.92)
    cairo_rectangle(cr, stem_x, y + 2.6, stem_width, 5.2)
    cairo_rectangle(cr, stem_x, y + 9.2, stem_width, 2.4)
    cairo_fill(cr)
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
    shared.set_hex(cr, '020617', 0.59)
    cairo_fill_preserve(cr)
    shared.set_hex(cr, accent, 0.70)
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

    -- Kept clear of the footer row so the trace underlines the due date instead
    -- of striking through it.
    shared.set_hex(cr, accent_secondary, 0.18)
    cairo_move_to(cr, x + card_width - 22, y + card_height - 14)
    cairo_line_to(cr, x + card_width - 48, y + card_height - 14)
    cairo_line_to(cr, x + card_width - 58, y + card_height - 24)
    cairo_stroke(cr)

    shared.set_hex(cr, accent, 0.34)
    cairo_arc(cr, x + 58, y + 28, 2, 0, math.pi * 2)
    cairo_fill(cr)
    shared.set_hex(cr, accent_secondary, 0.28)
    cairo_arc(cr, x + card_width - 58, y + card_height - 24, 2, 0, math.pi * 2)
    cairo_fill(cr)

    local project_name = card.project_name ~= '' and card.project_name or 'No project'
    local project_max_width = card_width - 44
    local icon_step = 0

    if card.project_icon ~= '' then
      cairo_select_font_face(cr, emoji_font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
      cairo_set_font_size(cr, project_icon_size)
      local icon_extents = cairo_text_extents_t:create()
      cairo_text_extents(cr, card.project_icon, icon_extents)
      icon_step = icon_extents.x_advance + project_icon_gap
      project_max_width = project_max_width - icon_step
    end

    -- Icon and name are measured first so the pair centres as one block.
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, project_font_size)
    local project_text = shared.truncate_title(cr, project_name, project_max_width)
    local project_extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, project_text, project_extents)
    local project_x = x + (card_width - icon_step - project_extents.width) / 2

    shared.set_hex(cr, accent, 0.88)
    cairo_move_to(cr, project_x + icon_step - project_extents.x_bearing, y + project_offset_y)
    cairo_show_text(cr, project_text)

    if card.project_icon ~= '' then
      cairo_select_font_face(cr, emoji_font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
      cairo_set_font_size(cr, project_icon_size)
      -- Color glyphs carry their own palette; the source only sets opacity.
      shared.set_hex(cr, 'f8fafc', 0.95)
      cairo_move_to(cr, project_x, y + project_offset_y)
      cairo_show_text(cr, card.project_icon)
    end

    -- The badge claims the footer's right edge; the due date falls in beside it.
    local footer_right = x + card_width - 22
    local footer_reserved = 0
    if card.urgent then
      draw_urgent_badge(cr, footer_right - urgent_badge_size, y + meta_offset_y - 11)
      footer_reserved = urgent_badge_size + urgent_badge_gap
      footer_right = footer_right - footer_reserved
    end

    local identifier_max_width = card_width - 44 - footer_reserved
    local visible_due_date = ''
    if not card.done and not card.due_today then
      visible_due_date = card.due_date ~= '' and card.due_date or card.competition_due_date
    end

    if visible_due_date ~= '' then
      -- Set explicitly: the header may have left the emoji font selected.
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
      cairo_set_font_size(cr, project_font_size)
      local due_extents = cairo_text_extents_t:create()
      cairo_text_extents(cr, visible_due_date, due_extents)
      shared.set_hex(cr, accent, 0.88)
      cairo_move_to(cr, footer_right - due_extents.width - due_extents.x_bearing, y + meta_offset_y)
      cairo_show_text(cr, visible_due_date)
      identifier_max_width = math.max(40, card_width - 62 - footer_reserved - due_extents.width)
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, meta_font_size)
    shared.set_hex(cr, '94a3b8', 0.76)
    cairo_move_to(cr, x + 22, y + meta_offset_y)
    cairo_show_text(cr, shared.truncate_title(cr, card.identifier, identifier_max_width))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    local title_font_size = font_size
    local title_line_height = line_height
    cairo_set_font_size(cr, title_font_size)

    local lines = shared.wrap_title(cr, card.title, card_width - 36, 3)
    if #lines > 2 then
      title_font_size = compact_font_size
      title_line_height = compact_line_height
      cairo_set_font_size(cr, title_font_size)
      lines = shared.wrap_title(cr, card.title, card_width - 36, 3)
    end

    local extents = cairo_text_extents_t:create()
    local total_text_height = #lines * title_line_height
    local first_baseline = y + (card_height - total_text_height) / 2 + title_font_size + title_offset_y

    for index, line in ipairs(lines) do
      cairo_text_extents(cr, line, extents)
      local text_x = x + (card_width - extents.width) / 2 - extents.x_bearing
      local text_y = first_baseline + (index - 1) * title_line_height

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
