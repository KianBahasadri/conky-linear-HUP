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
eq(shared.utf8_char(0xD800), '\xef\xbf\xbd', 'utf8_char lone high surrogate replacement')
eq(shared.utf8_char(0xDFFF), '\xef\xbf\xbd', 'utf8_char lone low surrogate replacement')
eq(shared.utf8_char(-1), '', 'utf8_char negative is empty')
eq(shared.utf8_char(0x110000), '', 'utf8_char beyond max codepoint')
eq(shared.utf8_char(nil), '', 'utf8_char nil')

-- unescape_json_string --------------------------------------------------
local u = shared.unescape_json_string
eq(u('a\\nb'), 'a b', 'unescape newline becomes space')
eq(u('a\\tb'), 'a b', 'unescape tab becomes space')
eq(u('a\\bb\\fc'), 'a b c', 'unescape backspace and form-feed become spaces')
eq(u('a\\\\nb'), 'a\\nb', 'escaped backslash keeps literal n')
eq(u('say \\"hi\\"'), 'say "hi"', 'unescape quotes')
eq(u('caf\\u00e9'), 'caf\xc3\xa9', 'unescape BMP codepoint')
eq(u('\\ud83d\\ude00'), '\xf0\x9f\x98\x80', 'unescape surrogate pair')
eq(u('\\ud83d'), '\xef\xbf\xbd', 'unescape lone high surrogate is valid UTF-8')
eq(u('\\ude00'), '\xef\xbf\xbd', 'unescape lone low surrogate is valid UTF-8')
eq(u('bad \\u12zz escape'), 'bad u12zz escape', 'malformed unicode drops backslash-u')
eq(u('unknown \\q escape'), 'unknown q escape', 'unknown escape drops backslash')
eq(u('trailing \\'), 'trailing \\', 'trailing backslash kept')
eq(u(nil), nil, 'unescape nil passthrough')

-- structural JSON helpers ----------------------------------------------
local json = [[{
  "ok": false,
  "zero": 0,
  "none": null,
  "name": "a \"quoted\" } [ thing \ud83d\ude00",
  "nested": {"ok": true, "items": [{"id": 9}]},
  "objects": [
    {"name": "one", "meta": {"brace": "}"}},
    {"name": "two", "values": [1, {"nested": true}]}
  ],
  "strings": ["a", "b \"q\"", "\ud83d\ude00", null]
}]]
eq(shared.json_boolean(json, 'ok', true), false, 'json_boolean direct false ignores nested true')
eq(shared.json_number(json, 'zero', 99), 0, 'json_number preserves zero')
eq(shared.json_number(json, 'none', 99), 99, 'json_number null uses fallback')
eq(shared.json_number('{"huge":1e999}', 'huge', 99), 99,
  'json_number non-finite value uses fallback')
eq(shared.json_string(json, 'name', ''), 'a "quoted" } [ thing \xf0\x9f\x98\x80',
  'json_string handles escapes surrogate and structural characters')
eq(shared.json_boolean(json, 'missing', nil), nil, 'json_boolean missing is nil')

local nested = shared.json_field(json, 'nested')
eq(shared.json_boolean(nested, 'ok', false), true, 'json_field returns nested object intact')
local nested_items = shared.json_array_objects(nested, 'items')
eq(#nested_items, 1, 'json_array_objects nested count')
eq(shared.json_number(nested_items[1], 'id', -1), 9, 'json_array_objects nested value')

local objects = shared.json_array_objects(json, 'objects')
eq(#objects, 2, 'json_array_objects count with nested containers')
eq(shared.json_string(objects[1], 'name', ''), 'one', 'json_array_objects first field')
eq(shared.json_string(objects[1], 'meta', 'fallback'), 'fallback',
  'json_string rejects object value')
eq(shared.json_string(objects[2], 'name', ''), 'two', 'json_array_objects second field')

local strings = shared.json_array_strings(json, 'strings')
eq(#strings, 3, 'json_array_strings skips null')
eq(strings[2], 'b "q"', 'json_array_strings escaped quote')
eq(strings[3], '\xf0\x9f\x98\x80', 'json_array_strings surrogate pair')

for index, malformed in ipairs({
  '{"objects":[{"name":"open"}]',
  '{"objects":[{"name":"mismatch"]}}',
  '{"name":"unterminated}',
  '{"name":"found first" trailing garbage}',
  '{"name":"missing comma" "ok":true}',
  '{"objects":[{"name":"one"} {"name":"two"}]}',
  '{"objects":[{"name":"trailing comma"},]}',
  '{"zero":01}',
  '{not-json}',
}) do
  eq(shared.json_field(malformed, 'name'), nil, 'malformed json_field ' .. index)
  eq(#shared.json_array_objects(malformed, 'objects'), 0, 'malformed json_array_objects ' .. index)
end

-- clamp -----------------------------------------------------------------
eq(shared.clamp(5, 0, 10), 5, 'clamp in range')
eq(shared.clamp(-3, 0, 10), 0, 'clamp below range')
eq(shared.clamp(99, 0, 10), 10, 'clamp above range')

-- surface creation -----------------------------------------------------
local surface_calls = 0
local surface_token = {}
conky_surface = function()
  surface_calls = surface_calls + 1
  return surface_token
end
conky_window = { width = 0, height = 100 }
local surface, owns_surface = shared.create_surface()
eq(surface, nil, 'create_surface rejects zero-width first frame')
eq(owns_surface, false, 'create_surface rejected frame owns nothing')
eq(surface_calls, 0, 'create_surface does not ask Cairo for invalid frame')
conky_window = { width = 100, height = 50 }
surface, owns_surface = shared.create_surface()
eq(surface, surface_token, 'create_surface uses Conky surface for valid frame')
eq(owns_surface, false, 'Conky surface is borrowed')
eq(surface_calls, 1, 'create_surface called once for valid frame')
conky_window = nil
conky_surface = nil


-- UTF-8 truncation ------------------------------------------------------
-- The renderer receives UTF-8 labels from every provider.  Assert not only the
-- result but every intermediate measurement, since byte-at-a-time truncation
-- briefly passed invalid strings to Cairo before landing on a valid prefix.
local measured_valid_utf8 = true
cairo_text_extents_t = { create = function() return {} end }
function cairo_text_extents(_cr, value, extents)
  if not utf8.len(value) then
    measured_valid_utf8 = false
  end
  extents.width = #value
end
eq(shared.truncate_title({}, '\xc3\xa9\xc3\xa9\xc3\xa9', 5), '\xc3\xa9...',
  'truncate_title removes whole UTF-8 codepoints')
eq(measured_valid_utf8, true, 'truncate_title only measures valid UTF-8')

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('renderer-shared characterization OK')
