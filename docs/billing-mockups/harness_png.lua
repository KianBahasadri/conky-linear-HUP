-- Dump every cairo op the real renderer emits, for replay through pycairo.
local root = arg[1]
local out = {}
local function emit(...)
  local parts = {}
  for _, v in ipairs({...}) do parts[#parts+1] = tostring(v) end
  out[#out+1] = table.concat(parts, '\t')
end

CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD, CAIRO_FONT_WEIGHT_NORMAL = 0, 1, 2
CAIRO_ANTIALIAS_DEFAULT, CAIRO_ANTIALIAS_NONE = 0, 1

local font_size = 10
function cairo_create() return {} end
function cairo_destroy() end
function cairo_surface_destroy() end
function cairo_select_font_face(cr, face, slant, weight) emit('font_face', face, slant, weight) end
function cairo_set_font_size(cr, size) font_size = size emit('font_size', size) end
function cairo_set_line_width(cr, w) emit('line_width', w) end
function cairo_set_antialias(cr, a) emit('antialias', a) end
function cairo_move_to(cr, x, y) emit('move_to', x, y) end
function cairo_line_to(cr, x, y) emit('line_to', x, y) end
function cairo_stroke(cr) emit('stroke') end
function cairo_fill(cr) emit('fill') end
function cairo_fill_preserve(cr) emit('fill_preserve') end
function cairo_set_source_rgba(cr, r, g, b, a) emit('rgba', r, g, b, a) end
function cairo_new_sub_path(cr) emit('new_sub_path') end
function cairo_arc(cr, x, y, r, a1, a2) emit('arc', x, y, r, a1, a2) end
function cairo_close_path(cr) emit('close_path') end
function cairo_rectangle(cr, x, y, w, h) emit('rectangle', x, y, w, h) end
function cairo_show_text(cr, text) emit('show_text', text) end
function cairo_save(cr) emit('save') end
function cairo_restore(cr) emit('restore') end
function cairo_clip(cr) emit('clip') end

local pattern_id = 0
function cairo_pattern_create_linear(x0, y0, x1, y1)
  pattern_id = pattern_id + 1
  emit('pattern', pattern_id, x0, y0, x1, y1)
  return pattern_id
end
function cairo_pattern_add_color_stop_rgba(p, off, r, g, b, a) emit('stop', p, off, r, g, b, a) end
function cairo_set_source(cr, p) emit('source_pattern', p) end
function cairo_pattern_destroy(p) emit('pattern_destroy', p) end

cairo_text_extents_t = { create = function() return { width = 0, height = 0 } end }
function cairo_text_extents(cr, text, extents)
  -- JetBrains Mono is monospaced at 0.6 em advance; verified against pycairo.
  extents.width = #text * (font_size * 0.6)
  extents.height = font_size
end

conky_window = { width = 1920, height = 400 }
package.path = root .. '/conky/?.lua;' .. package.path
local shared = dofile(root .. '/conky/renderer-shared.lua')
shared.create_surface = function() return {}, false end
local renderer = dofile(root .. '/conky/rate-limit-panel-renderer.lua')(shared, root)
renderer.draw()
print(table.concat(out, '\n'))
