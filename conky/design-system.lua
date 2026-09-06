-- The design-guide's dark tokens and passive Cairo components.
-- Text coordinates are baselines; component coordinates are top-left corners.
-- Overlays begin directly with their content: there are no section titles,
-- and only badges, callouts, cards, and charts carry a fill.
local module_dir = (debug.getinfo(1, 'S').source:gsub('^@', '')):match('^(.*)/') or './conky'

return function(shared)
  local ui = {
    sans = 'IBM Plex Sans', mono = 'IBM Plex Mono',
    canvas = '080b0d', surface = '11171b', raised = '151d21',
    ink = 'dbe3e6', strong = 'f3f6f5', muted = '849094', faint = '566166',
    line = '263137', line_strong = '3a4a51',
    accent = '62c8d8', good = '79c99e', caution = 'd6ad63',
    danger = 'df7e78', derived = 'b9aaef',
  }
  ui.icons = dofile(module_dir .. '/lucide-icons.lua')
  ui.marks = dofile(module_dir .. '/provider-marks.lua')

  -- Severity geometry: good is the most rounded, caution intermediate, danger square.
  function ui.radius(kind, base)
    if kind == 'danger' then return 0 end
    if kind == 'caution' then return 4 end
    return base or 6
  end

  -- `bold` selects the 500 (`'medium'`), 600 (`true`), or 700 (`'bold'`) face.
  function ui.font(cr, size, mono, bold)
    local family, weight = mono and ui.mono or ui.sans, CAIRO_FONT_WEIGHT_NORMAL
    if bold == 'bold' or (mono and bold) then
      weight = CAIRO_FONT_WEIGHT_BOLD
    elseif bold then
      family = bold == 'medium' and 'Conky Plex Sans Medium' or 'Conky Plex Sans SemiBold'
    end
    cairo_select_font_face(cr, family, CAIRO_FONT_SLANT_NORMAL, weight)
    cairo_set_font_size(cr, size or 15)
  end

  function ui.width(cr, value, size, mono, bold)
    ui.font(cr, size, mono, bold)
    local ext = cairo_text_extents_t:create()
    cairo_text_extents(cr, tostring(value or ''), ext)
    return ext.x_advance
  end

  function ui.text(cr, value, x, y, opts)
    opts = opts or {}
    ui.font(cr, opts.size or 15, opts.mono, opts.bold)
    local label = tostring(value or '')
    if opts.width then label = shared.truncate_title(cr, label, math.max(0, opts.width)) end
    local ext = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, ext)
    local glyphs = {}
    if opts.tracking then
      for glyph in label:gmatch('[%z\1-\127\194-\244][\128-\191]*') do glyphs[#glyphs + 1] = glyph end
    end
    local advance = ext.x_advance + (opts.tracking or 0) * math.max(0, #glyphs - 1)
    if opts.align == 'right' then x = x - advance
    elseif opts.align == 'center' then x = x - advance / 2 end
    shared.set_hex(cr, opts.color or ui.ink, opts.alpha or 1)
    if #glyphs > 0 then
      for _, glyph in ipairs(glyphs) do
        cairo_move_to(cr, x, y)
        cairo_show_text(cr, glyph)
        cairo_text_extents(cr, glyph, ext)
        x = x + ext.x_advance + opts.tracking
      end
    else
      cairo_move_to(cr, x, y)
      cairo_show_text(cr, label)
    end
    return advance
  end

  -- Uppercase 12px mono label; metric labels track 0.08em, table headers 0.04em.
  function ui.label(cr, value, x, y, opts)
    opts = opts or {}
    opts.size, opts.mono = 12, true
    opts.tracking = opts.tracking or 0.96
    opts.color = opts.color or ui.muted
    return ui.text(cr, string.upper(value), x, y, opts)
  end

  -- Color glyphs (Noto Color Emoji) alongside UI text; Cairo toy API does not
  -- fall back per glyph, so emoji characters require their own font selection.
  function ui.emoji(cr, glyph, x, y, size)
    if not glyph or glyph == '' then return 0 end
    cairo_select_font_face(cr, 'Noto Color Emoji', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, size or 11)
    local ext = cairo_text_extents_t:create()
    cairo_text_extents(cr, glyph, ext)
    shared.set_hex(cr, ui.strong, 0.95)
    cairo_move_to(cr, x, y)
    cairo_show_text(cr, glyph)
    return ext.x_advance
  end

  function ui.line_between(cr, x1, y1, x2, y2, color, width, alpha)
    cairo_new_path(cr)
    shared.set_hex(cr, color or ui.line, alpha or 1)
    cairo_set_line_width(cr, width or 1)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT or 0)
    cairo_move_to(cr, x1, y1)
    cairo_line_to(cr, x2, y2)
    cairo_stroke(cr)
  end

  -- Straight dashed stroke drawn as explicit segments, so it needs no Cairo
  -- dash-array binding. `on`/`off` are dash lengths in pixels.
  function ui.dash(cr, x1, y1, x2, y2, color, width, on, off, alpha)
    local length = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
    if length == 0 then return end
    cairo_new_path(cr)
    shared.set_hex(cr, color or ui.line, alpha or 1)
    cairo_set_line_width(cr, width or 1)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT or 0)
    local pos = 0
    while pos < length do
      local a, b = pos / length, math.min(pos + on, length) / length
      cairo_move_to(cr, x1 + (x2 - x1) * a, y1 + (y2 - y1) * a)
      cairo_line_to(cr, x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)
      pos = pos + on + off
    end
    cairo_stroke(cr)
  end

  function ui.polyline(cr, points, color, width, alpha, round)
    if #points < 2 then return end
    cairo_new_path(cr)
    shared.set_hex(cr, color or ui.accent, alpha or 1)
    cairo_set_line_width(cr, width or 1.5)
    cairo_set_line_cap(cr, round and (CAIRO_LINE_CAP_ROUND or 1) or (CAIRO_LINE_CAP_BUTT or 0))
    cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND or 1)
    cairo_move_to(cr, points[1][1], points[1][2])
    for index = 2, #points do cairo_line_to(cr, points[index][1], points[index][2]) end
    cairo_stroke(cr)
  end

  function ui.polygon(cr, points, color, alpha)
    if #points < 3 then return end
    cairo_new_path(cr)
    cairo_move_to(cr, points[1][1], points[1][2])
    for index = 2, #points do cairo_line_to(cr, points[index][1], points[index][2]) end
    cairo_close_path(cr)
    shared.set_hex(cr, color, alpha or 1)
    cairo_fill(cr)
  end

  function ui.rect(cr, x, y, w, h, color, radius, alpha, border)
    if w <= 0 or h <= 0 then return end
    cairo_new_path(cr)
    if (radius or 0) > 0 then
      shared.rounded_rect(cr, x, y, w, h, math.min(radius, h / 2, w / 2))
    else cairo_rectangle(cr, x, y, w, h) end
    shared.set_hex(cr, color, alpha or 1)
    if border then cairo_set_line_width(cr, border == true and 1 or border); cairo_stroke(cr)
    else cairo_fill(cr) end
  end

  function ui.circle(cr, x, y, r, color, alpha, border)
    cairo_new_path(cr)
    cairo_arc(cr, x, y, r, 0, math.pi * 2)
    shared.set_hex(cr, color, alpha or 1)
    if border then cairo_set_line_width(cr, border == true and 1 or border); cairo_stroke(cr)
    else cairo_fill(cr) end
  end

  -- Draw `callback` into a group composited at `alpha` (stale data is dimmed).
  function ui.group(cr, alpha, callback)
    if alpha >= 1 then callback(); return end
    cairo_push_group(cr)
    local ok, err = pcall(callback)
    cairo_pop_group_to_source(cr)
    cairo_paint_with_alpha(cr, alpha)
    if not ok then error(err) end
  end

  -- SVG path data (M L H V C S Q T A Z, absolute or relative) appended to the
  -- current Cairo path. Elliptical arcs use the SVG endpoint parameterization.
  local function arc_to(cr, x1, y1, rx, ry, rotation, large, sweep, x2, y2)
    if rx == 0 or ry == 0 then cairo_line_to(cr, x2, y2); return end
    rx, ry = math.abs(rx), math.abs(ry)
    local phi = math.rad(rotation)
    local cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    local dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    local x1p = cos_phi * dx + sin_phi * dy
    local y1p = -sin_phi * dx + cos_phi * dy
    local lambda = x1p ^ 2 / rx ^ 2 + y1p ^ 2 / ry ^ 2
    if lambda > 1 then rx, ry = rx * math.sqrt(lambda), ry * math.sqrt(lambda) end
    local numerator = rx ^ 2 * ry ^ 2 - rx ^ 2 * y1p ^ 2 - ry ^ 2 * x1p ^ 2
    local denominator = rx ^ 2 * y1p ^ 2 + ry ^ 2 * x1p ^ 2
    local coefficient = denominator > 0 and math.sqrt(math.max(0, numerator / denominator)) or 0
    if large == sweep then coefficient = -coefficient end
    local cxp, cyp = coefficient * rx * y1p / ry, -coefficient * ry * x1p / rx
    local cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
    local cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2
    local function angle(ux, uy, vx, vy)
      local dot = ux * vx + uy * vy
      local length = math.sqrt((ux ^ 2 + uy ^ 2) * (vx ^ 2 + vy ^ 2))
      local value = math.acos(math.max(-1, math.min(1, dot / length)))
      if ux * vy - uy * vx < 0 then value = -value end
      return value
    end
    local theta = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    local delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0 then delta = delta - 2 * math.pi
    elseif sweep and delta < 0 then delta = delta + 2 * math.pi end
    cairo_save(cr)
    cairo_translate(cr, cx, cy)
    cairo_rotate(cr, phi)
    cairo_scale(cr, rx, ry)
    if delta >= 0 then cairo_arc(cr, 0, 0, 1, theta, theta + delta)
    else cairo_arc_negative(cr, 0, 0, 1, theta, theta + delta) end
    cairo_restore(cr)
  end

  local function tokenize(d)
    local tokens, index = {}, 1
    while index <= #d do
      local character = d:sub(index, index)
      if character:match('[MmLlHhVvCcSsQqTtAaZz]') then
        tokens[#tokens + 1] = character
        index = index + 1
      elseif character:match('[%s,]') then
        index = index + 1
      else
        local start, stop = d:find('^[-+]?%d*%.?%d+', index)
        if not start then start, stop = d:find('^[-+]?%d+%.?', index) end
        if not start then break end
        local _, exponent = d:find('^[eE][-+]?%d+', stop + 1)
        if exponent then stop = exponent end
        tokens[#tokens + 1] = tonumber(d:sub(start, stop))
        index = stop + 1
      end
    end
    return tokens
  end

  function ui.path(cr, d)
    local tokens, index, command = tokenize(d), 1, 'M'
    local x, y, sx, sy, cx, cy, qx, qy, previous = 0, 0, 0, 0, 0, 0, 0, 0, ''
    local function number()
      local value = tokens[index]
      index = index + 1
      return type(value) == 'number' and value or 0
    end
    while index <= #tokens do
      if type(tokens[index]) == 'string' then
        command = tokens[index]
        index = index + 1
      end
      local relative, upper = command == command:lower(), command:upper()
      local ox, oy = relative and x or 0, relative and y or 0
      if upper == 'M' then
        x, y = ox + number(), oy + number()
        cairo_move_to(cr, x, y)
        sx, sy = x, y
        command = relative and 'l' or 'L'
      elseif upper == 'L' then
        x, y = ox + number(), oy + number()
        cairo_line_to(cr, x, y)
      elseif upper == 'H' then
        x = ox + number()
        cairo_line_to(cr, x, y)
      elseif upper == 'V' then
        y = oy + number()
        cairo_line_to(cr, x, y)
      elseif upper == 'C' or upper == 'S' then
        local x1, y1
        if upper == 'C' then x1, y1 = ox + number(), oy + number()
        elseif previous == 'C' then x1, y1 = 2 * x - cx, 2 * y - cy
        else x1, y1 = x, y end
        cx, cy = ox + number(), oy + number()
        x, y = ox + number(), oy + number()
        cairo_curve_to(cr, x1, y1, cx, cy, x, y)
      elseif upper == 'Q' or upper == 'T' then
        if upper == 'Q' then qx, qy = ox + number(), oy + number()
        elseif previous == 'Q' then qx, qy = 2 * x - qx, 2 * y - qy
        else qx, qy = x, y end
        local nx, ny = ox + number(), oy + number()
        cairo_curve_to(cr, x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y),
          nx + 2 / 3 * (qx - nx), ny + 2 / 3 * (qy - ny), nx, ny)
        x, y = nx, ny
      elseif upper == 'A' then
        local rx, ry, rotation = number(), number(), number()
        local large, sweep = number() ~= 0, number() ~= 0
        local nx, ny = ox + number(), oy + number()
        arc_to(cr, x, y, rx, ry, rotation, large, sweep, nx, ny)
        x, y = nx, ny
      elseif upper == 'Z' then
        cairo_close_path(cr)
        x, y = sx, sy
      end
      previous = (upper == 'C' or upper == 'S') and 'C' or (upper == 'Q' or upper == 'T') and 'Q' or ''
    end
  end

  -- Lucide icon with its top-left corner at (x, y); 16px by default.
  function ui.icon(cr, name, x, y, size, color)
    local paths = ui.icons[name]
    if not paths then return false end
    size = size or 16
    cairo_save(cr)
    cairo_translate(cr, x, y)
    cairo_scale(cr, size / 24, size / 24)
    cairo_new_path(cr)
    for _, d in ipairs(paths) do ui.path(cr, d) end
    shared.set_hex(cr, color or ui.muted, 1)
    cairo_set_line_width(cr, 2)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND or 1)
    cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND or 1)
    cairo_stroke(cr)
    cairo_restore(cr)
    return true
  end

  -- Provider mark centered on (x, y). Wide marks use 1.2× `size` for their width.
  function ui.mark(cr, key, x, y, size, color)
    local mark = key and ui.marks[key]
    if not mark then return false end
    local mark_width = mark.ratio > 1.8 and size * 1.2 or size
    local scale = math.min(mark_width / mark.view[3], mark_width / mark.ratio / mark.view[4])
    cairo_save(cr)
    cairo_translate(cr, x - (mark.view[1] + mark.view[3] / 2) * scale,
      y - (mark.view[2] + mark.view[4] / 2) * scale)
    cairo_scale(cr, scale, scale)
    for _, piece in ipairs(mark.paths) do
      cairo_save(cr)
      local piece_scale = 1
      for operation, a, b in (piece.transform or ''):gmatch('(%a+)%(%s*([-%d%.]+)[%s,]*([-%d%.]*)%s*%)') do
        a, b = tonumber(a), tonumber(b)
        if operation == 'translate' then cairo_translate(cr, a, b or 0)
        elseif operation == 'scale' then
          cairo_scale(cr, a, b or a)
          piece_scale = piece_scale * math.min(a, b or a)
        end
      end
      cairo_new_path(cr)
      ui.path(cr, piece.d)
      cairo_set_fill_rule(cr, piece.evenodd and (CAIRO_FILL_RULE_EVEN_ODD or 1) or (CAIRO_FILL_RULE_WINDING or 0))
      if piece.fill ~= 'none' then
        local fill_color = piece.fill == 'currentColor' and (color or ui.strong) or piece.fill
        shared.set_hex(cr, fill_color, piece.opacity or 1)
        if piece.stroke then cairo_fill_preserve(cr) else cairo_fill(cr) end
      end
      if piece.stroke then
        local stroke_color = piece.stroke == 'currentColor' and (color or ui.strong) or piece.stroke
        shared.set_hex(cr, stroke_color, 1)
        local stroke_width = piece.stroke_width or 1
        if piece.non_scaling then stroke_width = stroke_width / (scale * piece_scale) end
        cairo_set_line_width(cr, stroke_width)
        cairo_stroke(cr)
      end
      cairo_restore(cr)
    end
    cairo_restore(cr)
    return true
  end

  -- Status badge: 12px medium text, 3px/8px padding, no border. Neutral badges
  -- use the raised surface; semantic ones a 14% tint with severity geometry.
  function ui.badge(cr, label, x, y, kind, opts)
    opts = opts or {}
    local semantic = kind and kind ~= 'neutral' and ui[kind] or nil
    local width = ui.width(cr, label, 12, false, 'medium') + 16
    if opts.right then x = x - width end
    ui.rect(cr, x, y, width, 20, semantic or ui.raised, ui.radius(kind, 10), semantic and 0.14 or 1)
    ui.text(cr, label, x + 8, y + 14, {size = 12, color = semantic or ui.muted, bold = 'medium'})
    return width
  end

  -- Metric group: uppercase mono label over a 26px bold mono value, centered.
  function ui.metric(cr, label, value, x, y, width)
    local center = x + width / 2
    ui.label(cr, label, center, y + 12, {align = 'center'})
    ui.text(cr, value, center, y + 44,
      {size = 26, bold = 'bold', color = ui.muted, align = 'center'})
  end

  -- Realtime resource reading: a Lucide symbol over a 26px bold value with its
  -- 12px mono unit alongside, centered in `width`.
  function ui.reading(cr, icon, value, unit, x, y, width, color)
    local center = x + width / 2
    ui.icon(cr, icon, center - 8, y, 16, ui.muted)
    local value_width = ui.width(cr, value, 26, false, 'bold')
    local unit_width = unit ~= '' and ui.width(cr, unit, 12, true) + 5 or 0
    local left = center - (value_width + unit_width) / 2
    ui.text(cr, value, left, y + 46, {size = 26, bold = 'bold', color = color or ui.muted})
    if unit ~= '' then
      ui.text(cr, unit, left + value_width + 5, y + 46, {size = 12, mono = true, color = color or ui.muted})
    end
  end

  -- Inline callout: a semibold status label followed by its message, borderless.
  function ui.callout(cr, label, message, x, y, width, kind)
    local semantic = kind and kind ~= 'info' and ui[kind] or nil
    local prefix = label .. ':'
    local prefix_width = ui.width(cr, prefix, 13.5, false, true)
    ui.font(cr, 13.5)
    local words, lines, current = {}, {}, ''
    for word in tostring(message or ''):gmatch('%S+') do words[#words + 1] = word end
    local extents = cairo_text_extents_t:create()
    local limit = width - 20 - prefix_width - 5
    for _, word in ipairs(words) do
      local candidate = current == '' and word or current .. ' ' .. word
      cairo_text_extents(cr, candidate, extents)
      if extents.x_advance <= limit or current == '' then current = candidate
      else
        lines[#lines + 1] = current
        current, limit = word, width - 20
      end
      if #lines == 3 then break end
    end
    if current ~= '' and #lines < 3 then lines[#lines + 1] = current end
    local height = 16 + math.max(1, #lines) * 20
    ui.rect(cr, x, y, width, height, semantic or ui.raised, ui.radius(kind), semantic and 0.14 or 1)
    ui.text(cr, prefix, x + 10, y + 22, {size = 13.5, bold = true})
    for index, line in ipairs(lines) do
      ui.text(cr, line, x + 10 + (index == 1 and prefix_width + 5 or 0), y + 2 + index * 20,
        {size = 13.5, width = width - 20 - (index == 1 and prefix_width + 5 or 0)})
    end
    return height
  end

  function ui.ago(seconds)
    if not seconds or seconds < 0 then return 'unknown' end
    if seconds < 60 then return math.floor(seconds) .. 's' end
    if seconds < 3600 then return math.floor(seconds / 60) .. 'm' end
    if seconds < 86400 then return math.floor(seconds / 3600) .. 'h' end
    return math.floor(seconds / 86400) .. 'd'
  end

  -- Bounded passive panels rotate only when there are more records than fit.
  function ui.page(count, capacity, period)
    capacity = math.max(1, math.floor(capacity))
    local pages = math.max(1, math.ceil(count / capacity))
    local page = math.floor(os.time() / (period or 30)) % pages
    local first = page * capacity + 1
    return first, math.min(count, first + capacity - 1), pages > 1 and
      string.format('%d–%d of %d', first, math.min(count, first + capacity - 1), count) or ''
  end

  -- Rows of a fixed `pitch` below `top`. When records exceed the window (or
  -- `footer` is already needed), a 16px footer line is reserved for context.
  function ui.rows(count, height, pitch, top, footer)
    top = top or 0
    local capacity = math.max(1, math.floor((height - top) / pitch))
    if count <= capacity and not footer then return 1, count, '' end
    return ui.page(count, math.max(1, math.floor((height - top - 16) / pitch)))
  end

  -- Records whose heights differ. Fits whole records within the available
  -- window height and drops overflowing extras without paging.
  function ui.stack(heights, height, top, footer)
    if #heights == 0 then return 1, 0, '' end
    local available = height - (top or 0) - (footer and 16 or 0)
    local last, used = 0, 0
    for index, value in ipairs(heights) do
      if used + value > available then break end
      used = used + value
      last = index
    end
    return 1, math.max(1, last), ''
  end

  -- Variable-height records packed into pages, rotating like `ui.page`.
  function ui.pack(heights, height, top, period)
    if #heights == 0 then return 1, 0, '' end
    top = top or 0
    local function pages_for(available)
      local pages, current, used = {}, {}, 0
      for index, value in ipairs(heights) do
        local pitch = math.max(1, value)
        if #current > 0 and used + pitch > available then
          pages[#pages + 1] = current
          current, used = {}, 0
        end
        current[#current + 1] = index
        used = used + pitch
      end
      if #current > 0 then pages[#pages + 1] = current end
      return pages
    end
    local pages = pages_for(math.max(1, height - top))
    if #pages <= 1 then return 1, #heights, '' end
    pages = pages_for(math.max(1, height - top - 16))
    local slots = pages[math.floor(os.time() / (period or 30)) % #pages + 1]
    return slots[1], slots[#slots],
      string.format('%d–%d of %d', slots[1], slots[#slots], #heights)
  end

  function ui.footer(cr, text, width, height, color)
    if text and text ~= '' then
      ui.text(cr, text, width, height - 4, {size = 11, mono = true, color = color or ui.muted, align = 'right'})
    end
  end

  function ui.draw(callback)
    local surface, owned = shared.create_surface()
    if not surface then return end
    local cr = cairo_create(surface)
    -- Cairo contexts are destroyed even if a renderer fails mid-frame.
    local ok, err = pcall(callback, cr, conky_window.width, conky_window.height)
    cairo_destroy(cr)
    if owned then cairo_surface_destroy(surface) end
    if not ok then error(err) end
  end

  return ui
end
