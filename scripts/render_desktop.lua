-- Headless Cairo worker for scripts/render_desktop.py.
--
-- Loads the shipped Conky renderers with an in-memory image surface standing in
-- for the X drawable, so overlays render without a display, a compositor, or a
-- running Conky. Renderers reach the surface through shared.create_surface(),
-- which prefers the conky_surface() global that this file installs.
--
-- Driven by a tab-separated spec file rather than argv so the Python side can
-- describe every window in one call. Two modes:
--
--   plan   <spec>            spec lines: id  entrypoint  hook  spacer_fn  w  h
--                            prints:     id  hook_present(1|0)  voffset(-1 none)
--   render <spec> <out.png>  spec line 1: canvas  w  h  r  g  b  a  scale
--                            spec line n: window  entrypoint  hook  x  y  w  h
--                            prints:      composited  <count drawn>
--
-- Windows are composited in spec order, so later lines land on top.

local mode = arg[1]
local spec_path = arg[2]

if not mode or not spec_path then
  io.stderr:write('usage: render_desktop.lua plan|render <spec> [out.png]\n')
  os.exit(2)
end

package.cpath = (os.getenv('CONKY_LUA_CPATH') or '/usr/lib/conky/lib?.so') .. ';' .. package.cpath

local cairo_ok, cairo_err = pcall(require, 'cairo')
if not cairo_ok then
  io.stderr:write('cannot load the Conky Cairo binding: ' .. tostring(cairo_err) .. '\n')
  os.exit(3)
end

-- Keep the X binding out of a headless render. The entrypoints pcall-require
-- cairo_xlib; handing them a stub means the real one never defines
-- cairo_xlib_surface_create, so shared.create_surface() cannot fall through to
-- a path that needs a live display.
package.preload['cairo_xlib'] = function()
  return {}
end

-- A renderer that builds its own Xlib surface instead of calling
-- shared.create_surface() would segfault on the nil display. Fail loudly.
function cairo_xlib_surface_create()
  error(
    'renderer called cairo_xlib_surface_create() directly; it must use ' ..
    'shared.create_surface() so it can render headless',
    2
  )
end

-- Split on tabs by hand: a gmatch pattern that can match the empty string
-- behaves differently across Lua versions, and empty fields are meaningful
-- here (a window with no height spacer).
local function split_tabs(line)
  local fields = {}
  local position = 1
  while true do
    local tab = line:find('\t', position, true)
    if not tab then
      table.insert(fields, line:sub(position))
      return fields
    end
    table.insert(fields, line:sub(position, tab - 1))
    position = tab + 1
  end
end

local function read_spec(path)
  local rows = {}
  local file = assert(io.open(path, 'r'), 'cannot read spec: ' .. path)
  for line in file:lines() do
    if line ~= '' then
      table.insert(rows, split_tabs(line))
    end
  end
  file:close()
  return rows
end

-- Point the renderers at `surface`, load `entrypoint`, and hand back the hook.
-- The entrypoint is re-loaded per window so every renderer instance is built
-- against the conky_window it is about to draw into.
local function load_hook(entrypoint, hook, width, height, surface)
  conky_window = { width = width, height = height }
  conky_surface = function()
    return surface
  end

  -- Entrypoints share this worker process, unlike real Conky windows. Remove
  -- the requested global first so a mismatched/stale config cannot reuse a
  -- hook left behind by the entrypoint loaded for the previous window.
  _G['conky_' .. hook] = nil
  local loaded, load_err = pcall(dofile, entrypoint)
  if not loaded then
    return nil, load_err
  end

  local fn = _G['conky_' .. hook]
  if type(fn) ~= 'function' then
    return nil, 'no such hook: conky_' .. hook
  end
  return fn
end

