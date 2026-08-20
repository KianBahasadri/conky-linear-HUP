-- Generic op dump for the existing right-rail renderers.
local root = arg[1]
local overlay = arg[2]
local out = {}
local function emit(...)
  local parts = {}
  for _, value in ipairs({...}) do parts[#parts + 1] = tostring(value) end
  out[#out + 1] = table.concat(parts, '\t')
end

CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD, CAIRO_FONT_WEIGHT_NORMAL = 0, 1, 2
CAIRO_ANTIALIAS_DEFAULT, CAIRO_ANTIALIAS_NONE = 0, 1
CAIRO_LINE_CAP_ROUND, CAIRO_LINE_CAP_BUTT = 1, 0

local font_size = 10
function cairo_create() return {} end
function cairo_destroy() end
function cairo_surface_destroy() end
function cairo_select_font_face(cr, face, slant, weight) emit('font_face', face, slant, weight) end
function cairo_set_font_size(cr, size) font_size = size emit('font_size', size) end
function cairo_set_line_width(cr, width) emit('line_width', width) end
function cairo_set_line_cap(cr, cap) emit('line_cap', cap) end
function cairo_set_antialias(cr, value) emit('antialias', value) end
function cairo_move_to(cr, x, y) emit('move_to', x, y) end
function cairo_line_to(cr, x, y) emit('line_to', x, y) end
function cairo_stroke(cr) emit('stroke') end
function cairo_fill(cr) emit('fill') end
function cairo_fill_preserve(cr) emit('fill_preserve') end
function cairo_set_source_rgba(cr, r, g, b, a) emit('rgba', r, g, b, a) end
function cairo_new_path(cr) emit('new_path') end
function cairo_new_sub_path(cr) emit('new_sub_path') end
function cairo_arc(cr, x, y, radius, a1, a2) emit('arc', x, y, radius, a1, a2) end
function cairo_arc_negative(cr, x, y, radius, a1, a2) emit('arc_negative', x, y, radius, a1, a2) end
function cairo_close_path(cr) emit('close_path') end
function cairo_rectangle(cr, x, y, width, height) emit('rectangle', x, y, width, height) end
function cairo_show_text(cr, label) emit('show_text', label) end
function cairo_save(cr) emit('save') end
function cairo_restore(cr) emit('restore') end
function cairo_clip(cr) emit('clip') end

cairo_text_extents_t = {
  create = function()
    return { width = 0, height = 0, x_bearing = 0, y_bearing = 0, x_advance = 0 }
  end
}
function cairo_text_extents(cr, label, extents)
  extents.width = #label * (font_size * 0.6)
  extents.height = font_size
  extents.x_bearing = 0
  extents.y_bearing = -font_size * 0.75
  extents.x_advance = extents.width
end

local specs = {
  resource = { width = 280, height = 258, file = 'resource-monitor-renderer.lua' },
  weather = { width = 456, height = 276, file = 'weather-renderer.lua' },
}
local spec = assert(specs[overlay], 'unknown overlay: ' .. tostring(overlay))
conky_window = { width = spec.width, height = spec.height }
package.path = root .. '/conky/?.lua;' .. package.path
local shared = dofile(root .. '/conky/renderer-shared.lua')
shared.create_surface = function() return {}, false end
local renderer = dofile(root .. '/conky/' .. spec.file)(shared, root)
renderer.draw()
print(table.concat(out, '\n'))
