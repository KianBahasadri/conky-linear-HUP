-- Characterization harness for the quota panel's self-sizing cache adapters.
local root = arg[1]
local cache_root = arg[2]

local shared = dofile(root .. '/conky/renderer-shared.lua')
local factory = dofile(root .. '/conky/rate-limit-panel-renderer.lua')

local failures = 0

local function eq(actual, expected, label)
  if actual ~= expected then
    print('FAIL ' .. label .. ': expected ' .. string.format('%q', tostring(expected))
      .. ', got ' .. string.format('%q', tostring(actual)))
    failures = failures + 1
  end
end

os.execute('mkdir -p "' .. cache_root .. '/cache"')
for _, name in ipairs({
  'codex', 'claude', 'cursor', 'gemini', 'grok', 'opencode', 'commandcode',
}) do
  os.remove(cache_root .. '/cache/' .. name .. '-usage-render.tsv')
end

local json_path = cache_root .. '/cache/codex-usage.json'
local function write_json(content)
  local file = io.open(json_path, 'w')
  if not file then
    print('FAIL could not write ' .. json_path)
    os.exit(1)
  end
  file:write(content)
  file:close()
end

local function spacer_for(content)
  write_json(content)
  return factory(shared, cache_root).height_spacer()
end

os.remove(json_path)
eq(factory(shared, cache_root).height_spacer(), '${voffset 112}',
  'missing caches use the window floor')

local accounts = {}
for index = 1, 20 do
  table.insert(accounts, string.format([[
    {"ok":true,"label":"acct-%d","planType":"plus","isSelected":false,
     "note":"brace } and bracket ] stay text","windows":[
       {"label":"weekly","usedPercent":0,"remainingPercent":100,
        "resetAtEpoch":0,"resetAfterSeconds":0,"windowSeconds":604800}
     ]}]], index))
end

local current_shape = '{"ok":true,"error":"","accounts":['
  .. table.concat(accounts, ',') .. ']}'
eq(spacer_for(current_shape), '${voffset 496}',
  'current nested Codex JSON fallback sizes all accounts')

local bars = {}
for index = 1, 20 do
  table.insert(bars, string.format(
    '{"account":"acct-%d","planType":"plus","window":"weekly","usedPercent":0,"remainingPercent":100}',
    index
  ))
end
eq(spacer_for('{"ok":true,"bars":[' .. table.concat(bars, ',') .. ']}'),
  '${voffset 496}', 'legacy flattened Codex JSON fallback remains supported')

eq(spacer_for('{"ok":true,"accounts":[{"label":"unterminated}]}'),
  '${voffset 112}', 'malformed JSON cache degrades to the window floor')

local test_accounts = {
  { provider = 'Cursor', label = 'sepehr', plan_type = 'pro' },
  { provider = 'Cursor', label = 'kian', plan_type = 'free' },
  { provider = 'Cursor', label = '21kb60', plan_type = 'pro' },
  { provider = 'Codex', label = 'sepehr', plan_type = 'plus' },
  { provider = 'Codex', label = 'bashir', plan_type = 'free' },
  { provider = 'Codex', label = 'kian', plan_type = 'pro' },
  { provider = 'Codex', label = 'ahmad', plan_type = 'plus' },
  { provider = 'Gemini', label = 'kian', plan_type = 'pro' },
  { provider = 'Gemini', label = 'baba', plan_type = 'free' },
}
local renderer = factory(shared, cache_root)
renderer._test.sort_accounts(test_accounts)
local ordered = {}
for _, acct in ipairs(test_accounts) do
  table.insert(ordered, acct.provider .. ':' .. acct.label)
end
eq(table.concat(ordered, ','),
  'Codex:ahmad,Codex:bashir,Codex:kian,Codex:sepehr,Cursor:21kb60,Cursor:kian,Cursor:sepehr,Gemini:baba,Gemini:kian',
  'accounts within each provider are sorted alphabetically without separating free accounts')

local has_filled = renderer._test.account_has_filled_bar
local normal_acct = { stale = false }
local partial_wins = { { used_percent = 50.0 }, { used_percent = 0.0 } }
local full_wins = { { used_percent = 50.0 }, { used_percent = 100.0 } }
local over_wins = { { used_percent = 105.0 } }
local refresh_wins = { { used_percent = 100.0, needs_refresh = true } }

