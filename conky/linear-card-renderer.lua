return function(shared, repo_root)
  local cards_path = repo_root .. '/cache/linear-cards.json'
  local card_width = 268
  local card_height = 84
  local card_gap = 0
  local row_gap = 12
  local top_padding = 8
  -- Extra space below the last row for the In Progress edge marker.
  local bottom_padding = 8
  local empty_height = 96
  local font = 'JetBrains Mono'
  -- JetBrains Mono has no emoji glyphs, and the cairo toy text API does not fall
  -- back per glyph, so project icons need their own family.
  local emoji_font = 'Noto Color Emoji'
  local font_size = 15
  local line_height = 18
  local project_font_size = 10
  -- Emoji glyphs are taller than their nominal size, so run them a step smaller
  -- than the project name to keep both inside the card's inner border.
  local project_icon_size = 9
  local project_icon_gap = 4
  local compact_font_size = 13
  local compact_line_height = 16
  -- Baseline of the header row that carries the project icon and name.
  local project_offset_y = 15
  -- Identifier and due date share a footer row, mirroring the project row's inset.
  local meta_font_size = 10
  local meta_offset_y = card_height - 9
  -- Linear marks urgent issues with an orange square carrying a knocked
  -- out exclamation mark; it rides the footer row's right edge.
  local urgent_color = 'ff7236'
  local urgent_badge_size = 12
  local urgent_badge_gap = 8
  local default_window_width = 1540

  local function read_cards()
    local content = shared.read_file(cards_path)
    if not content then
      return { cards = {}, error = '' }
    end

    local error_message = shared.match_json_string(content, 'error')
    -- Payload-level lifetime of done cards in seconds; precomputed by the
    -- fetcher from LINEAR_DONE_LOOKBACK_HOURS so the renderer stays dumb.
    local done_lookback_seconds = tonumber(content:match('"doneLookbackSeconds"%s*:%s*([%d%.]+)') or '')
    local cards = {}
    for object in content:gmatch('{%s-"identifier".-}') do
      local identifier = shared.match_json_string(object, 'identifier')
      local label = shared.match_json_string(object, 'label')
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
      -- Lua patterns have no optional groups: pull completedAtEpoch either as
      -- digits or as 0 (the fetcher's sentinel for "no completion timestamp").
      local completed_at_epoch = tonumber(object:match('"completedAtEpoch"%s*:%s*(%d+)') or '0')

      if title then
        table.insert(cards, {
          identifier = identifier and shared.unescape_json_string(identifier) or '',
          label = label and shared.unescape_json_string(label) or '',
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
          completed_at_epoch = completed_at_epoch,
        })
      end
    end

    return {
      cards = cards,
      error = error_message and shared.unescape_json_string(error_message) or '',
      done_lookback_seconds = done_lookback_seconds,
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

    cairo_rectangle(cr, x, y, width, height)
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

  local function draw_urgent_badge(cr, x, y, fade)
    cairo_rectangle(cr, x, y, urgent_badge_size, urgent_badge_size)
    shared.set_hex(cr, urgent_color, 0.96 * fade)
    cairo_fill(cr)

    -- Bar and dot are cut in the card's body color, the way Linear's icon shows
    -- the surface through the mark.
    local stem_width = 2.4
    local stem_x = x + (urgent_badge_size - stem_width) / 2
    shared.set_hex(cr, '020617', 0.92 * fade)
    cairo_rectangle(cr, stem_x, y + 2.6, stem_width, 5.2)
    cairo_rectangle(cr, stem_x, y + 9.2, stem_width, 2.4)
    cairo_fill(cr)
  end

  local function draw_card(cr, card, x, y, fade)
    -- Fresh done cards sit at full strength and every stroke and glyph dims
    -- together on one straight line down to nothing as the lookback expires;
    -- active work stays untouched at fade = 1.
    local function ink(hex, alpha)
      shared.set_hex(cr, hex, (alpha or 1) * fade)
    end

    local accent = card.done and '39ff88' or card.due_today and 'ff1a1a' or '00e5ff'
    local accent_secondary = card.done and '00f5d4' or card.due_today and 'ff4d00' or '8b5cf6'

    -- Flat panel construction keeps the grid dense: one body fill, one crisp
    -- state border, and a slim accent rail instead of a three-layer glow.
    cairo_rectangle(cr, x, y, card_width, card_height)
    ink('020617', 0.82)
    cairo_fill_preserve(cr)
    ink(accent, 0.78)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)

    cairo_rectangle(cr, x, y, 3, card_height)
    ink(accent, 0.92)
    cairo_fill(cr)

    if card.state == 'In Progress' and not card.done then
      -- Keep the active-work state visible after removing the old halo.
      shared.set_hex(cr, 'facc15', 0.90 * fade)
      cairo_set_line_width(cr, 2)
      cairo_move_to(cr, x + 1, y + 1)
      cairo_line_to(cr, x + card_width - 1, y + 1)
      cairo_stroke(cr)
    end

    cairo_rectangle(cr, x + 8, y + 8, card_width - 16, card_height - 16)
    ink(accent_secondary, 0.22)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)

    -- These two rules divide the three information bands without consuming
    -- another row of height.
    ink(accent, 0.26)
    cairo_move_to(cr, x + 12, y + 20)
    cairo_line_to(cr, x + card_width - 12, y + 20)
    cairo_stroke(cr)
    ink(accent_secondary, 0.28)
    cairo_move_to(cr, x + 12, y + card_height - 20)
    cairo_line_to(cr, x + card_width - 12, y + card_height - 20)
    cairo_stroke(cr)

    local project_name = card.project_name ~= '' and card.project_name or 'No project'
    local project_max_width = card_width - 24
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

    ink(accent, 0.88)
    cairo_move_to(cr, project_x + icon_step - project_extents.x_bearing, y + project_offset_y)
    cairo_show_text(cr, project_text)

    if card.project_icon ~= '' then
      cairo_select_font_face(cr, emoji_font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
      cairo_set_font_size(cr, project_icon_size)
      -- Color glyphs carry their own palette and alpha, so the fill source only
      -- sets opacity for them and cannot express a fade. Raster the glyph into
      -- a group and paint it back scaled by the card's fade instead; active
      -- cards (fade = 1) skip the round trip and draw straight to the surface.
      ink('f8fafc', 0.95)
      if fade < 1 then
        cairo_push_group(cr)
      end
      cairo_move_to(cr, project_x, y + project_offset_y)
      cairo_show_text(cr, card.project_icon)
      if fade < 1 then
        cairo_pop_group_to_source(cr)
        cairo_paint_with_alpha(cr, fade)
      end
    end

    -- The badge claims the footer's right edge; the due date falls in beside it.
    local footer_right = x + card_width - 12
    local footer_reserved = 0
    if card.urgent then
      draw_urgent_badge(cr, footer_right - urgent_badge_size, y + meta_offset_y - 9, fade)
      footer_reserved = urgent_badge_size + urgent_badge_gap
      footer_right = footer_right - footer_reserved
    end

    local identifier_max_width = card_width - 24 - footer_reserved
    local visible_due_date = ''
    if not card.done and not card.due_today then
      visible_due_date = card.due_date ~= '' and card.due_date or card.competition_due_date
    end

    local due_width = 0
    if visible_due_date ~= '' then
      -- Set explicitly: the header may have left the emoji font selected.
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
      cairo_set_font_size(cr, meta_font_size)
      local due_extents = cairo_text_extents_t:create()
      cairo_text_extents(cr, visible_due_date, due_extents)
      due_width = due_extents.width
      ink(accent, 0.88)
      cairo_move_to(cr, footer_right - due_extents.width - due_extents.x_bearing, y + meta_offset_y)
      cairo_show_text(cr, visible_due_date)
      identifier_max_width = math.max(40, footer_right - (x + 12) - due_extents.width - 8)
    end

    if card.label and card.label ~= '' then
      cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
      cairo_set_font_size(cr, meta_font_size)
      local right_content_x = footer_right - (due_width > 0 and (due_width + 8) or 0)
      local max_half_right = math.max(20, right_content_x - (x + card_width / 2))
      local max_label_width = math.min(120, max_half_right * 2)
      local label_text = shared.truncate_title(cr, card.label, max_label_width)
      local label_extents = cairo_text_extents_t:create()
      cairo_text_extents(cr, label_text, label_extents)
      local label_x = x + (card_width - label_extents.width) / 2 - label_extents.x_bearing

      ink('94a3b8', 0.76)
      cairo_move_to(cr, label_x, y + meta_offset_y)
      cairo_show_text(cr, label_text)

      local id_right_limit = label_x + label_extents.x_bearing - 8
      identifier_max_width = math.max(30, math.min(identifier_max_width, id_right_limit - (x + 12)))
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, meta_font_size)
    ink('94a3b8', 0.76)
    cairo_move_to(cr, x + 12, y + meta_offset_y)
    cairo_show_text(cr, shared.truncate_title(cr, card.identifier, identifier_max_width))

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    local title_font_size = font_size
    local title_line_height = line_height
    cairo_set_font_size(cr, title_font_size)

    local lines = shared.wrap_title(cr, card.title, card_width - 24, 3)
    if #lines > 2 then
      title_font_size = compact_font_size
      title_line_height = compact_line_height
      cairo_set_font_size(cr, title_font_size)
      lines = shared.wrap_title(cr, card.title, card_width - 24, 3)
    end

    local extents = cairo_text_extents_t:create()
    local total_text_height = #lines * title_line_height
    local title_top = y + 22
    local title_area_height = card_height - 44
    local first_baseline = title_top
      + (title_area_height - total_text_height) / 2
      + title_font_size

    for index, line in ipairs(lines) do
      cairo_text_extents(cr, line, extents)
      local text_x = x + (card_width - extents.width) / 2 - extents.x_bearing
      local text_y = first_baseline + (index - 1) * title_line_height

      ink('f8fafc', 1)
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
    -- Default matches the fetcher's LINEAR_DONE_LOOKBACK_HOURS fallback.
    local done_lookback = state.done_lookback_seconds or 18 * 3600
    local now_epoch = os.time()

    for index, card in ipairs(cards) do
      local row = math.floor((index - 1) / per_row)
      local column = (index - 1) % per_row
      local items_in_row = math.min(per_row, #cards - row * per_row)
      local row_width = items_in_row * card_width + (items_in_row - 1) * card_gap
      local start_x = (conky_window.width - row_width) / 2
      local x = start_x + column * (card_width + card_gap)
      local y = top_padding + row * (card_height + row_gap)

      local fade = 1
      if card.done then
        -- Epoch 0 means no known completion (legacy cache); hold full strength
        -- rather than reading an infinite age and blinking straight to zero.
        local age = card.completed_at_epoch > 0 and now_epoch - card.completed_at_epoch or 0
        fade = 1 - shared.clamp(age / done_lookback, 0, 1)
      end

      draw_card(cr, card, x, y, fade)
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
