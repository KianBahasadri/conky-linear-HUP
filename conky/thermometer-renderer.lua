local module_dir = (debug.getinfo(1, 'S').source:gsub('^@', '')):match('^(.*)/') or './conky'

return function(shared, repo_root)
  local thermometer = dofile(module_dir .. '/thermometer-component.lua')(shared, repo_root, {scale = 0.5})
  return {draw = function()
    shared.ui.draw(function(cr, _, height)
      thermometer.draw(cr, thermometer.read(), 0, math.max(0, height - thermometer.height))
    end)
  end}
end
