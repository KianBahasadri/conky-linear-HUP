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

-- Codex
local codex_usage = dofile(conky_dir .. '/codex-usage-renderer.lua')(shared, repo_root)

function conky_draw_codex_usage()
  codex_usage.draw()
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
