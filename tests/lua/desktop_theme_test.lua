-- Theme changes must reach existing renderer instances on the next frame.
local root = arg[1]
local create_ui = dofile(root .. '/conky/design-system.lua')
local original_getenv = os.getenv
local override, content
os.getenv = function(key)
  if key == 'CONKY_OVERLAY_THEME' then return override end
  return original_getenv(key)
end
local shared = {
  read_file = function(path)
    assert(path:match('/cache/desktop%-theme$'))
    return content
  end,
  create_surface = function() return {}, false end,
}
cairo_create = function(surface) return surface end
cairo_destroy = function() end
conky_window = {width = 300, height = 200}

local ui = create_ui(shared)
assert(ui.theme == 'dark' and ui.ink == 'dbe3e6', 'missing initial cache defaults to dark')
local retained_ui = ui
local dark = {}
for key, value in pairs(ui) do if type(value) == 'string' then dark[key] = value end end

content = 'light\n'
ui.draw(function()
  assert(ui == retained_ui, 'existing renderers keep the same shared table')
  assert(ui.theme == 'light' and ui.ink == '172027' and ui.strong == '0a0d0f')
  assert(ui.surface == 'f7f8f5' and ui.raised == 'ffffff' and ui.canvas == 'ecefec')
  assert(ui.muted == '536168' and ui.faint == '778287')
  assert(ui.line == 'c8d1d0' and ui.line_strong == '9dacab')
  assert(ui.accent == '006f7c' and ui.good == '1d6846' and ui.caution == '805600')
  assert(ui.danger == '9a332f' and ui.derived == '63559b' and ui.soft_alpha == 0.12)
end)
for _, invalid in ipairs({'', 'li', 'unknown', 'light dark'}) do
  content = invalid
  ui.draw(function() assert(ui.theme == 'light', 'invalid cache keeps the last palette') end)
end
content = nil
ui.refresh_theme()
assert(ui.theme == 'light', 'missing cache keeps the last palette')

content = 'dark\n'
ui.draw(function()
  for key, value in pairs(dark) do assert(ui[key] == value, 'dark token not restored: ' .. key) end
  assert(ui.soft_alpha == 0.14)
end)
for _, forced in ipairs({'light', 'dark'}) do
  override = forced
  local pinned = create_ui(shared)
  content = forced == 'light' and 'dark\n' or 'light\n'
  pinned.draw(function() assert(pinned.theme == forced, 'explicit palette overrides the cache') end)
end
override, content = 'auto', 'light\n'
assert(create_ui(shared).theme == 'light', 'auto follows the cache')
os.getenv = original_getenv
print('desktop theme switching OK')
