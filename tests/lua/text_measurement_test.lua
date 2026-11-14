local shared = dofile(arg[1] .. '/conky/renderer-shared.lua')
local ui = shared.ui
local allocations, size = 0, 0
cairo_text_extents_t = {create = function()
  allocations = allocations + 1
  return {}
end}
CAIRO_FONT_WEIGHT_NORMAL, CAIRO_FONT_WEIGHT_BOLD, CAIRO_FONT_SLANT_NORMAL = 0, 1, 0
cairo_select_font_face = function() end
cairo_set_font_size = function(_, value) size = value end
cairo_text_extents = function(_, text, extents)
  extents.width, extents.x_advance = #text * size, #text * size
end
cairo_set_source_rgba, cairo_move_to, cairo_show_text = function() end, function() end, function() end
for index = 1, 1000 do
  local font_size = 10 + index % 5
  local text = 'sample ' .. index
  assert(ui.width({}, text, font_size) == #text * font_size)
  assert(ui.text({}, text, 0, 0, {size = font_size}) == #text * font_size)
  assert(shared.truncate_title({}, text, #text * font_size) == text)
  assert(#shared.wrap_title({}, 'one two three', font_size * 7, 2) == 2)
end
assert(allocations <= 4, 'repeated text measurements must not retain new native extents objects')
print('text measurement preserves changing metrics with bounded native allocations')
