local cairo = require('cairo')
pcall(require, 'cairo_xlib')

local script_path = debug.getinfo(1, 'S').source:gsub('^@', '')
local repo_root = script_path:match('^(.*)/conky/overlay%-entrypoint%.lua$') or '.'
local conky_dir = repo_root .. '/conky'

local shared = dofile(conky_dir .. '/renderer-shared.lua')

-- Linear
local linear_cards = dofile(conky_dir .. '/linear-card-renderer.lua')(shared, repo_root)

function conky_draw_linear_cards()
  linear_cards.draw()
end

function conky_linear_height_spacer()
  return linear_cards.height_spacer()
end

-- Rate limit panel
local rate_limit_panel = dofile(conky_dir .. '/rate-limit-panel-renderer.lua')(shared, repo_root)

function conky_draw_rate_limit_panel()
  rate_limit_panel.draw()
end

-- Minecraft
local minecraft_status = dofile(conky_dir .. '/minecraft-status-renderer.lua')(shared, repo_root)

function conky_draw_minecraft_status()
  minecraft_status.draw()
end

-- GitHub
local github_tracker = dofile(conky_dir .. '/github-tracker-renderer.lua')(shared, repo_root)

function conky_draw_github_tracker()
  github_tracker.draw()
end
