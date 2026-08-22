-- Characterization harness: pins the pure helpers in renderer-shared.lua as
-- they behave today under Lua 5.4. Run via tests/test_lua_renderers.py; a
-- nonzero exit means an assertion failed.
local root = arg[1]
local shared = dofile(root .. '/conky/renderer-shared.lua')

local failures = 0

local function eq(actual, expected, label)
  if actual ~= expected then
    print('FAIL ' .. label .. ': expected ' .. string.format('%q', tostring(expected))
      .. ', got ' .. string.format('%q', tostring(actual)))
    failures = failures + 1
  end
end

-- utf8_char -------------------------------------------------------------
eq(shared.utf8_char(65), 'A', 'utf8_char ascii')
eq(shared.utf8_char(0xE9), '\xc3\xa9', 'utf8_char two-byte')
eq(shared.utf8_char(0x2014), '\xe2\x80\x94', 'utf8_char three-byte')
eq(shared.utf8_char(0x1F600), '\xf0\x9f\x98\x80', 'utf8_char four-byte')
eq(shared.utf8_char(-1), '', 'utf8_char negative is empty')
eq(shared.utf8_char(0x110000), '', 'utf8_char beyond max codepoint')
eq(shared.utf8_char(nil), '', 'utf8_char nil')

-- unescape_json_string --------------------------------------------------
local u = shared.unescape_json_string
eq(u('a\\nb'), 'a b', 'unescape newline becomes space')
eq(u('a\\tb'), 'a b', 'unescape tab becomes space')
eq(u('a\\\\nb'), 'a\\nb', 'escaped backslash keeps literal n')
eq(u('say \\"hi\\"'), 'say "hi"', 'unescape quotes')
eq(u('caf\\u00e9'), 'caf\xc3\xa9', 'unescape BMP codepoint')
eq(u('\\ud83d\\ude00'), '\xf0\x9f\x98\x80', 'unescape surrogate pair')
eq(u('bad \\u12zz escape'), 'bad u12zz escape', 'malformed unicode drops backslash-u')
eq(u('unknown \\q escape'), 'unknown q escape', 'unknown escape drops backslash')
eq(u('trailing \\'), 'trailing \\', 'trailing backslash kept')
eq(u(nil), nil, 'unescape nil passthrough')

-- match_json_string -----------------------------------------------------
local m = shared.match_json_string
eq(m('{"title":"add \\"create\\" button"}', 'title'), 'add \\"create\\" button',
  'match_json_string keeps escapes verbatim (callers unescape separately)')
eq(m('{"t":"line\\nbreak"}', 't'), 'line\\nbreak', 'match_json_string keeps raw escapes')
eq(m('{"count":42}', 'title'), nil, 'match_json_string missing key')
eq(m(nil, 'title'), nil, 'match_json_string nil text')

-- clamp -----------------------------------------------------------------
eq(shared.clamp(5, 0, 10), 5, 'clamp in range')
eq(shared.clamp(-3, 0, 10), 0, 'clamp below range')
eq(shared.clamp(99, 0, 10), 10, 'clamp above range')

-- git panel geometry ----------------------------------------------------
-- Constants live in shared.git_panel; frame height follows content_top +
-- row_height * max(1, count) + content_bottom; occupied adds footer gap+height.
eq(shared.git_panel_frame_height(0), 120, 'git_panel_frame_height empty floor')
eq(shared.git_panel_occupied_height(0), 148, 'git_panel_occupied_height empty')
eq(shared.git_panel_frame_height(1), 58, 'git_panel_frame_height one repo')
eq(shared.git_panel_occupied_height(1), 86, 'git_panel_occupied_height one repo')
eq(shared.git_panel_frame_height(3), 138, 'git_panel_frame_height three repos')
eq(shared.git_panel_occupied_height(3), 166, 'git_panel_occupied_height three repos')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('renderer-shared characterization OK')