eq(has_filled(normal_acct, partial_wins), false, 'partial bars do not trigger filled status')
eq(has_filled(normal_acct, full_wins), true, '100% bar triggers filled status')
eq(has_filled(normal_acct, over_wins), true, 'over 100% bar triggers filled status')
eq(has_filled(normal_acct, refresh_wins), false, 'refresh-needed bar does not trigger filled status')

local gemini_wins = {
  {label = 'gemini-5h'}, {label = 'gemini-weekly'},
  {label = 'other-5h'}, {label = 'other-weekly'},
}
local columns = renderer._test.gemini_duration_columns(gemini_wins)
eq(columns ~= nil, true, 'pro Gemini windows split into duration columns')
eq(columns[1][1].label, 'gemini-5h', '5h column starts with Gem')
eq(columns[1][2].label, 'other-5h', '5h column stacks Other under Gem')
eq(columns[2][1].label, 'gemini-weekly', 'weekly column starts with Gem')
eq(columns[2][2].label, 'other-weekly', 'weekly column stacks Other under Gem')
eq(renderer._test.gemini_duration_columns({{label = 'gemini-weekly'}, {label = 'other-weekly'}}) == nil, true,
  'weekly-only Gemini stays a single row')
eq(renderer._test.account_pitch(1040, {provider = 'Gemini'}, gemini_wins), 24,
  'pro Gemini uses a slightly taller row for the compact 2×2 stack')
eq(renderer._test.gemini_duration_columns({{label = 'gemini-5h'}, {label = 'gemini-weekly'}}) == nil, true,
  'unstacked Gemini stays a single row')
eq(renderer._test.gemini_duration_columns({{label = 'gemini-5h'}, {label = 'gemini-weekly'}, {label = 'argon'}}) == nil, true,
  'Gemini Pro with Argon weekly pool stays a single horizontal row')
eq(renderer._test.account_pitch(1040, {provider = 'Gemini'}, {{label = 'gemini-5h'}, {label = 'gemini-weekly'}}), 16,
  'gemini without other stays a single 16px line')
eq(renderer._test.account_pitch(1040, {provider = 'Gemini'}, {{label = 'gemini-5h'}, {label = 'gemini-weekly'}, {label = 'argon'}}), 16,
  'gemini with argon stays a single 16px line')
eq(renderer._test.account_pitch(1040, {provider = 'Gemini'}, {{label = 'gemini-weekly'}}), 16,
  'free Gemini keeps a single line')
eq(renderer._test.account_pitch(1040, {provider = 'Codex'}, gemini_wins), 16,
  'non-Gemini accounts keep a single line')

local mark_test_accounts = {
  { provider = 'Codex', label = 'ahmad', is_selected = false },
  { provider = 'Codex', label = 'bashir', is_selected = false },
  { provider = 'Codex', label = 'kian', is_selected = true },
  { provider = 'Codex', label = 'sepehr', is_selected = false },
  { provider = 'Cursor', label = '21kb60', is_selected = false },
  { provider = 'Cursor', label = 'kian', is_selected = true },
  { provider = 'Gemini', label = 'baba', is_selected = false },
  { provider = 'Gemini', label = 'sepehr', is_selected = false },
}
local marks = renderer._test.provider_mark_indices(mark_test_accounts, 1, 8)
eq(marks[3], true, 'Codex mark lands on highlighted account (kian)')
eq(marks[1], nil, 'Codex first account (ahmad) does not get mark when another is selected')
eq(marks[6], true, 'Cursor mark lands on highlighted account (kian)')
eq(marks[5], nil, 'Cursor first account does not get mark when another is selected')
eq(marks[7], true, 'Gemini mark falls back to first account when none is selected')
eq(marks[8], nil, 'Gemini second account does not get mark when none selected')

local noon = os.time({year = 2026, month = 10, day = 21, hour = 12, min = 0, sec = 0})
local noon_start = renderer._test.day_start_epoch(noon)
local noon_parts = os.date('*t', noon_start)
eq(noon_parts.year, 2026, 'day start keeps the year')
eq(noon_parts.month, 10, 'day start keeps the month')
eq(noon_parts.day, 21, 'afternoon belongs to the same local day')
eq(noon_parts.hour, 5, 'day start is 05:00')
eq(noon_parts.min, 0, 'day start is on the hour')

