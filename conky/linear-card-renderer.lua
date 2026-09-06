-- Task cards: a gapless grid of soft-filled records with project and state on
-- top, a title that shrinks before wrapping past two lines, then the issue id
-- and deadline.
return function(shared, repo_root)
  local cards_path = repo_root .. '/cache/linear-cards.json'
  local ui = shared.ui
  local card_min_width, row_height, max_title_lines = 252, 124, 2
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

  -- Tone follows the record's state and the deadline policy; the state text
  -- is the only status treatment inside the card.
  local function describe(card)
    local due = card.due_date ~= '' and card.due_date or card.competition_due_date
    local meta = {}
    if card.label ~= '' then meta[#meta + 1] = card.label end
    if due ~= '' then meta[#meta + 1] = 'Due ' .. due end
    local state, tone
    if card.done then state, tone = 'Done', 'good'
    elseif card.due_today then state, tone = 'Due today', 'danger'
    elseif card.urgent then state, tone = 'Urgent', 'caution'
    else state, tone = card.state ~= '' and card.state or 'Active', 'neutral' end
    return state, tone, table.concat(meta, ' · ')
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
      local state, tone, meta = describe(card)
      local fill = ui[tone]
      ui.rect(cr, x, y, width, height, fill or ui.surface, ui.radius(tone), fill and 0.14 or 1)
      local state_width = ui.text(cr, state, x + width - 12, y + 24,
        {size = 12, bold = 'medium', align = 'right', color = fill or ui.muted, width = width * 0.55})
      local project_x = x + 12
      local project_max_width = width - 32 - state_width
      if card.project_icon ~= '' then
        local icon_w = ui.emoji(cr, card.project_icon, project_x, y + 24, 11)
        if icon_w > 0 then
          local step = icon_w + 5
          project_x = project_x + step
          project_max_width = math.max(0, project_max_width - step)
        end
      end
      ui.text(cr, card.project_name ~= '' and card.project_name or 'No project',
        project_x, y + 24, {size = 12, color = ui.muted, width = project_max_width})
      for index, line in ipairs(layout.lines) do
        ui.text(cr, line, x + 12, y + 46 + (index - 1) * 20,
          {size = layout.size, bold = 'medium'})
      end
      local id_width = ui.text(cr, card.identifier, x + 12, y + height - 16,
        {size = 12, mono = true, color = ui.muted})
      if meta ~= '' then
        ui.text(cr, meta, x + width - 12, y + height - 16,
          {size = 12, color = ui.muted, align = 'right', width = width - 32 - id_width})
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
        local layouts, row_h = {}, 104
        for index = row_start, row_end do
          layouts[index] = title_layout(cr, cards[index], card_width)
          row_h = math.max(row_h, 64 + #layouts[index].lines * 20)
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

  return {draw = draw, height_spacer = height_spacer, read_cards = read_cards}
end
