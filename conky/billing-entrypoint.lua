local cairo = require('cairo')
pcall(require, 'cairo_xlib')

local script_path = debug.getinfo(1, 'S').source:gsub('^@', '')
local repo_root = script_path:match('^(.*)/conky/billing%-entrypoint%.lua$') or '.'
local conky_dir = repo_root .. '/conky'

local shared = dofile(conky_dir .. '/renderer-shared.lua')
local billing = dofile(conky_dir .. '/billing-renderer.lua')(shared, repo_root)

function conky_draw_billing()
  billing.draw()
end