local early = os.time({year = 2026, month = 10, day = 21, hour = 4, min = 30, sec = 0})
local early_parts = os.date('*t', renderer._test.day_start_epoch(early))
eq(early_parts.day, 20, 'before 05:00 still belongs to the previous local day')
eq(early_parts.hour, 5, 'previous day also starts at 05:00')

local day_start = noon_start
local reset = day_start + 500000
local history = {
  {t = day_start - 60, provider = 'codex', account = 'ahmad', window = 'weekly', reset = reset, used = 16},
  {t = day_start + 60, provider = 'codex', account = 'ahmad', window = 'weekly', reset = reset, used = 31},
  {t = day_start - 10, provider = 'cursor', account = 'ahmad', window = 'weekly', reset = reset, used = 90},
}
local weekly = {
  label = 'weekly', raw_label = 'weekly', used_percent = 31,
  reset_at_epoch = reset, window_seconds = 604800,
}
eq(renderer._test.used_before_today({provider = 'Codex', label = 'ahmad'}, weekly, history, noon), 16,
  'usage already recorded at 05:00 stays the prior portion')
eq(renderer._test.used_before_today(
  {provider = 'Codex', label = 'ahmad'},
  {label = 'weekly', raw_label = 'weekly', used_percent = 10, reset_at_epoch = reset, window_seconds = 604800},
  history, noon), 10,
  'a later drop does not draw prior usage past the current fill')
local opened_today = {
  label = '5h', raw_label = '5h', used_percent = 13,
  reset_at_epoch = noon + 18000, window_seconds = 18000,
}
eq(renderer._test.used_before_today({provider = 'Codex', label = 'sepehr'}, opened_today, history, noon), 0,
  'a window that opened after 05:00 is all current usage')
eq(renderer._test.used_before_today({provider = 'Codex', label = 'ryan'}, weekly, {}, noon), 0,
  'missing history leaves the whole fill in the current color')

