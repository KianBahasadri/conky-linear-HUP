-- Task cards: a gapless grid of soft-filled records with project, issue id,
-- and deadline/urgency on top, followed by a single-line title that steps down
-- in size before truncating.
return function(shared, repo_root)
  local cards_path = repo_root .. '/cache/linear-cards.json'
  local ui = shared.ui
  local card_min_width, row_height, max_title_lines = 252, 50, 1
  local title_sizes = {15, 14, 13}

  local function read_cards()
    local content = shared.read_file(cards_path)
    if not content then
      return { cards = {}, error = '' }
    end

    local error_message = shared.json_string(content, 'error', nil)
    -- Payload-level lifetime of done cards in seconds; precomputed by the
    -- fetcher from LINEAR_DONE_LOOKBACK_HOURS so the renderer stays dumb.
    local done_lookback_seconds = shared.json_number(content, 'doneLookbackSeconds', nil)
    local cards = {}
    for _, object in ipairs(shared.json_array_objects(content, 'cards')) do
      local identifier = shared.json_string(object, 'identifier', '')
      local label = shared.json_string(object, 'label', '')
      local project_name = shared.json_string(object, 'projectName', '')
      local project_icon = shared.json_string(object, 'projectIcon', '')
      local state = shared.json_string(object, 'state', '')
      local title = shared.json_string(object, 'title', nil)
      local done = shared.json_boolean(object, 'done', false)
      local due_today = shared.json_boolean(object, 'dueToday', false)
      local due_date = shared.json_string(object, 'dueDate', '')
      local competition_upcoming = shared.json_boolean(object, 'competitionUpcoming', false)
      local competition_due_date = shared.json_string(object, 'competitionDueDate', '')
      local backlog_due_soon = shared.json_boolean(object, 'backlogDueSoon', false)
      local urgent = shared.json_boolean(object, 'urgent', false)
      local completed_at_epoch = shared.json_number(object, 'completedAtEpoch', 0)

      if title then
        table.insert(cards, {
          identifier = identifier,
          label = label,
          project_name = project_name,
          project_icon = project_icon,
          state = state,
          title = title,
          done = done,
          due_today = due_today,
          due_date = due_date,
          competition_upcoming = competition_upcoming,
          competition_due_date = competition_due_date,
          backlog_due_soon = backlog_due_soon,
          urgent = urgent,
          completed_at_epoch = completed_at_epoch,
        })
      end
    end

    return {
      cards = cards,
      error = error_message or '',
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

  local function columns_for(width)
    return math.max(1, math.floor(width / card_min_width))
  end

  local function height_spacer()
    local cards = visible_cards(read_cards().cards)
    local columns = columns_for(conky_window and conky_window.width or 1136)
    local rows = math.min(3, math.max(1, math.ceil(#cards / columns)))
    return string.format('${voffset %d}', rows * row_height)
  end

  -- Tone follows the record's state and the deadline policy; the header
  -- carries urgency or deadline text on the right while ordinary workflow
  -- states (In Progress, Todo) are conveyed via title contrast.
  local function describe(card)
    local due = (card.due_date and card.due_date ~= '') and card.due_date or (card.competition_due_date or '')
    local parts = {}
    local tone
    if card.done then
      parts[#parts + 1] = 'Done'
      tone = 'good'
    elseif card.due_today then
      parts[#parts + 1] = 'Due today'
      tone = 'danger'
    elseif card.urgent then
      parts[#parts + 1] = 'Urgent'
      tone = 'caution'
      if due ~= '' then parts[#parts + 1] = 'Due ' .. due end
    else
      tone = 'neutral'
      if due ~= '' then parts[#parts + 1] = 'Due ' .. due end
    end
    return table.concat(parts, ' · '), tone
  end

  local function title_color(card)
    return (card.state == 'In Progress' and not card.done) and ui.ink or ui.muted
  end

  local function title_layout(cr, card, width)
    local max_width = width - 24
    local size, lines = title_sizes[#title_sizes], nil
    for _, candidate in ipairs(title_sizes) do
      size = candidate
      ui.font(cr, size, false, 'medium')
      lines = shared.wrap_title(cr, card.title, max_width, 32)
      if #lines <= max_title_lines then
        return {lines = lines, size = size}
      end
    end
    ui.font(cr, size, false, 'medium')
    return {
      lines = shared.wrap_title(cr, card.title, max_width, max_title_lines),
      size = size,
    }
  end

  local function draw_card(cr, card, layout, x, y, width, height, fade)
    ui.group(cr, fade, function()
      local state, tone = describe(card)
      local fill = ui[tone]
      ui.rect(cr, x, y, width, height, fill or ui.surface, ui.radius(tone), fill and 0.14 or 1)
      local state_width = 0
      if state ~= '' then
        state_width = ui.text(cr, state, x + width - 12, y + 18,
          {size = 12, bold = 'medium', align = 'right', color = fill or ui.muted, width = width * 0.55})
      end
      local right_limit = state_width > 0 and (x + width - 16 - state_width) or (x + width - 12)
      local project_x = x + 12
      if card.project_icon ~= '' then
        local icon_w = ui.emoji(cr, card.project_icon, project_x, y + 18, 11)
        if icon_w > 0 then
          project_x = project_x + icon_w + 5
        end
      end
      local total_available = math.max(0, right_limit - project_x)
      local id_w = 0
      if card.identifier ~= '' then
        ui.font(cr, 12, true, nil)
        id_w = ui.width(cr, card.identifier)
      end
      local sep_w = 0
      if card.project_name ~= '' and card.identifier ~= '' then
        ui.font(cr, 12, false, nil)
        sep_w = ui.width(cr, ' · ')
      end
      if card.project_name ~= '' then
        local name_max_w = card.identifier ~= '' and math.max(20, total_available - id_w - sep_w) or total_available
        local name_w = ui.text(cr, card.project_name, project_x, y + 18,
          {size = 12, color = ui.muted, width = name_max_w})
        project_x = project_x + name_w
        if card.identifier ~= '' and project_x < right_limit then
          local drawn_sep_w = ui.text(cr, ' · ', project_x, y + 18, {size = 12, color = ui.muted})
          project_x = project_x + drawn_sep_w
        end
      end
      if card.identifier ~= '' then
        local id_max_w = math.max(0, right_limit - project_x)
        ui.text(cr, card.identifier, project_x, y + 18,
          {size = 12, mono = true, color = ui.muted, width = id_max_w})
      end
      local t_color = title_color(card)
      for index, line in ipairs(layout.lines) do
        ui.text(cr, line, x + 12, y + 37 + (index - 1) * 20,
          {size = layout.size, bold = 'medium', color = t_color})
      end
    end)
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local state = read_cards()
      local cards = visible_cards(state.cards)
      if #cards == 0 then
        if state.error ~= '' then ui.callout(cr, 'Unavailable', state.error, 0, 0, width, 'danger')
        else ui.text(cr, 'No active issues', 0, 16, {size = 13.5, color = ui.muted}) end
        return
      end
      local columns = columns_for(width)
      local rows = math.max(1, math.floor(height / row_height))
      local first, last, page = ui.page(#cards, columns * rows)
      -- An overflowing grid gives up one line of height to its page footer.
      if page ~= '' then
        rows = math.max(1, math.floor((height - 16) / row_height))
        first, last, page = ui.page(#cards, columns * rows)
      end
      local card_width = width / columns
      local lookback = math.max(1, state.done_lookback_seconds or 18 * 3600)
      local y = 0
      for row_start = first, last, columns do
        local row_end = math.min(last, row_start + columns - 1)
        local layouts, row_h = {}, 50
        for index = row_start, row_end do
          layouts[index] = title_layout(cr, cards[index], card_width)
          row_h = math.max(row_h, 30 + #layouts[index].lines * 20)
        end
        for index = row_start, row_end do
          local card = cards[index]
          local age = card.completed_at_epoch > 0 and os.time() - card.completed_at_epoch or 0
          local fade = card.done and (1 - shared.clamp(age / lookback, 0, 1)) or 1
          draw_card(cr, card, layouts[index], (index - row_start) * card_width, y, card_width, row_h, fade)
        end
        y = y + row_h
      end
      ui.footer(cr, page, width, height)
    end)
  end

  return {
    draw = draw,
    describe = describe,
    height_spacer = height_spacer,
    read_cards = read_cards,
    title_layout = title_layout,
    title_color = title_color,
  }
end
