local module_dir = (debug.getinfo(1, 'S').source:gsub('^@', '')):match('^(.*)/') or './conky'

return function(shared, repo_root)
  local thermometer = dofile(module_dir .. '/thermometer-component.lua')(shared, repo_root, {
    scale = 0.5,
    padding_x = 6,
    glyph_size = 38,
    stack_gap = 8,
    row_gap = 6.5,
    tube_scale = 0.628,
    tube_offset_y = -13.76,
  })
  return {draw = function()
    shared.ui.draw(function(cr, _, height)
      thermometer.draw(cr, thermometer.read(), 0, height - thermometer.height + 14)
    end)
  end}
end
