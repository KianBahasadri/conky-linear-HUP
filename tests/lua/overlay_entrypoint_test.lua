-- Characterization harness for lazy renderer loading in overlay-entrypoint.lua.
local root = arg[1]

package.preload.cairo = function() return {} end

local failures = 0
local function eq(actual, expected, label)
  if actual ~= expected then
    print('FAIL ' .. label .. ': expected ' .. string.format('%q', tostring(expected))
      .. ', got ' .. string.format('%q', tostring(actual)))
    failures = failures + 1
  end
end

local original_dofile = dofile
local loaded_paths = {}
dofile = function(path)
  table.insert(loaded_paths, path)
  return original_dofile(path)
end

original_dofile(root .. '/conky/overlay-entrypoint.lua')

local function renderer_load_count()
  local count = 0
  for _, path in ipairs(loaded_paths) do
    if path:match('%-renderer%.lua$') and not path:match('renderer%-shared%.lua$') then
      count = count + 1
    end
  end
  return count
end

eq(renderer_load_count(), 0, 'entrypoint loads no renderer eagerly')
eq(type(conky_draw_linear_cards), 'function', 'linear draw hook is registered')
eq(type(conky_linear_height_spacer), 'function', 'linear spacer hook is registered')
eq(type(conky_draw_rate_limit_panel), 'function', 'rate limit draw hook is registered')
eq(type(conky_draw_minecraft_status), 'function', 'minecraft draw hook is registered')
eq(type(conky_draw_github_tracker), 'function', 'github draw hook is registered')
eq(type(conky_draw_weather), 'function', 'weather draw hook is registered')
eq(type(conky_draw_resource_monitor), 'function', 'resource draw hook is registered')
eq(type(conky_draw_sessions), 'function', 'sessions draw hook is registered')
eq(type(conky_draw_git_status), 'function', 'git draw hook is registered')

conky_linear_height_spacer()
eq(renderer_load_count(), 1, 'first linear hook loads only linear renderer')
conky_linear_height_spacer()
eq(renderer_load_count(), 1, 'second linear hook reuses cached renderer')

-- With no conky_window the draw exits before any Cairo calls, while still
-- proving that a second hook loads only its own renderer.
conky_draw_minecraft_status()
eq(renderer_load_count(), 2, 'minecraft hook loads only minecraft renderer')

dofile = original_dofile

if failures > 0 then
  print(failures .. ' failure(s)')
  os.exit(1)
end
print('overlay-entrypoint characterization OK')