local function run_plan(rows)
  for _, row in ipairs(rows) do
    local id, entrypoint, hook, spacer_fn = row[1], row[2], row[3], row[4]
    -- The spacers size themselves against the window they are measuring, so
    -- they have to see the pre-spacer window, not a placeholder. Conky has the
    -- same ordering: the window starts at its configured minimum and the
    -- ${lua_parse} spacer then grows it.
    local width = math.max(1, math.floor(tonumber(row[5]) or 1))
    local height = math.max(1, math.floor(tonumber(row[6]) or 1))
    local scratch = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 1, 1)
    if spacer_fn and spacer_fn ~= '' then
      -- The same isolation rule applies to the optional sizing hook.
      _G['conky_' .. spacer_fn] = nil
    end
    local fn = load_hook(entrypoint, hook, width, height, scratch)
    local voffset = -1

    if fn and spacer_fn and spacer_fn ~= '' then
      local spacer = _G['conky_' .. spacer_fn]
      if type(spacer) == 'function' then
        local ok, text = pcall(spacer)
        if ok and type(text) == 'string' then
          voffset = tonumber(text:match('%${voffset%s+(-?%d+)}')) or -1
        end
      end
    end

    print(string.format('%s\t%d\t%d', id, fn and 1 or 0, voffset))
    cairo_surface_destroy(scratch)
  end
end

local function run_render(rows, out_png)
  local canvas_row = rows[1]
  assert(canvas_row and canvas_row[1] == 'canvas', 'spec must start with a canvas row')

  local width = math.floor(tonumber(canvas_row[2]))
  local height = math.floor(tonumber(canvas_row[3]))
  local red, green, blue, alpha =
    tonumber(canvas_row[4]), tonumber(canvas_row[5]),
    tonumber(canvas_row[6]), tonumber(canvas_row[7])
  local scale = tonumber(canvas_row[8]) or 1

  local canvas = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height)
  local canvas_cr = cairo_create(canvas)
  cairo_set_source_rgba(canvas_cr, red, green, blue, alpha)
  cairo_paint(canvas_cr)

  local failures, composited = 0, 0
  for index = 2, #rows do
    local row = rows[index]
    if row[1] == 'window' then
      local entrypoint, hook = row[2], row[3]
      local x, y = tonumber(row[4]), tonumber(row[5])
      local w, h = math.floor(tonumber(row[6])), math.floor(tonumber(row[7]))

      -- Each overlay draws into its own transparent surface, exactly like its
      -- ARGB Conky window, then gets composited over the background.
      local window_surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h)
      local fn, load_err = load_hook(entrypoint, hook, w, h, window_surface)

      if not fn then
        io.stderr:write(string.format('%s: %s\n', hook, tostring(load_err)))
        failures = failures + 1
      else
        local ok, draw_err = pcall(fn)
        if not ok then
          io.stderr:write(string.format('%s: %s\n', hook, tostring(draw_err)))
          failures = failures + 1
        else
          cairo_surface_flush(window_surface)
          cairo_set_source_surface(canvas_cr, window_surface, x, y)
          cairo_paint(canvas_cr)
          composited = composited + 1
        end
      end

      cairo_surface_destroy(window_surface)
    end
  end

  cairo_destroy(canvas_cr)

  local output = canvas
  if scale ~= 1 then
    local scaled_width = math.max(1, math.floor(width * scale + 0.5))
    local scaled_height = math.max(1, math.floor(height * scale + 0.5))
    output = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, scaled_width, scaled_height)
    local scaled_cr = cairo_create(output)
    cairo_scale(scaled_cr, scale, scale)
    cairo_set_source_surface(scaled_cr, canvas, 0, 0)
    cairo_paint(scaled_cr)
    cairo_destroy(scaled_cr)
  end

  cairo_surface_write_to_png(output, out_png)
  if output ~= canvas then
    cairo_surface_destroy(output)
  end
  cairo_surface_destroy(canvas)

  print(string.format('composited\t%d', composited))

  if failures > 0 then
    os.exit(1)
  end
end

local rows = read_spec(spec_path)

if mode == 'plan' then
  run_plan(rows)
elseif mode == 'render' then
  local out_png = arg[3]
  if not out_png then
    io.stderr:write('render mode needs an output path\n')
    os.exit(2)
  end
  run_render(rows, out_png)
else
  io.stderr:write('unknown mode: ' .. tostring(mode) .. '\n')
  os.exit(2)
end
