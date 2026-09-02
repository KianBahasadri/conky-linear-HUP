local cairo = require('cairo')
pcall(require, 'cairo_xlib')

local script_path = debug.getinfo(1, 'S').source:gsub('^@', '')
local repo_root = script_path:match('^(.*)/conky/overlay%-entrypoint%.lua$') or '.'
local conky_dir = repo_root .. '/conky'

local shared = dofile(conky_dir .. '/renderer-shared.lua')

-- Every Conky window loads this entrypoint, but each window invokes only one
-- draw hook (plus its matching height spacer).  Instantiate a renderer on its
-- first hook call so a load failure or state allocation in one overlay cannot
-- take down every unrelated window.
local renderers = {}

local function renderer(filename)
  if not renderers[filename] then
    renderers[filename] = dofile(conky_dir .. '/' .. filename)(shared, repo_root)
  end
  return renderers[filename]
end

function conky_draw_linear_cards()
  renderer('linear-card-renderer.lua').draw()
end

function conky_linear_height_spacer()
  return renderer('linear-card-renderer.lua').height_spacer()
end

function conky_draw_rate_limit_panel()
  renderer('rate-limit-panel-renderer.lua').draw()
end

function conky_rate_limit_panel_height_spacer()
  return renderer('rate-limit-panel-renderer.lua').height_spacer()
end

function conky_draw_minecraft_status()
  renderer('minecraft-status-renderer.lua').draw()
end

function conky_draw_github_tracker()
  renderer('github-tracker-renderer.lua').draw()
end

function conky_draw_weather()
  renderer('weather-renderer.lua').draw()
end

function conky_draw_resource_monitor()
  renderer('resource-monitor-renderer.lua').draw()
end

function conky_draw_sessions()
  renderer('sessions-renderer.lua').draw()
end

function conky_sessions_height_spacer()
  return renderer('sessions-renderer.lua').height_spacer()
end

function conky_draw_git_status()
  renderer('git-status-renderer.lua').draw()
end
