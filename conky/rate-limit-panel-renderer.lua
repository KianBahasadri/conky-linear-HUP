return function(shared, repo_root)
  local ui = shared.ui
  local five_hour_window_seconds, weekly_window_seconds, pace_threshold = 18000, 604800, 10
  local codex_usage_path = repo_root .. '/cache/codex-usage.json'
  local codex_usage_tsv_path = repo_root .. '/cache/codex-usage-render.tsv'
  local claude_usage_tsv_path = repo_root .. '/cache/claude-usage-render.tsv'
  local cursor_usage_tsv_path = repo_root .. '/cache/cursor-usage-render.tsv'
  local gemini_usage_tsv_path = repo_root .. '/cache/gemini-usage-render.tsv'
  local grok_usage_tsv_path = repo_root .. '/cache/grok-usage-render.tsv'
  local opencode_usage_tsv_path = repo_root .. '/cache/opencode-usage-render.tsv'
  local commandcode_usage_tsv_path = repo_root .. '/cache/commandcode-usage-render.tsv'
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

    local ok = shared.json_boolean(content, 'ok', false)
    local error_message = shared.json_string(content, 'error', '')
    local accounts = {}
    local account_index = {}

    local function parse_window(object, label_key)
      local label = shared.json_string(object, label_key, nil)
      if not label then
        return nil
      end
      local used_percent = shared.json_number(object, 'usedPercent', 0)
      local reset_at_epoch = shared.json_number(object, 'resetAtEpoch', 0)
      local reset_after_seconds = shared.json_number(object, 'resetAfterSeconds', 0)
      return {
        label = normalized_window_label({
          label = label,
          reset_at_epoch = reset_at_epoch,
          reset_after_seconds = reset_after_seconds,
        }),
        used_percent = used_percent,
        remaining_percent = shared.json_number(
          object,
          'remainingPercent',
          math.max(0, 100 - used_percent)
        ),
        resets_at = shared.json_string(object, 'resetsAt', ''),
        reset_at_epoch = reset_at_epoch,
        reset_after_seconds = reset_after_seconds,
        window_seconds = shared.json_number(object, 'windowSeconds', 0),
      }
    end

    -- Current cache shape: account records own nested window arrays.  Keeping
    -- account-level stale/error state makes the JSON fallback behave the same
    -- as the render TSV when that derived cache has not been written yet.
    for _, object in ipairs(shared.json_array_objects(content, 'accounts')) do
      local label = shared.json_string(object, 'label', nil)
      if label then
        local account = {
          label = label,
          provider = 'Codex',
          plan_type = shared.json_string(object, 'planType', ''),
          is_selected = shared.json_boolean(object, 'isSelected', false),
          ok = shared.json_boolean(object, 'ok', false),
          error = shared.json_string(object, 'error', ''),
          stale = shared.json_boolean(object, 'stale', false),
          windows = {},
        }
        for _, window_object in ipairs(shared.json_array_objects(object, 'windows')) do
          local window = parse_window(window_object, 'label')
          if window then
            table.insert(account.windows, window)
          end
        end
        account_index[label] = account
        table.insert(accounts, account)
      end
    end

    -- Compatibility with the older flattened `bars` cache shape.
    if #accounts == 0 then
      for _, object in ipairs(shared.json_array_objects(content, 'bars')) do
        local label = shared.json_string(object, 'account', nil)
        local window = parse_window(object, 'window')
        if label and window then
          if not account_index[label] then
            account_index[label] = {
              label = label,
              provider = 'Codex',
              plan_type = shared.json_string(object, 'planType', ''),
              is_selected = shared.json_boolean(object, 'isSelected', false),
              ok = shared.json_boolean(object, 'ok', true),
              error = shared.json_string(object, 'error', ''),
              stale = shared.json_boolean(object, 'stale', false),
              windows = {},
            }
            table.insert(accounts, account_index[label])
          elseif shared.json_boolean(object, 'isSelected', false) then
            account_index[label].is_selected = true
          end
          table.insert(account_index[label].windows, window)
        end
      end
    end

    return {
      ok = ok,
      error = error_message,
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
        local left_label = string.lower(left.label or '')
        local right_label = string.lower(right.label or '')
        if left_label ~= right_label then
          return left_label < right_label
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
            -- expose the 5h bar, so keep it as the fallback. Pro accounts carry
            -- 20x the capacity weight of a standard Plus account in the chip average.
            local window = find_weekly_window(account) or find_five_hour_window(account)
            if window then
              local pace = calculate_window_pace(window, window_duration(window))
              if pace then
                local weight = string.lower(account.plan_type or '') == 'pro' and 20 or 1
                delta_total = delta_total + pace.delta * weight
                delta_count = delta_count + weight
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

    if provider == 'gemini' then
      local is_free = is_free_account(account)
      local result = {}
      local seen = {}
      local order = is_free
        and { 'gemini-weekly', 'gemini', 'other-weekly', 'other', '3p-weekly' }
        or { 'gemini-5h', 'gemini-weekly', 'other-5h', '3p-5h', 'other-weekly', '3p-weekly', 'gemini', 'other' }
      for _, target in ipairs(order) do
        for _, w in ipairs(windows) do
          if normalized_window_label(w) == target and not seen[w] then
            table.insert(result, w)
            seen[w] = true
          end
        end
      end
      for _, w in ipairs(windows) do
        if not seen[w] then
          table.insert(result, w)
          seen[w] = true
        end
      end
      if is_free and #result > 2 then
        return { result[1], result[2] }
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

  local provider_labels = {Codex='Codex', Claude='Claude', Cursor='Cursor',
    Gemini='Antigravity', Grok='Grok', OpenCode='OpenCode', CommandCode='Cmd'}
  local window_labels = {weekly='7d', monthly='Month', reserve='Reserve', auto='Auto', api='API',
    ['gemini-5h']='Gem 5h', ['gemini-weekly']='Gem 7d', ['other-5h']='Other 5h',
    ['other-weekly']='Other 7d', ['3p-weekly']='Other 7d', ['3p-5h']='Other 5h'}

  local function row_height(width) return width < 760 and 76 or width < 880 and 40 or 18 end

  -- One quota window: label and countdown on the sides of a flat observed bar
  -- with a derived-color tick at the expected on-pace position.
  local function draw_window(cr, account, window, x, y, width, show_pace, tall)
    local refresh = window_needs_refresh(account, window)
    local used = shared.clamp(window.used_percent or 0, 0, 100)
    local name = window_labels[window.label] or window.label
    local count = refresh and 'Refresh' or format_window_countdown(window)
    if used >= 100 and not refresh then name = name .. ' full' end
    local color = refresh and ui.caution or used >= 100 and ui.danger or ui.accent

    local nw = ui.width(cr, name, 11, true)
    local cw = ui.width(cr, count, 11, true)
    local gap = 6
    local bx = x + nw + gap
    local bx2 = x + width - cw - gap
    local bw = math.max(10, bx2 - bx)

    ui.text(cr, name, x, y + 13, {size = 11, mono = true, color = used >= 100 and ui.danger or ui.muted})
    ui.text(cr, count, x + width, y + 13,
      {size = 11, mono = true, align = 'right', color = refresh and ui.caution or ui.muted})

    local by = y + 9
    ui.rect(cr, bx, by, bw, 3, ui.line, 0)
    if not refresh then ui.rect(cr, bx, by, bw * used / 100, 3, color, 0) end
    if show_pace and not refresh then
      local pace = calculate_window_pace(window, window_duration(window))
      if pace and pace.expected > 0 then
        local px = bx + bw * pace.expected / 100
        ui.line_between(cr, px, by - 2, px, by + 5, ui.derived, 1)
      end
    end
  end

  local function draw()
    ui.draw(function(cr, width, height)
      local usage = read_ai_usage() or {ok=false, accounts={}, error='Waiting for usage data'}
      local accounts = usage.accounts or {}
      if #accounts == 0 then
        ui.callout(cr, 'Unavailable', usage.error or 'Waiting for usage data', 0, 0, width, 'danger')
        return
      end
      local rh = row_height(width)
      local first, last, page = ui.rows(#accounts, height, rh, 0)
      local provider_width, name_width = width < 880 and 96 or 112, width < 880 and 48 or 56
      for index = first, last do
        local account = accounts[index]
        local y = (index - first) * rh
        if account.is_selected then ui.rect(cr, 0, y, width, rh, ui.raised, 4) end
        if index == first or accounts[index - 1].provider ~= account.provider then
          -- The provider's average pace delta is a derived value; it sits beside
          -- the group label rather than in a separate summary row.
          local delta = calculate_provider_average_pace(accounts, account.provider)
          local delta_width = ui.text(cr, delta and string.format('%+.0f%%', delta) or '—',
            provider_width - 6, y + 13, {size = 11, mono = true, color = ui.derived, align = 'right'})
          ui.text(cr, provider_labels[account.provider] or account.provider, 6, y + 13,
            {size = 13.5, color = ui.muted, width = provider_width - delta_width - 12})
        end
        ui.text(cr, account.label, provider_width, y + 13,
          {size = 13.5, bold = account.is_selected and 'medium' or nil,
            color = account.is_selected and ui.strong or ui.ink, width = name_width - 4})
        local x = provider_width + name_width
        local wins = get_row_windows(account)
        if #wins == 0 then
          ui.text(cr, 'Retrying: ' .. (account.error ~= '' and account.error or 'No usable windows'),
            x, y + 13, {size = 12, color = ui.danger, width = width - x - 8})
        else
          local window_columns = width < 760 and math.min(2, #wins) or #wins
          local ww = (width - x) / window_columns
          local show_pace = not is_free_account(account) or provider_is_free_only(accounts, account.provider)
          for i, window in ipairs(wins) do
            draw_window(cr, account, window, x + ((i - 1) % window_columns) * ww,
              y + math.floor((i - 1) / window_columns) * 36, ww - 16, show_pace, rh > 24)
          end
        end
      end
      ui.footer(cr, page, width, height)
    end)
  end

  local function height_spacer()
    local usage = read_ai_usage()
    local count = usage and #usage.accounts or 0
    return string.format('${voffset %d}', math.max(112, 16 + math.max(1, count) * 24))
  end

  return {draw = draw, height_spacer = height_spacer,
    _test = {read_ai_usage = read_ai_usage, sort_accounts = sort_accounts}}
end
