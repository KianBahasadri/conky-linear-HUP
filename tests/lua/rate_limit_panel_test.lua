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
eq(renderer._test.account_pitch(1040, {provider = 'Gemini'}, {{label = 'gemini-weekly'}}), 18,
  'free Gemini keeps a single line')
eq(renderer._test.account_pitch(1040, {provider = 'Codex'}, gemini_wins), 18,
  'non-Gemini accounts keep a single line')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('rate-limit-panel characterization OK')
