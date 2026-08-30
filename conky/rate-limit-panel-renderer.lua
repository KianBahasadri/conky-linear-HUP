return function(shared, repo_root)
  local codex_usage_path = repo_root .. '/cache/codex-usage.json'
  local codex_usage_tsv_path = repo_root .. '/cache/codex-usage-render.tsv'
  local claude_usage_tsv_path = repo_root .. '/cache/claude-usage-render.tsv'
  local cursor_usage_tsv_path = repo_root .. '/cache/cursor-usage-render.tsv'
  local gemini_usage_tsv_path = repo_root .. '/cache/gemini-usage-render.tsv'
  local grok_usage_tsv_path = repo_root .. '/cache/grok-usage-render.tsv'
  local opencode_usage_tsv_path = repo_root .. '/cache/opencode-usage-render.tsv'
  local commandcode_usage_tsv_path = repo_root .. '/cache/commandcode-usage-render.tsv'
  local font = 'JetBrains Mono'
  local panel_width = 1000
  local panel_height = 110
  local panel_auto_height = true
  local panel_radius = 18
  local account_row_x = 34
  local account_row_y = 8
  local account_row_gap = 16
  local panel_dynamic_height_padding = 24
  local panel_first_bar_x = 90
  -- Width of each usage progress bar.
  local bar_width = 230
  local bar_height = 8
  local bar_text_gap = 14
  local bar_countdown_width = 54
  -- Insets keep title chips (drawn at y-9) and the frame glow (y+7) inside the
  -- Conky window. Must stay in sync with fetch_common.rate_limit_panel_window_height.
  local panel_top_inset = 12
  local panel_bottom_inset = 12
  local title_chip_gap = 8
  local panel_window_floor = 320
  local five_hour_window_seconds = 18000
  local weekly_window_seconds = 604800
  local pace_threshold = 10
  -- Pace marker appearance; does not affect bar fill.
  local pace_marker_color = 'ff9f1c'
  local pace_marker_width = 1
  local pace_marker_opacity_neutral = 1.0
  local pace_marker_opacity = 0.96

  local function seconds_until_reset(window)
    if window.reset_at_epoch and window.reset_at_epoch > 0 then
      return math.max(0, window.reset_at_epoch - os.time())
    end
    return math.max(0, window.reset_after_seconds or 0)
  end

  local function normalized_window_label(window)
    local label = string.lower(window.label or '')
    if label == '5h' and seconds_until_reset(window) > 86400 then
      return 'weekly'
    end
    return label
  end

  local function window_duration(window)
    if window.window_seconds and window.window_seconds > 0 then
      return window.window_seconds
    end
    if normalized_window_label(window) == 'weekly' then
      return weekly_window_seconds
    end
    if normalized_window_label(window) == 'reserve' then
      return weekly_window_seconds
    end
    if normalized_window_label(window) == 'monthly' then
      if window.window_seconds and window.window_seconds > 0 then
        return window.window_seconds
      end
      return 31 * 86400
    end
    if normalized_window_label(window) == 'daily' then
      return 86400
    end
    return five_hour_window_seconds
  end

  local function unescape_tsv(value)
    local output = {}
    local index = 1

    while index <= #value do
      local character = value:sub(index, index)
      if character == '\\' and index < #value then
        local next_character = value:sub(index + 1, index + 1)
        if next_character == 't' then
          table.insert(output, '\t')
        elseif next_character == 'n' then
          table.insert(output, ' ')
        elseif next_character == '\\' then
          table.insert(output, '\\')
        else
          table.insert(output, next_character)
        end
        index = index + 2
      else
        table.insert(output, character)
        index = index + 1
      end
    end

    return table.concat(output)
  end

  local function split_tsv(line)
    local fields = {}
    for field in (line .. '\t'):gmatch('(.-)\t') do
      table.insert(fields, unescape_tsv(field))
    end
    return fields
  end

  local function read_usage_tsv(path, provider)
    local content = shared.read_file(path)
    if not content then
      return nil
    end

    local usage = {
      ok = false,
      error = '',
      accounts = {},
    }
    local account_index = {}

    for line in content:gmatch('[^\r\n]+') do
      local fields = split_tsv(line)
      local row_type = fields[1]

      if row_type == 'meta' then
        for index = 2, #fields, 2 do
          local key = fields[index]
          local value = fields[index + 1] or ''
          if key == 'ok' then
            usage.ok = value == '1'
          elseif key == 'error' then
            usage.error = value
          end
        end
      elseif row_type == 'account' then
        local label = fields[2] or ''
        if label ~= '' and not account_index[label] then
          account_index[label] = {
            label = label,
            provider = provider,
            plan_type = fields[3] or '',
            is_selected = fields[4] == '1',
            ok = fields[5] == '1',
            error = fields[6] or '',
            stale = fields[7] == '1',
            windows = {},
          }
          table.insert(usage.accounts, account_index[label])
        end
      elseif row_type == 'bar' then
        local label = fields[2] or ''
        if label ~= '' then
          if not account_index[label] then
            account_index[label] = {
              label = label,
              provider = provider,
              plan_type = fields[3] or '',
              is_selected = fields[4] == '1',
              ok = true,
              error = '',
              stale = false,
              windows = {},
            }
            table.insert(usage.accounts, account_index[label])
          end

          table.insert(account_index[label].windows, {
            label = normalized_window_label({
              label = fields[5] or '',
              reset_at_epoch = tonumber(fields[9]) or 0,
              reset_after_seconds = tonumber(fields[10]) or 0,
            }),
            used_percent = tonumber(fields[6]) or 0,
            remaining_percent = tonumber(fields[7]) or 0,
            resets_at = fields[8] or '',
            reset_at_epoch = tonumber(fields[9]) or 0,
            reset_after_seconds = tonumber(fields[10]) or 0,
            window_seconds = tonumber(fields[11]) or 0,
          })
        end
      end
    end

    return usage
  end

  local function read_codex_usage_tsv()
    return read_usage_tsv(codex_usage_tsv_path, 'Codex')
  end

  local function read_claude_usage_tsv()
    return read_usage_tsv(claude_usage_tsv_path, 'Claude')
  end

  local function read_cursor_usage_tsv()
    return read_usage_tsv(cursor_usage_tsv_path, 'Cursor')
  end

  local function read_gemini_usage_tsv()
    return read_usage_tsv(gemini_usage_tsv_path, 'Gemini')
  end

  local function read_grok_usage_tsv()
    return read_usage_tsv(grok_usage_tsv_path, 'Grok')
  end

  local function read_opencode_usage_tsv()
    return read_usage_tsv(opencode_usage_tsv_path, 'OpenCode')
  end

  local function read_commandcode_usage_tsv()
    return read_usage_tsv(commandcode_usage_tsv_path, 'CommandCode')
  end

  local function read_codex_usage_json()
    local content = shared.read_file(codex_usage_path)
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
      local is_selected = object:match('"isSelected"%s*:%s*true') ~= nil
      local window = object:match('"window"%s*:%s*"(.-)"')
      local used_percent = tonumber(object:match('"usedPercent"%s*:%s*([%d%.]+)')) or 0
      local remaining_percent = tonumber(object:match('"remainingPercent"%s*:%s*([%d%.]+)')) or math.max(0, 100 - used_percent)
      local resets_at = object:match('"resetsAt"%s*:%s*"(.-)"') or ''
      local reset_at_epoch = tonumber(object:match('"resetAtEpoch"%s*:%s*(%d+)')) or 0
      local reset_after_seconds = tonumber(object:match('"resetAfterSeconds"%s*:%s*(%d+)')) or 0
      local window_seconds = tonumber(object:match('"windowSeconds"%s*:%s*(%d+)')) or 0

      if account and window then
        if not account_index[account] then
          account_index[account] = {
            label = shared.unescape_json_string(account),
            provider = 'Codex',
            plan_type = shared.unescape_json_string(plan_type),
            is_selected = is_selected,
            windows = {},
          }
          table.insert(accounts, account_index[account])
        elseif is_selected then
          account_index[account].is_selected = true
        end

        table.insert(account_index[account].windows, {
          label = normalized_window_label({
            label = window,
            reset_at_epoch = reset_at_epoch,
            reset_after_seconds = reset_after_seconds,
          }),
          used_percent = used_percent,
          remaining_percent = remaining_percent,
          resets_at = resets_at,
          reset_at_epoch = reset_at_epoch,
          reset_after_seconds = reset_after_seconds,
          window_seconds = window_seconds,
        })
      end
    end

    return {
      ok = ok,
      error = error_message and shared.unescape_json_string(error_message) or '',
      accounts = accounts,
    }
  end

  local function plan_sort_rank(account)
    local provider = string.lower(account.provider or '')
    if provider == 'codex' then
      return 0
    elseif provider == 'claude' then
      return 10
    elseif provider == 'cursor' then
      return 20
    elseif provider == 'gemini' then
      return 30
    elseif provider == 'grok' then
      return 35
    elseif provider == 'opencode' then
      return 38
    elseif provider == 'commandcode' then
      return 39
    end

    return 40
  end

  local function plan_type_sort_rank(account)
    local plan_type = string.lower(account.plan_type or '')
    if plan_type == 'free' then
      return 0
    elseif plan_type == 'plus' or plan_type == 'pro' then
      return 2
    end
    return 1
  end

  local function is_free_account(account)
    return string.lower(account.plan_type or '') == 'free'
  end

  -- Pace is normally a paid-account signal, but a provider with no paid plan at
  -- all (Antigravity today) would lose its chip percentage and bar ticks
  -- permanently. Keep pace for the free accounts of such a provider.
  local function provider_is_free_only(accounts, provider)
    local provider_lower = string.lower(provider or '')
    local seen = false

    for _, account in ipairs(accounts or {}) do
      if string.lower(account.provider or '') == provider_lower then
        seen = true
        if not is_free_account(account) then
          return false
        end
      end
    end

    return seen
  end

  local function sort_accounts(accounts)
    for index, account in ipairs(accounts or {}) do
      account.original_index = index
    end

    table.sort(accounts, function(left, right)
      local left_rank = plan_sort_rank(left)
      local right_rank = plan_sort_rank(right)
      if left_rank == right_rank then
        local left_plan_rank = plan_type_sort_rank(left)
        local right_plan_rank = plan_type_sort_rank(right)
        if left_plan_rank ~= right_plan_rank then
          return left_plan_rank < right_plan_rank
        end
        return (left.original_index or 0) < (right.original_index or 0)
      end
      return left_rank < right_rank
    end)
  end

  local function read_ai_usage()
    local codex_usage = read_codex_usage_tsv() or read_codex_usage_json()
    local claude_usage = read_claude_usage_tsv()
    local cursor_usage = read_cursor_usage_tsv()
    local gemini_usage = read_gemini_usage_tsv()
    local grok_usage = read_grok_usage_tsv()
    local opencode_usage = read_opencode_usage_tsv()
    local commandcode_usage = read_commandcode_usage_tsv()
    local usage = {
      ok = false,
      error = '',
      accounts = {},
    }

    if codex_usage then
      usage.ok = usage.ok or codex_usage.ok
      usage.error = codex_usage.error or ''
      for _, account in ipairs(codex_usage.accounts or {}) do
        account.provider = account.provider or 'Codex'
        table.insert(usage.accounts, account)
      end
    end

    if claude_usage then
      usage.ok = usage.ok or claude_usage.ok
      if usage.error == '' then
        usage.error = claude_usage.error or ''
      end
      for _, account in ipairs(claude_usage.accounts or {}) do
        account.provider = account.provider or 'Claude'
        table.insert(usage.accounts, account)
      end
    end

    if cursor_usage then
      usage.ok = usage.ok or cursor_usage.ok
      if usage.error == '' then
        usage.error = cursor_usage.error or ''
      end
      for _, account in ipairs(cursor_usage.accounts or {}) do
        account.provider = account.provider or 'Cursor'
        table.insert(usage.accounts, account)
      end
    end

    if gemini_usage then
      usage.ok = usage.ok or gemini_usage.ok
      if usage.error == '' then
        usage.error = gemini_usage.error or ''
      end
      for _, account in ipairs(gemini_usage.accounts or {}) do
        account.provider = account.provider or 'Gemini'
        table.insert(usage.accounts, account)
      end
    end

    if grok_usage then
      usage.ok = usage.ok or grok_usage.ok
      if usage.error == '' then
        usage.error = grok_usage.error or ''
      end
      for _, account in ipairs(grok_usage.accounts or {}) do
        account.provider = account.provider or 'Grok'
        table.insert(usage.accounts, account)
      end
    end

    if opencode_usage then
      usage.ok = usage.ok or opencode_usage.ok
      if usage.error == '' then
        usage.error = opencode_usage.error or ''
      end
      for _, account in ipairs(opencode_usage.accounts or {}) do
        account.provider = account.provider or 'OpenCode'
        table.insert(usage.accounts, account)
      end
    end

    if commandcode_usage then
      usage.ok = usage.ok or commandcode_usage.ok
      if usage.error == '' then
        usage.error = commandcode_usage.error or ''
      end
      for _, account in ipairs(commandcode_usage.accounts or {}) do
        account.provider = account.provider or 'CommandCode'
        table.insert(usage.accounts, account)
      end
    end

    if usage then
      sort_accounts(usage.accounts)
    end
    return usage
  end

  local function format_reset(seconds)
    if seconds <= 0 then
      return 'wait'
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

  local function format_window_span(seconds)
    if seconds >= 86400 then
      return string.format('%dd', math.floor(seconds / 86400))
    end
    if seconds >= 3600 then
      return string.format('%dh', math.floor(seconds / 3600))
    end
    return string.format('%dm', math.floor(seconds / 60))
  end

  -- Nothing used and no countdown left means the window has not started rather
  -- than run out: a rolling window nobody has touched carries no reset at all,
  -- so its remaining seconds read zero from the very beginning.
  local function window_has_not_started(window)
    if not window or (window.used_percent or 0) > 0 then
      return false
    end
    return seconds_until_reset(window) <= 0
  end

  local function format_window_countdown(window)
    if window_has_not_started(window) then
      return format_window_span(window_duration(window)) .. ' left'
    end
    return format_reset(seconds_until_reset(window))
  end

  local function find_weekly_window(account)
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == 'weekly' then
        return window
      end
    end
    return nil
  end

  local function find_monthly_window(account)
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == 'monthly' then
        return window
      end
    end
    return nil
  end

  local function find_five_hour_window(account)
    for _, window in ipairs(account.windows or {}) do
      if normalized_window_label(window) == '5h' then
        return window
      end
    end
    return nil
  end

  local function remaining_for_pace(window, window_seconds)
    -- A window that has not started has its whole span still ahead of it, so
    -- its zero countdown must not read as fully elapsed and pin the tick to
    -- the right edge.
    if window_has_not_started(window) then
      return window_seconds
    end

    -- Unused sliding resets report remaining == full duration at fetch time.
    -- Live epoch countdown would otherwise make expected > 0 a few seconds later
    -- and draw a left-edge tick on a window that has not actually started.
    local snapshot_remaining = tonumber(window.reset_after_seconds) or 0
    if snapshot_remaining >= window_seconds then
      return window_seconds
    end
    return seconds_until_reset(window)
  end

  local function calculate_window_pace(window, window_seconds)
    if not window or window_seconds <= 0 then
      return nil
    end

    local elapsed_seconds = window_seconds - remaining_for_pace(window, window_seconds)
    local expected = shared.clamp((elapsed_seconds / window_seconds) * 100, 0, 100)
    local actual = shared.clamp(window.used_percent, 0, 100)
    local delta = actual - expected
    local state = 'neutral'

    if delta >= pace_threshold then
      state = 'over'
    elseif expected >= pace_threshold and delta <= -pace_threshold then
      state = 'under'
    end

    return {
      expected = expected,
      actual = actual,
      delta = delta,
      state = state,
    }
  end

  local function calculate_provider_average_pace(accounts, provider)
    local provider_lower = string.lower(provider)
    local include_free = provider_is_free_only(accounts, provider_lower)
    local delta_total = 0
    local delta_count = 0

    for _, account in ipairs(accounts or {}) do
      if string.lower(account.provider or '') == provider_lower then
        if include_free or not is_free_account(account) then
          if provider_lower == 'cursor' or provider_lower == 'gemini' or provider_lower == 'grok' then
            for _, window in ipairs(account.windows or {}) do
              local pace = calculate_window_pace(window, window_duration(window))
              if pace then
                delta_total = delta_total + pace.delta
                delta_count = delta_count + 1
              end
            end
          elseif provider_lower == 'codex' then
            -- Prefer the weekly bar when both windows exist. Some accounts only
            -- expose the 5h bar, so keep it as the fallback.
            local window = find_weekly_window(account) or find_five_hour_window(account)
            if window then
              local pace = calculate_window_pace(window, window_duration(window))
              if pace then
                delta_total = delta_total + pace.delta
                delta_count = delta_count + 1
              end
            end
          elseif provider_lower == 'opencode' or provider_lower == 'commandcode' then
            local monthly = find_monthly_window(account)
            if monthly then
              local pace = calculate_window_pace(monthly, window_duration(monthly))
              if pace then
                delta_total = delta_total + pace.delta
                delta_count = delta_count + 1
              end
            end
          else
            local weekly = find_weekly_window(account)
            if weekly then
              local pace = calculate_window_pace(weekly, window_duration(weekly))
              if pace then
                delta_total = delta_total + pace.delta
                delta_count = delta_count + 1
              end
            end
          end
        end
      end
    end

    if delta_count == 0 then
      return nil
    end

    return delta_total / delta_count
  end

  local function get_provider_label_from_delta(provider_name, avg_delta)
    if not avg_delta then
      return string.upper(provider_name)
    end
    local sign = avg_delta < 0 and '-' or '+'
    return string.format('%s: %s%.0f%%', string.upper(provider_name), sign, math.abs(avg_delta))
  end

  local function hex_rgb(hex)
    return tonumber(hex:sub(1, 2), 16) / 255,
           tonumber(hex:sub(3, 4), 16) / 255,
           tonumber(hex:sub(5, 6), 16) / 255
  end

  -- A gradient stop is { offset, hex, alpha, shade }, where shade mixes the
  -- color toward white (positive) or black (negative) so one accent can supply
  -- the whole lit-to-shadowed run of a curved surface.
  local function add_gradient_stop(pattern, stop)
    local r, g, b = hex_rgb(stop[2])
    local shade = stop[4] or 0
    if shade > 0 then
      r, g, b = r + (1 - r) * shade, g + (1 - g) * shade, b + (1 - b) * shade
    elseif shade < 0 then
      local amount = 1 + shade
      r, g, b = r * amount, g * amount, b * amount
    end
    cairo_pattern_add_color_stop_rgba(pattern, stop[1], r, g, b, stop[3])
  end

  -- Cairo patterns are refcounted objects rather than values, and the panel
  -- redraws every tick, so each one has to be destroyed here or the overlay
  -- leaks a dozen per bar per frame for as long as it stays up.
  local function paint_gradient(cr, x0, y0, x1, y1, stops, paint)
    local pattern = cairo_pattern_create_linear(x0, y0, x1, y1)
    for _, stop in ipairs(stops) do
      add_gradient_stop(pattern, stop)
    end
    cairo_set_source(cr, pattern)
    paint(cr)
    cairo_pattern_destroy(pattern)
  end

  local function fill_gradient(cr, x0, y0, x1, y1, stops)
    paint_gradient(cr, x0, y0, x1, y1, stops, cairo_fill)
  end

  local function stroke_gradient(cr, x0, y0, x1, y1, stops)
    paint_gradient(cr, x0, y0, x1, y1, stops, cairo_stroke)
  end

  local function fill_preserve_gradient(cr, x0, y0, x1, y1, stops)
    paint_gradient(cr, x0, y0, x1, y1, stops, cairo_fill_preserve)
  end

  -- Labels are lit the same way as the surfaces under them: a dark pass one
  -- pixel below drops the glyphs onto their background, then the glyphs
  -- themselves run from a bright top edge down to a deepened base. The light
  -- on this panel comes from straight overhead, so the shadow is offset in y
  -- only -- a diagonal one would imply a second light source that nothing else
  -- here is lit by.
  --
  -- The lit pass shows the text with the gradient as its source rather than
  -- filling a text path: an outline fill loses the hinting that keeps the 10px
  -- countdowns crisp, and at that size the loss is worse than the lighting is
  -- worth. Cap height is 0.70 em and the run reaches just past the baseline, so
  -- lowercase still catches the top of the highlight instead of sitting
  -- entirely in the flat middle.
  local text_cap_height = 0.70
  local text_baseline_overshoot = 0.06

  -- Each profile is a shade curve down the glyph, plus how much of the shadow
  -- to repeat a second pixel lower. `soft` is a sheen for labels that already
  -- sit on a lit surface. `lifted` keeps inherently dark countdown hues above
  -- a readable floor. `raised` packs a specular band into the top eighth and
  -- digs the base out further, which needs the full cap height to land: the
  -- all-caps account names have it, and at 10px the countdowns would only smear.
  local text_relief = {
    soft = {
      contact = 0,
      { 0.00, 0.50 },
      { 0.30, 0.26 },
      { 0.62, 0.02 },
      { 1.00, -0.22 },
    },
    lifted = {
      contact = 0,
      { 0.00, 0.72 },
      { 0.30, 0.50 },
      { 0.62, 0.32 },
      { 1.00, 0.22 },
    },
    raised = {
      contact = 0.55,
      { 0.00, 0.85 },
      { 0.13, 0.60 },
      { 0.40, 0.14 },
      { 0.70, -0.06 },
      { 1.00, -0.40 },
    },
  }

  local function draw_lit_text(cr, label, x, y, size, color, opts)
    opts = opts or {}
    local alpha = opts.alpha or 1
    local shadow = opts.shadow or 0.5
    local relief = text_relief[opts.relief or 'soft']

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, opts.weight or CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, size)

    if relief.contact > 0 then
      shared.set_hex(cr, '000000', shadow * relief.contact)
      cairo_move_to(cr, x, y + 2)
      cairo_show_text(cr, label)
    end
    shared.set_hex(cr, '000000', shadow)
    cairo_move_to(cr, x, y + 1)
    cairo_show_text(cr, label)

    local stops = {}
    for i, stop in ipairs(relief) do
      stops[i] = { stop[1], color, alpha, stop[2] }
    end

    paint_gradient(cr, x, y - size * text_cap_height, x, y + size * text_baseline_overshoot, stops, function(target)
      cairo_move_to(target, x, y)
      cairo_show_text(target, label)
    end)
  end

  local function draw_panel_frame(cr, x, y)
    shared.rounded_rect(cr, x + 4, y + 7, panel_width, panel_height, panel_radius)
    shared.set_hex(cr, '00e5ff', 0.10)
    cairo_fill(cr)

    shared.rounded_rect(cr, x + 2, y + 3, panel_width, panel_height, panel_radius)
    shared.set_hex(cr, '00e5ff', 0.15)
    cairo_set_line_width(cr, 8)
    cairo_stroke(cr)

    shared.rounded_rect(cr, x + 1, y + 2, panel_width, panel_height, panel_radius)
    shared.set_hex(cr, '8b5cf6', 0.22)
    cairo_set_line_width(cr, 4)
    cairo_stroke(cr)

    -- The slab catches light along its top edge and sinks toward the bottom,
    -- so the panel reads as a pane standing off the desktop rather than a hole
    -- cut in it.
    shared.rounded_rect(cr, x, y, panel_width, panel_height, panel_radius)
    fill_preserve_gradient(cr, x, y, x, y + panel_height, {
      { 0.00, '0d1a30', 0.63 },
      { 0.06, '050d1c', 0.57 },
      { 0.80, '020617', 0.55 },
      { 1.00, '08111f', 0.60 },
    })
    cairo_set_line_width(cr, 2)
    stroke_gradient(cr, x, y, x, y + panel_height, {
      { 0.00, '00e5ff', 0.75, 0.40 },
      { 0.40, '00e5ff', 0.55 },
      { 1.00, '00e5ff', 0.70, 0.08 },
    })

    -- Inner bevel: the lit lip sits just inside the top edge, the violet rail
    -- fades as it comes around the bottom.
    shared.rounded_rect(cr, x + 8, y + 8, panel_width - 16, panel_height - 16, panel_radius - 6)
    cairo_set_line_width(cr, 1)
    stroke_gradient(cr, x, y + 8, x, y + panel_height - 8, {
      { 0.00, 'c4b5fd', 0.42 },
      { 0.35, '8b5cf6', 0.24 },
      { 1.00, '8b5cf6', 0.10 },
    })

  end

  local function draw_pace_marker(cr, pace, x, bar_y, bar_w)
    if not pace then
      return
    end
    -- Hide while none of the reset window has elapsed (expected <= 0), including
    -- unused sliding resets whose fetch remaining still equals the full duration.
    -- Show as soon as any time has elapsed, even at 0% fill or the left edge.
    -- Do not gate on usedPercent or on pixel/rounded display position.
    if (pace.expected or 0) <= 0 then
      return
    end

    local marker_x = math.floor(x + bar_w * (shared.clamp(pace.expected, 0, 100) / 100) + 0.5)
    local marker_left = marker_x - math.floor(pace_marker_width / 2)
    local is_neutral = pace.state == 'neutral'
    local opacity = is_neutral and pace_marker_opacity_neutral or pace_marker_opacity

    -- Fade the ends so the tick sits on the tube's curve instead of cutting
    -- straight across it; the position itself is unchanged.
    cairo_set_antialias(cr, CAIRO_ANTIALIAS_NONE)
    cairo_rectangle(cr, marker_left, bar_y, pace_marker_width, bar_height)
    fill_gradient(cr, marker_left, bar_y, marker_left, bar_y + bar_height, {
      { 0.00, pace_marker_color, opacity * 0.36 },
      { 0.45, pace_marker_color, opacity },
      { 1.00, pace_marker_color, opacity * 0.36 },
    })
    cairo_set_antialias(cr, CAIRO_ANTIALIAS_DEFAULT)

  end

  -- Left flat on purpose. These are 8px inside an 8px tube, so neither a
  -- gradient across the glyphs nor a contrast pass under them has the room to
  -- read as depth -- both just cost the crispness the label needs at that size.
  local function draw_bar_overlay_label(cr, label, x, bar_y, color)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 8)
    shared.set_hex(cr, color or 'f8fafc', 0.95)
    cairo_move_to(cr, x + 4, bar_y + 7)
    cairo_show_text(cr, label)
  end

  local function draw_usage_bar(cr, window, x, y, accent, accent_secondary, show_pace, refresh_mode, layout)
    if show_pace == nil then
      show_pace = true
    end

    local bw = layout and layout.bar_width or bar_width
    local btg = layout and layout.bar_text_gap or bar_text_gap
    local bcw = layout and layout.bar_countdown_width or bar_countdown_width

    local used = shared.clamp(window.used_percent, 0, 100)
    if refresh_mode then
      used = 0
    end
    local fill_width = bw * (used / 100)
    local countdown_label = format_window_countdown(window)
    if refresh_mode then
      -- The token is no longer fresh, so any cached number is stale: blank the
      -- countdown and prompt a re-auth instead.
      countdown_label = 'refresh'
    end

    local bar_y = y
    -- Half the height makes the outline a capsule, which is the silhouette of a
    -- tube seen side on; every layer below shades that silhouette.
    local radius = bar_height / 2

    -- Contact shadow. Nothing else lifts the tube off the panel background.
    shared.rounded_rect(cr, x + 0.5, bar_y + 2, bw, bar_height, radius)
    shared.set_hex(cr, '000000', 0.38)
    cairo_fill(cr)
    shared.rounded_rect(cr, x, bar_y + 1, bw, bar_height, radius)
    shared.set_hex(cr, '000000', 0.30)
    cairo_fill(cr)

    -- The tube body itself: lit slate along the top rim, near black through the
    -- middle, a faint bounce underneath. This vertical roll is the illusion;
    -- everything after it is refinement.
    shared.rounded_rect(cr, x, bar_y, bw, bar_height, radius)
    fill_gradient(cr, x, bar_y, x, bar_y + bar_height, {
      { 0.00, '32415c', 0.95 },
      { 0.16, '0b1424', 0.96 },
      { 0.55, '01040c', 0.97 },
      { 0.86, '060d1a', 0.96 },
      { 1.00, '1b2942', 0.95 },
    })

    cairo_save(cr)
    shared.rounded_rect(cr, x, bar_y, bw, bar_height, radius)
    cairo_clip(cr)

    -- Empty glass sits in the shadow of its own rim.
    cairo_rectangle(cr, x, bar_y, bw, bar_height * 0.55)
    fill_gradient(cr, x, bar_y, x, bar_y + bar_height * 0.55, {
      { 0.00, '000000', 0.45 },
      { 1.00, '000000', 0.00 },
    })

    if fill_width > 0 then
      -- A sub-bar-height sliver cannot keep the full end radius: the arc
      -- centers of shared.rounded_rect would land outside the shape and render
      -- garbage, so the rounding shrinks with the width.
      local active_width = fill_width
      local fill_radius = math.min(radius, active_width / 2)

      shared.rounded_rect(cr, x, bar_y, active_width, bar_height, fill_radius)
      fill_gradient(cr, x, bar_y, x, bar_y + bar_height, {
        { 0.00, accent, 1, -0.38 },
        { 0.18, accent, 1, 0.46 },
        { 0.34, accent, 1, 0.10 },
        { 0.52, accent, 1 },
        { 0.84, accent, 1, -0.52 },
        { 0.94, accent, 1, -0.56 },
        { 1.00, accent, 1, -0.18 },
      })

      -- Meniscus: a bright leading edge plus the shadow the liquid throws down
      -- the empty tube. Skipped once the fill reaches either end, where there is
      -- no edge left to catch light.
      if fill_width > bar_height and fill_width < bw - 1 then
        cairo_set_line_width(cr, 1)
        cairo_move_to(cr, x + active_width - 1, bar_y)
        cairo_line_to(cr, x + active_width - 1, bar_y + bar_height)
        stroke_gradient(cr, x, bar_y, x, bar_y + bar_height, {
          { 0.00, accent, 0.00, 0.70 },
          { 0.35, accent, 0.90, 0.85 },
          { 1.00, accent, 0.10, 0.40 },
        })

        cairo_rectangle(cr, x + active_width, bar_y, 5, bar_height)
        fill_gradient(cr, x + active_width, bar_y, x + active_width + 5, bar_y, {
          { 0.00, '000000', 0.50 },
          { 1.00, '000000', 0.00 },
        })
      end
    end

    -- Quarter dividers, faded top and bottom so they look painted onto the
    -- curve rather than cut through a flat face.
    cairo_set_line_width(cr, 1)
    local tick_gap = bw / 4
    for tick = 1, 3 do
      local tick_x = x + tick * tick_gap
      cairo_move_to(cr, tick_x, bar_y)
      cairo_line_to(cr, tick_x, bar_y + bar_height)
      stroke_gradient(cr, x, bar_y, x, bar_y + bar_height, {
        { 0.00, accent_secondary, 0.04 },
        { 0.45, accent_secondary, 0.30 },
        { 1.00, accent_secondary, 0.04 },
      })
    end

    -- One reflection running the length of the glass, tapered at both ends.
    local streak_height = math.max(1.2, bar_height * 0.17)
    shared.rounded_rect(cr, x + radius * 0.8, bar_y + bar_height * 0.13,
      bw - radius * 1.6, streak_height, streak_height / 2)
    fill_gradient(cr, x, bar_y, x + bw, bar_y, {
      { 0.00, 'ffffff', 0.00 },
      { 0.09, 'ffffff', 0.13 },
      { 0.55, 'ffffff', 0.08 },
      { 0.92, 'ffffff', 0.03 },
      { 1.00, 'ffffff', 0.00 },
    })

    -- The ends of a cylinder curve away from the light.
    shared.rounded_rect(cr, x, bar_y, bw, bar_height, radius)
    fill_gradient(cr, x, bar_y, x + bw, bar_y, {
      { 0.00, '000000', 0.34 },
      { 0.05, '000000', 0.00 },
      { 0.95, '000000', 0.00 },
      { 1.00, '000000', 0.30 },
    })

    if show_pace and not refresh_mode then
      draw_pace_marker(cr, calculate_window_pace(window, window_duration(window)), x, bar_y, bw)
    end

    cairo_restore(cr)

    -- Rim: bright along the top, dim at the equator, half bright underneath.
    shared.rounded_rect(cr, x, bar_y, bw, bar_height, radius)
    cairo_set_line_width(cr, 1)
    stroke_gradient(cr, x, bar_y, x, bar_y + bar_height, {
      { 0.00, accent, 0.62, 0.45 },
      { 0.45, accent, 0.20 },
      { 1.00, accent, 0.45, 0.20 },
    })

    local text_x = x + bw + btg
    local font_size = 10

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, font_size)
    countdown_label = shared.truncate_title(cr, countdown_label, bcw)

    draw_lit_text(cr, countdown_label, text_x, y + 8, font_size, accent, {
      alpha = 0.95,
      shadow = 0.55,
      relief = 'lifted',
    })
  end

  local function draw_panel_error(cr, usage, x, y)
    draw_lit_text(cr, 'AI QUOTA SIGNAL LOST', x + 34, y + 58, 15, 'f87171')

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, 12)
    local detail = shared.truncate_title(cr, usage and usage.error or 'No usage cache found.', panel_width - 68)
    draw_lit_text(cr, detail, x + 34, y + 82, 12, 'f8fafc', {
      alpha = 0.88,
      weight = CAIRO_FONT_WEIGHT_NORMAL,
    })
  end

  local function provider_name(account)
    return string.lower(account.provider or 'codex')
  end

  local function window_reset_has_passed(window)
    -- Only absolute reset timestamps can prove a cached window is over.
    if window.reset_at_epoch and window.reset_at_epoch > 0 then
      return window.reset_at_epoch <= os.time()
    end
    return false
  end

  local function window_needs_refresh(account, window)
    -- Placeholder bars stand in for an account with no cached sample at all.
    if window.needs_refresh then
      return true
    end

    -- Every expired/stale account: keep cached fill and reset until that
    -- window's reset time has already passed.
    return account.stale and window_reset_has_passed(window)
  end

  local function provider_accents(account, is_free)
    if provider_name(account) == 'cursor' then
      if is_free then
        -- Free rows sit two shades further down the bronze ramp than paid ones.
        -- The second bar already starts deep, so reusing the paid pair for it
        -- would leave it undimmed next to a dimmed first bar.
        return '574a29', '433720', '352b17', '272011'
      end
      return '938354', '756642', '574a29', '433720'
    end

    if provider_name(account) == 'gemini' then
      -- Bright spring green Gemini, pine Other.
      return '4ade80', '86efac', '318f6a', '1f6b52'
    end

    if provider_name(account) == 'grok' then
      -- Graphite black 5h, lighter charcoal weekly, deep black monthly.
      return '52525b', '71717a', '3f3f46', '27272a'
    end

    if provider_name(account) == 'opencode' then
      -- Soft rose-crimson 5h, lighter rose weekly, deeper rose monthly.
      return 'f43f5e', 'fb7185', 'be123c', '881337', 'e11d48', 'be123c'
    end

    if provider_name(account) == 'commandcode' then
      -- Indigo 5h, brighter periwinkle weekly, deep indigo monthly.
      return '6e52d6', '9d88e8', '2e1b9c', '8a74e0', '241575', '3a28a8'
    end

    if is_free then
      if provider_name(account) == 'codex' then
        return '2563eb', '1e3a8a', '2563eb', '1e3a8a'
      end
      return '94a3b8', '64748b', '94a3b8', '64748b'
    end

    if provider_name(account) == 'claude' then
      -- Light coral/gold 5h, deeper coral weekly.
      return 'ff8f73', 'fcd34d', 'c85f49', '81392e'
    end

    -- Bright cyan 5h, rich navy weekly, teal reserve.
    return '00e5ff', '8b5cf6', '2563eb', '1e3a8a', '22d3ee', '0e7490'
  end

  -- Match the left row inset so panel content has equal side padding.
  local bar_area_side_margin = account_row_x

  local function make_bar_layout(num_bars)
    local available = panel_width - account_row_x - panel_first_bar_x - bar_area_side_margin
    local btx = num_bars == 3 and 6 or 8
    local bcw = 54
    local text_total = btx + bcw
    local min_bw = num_bars == 1 and 40 or (num_bars == 3 and 40 or 30)
    local unit = available / num_bars
    local bw = math.max(min_bw, math.floor(unit - text_total))
    -- Fold floor remainder into the bar so unused width does not collect on the right.
    local used = num_bars * (bw + text_total)
    local leftover = available - used
    if leftover > 0 then
      bw = bw + math.floor(leftover / num_bars)
    end

    return {
      bar_width = bw,
      bar_text_gap = btx,
      bar_countdown_width = bcw,
      text_total = text_total,
      num_bars = num_bars,
    }
  end

  local function draw_account_error(cr, account, x, y)
    local detail = account.error and account.error ~= '' and account.error or 'quota data unavailable'
    local label = 'ERROR: ' .. detail .. ' / RETRYING'
    local error_area_width = panel_width - account_row_x - panel_first_bar_x - bar_area_side_margin
    local max_label_width = math.max(80, error_area_width - 24)

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 9)
    label = shared.truncate_title(cr, string.upper(label), max_label_width)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)

    local badge_x = x + panel_first_bar_x
    local badge_y = y + 9
    local badge_height = 14
    local badge_width = math.min(error_area_width, math.max(160, extents.width + 20))

    shared.rounded_rect(cr, badge_x + 0.5, badge_y + 2, badge_width, badge_height, 4)
    shared.set_hex(cr, '000000', 0.34)
    cairo_fill(cr)

    shared.rounded_rect(cr, badge_x, badge_y + 1, badge_width, badge_height, 4)
    shared.set_hex(cr, '000000', 0.28)
    cairo_fill(cr)

    shared.rounded_rect(cr, badge_x, badge_y, badge_width, badge_height, 4)
    fill_gradient(cr, badge_x, badge_y, badge_x, badge_y + badge_height, {
      { 0.00, '7f1d1d', 0.99 },
      { 0.48, '4c1018', 0.99 },
      { 1.00, '25070d', 0.99 },
    })

    shared.rounded_rect(cr, badge_x, badge_y, badge_width, badge_height, 4)
    shared.set_hex(cr, 'fb7185', 0.96)
    cairo_set_line_width(cr, 1.2)
    cairo_stroke(cr)

    draw_lit_text(cr, label, badge_x + 10, badge_y + 10, 9, 'fca5a5', {
      alpha = 0.98,
      shadow = 0.55,
      relief = 'soft',
    })
  end

  local function get_row_windows(account)
    local provider = provider_name(account)
    local windows = account.windows or {}

    if provider == 'grok' then
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'monthly' then return { w } end
      end
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'weekly' then return { w } end
      end
      if windows[1] then return { windows[1] } end
      return {}
    end

    if provider == 'opencode' or provider == 'commandcode' or provider == 'codex' then
      local result = {}
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == '5h' then table.insert(result, w) end
      end
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'weekly' then table.insert(result, w) end
      end
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'monthly' then table.insert(result, w) end
      end
      for _, w in ipairs(windows) do
        if normalized_window_label(w) == 'reserve' then table.insert(result, w) end
      end
      return result
    end

    local first, second
    for _, window in ipairs(windows) do
      local window_label = normalized_window_label(window)
      if provider == 'cursor' and window_label == 'api' then
        second = window
      elseif provider == 'cursor' and window_label == 'auto' then
        first = window
      elseif provider == 'gemini' and window_label == 'other' then
        second = window
      elseif provider == 'gemini' and window_label == 'gemini' then
        first = window
      elseif window_label == 'weekly' then
        second = window
      elseif not first then
        first = window
      end
    end

    local result = {}
    if first then table.insert(result, first) end
    if second then table.insert(result, second) end
    return result
  end

  local function draw_account_row(cr, account, x, y, pace_includes_free)
    local name = string.upper(account.label)
    local label_x = x + 22
    local is_free = is_free_account(account)
    local first_accent, first_accent_secondary, second_accent, second_accent_secondary, third_accent, third_accent_secondary = provider_accents(account, is_free)
    local is_active = account.is_selected

    local row_windows = get_row_windows(account)

    -- A Claude account with no windows at all (no cached sample, or unreadable
    -- credentials) would drop off the panel entirely. Keep the row with an empty
    -- 5h bar labeled "refresh" to prompt a re-auth.
    local claude_has_no_data = provider_name(account) == 'claude' and (account.stale or not account.ok)
    if claude_has_no_data and #row_windows == 0 then
      row_windows = {
        {
          used_percent = 0,
          label = '5h',
          reset_at_epoch = 0,
          reset_after_seconds = 0,
          window_seconds = five_hour_window_seconds,
          needs_refresh = true,
        }
      }
    end

    if account.is_selected then
      local selection_color = provider_name(account) == 'codex' and '00e5ff'
        or provider_name(account) == 'cursor' and '938354'
        or provider_name(account) == 'grok' and '71717a'
        or provider_name(account) == 'opencode' and 'ef4444'
        or provider_name(account) == 'commandcode' and '5543c9'
        or first_accent

      shared.set_hex(cr, selection_color, 0.20)
      cairo_set_line_width(cr, 5)
      cairo_move_to(cr, label_x - 20, y + 11)
      cairo_line_to(cr, label_x - 12, y + 18)
      cairo_line_to(cr, label_x - 20, y + 25)
      cairo_stroke(cr)

      -- The chevron drops onto the panel before it lights up, and its stroke
      -- catches the same overhead light as the bars and chips.
      shared.set_hex(cr, '000000', 0.45)
      cairo_set_line_width(cr, 2)
      cairo_move_to(cr, label_x - 19, y + 12)
      cairo_line_to(cr, label_x - 11, y + 19)
      cairo_line_to(cr, label_x - 19, y + 26)
      cairo_stroke(cr)

      cairo_set_line_width(cr, 2)
      cairo_move_to(cr, label_x - 20, y + 11)
      cairo_line_to(cr, label_x - 12, y + 18)
      cairo_line_to(cr, label_x - 20, y + 25)
      stroke_gradient(cr, label_x, y + 11, label_x, y + 25, {
        { 0.00, selection_color, 1.00, 0.45 },
        { 0.45, selection_color, 0.94 },
        { 1.00, selection_color, 0.85, 0.05 },
      })
    end

    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 14)
    local row_label = shared.truncate_title(cr, name, 120)
    draw_lit_text(cr, row_label, label_x, y + 23, 14, is_active and 'ffffff' or 'f8fafc', {
      alpha = is_active and 1 or 0.72,
      relief = 'raised',
      shadow = 0.62,
    })

    local num_bars = #row_windows
    if num_bars == 0 then
      draw_account_error(cr, account, x, y)
      return
    end

    local show_bar_pace = not is_free or pace_includes_free == true
    local bar_y = y + 15
    local layout = make_bar_layout(num_bars)
    local bar_unit_width = layout.bar_width + layout.text_total
    local bar_area_start = x + panel_first_bar_x

    local accent_list = { first_accent, second_accent, third_accent or second_accent }
    local accent_secondary_list = { first_accent_secondary, second_accent_secondary, third_accent_secondary or second_accent_secondary }
    local overlay_labels = {}
    if provider_name(account) == 'cursor' then
      if is_free then
        overlay_labels = { 'AUTO (Free)', 'API (Free)' }
      else
        overlay_labels = { 'AUTO', 'API' }
      end
    elseif provider_name(account) == 'gemini' then
      overlay_labels = { 'Gemini', 'Other' }
    elseif provider_name(account) == 'codex' then
      for i, window in ipairs(row_windows) do
        if normalized_window_label(window) == 'reserve' then
          overlay_labels[i] = 'RESERVE'
        end
      end
    end

    for i, window in ipairs(row_windows) do
      local bar_x = bar_area_start + (i - 1) * bar_unit_width
      local accent = accent_list[i] or second_accent
      local accent_secondary = accent_secondary_list[i] or second_accent_secondary
      local refresh = window_needs_refresh(account, window)
      draw_usage_bar(cr, window, bar_x, bar_y, accent, accent_secondary, show_bar_pace, refresh, layout)

      if overlay_labels[i] then
        draw_bar_overlay_label(cr, overlay_labels[i], bar_x, bar_y, i == 1 and '000000' or nil)
      end
    end
  end

  -- Chips are lit the same way as the bars: a shadow underneath, a face that
  -- runs from a lit top edge down to a dark base, a reflection across the top
  -- half, and a rim that is brightest where the light lands.
  local function draw_chip(cr, label, color, x, y, chip_width)
    local chip_height = 20
    local radius = 6

    shared.rounded_rect(cr, x + 0.5, y + 2, chip_width, chip_height, radius)
    shared.set_hex(cr, '000000', 0.34)
    cairo_fill(cr)
    shared.rounded_rect(cr, x, y + 1, chip_width, chip_height, radius)
    shared.set_hex(cr, '000000', 0.28)
    cairo_fill(cr)

    -- The face is tinted with the chip's own color so each provider keeps its
    -- hue even in shadow.
    shared.rounded_rect(cr, x, y, chip_width, chip_height, radius)
    fill_gradient(cr, x, y, x, y + chip_height, {
      { 0.00, color, 0.94, -0.58 },
      { 0.20, color, 0.95, -0.86 },
      { 0.66, '020617', 0.95 },
      { 1.00, color, 0.94, -0.76 },
    })

    cairo_save(cr)
    shared.rounded_rect(cr, x, y, chip_width, chip_height, radius)
    cairo_clip(cr)
    shared.rounded_rect(cr, x + 3, y + 2, chip_width - 6, chip_height * 0.42, 4)
    fill_gradient(cr, x, y, x + chip_width, y, {
      { 0.00, 'ffffff', 0.00 },
      { 0.12, 'ffffff', 0.11 },
      { 0.62, 'ffffff', 0.05 },
      { 1.00, 'ffffff', 0.00 },
    })
    cairo_restore(cr)

    shared.rounded_rect(cr, x, y, chip_width, chip_height, radius)
    cairo_set_line_width(cr, 1.5)
    stroke_gradient(cr, x, y, x, y + chip_height, {
      { 0.00, color, 0.95, 0.45 },
      { 0.50, color, 0.74 },
      { 1.00, color, 0.88, 0.12 },
    })

    -- The label sits on the face, so it drops its own shadow onto it.
    draw_lit_text(cr, label, x + 12, y + 15, 15, color, { shadow = 0.55 })
  end

  local function title_chip_width(cr, label)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 15)

    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    return extents.width + 24
  end

  local function draw_title_chip(cr, label, color, x, y)
    local chip_width = title_chip_width(cr, label)
    draw_chip(cr, label, color, x, y - 9, chip_width)
    return chip_width
  end

  local function draw_title_chips(cr, chips, x, y)
    local widths = {}
    local total_width = 0

    for i, chip in ipairs(chips) do
      widths[i] = title_chip_width(cr, chip.label)
      total_width = total_width + widths[i]
      if i > 1 then
        total_width = total_width + title_chip_gap
      end
    end

    local chip_x = x + (panel_width - total_width) / 2
    for i, chip in ipairs(chips) do
      draw_title_chip(cr, chip.label, chip.color, chip_x, y)
      chip_x = chip_x + widths[i] + title_chip_gap
    end
  end

  local function draw_rate_limit_panel(cr, usage, x, y)
    draw_panel_frame(cr, x, y)

    local codex_label = 'CODEX'
    local claude_label = 'CLAUDE'
    local cursor_label = 'CURSOR'
    local gemini_label = 'ANTIGRAVITY'
    local grok_label = 'GROK'
    local opencode_label = 'OPENCODE'
    local commandcode_label = 'CMD'

    local codex_color = '00e5ff'
    local claude_color = 'ff7a59'
    local cursor_color = '938354'
    local gemini_color = '4ade80'
    local grok_color = '71717a'
    local opencode_color = 'ef4444'
    local commandcode_color = '5543c9'

    if usage.ok and #usage.accounts > 0 then
      local codex_avg_delta = calculate_provider_average_pace(usage.accounts, 'Codex')
      local claude_avg_delta = calculate_provider_average_pace(usage.accounts, 'Claude')
      local cursor_avg_delta = calculate_provider_average_pace(usage.accounts, 'Cursor')
      local gemini_avg_delta = calculate_provider_average_pace(usage.accounts, 'Gemini')
      local grok_avg_delta = calculate_provider_average_pace(usage.accounts, 'Grok')
      local opencode_avg_delta = calculate_provider_average_pace(usage.accounts, 'OpenCode')
      local commandcode_avg_delta = calculate_provider_average_pace(usage.accounts, 'CommandCode')

      codex_label = get_provider_label_from_delta('Codex', codex_avg_delta)
      claude_label = get_provider_label_from_delta('Claude', claude_avg_delta)
      cursor_label = get_provider_label_from_delta('Cursor', cursor_avg_delta)
      gemini_label = get_provider_label_from_delta('Antigravity', gemini_avg_delta)
      grok_label = get_provider_label_from_delta('Grok', grok_avg_delta)
      opencode_label = get_provider_label_from_delta('OpenCode', opencode_avg_delta)
      commandcode_label = get_provider_label_from_delta('CMD', commandcode_avg_delta)
    end

    draw_title_chips(cr, {
      { label = codex_label, color = codex_color },
      { label = claude_label, color = claude_color },
      { label = cursor_label, color = cursor_color },
      { label = gemini_label, color = gemini_color },
      { label = grok_label, color = grok_color },
      { label = opencode_label, color = opencode_color },
      { label = commandcode_label, color = commandcode_color },
    }, x, y)

    if not usage.ok or #usage.accounts == 0 then
      draw_panel_error(cr, usage, x, y)
      return
    end

    for index, account in ipairs(usage.accounts) do
      draw_account_row(
        cr,
        account,
        x + account_row_x,
        y + account_row_y + (index - 1) * account_row_gap,
        provider_is_free_only(usage.accounts, account.provider)
      )
    end
  end

  local function account_count_from_usage(usage)
    if usage and usage.accounts then
      return math.max(1, #usage.accounts)
    end
    return 1
  end

  local function panel_height_for(account_count)
    local count = math.max(1, tonumber(account_count) or 1)
    if not panel_auto_height then
      return panel_height
    end
    return math.max(panel_height, panel_dynamic_height_padding + count * account_row_gap)
  end

  local function window_height_for(account_count)
    return math.max(
      panel_window_floor,
      panel_top_inset + panel_height_for(account_count) + panel_bottom_inset
    )
  end

  local function needed_height()
    return window_height_for(account_count_from_usage(read_ai_usage()))
  end

  -- Expand the Conky window to fit the current account list. Returned text is
  -- re-parsed via ${lua_parse} so the voffset becomes real vertical space.
  local function height_spacer()
    return string.format('${voffset %d}', needed_height())
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local usage = read_ai_usage()

    if not usage then
      usage = {
        ok = false,
        error = 'No AI usage cache found.',
        accounts = {},
      }
    end

    local dynamic_height = panel_height_for(account_count_from_usage(usage))
    local render_width = math.min(panel_width, conky_window.width - 40)
    local x = (conky_window.width - render_width) / 2
    local y = math.max(
      panel_top_inset,
      conky_window.height - dynamic_height - panel_bottom_inset
    )
    local previous_width = panel_width
    local previous_height = panel_height

    panel_width = render_width
    panel_height = dynamic_height
    draw_rate_limit_panel(cr, usage, x, y)
    panel_width = previous_width
    panel_height = previous_height

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