local history_path = cache_root .. '/cache/rate-limit-usage-history.tsv'
local history_file = io.open(history_path, 'w')
history_file:write(string.format('%d\tcodex\tahmad\tweekly\t%d\t16.0\n', day_start - 60, reset))
history_file:close()
local loaded = renderer._test.read_usage_history()
eq(#loaded, 1, 'history file yields one sample')
eq(loaded[1].used, 16, 'history file keeps the used percent')
eq(loaded[1].account, 'ahmad', 'history file keeps the account')

-- Gemini pace calculation weights Pro accounts 20x relative to Free accounts.
local calc_pace = renderer._test.calculate_provider_average_pace
local gemini_mixed_accounts = {
  {
    provider = 'Gemini', label = 'kian', plan_type = 'pro',
    windows = {
      { label = 'gemini-weekly', used_percent = 65, reset_after_seconds = 302400, window_seconds = 604800 },
      { label = 'gemini-5h', used_percent = 65, reset_after_seconds = 9000, window_seconds = 18000 },
    }
  },
  {
    provider = 'Gemini', label = 'baba', plan_type = 'free',
    windows = {
      { label = 'gemini-weekly', used_percent = 44, reset_after_seconds = 302400, window_seconds = 604800 },
    }
  },
}
-- Window pace: elapsed = 302400 / 604800 = 50%, expected = 50%
-- kian windows: used = 65%, expected = 50% -> delta = +15%
-- baba window: used = 44%, expected = 50% -> delta = -6%
-- Weighted avg: (20 * 15 + 1 * -6) / 21 = (300 - 6) / 21 = 14%
local gemini_delta = calc_pace(gemini_mixed_accounts, 'Gemini')
eq(gemini_delta ~= nil, true, 'Gemini pace calculation produces a value with mixed free/pro')
eq(math.floor(gemini_delta + 0.5), 14, 'Gemini Pro carries 20x the weight of Gemini Free in pace delta')

local shows_pace = renderer._test.account_shows_pace
eq(shows_pace(gemini_mixed_accounts, gemini_mixed_accounts[1]), true, 'Gemini Pro shows pace')
eq(shows_pace(gemini_mixed_accounts, gemini_mixed_accounts[2]), true, 'Gemini Free (baba) shows pace')

local cursor_mixed_accounts = {
  {
    provider = 'Cursor', label = 'sepehr', plan_type = 'pro',
    windows = {
      { label = 'auto', used_percent = 65, reset_after_seconds = 1296000, window_seconds = 2592000 },
      { label = 'api', used_percent = 65, reset_after_seconds = 1296000, window_seconds = 2592000 },
    }
  },
  {
    provider = 'Cursor', label = 'kian', plan_type = 'free',
    windows = {
      { label = 'auto', used_percent = 44, reset_after_seconds = 1296000, window_seconds = 2592000 },
    }
  },
}
eq(shows_pace(cursor_mixed_accounts, cursor_mixed_accounts[1]), true, 'Cursor Pro shows pace')
eq(shows_pace(cursor_mixed_accounts, cursor_mixed_accounts[2]), true, 'Cursor Free shows pace')

local get_row_windows = renderer._test.get_row_windows
eq(#get_row_windows(cursor_mixed_accounts[1]), 2, 'Cursor Pro returns auto and api windows')
eq(#get_row_windows(cursor_mixed_accounts[2]), 1, 'Cursor Free returns only auto window')
local free_with_api = {
  provider = 'Cursor', label = 'free_with_api', plan_type = 'free',
  windows = {
    { label = 'auto', used_percent = 20, reset_after_seconds = 1000, window_seconds = 2000 },
    { label = 'api', used_percent = 0, reset_after_seconds = 1000, window_seconds = 2000 },
  }
}
local free_windows = get_row_windows(free_with_api)
eq(#free_windows, 1, 'Cursor Free drops api window even if present in raw windows')
eq(free_windows[1].label, 'auto', 'Cursor Free retains auto window')

-- Cursor pace calculation: sepehr delta = +15 (weight 20), kian delta = -6 (weight 1)
-- (20 * 15 + 1 * -6) / 21 = 14%
local cursor_delta = calc_pace(cursor_mixed_accounts, 'Cursor')
eq(cursor_delta ~= nil, true, 'Cursor pace calculation produces a value with mixed free/pro')
eq(math.floor(cursor_delta + 0.5), 14, 'Cursor Pro carries 20x the weight of Cursor Free in pace delta')

local codex_mixed_accounts = {
  {
    provider = 'Codex', label = 'kian', plan_type = 'pro',
    windows = {
      { label = 'weekly', used_percent = 65, reset_after_seconds = 302400, window_seconds = 604800 },
    }
  },
  {
    provider = 'Codex', label = 'ahmad', plan_type = 'plus',
    windows = {
      { label = 'weekly', used_percent = 55, reset_after_seconds = 302400, window_seconds = 604800 },
    }
  },
  {
    provider = 'Codex', label = 'bashir', plan_type = 'free',
    windows = {
      { label = 'monthly', used_percent = 50, reset_after_seconds = 1296000, window_seconds = 2592000 },
    }
  },
}
eq(shows_pace(codex_mixed_accounts, codex_mixed_accounts[1]), true, 'Codex Pro shows pace')
eq(shows_pace(codex_mixed_accounts, codex_mixed_accounts[2]), true, 'Codex Plus shows pace')
eq(shows_pace(codex_mixed_accounts, codex_mixed_accounts[3]), true, 'Codex Free shows pace')

-- Codex pace calculation: kian (pro, weight 400) delta = +15, ahmad (plus, weight 20) delta = +5, bashir (free, weight 1) delta = 0
-- (400 * 15 + 20 * 5 + 1 * 0) / 421 = (6000 + 100) / 421 = 6100 / 421 = 14.489% -> 14%
local codex_delta = calc_pace(codex_mixed_accounts, 'Codex')
eq(codex_delta ~= nil, true, 'Codex pace calculation produces a value with mixed free/plus/pro')
eq(math.floor(codex_delta + 0.5), 14, 'Codex Pro (400x) and Plus (20x) properly weight against Free (1x) in pace delta')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('rate-limit-panel characterization OK')
