local cairo = require('cairo')
pcall(require, 'cairo_xlib')

local script_path = debug.getinfo(1, 'S').source:gsub('^@', '')
local repo_root = script_path:match('^(.*)/conky/linear%-cards%.lua$') or '.'
local conky_dir = repo_root .. '/conky'

local shared = dofile(conky_dir .. '/renderer-shared.lua')
local linear_cards = dofile(conky_dir .. '/linear-card-renderer.lua')(shared, repo_root)
local codex_usage = dofile(conky_dir .. '/codex-usage-renderer.lua')(shared, repo_root)
local minecraft_status = dofile(conky_dir .. '/minecraft-status-renderer.lua')(shared, repo_root)

function conky_draw_linear_cards()
  linear_cards.draw()
end

function conky_draw_codex_usage()
  codex_usage.draw()
end

function conky_draw_minecraft_status()
  minecraft_status.draw()
end
