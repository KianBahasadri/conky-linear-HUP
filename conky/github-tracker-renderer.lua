return function(shared, repo_root)
  local github_path = repo_root .. '/cache/github-contributions.json'
  local log_path = repo_root .. '/cache/conky-github.log'
  local font = 'JetBrains Mono'

  -- The lattice. A week steps straight right; a weekday steps right and away.
  -- The level week axis is the whole point: it gives the skyline a straight
  -- front edge, so it can sit on the rate limit panel's top edge as its roof
  -- instead of floating.
  local day_dx_ratio = 0.015
  local day_dy_ratio = 0.095
  local fill = 0.86
  local deck_ratio = 0.55
  local columns = 7
  local weeks_max = 105
  local window_inset = 4

  local deck_color = '1e293b'
  local gold = 'd4af37'
  local gold_lit = 'f3e27a'
  local gold_dim = '8a7340'
  local glass = '101816'
  local glow = { '1c3320', '2f7a32', '6adf45', 'b4ff6a', 'e8ffb0' }
  local palettes = {
    { 'd4c6a8', '8a7c62', 'e4d7bb' },
    { 'cbb892', '7d6c4e', 'e6d7b4' },
    { '8b4a3c', '5a2e28', 'b56a5a' },
    { '9aa3a0', '5c6462', 'c5ccc9' },
    { 'e2d6bc', 'a09070', 'f3ead8' },
  }

  local month_names = {
    'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
    'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC',
  }

  local logged_signature = nil

  local function flat_text(cr, label, x, baseline, size, color, alpha, align)
    cairo_select_font_face(cr, font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, size)
    local extents = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, extents)
    if align == 'right' then
      x = x - extents.x_advance
    elseif align == 'center' then
      x = x - extents.x_advance / 2
    end
    shared.set_hex(cr, color, alpha or 1)
    cairo_move_to(cr, x, baseline)
    cairo_show_text(cr, label)
    return extents.x_advance
  end

  local function parse_entries()
    local content = shared.read_file(github_path)
    if not content or not shared.json_boolean(content, 'ok', false) then
      return {}
    end

    local entries = {}
    for _, object in ipairs(shared.json_array_objects(content, 'contributions')) do
      local date = shared.json_string(object, 'date', '')
      local year, month, day = date:match('^(%d+)%-(%d+)%-(%d+)$')
      local level = shared.json_number(object, 'level', 0)
      local count = shared.json_number(object, 'count', nil)
      if not count then
        count = level == 0 and 0 or level * 2
      end
      if year then
        table.insert(entries, {
          year = tonumber(year),
          month = tonumber(month),
          day = tonumber(day),
          level = shared.clamp(level, 0, 4),
          count = count,
        })
      end
    end

    while #entries > weeks_max * columns do
      table.remove(entries, 1)
    end

    return entries
  end

  local function weekday_offset(entry)
    if not entry then
      return 0
    end
    local stamp = os.time({ year = entry.year, month = entry.month, day = entry.day, hour = 12 })
    return (tonumber(os.date('*t', stamp).wday) or 1) - 1
  end

  local function poly(cr, points)
    cairo_move_to(cr, points[1][1], points[1][2])
    for index = 2, #points do
      cairo_line_to(cr, points[index][1], points[index][2])
    end
    cairo_close_path(cr)
  end

  local function lerp(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t }
  end

  local function inset_quad(quad, t)
    local cx = (quad[1][1] + quad[2][1] + quad[3][1] + quad[4][1]) / 4
    local cy = (quad[1][2] + quad[2][2] + quad[3][2] + quad[4][2]) / 4
    local out = {}
    for i = 1, 4 do
      out[i] = { cx + (quad[i][1] - cx) * t, cy + (quad[i][2] - cy) * t }
    end
    return out
  end

  local function rnd(entry, key)
    local n = entry.year * 73 + entry.month * 37 + entry.day * 17
    for i = 1, #key do
      n = (n * 33 + key:byte(i)) % 2147483647
    end
    return (n % 1000) / 1000
  end

  local function gold_edge(cr, a, b, width, color, alpha)
    shared.set_hex(cr, color or gold, alpha or 0.92)
    cairo_set_line_width(cr, width or 1.15)
    cairo_move_to(cr, a[1], a[2])
    cairo_line_to(cr, b[1], b[2])
    cairo_stroke(cr)
  end

  local function prism(cr, base, height, stone, side, topc, use_gold)
    if height <= 0 then
      return { base[1], base[2], base[3], base[4] }
    end
    local top = {}
    for i, point in ipairs(base) do
      top[i] = { point[1], point[2] - height }
    end
    poly(cr, { base[1], base[2], top[2], top[1] })
    shared.set_hex(cr, stone, 0.96)
    cairo_fill(cr)
    poly(cr, { base[2], base[3], top[3], top[2] })
    shared.set_hex(cr, side, 0.96)
    cairo_fill(cr)
    poly(cr, top)
    shared.set_hex(cr, topc, 0.96)
    cairo_fill(cr)
    if use_gold ~= false then
      gold_edge(cr, top[1], top[2], 1.15, gold, 0.92)
      gold_edge(cr, top[2], top[3], 0.8, gold_dim, 0.7)
    end
    return top
  end

  local function facade_windows(cr, base, top, count, level, seed, bay, cols, pitch)
    bay = bay or 0.14
    pitch = pitch or 3.2
    local south_w = math.abs(base[2][1] - base[1][1])
    local south_h = math.abs(base[1][2] - top[1][2])
    if south_w < 3 or south_h < 3 then
      return
    end
    local b0 = lerp(base[1], base[2], bay)
    local b1 = lerp(base[1], base[2], 1 - bay)
    local t0 = lerp(top[1], top[2], bay)
    local t1 = lerp(top[1], top[2], 1 - bay)
    b0 = lerp(b0, t0, 0.08)
    b1 = lerp(b1, t1, 0.08)
    t0 = lerp(b0, t0, 0.92)
    t1 = lerp(b1, t1, 0.92)
    poly(cr, { b0, b1, t1, t0 })
    shared.set_hex(cr, glass, 0.96)
    cairo_fill(cr)
    if not cols then
      if south_w < 8 then cols = 1
      elseif south_w < 16 then cols = 2
      else cols = 3
      end
    end
    local rows = math.max(1, math.floor(south_h / pitch))
    local lit = 0.55 + 0.40 * math.min(1.0, math.sqrt(math.max(count, 1) / 80.0))
    local pane = glow[shared.clamp(level, 0, 4) + 1]
    local pad = 0.18
    for row = 0, rows - 1 do
      for col = 0, cols - 1 do
        if rnd(seed, 'w' .. row .. col) <= lit then
          local u0 = (col + pad) / cols
          local u1 = (col + 1 - pad) / cols
          local v0 = (row + 0.22) / rows
          local v1 = (row + 0.78) / rows
          local p00 = lerp(lerp(b0, b1, u0), lerp(t0, t1, u0), v0)
          local p10 = lerp(lerp(b0, b1, u1), lerp(t0, t1, u1), v0)
          local p11 = lerp(lerp(b0, b1, u1), lerp(t0, t1, u1), v1)
          local p01 = lerp(lerp(b0, b1, u0), lerp(t0, t1, u0), v1)
          poly(cr, { p00, p10, p11, p01 })
          shared.set_hex(cr, pane, 0.95)
          cairo_fill(cr)
        end
      end
    end
  end

  local function pick_kind(entry, height)
    local r = rnd(entry, 'kind')
    if height < 14 then
      if r < 0.55 then return 'house' end
      if r < 0.85 then return 'shop' end
      return 'warehouse'
    end
    if height < 24 then
      if r < 0.45 then return 'walkup' end
      if r < 0.7 then return 'shop' end
      if r < 0.88 then return 'house' end
      return 'gothic'
    end
    if height < 42 then
      if r < 0.4 then return 'office' end
      if r < 0.65 then return 'walkup' end
      if r < 0.85 then return 'setback' end
      return 'glass'
    end
    if height < 72 then
      local kinds = { 'setback', 'office', 'chrysler', 'empire', 'glass' }
      return kinds[math.floor(r * 5) % 5 + 1]
    end
    local kinds = { 'empire', 'chrysler', 'setback', 'slab' }
    return kinds[math.floor(r * 4) % 4 + 1]
  end

  local function pick_palette(entry, kind)
    local r = rnd(entry, 'pal')
    if kind == 'house' or kind == 'shop' or kind == 'warehouse' then
      return palettes[math.floor(r * 5) % 5 + 1]
    end
    if kind == 'gothic' then
      return palettes[4]
    end
    if kind == 'glass' then
      return { '2a4038', '1a2822', '3d5a4c' }
    end
    return palettes[math.floor(r * 3) % 3 + 1]
  end

  local function roof_frame(top)
    local cx = (top[1][1] + top[2][1]) / 2
    local cy = math.min(top[1][2], top[2][2], top[3][2], top[4][2])
    local w = math.max(4.0, math.abs(top[2][1] - top[1][1]))
    return cx, cy, w
  end

  local function pitched_roof(cr, top, rise, side)
    local cx, cy, w = roof_frame(top)
    rise = math.min(rise, w * 0.55)
    local peak = { cx, cy - rise }
    poly(cr, { top[1], top[2], peak })
    shared.set_hex(cr, '6a3a32', 1)
    cairo_fill(cr)
    poly(cr, { top[2], top[3], peak })
    shared.set_hex_shaded(cr, side, 1, -0.15)
    cairo_fill(cr)
    local hx = lerp(top[1], top[2], 0.28)[1]
    cairo_rectangle(cr, hx - 1.4, peak[2] + rise * 0.35, 2.8, rise * 0.28)
    shared.set_hex(cr, '4a322c', 1)
    cairo_fill(cr)
  end

  local function hip_roof(cr, top)
    local cx, cy, w = roof_frame(top)
    local rise = w * 0.38
    local peak = { cx, cy - rise }
    poly(cr, { top[1], top[2], peak })
    shared.set_hex(cr, '7a4a36', 1)
    cairo_fill(cr)
    poly(cr, { top[2], top[3], peak })
    shared.set_hex(cr, '5a3428', 1)
    cairo_fill(cr)
  end

  local function gold_dome(cr, top)
    local cx, cy, w = roof_frame(top)
    local rx = math.max(4.0, w * 0.42)
    local ry = math.max(3.5, math.min(rx * 0.78, w * 0.36))
    cairo_save(cr)
    cairo_translate(cr, cx, cy)
    cairo_scale(cr, 1.0, ry / rx)
    cairo_arc(cr, 0, 0, rx, math.pi, 0)
    cairo_close_path(cr)
    shared.set_hex(cr, gold, 0.95)
    cairo_fill(cr)
    cairo_restore(cr)
    cairo_rectangle(cr, cx - rx * 0.55, cy - 1.5, rx * 1.1, 2.2)
    shared.set_hex(cr, gold_dim, 0.95)
    cairo_fill(cr)
  end

  local function barrel_vault(cr, top)
    local cx, cy, w = roof_frame(top)
    local rx = w * 0.48
    local ry = w * 0.28
    cairo_save(cr)
    cairo_translate(cr, cx, cy)
    cairo_scale(cr, 1.0, ry / rx)
    cairo_arc(cr, 0, 0, rx, math.pi, 0)
    cairo_close_path(cr)
    cairo_restore(cr)
    shared.set_hex(cr, '8a7c62', 1)
    cairo_fill(cr)
  end

  local function water_tank(cr, top)
    local cx, cy, w = roof_frame(top)
    local tw = math.max(5.0, w * 0.42)
    local th = math.max(5.0, tw * 0.72)
    cairo_rectangle(cr, cx - tw / 2, cy - th, tw, th)
    shared.set_hex(cr, '5a6570', 0.95)
    cairo_fill(cr)
    cairo_save(cr)
    cairo_translate(cr, cx, cy - th)
    cairo_scale(cr, 1.0, 0.35)
    cairo_arc(cr, 0, 0, tw / 2, 0, math.pi * 2)
    cairo_restore(cr)
    shared.set_hex(cr, '6a7580', 0.95)
    cairo_fill(cr)
  end

  local function lantern(cr, top)
    local cx, cy, w = roof_frame(top)
    local s = math.max(5.0, w * 0.40)
    cairo_rectangle(cr, cx - s / 2, cy - s, s, s)
    shared.set_hex(cr, gold, 0.95)
    cairo_fill(cr)
    cairo_rectangle(cr, cx - s * 0.28, cy - s * 0.78, s * 0.56, s * 0.42)
    shared.set_hex(cr, '1c3320', 0.95)
    cairo_fill(cr)
    cairo_rectangle(cr, cx - s / 2, cy - s - w * 0.08, s, w * 0.08)
    shared.set_hex(cr, gold_lit, 0.95)
    cairo_fill(cr)
  end

  local function penthouse(cr, top, stone, side)
    local cap = inset_quad(top, 0.58)
    local h = math.max(5.5, math.abs(top[2][1] - top[1][1]) * 0.38)
    local ph = prism(cr, cap, h, stone or palettes[1][1], side or palettes[1][2], palettes[1][3], true)
    facade_windows(cr, cap, ph, 8, 2, { year = 1, month = 1, day = 1 }, 0.16, 2, 4.0)
  end

  local function parapet(cr, top)
    local cx, cy, w = roof_frame(top)
    cairo_rectangle(cr, cx - w / 2, cy - w * 0.12, w, w * 0.12)
    shared.set_hex(cr, gold, 0.92)
    cairo_fill(cr)
    for _, t in ipairs({ 0.08, 0.92 }) do
      local x = cx - w / 2 + w * t
      cairo_rectangle(cr, x - 1.4, cy - w * 0.22, 2.8, w * 0.22)
      shared.set_hex(cr, gold_dim, 0.95)
      cairo_fill(cr)
    end
  end

  local function arcade(cr, top)
    local cx, cy, w = roof_frame(top)
    local n = w < 22 and 3 or 4
    local bw = w / n
    for i = 0, n - 1 do
      local x = cx - w / 2 + (i + 0.5) * bw
      cairo_save(cr)
      cairo_translate(cr, x, cy)
      cairo_scale(cr, 1.0, 0.7)
      cairo_arc(cr, 0, 0, bw * 0.38, math.pi, 0)
      cairo_close_path(cr)
      cairo_restore(cr)
      shared.set_hex(cr, gold, 0.9)
      cairo_fill(cr)
    end
  end

  local function sawtooth(cr, top)
    local cx, cy, w = roof_frame(top)
    local n = w < 20 and 3 or 4
    local bw = w / n
    local h = bw * 0.55
    for i = 0, n - 1 do
      local x0 = cx - w / 2 + i * bw
      poly(cr, { { x0, cy }, { x0 + bw, cy }, { x0 + bw * 0.45, cy - h } })
      shared.set_hex(cr, i % 2 == 0 and '6a6458' or '8a7c62', 1)
      cairo_fill(cr)
    end
  end

  local function billboard(cr, top)
    local cx, cy, w = roof_frame(top)
    local bw = w * 0.72
    local bh = math.max(4.0, w * 0.28)
    cairo_rectangle(cr, cx - bw / 2, cy - bh, bw, bh)
    shared.set_hex(cr, '1a1814', 0.95)
    cairo_fill(cr)
    cairo_rectangle(cr, cx - bw / 2 + 1.2, cy - bh + 1.0, bw - 2.4, bh - 2.0)
    shared.set_hex(cr, '6adf45', 0.55)
    cairo_fill(cr)
  end

  local function hvac_farm(cr, top)
    local cx, cy, w = roof_frame(top)
    for i, t in ipairs({ 0.28, 0.52, 0.76 }) do
      local x = cx - w / 2 + w * t
      local bw = math.max(3.2, w * 0.18)
      local bh = bw * (0.7 + 0.15 * ((i - 1) % 2))
      cairo_rectangle(cr, x - bw / 2, cy - bh, bw, bh)
      shared.set_hex(cr, i ~= 2 and '4a5560' or '5a6570', 0.95)
      cairo_fill(cr)
    end
  end

  local function mansard(cr, top)
    local cx, cy, w = roof_frame(top)
    local h = w * 0.42
    local inset = w * 0.22
    poly(cr, {
      { cx - w / 2, cy }, { cx + w / 2, cy },
      { cx + w / 2 - inset, cy - h }, { cx - w / 2 + inset, cy - h },
    })
    shared.set_hex(cr, '5c4030', 1)
    cairo_fill(cr)
    cairo_rectangle(cr, cx - w / 2 + inset, cy - h - w * 0.08, w - 2 * inset, w * 0.08)
    shared.set_hex(cr, gold, 0.92)
    cairo_fill(cr)
  end

  local function chrysler_crown(cr, top, height)
    local cx, cy, w = roof_frame(top)
    local h = math.max(6.0, math.min(w * 0.55, height * 0.10))
    for i, t in ipairs({ 1.0, 0.68, 0.40 }) do
      local hw = w * 0.48 * t
      local y0 = cy - (i - 1) * (h / 2.6)
      poly(cr, {
        { cx - hw, y0 }, { cx + hw, y0 },
        { cx + hw * 0.55, y0 - h / 2.8 }, { cx - hw * 0.55, y0 - h / 2.8 },
      })
      shared.set_hex(cr, i == 1 and gold_dim or gold, 0.95)
      cairo_fill(cr)
    end
    local s = math.max(4.0, w * 0.24)
    cairo_rectangle(cr, cx - s / 2, cy - h - s * 0.15, s, s * 0.65)
    shared.set_hex(cr, gold, 0.95)
    cairo_fill(cr)
  end

  local function empire_cap(cr, top)
    local cap = inset_quad(top, 0.62)
    local h1 = math.max(5.0, math.abs(top[2][1] - top[1][1]) * 0.28)
    local mid = prism(cr, cap, h1, palettes[1][1], palettes[1][2], palettes[1][3], true)
    facade_windows(cr, cap, mid, 6, 2, { year = 2, month = 1, day = 1 }, 0.18, 2, 3.8)
    lantern(cr, mid)
  end

  local function crown(cr, top, height, entry, kind, stone, side)
    if kind == 'house' then
      return
    elseif kind == 'warehouse' then
      water_tank(cr, top)
    elseif kind == 'gothic' then
      hip_roof(cr, top)
    elseif kind == 'chrysler' then
      chrysler_crown(cr, top, height)
    elseif kind == 'empire' then
      empire_cap(cr, top)
    elseif kind == 'slab' then
      penthouse(cr, top, stone, side)
    elseif kind == 'glass' then
      hvac_farm(cr, top)
    elseif kind == 'shop' or height < 14 then
      parapet(cr, top)
    else
      local pick = math.floor(rnd(entry, 'crown') * 9)
      if pick == 0 then penthouse(cr, top, stone, side)
      elseif pick == 1 then lantern(cr, top)
      elseif pick == 2 then hip_roof(cr, top)
      elseif pick == 3 then gold_dome(cr, top)
      elseif pick == 4 then barrel_vault(cr, top)
      elseif pick == 5 then mansard(cr, top)
      elseif pick == 6 then arcade(cr, top)
      elseif pick == 7 then sawtooth(cr, top)
      else billboard(cr, top)
      end
    end
  end

  local function stages_for(kind, height)
    if kind == 'house' or kind == 'shop' or kind == 'warehouse'
        or kind == 'walkup' or kind == 'gothic' then
      return { { 1.00, 1.00 } }
    end
    if kind == 'glass' then
      return { { 0.92, 1.00 } }
    end
    if kind == 'office' then
      if height >= 28 then return { { 1.00, 0.86 }, { 0.82, 1.00 } } end
      return { { 1.00, 1.00 } }
    end
    if kind == 'slab' then
      return { { 0.62, 0.78 }, { 0.44, 1.00 } }
    end
    if kind == 'chrysler' then
      return { { 1.00, 0.72 }, { 0.78, 0.90 }, { 0.52, 1.00 } }
    end
    if kind == 'empire' then
      return { { 1.00, 0.62 }, { 0.80, 0.78 }, { 0.62, 0.90 }, { 0.42, 1.00 } }
    end
    if height < 32 then
      return { { 1.00, 0.80 }, { 0.80, 1.00 } }
    end
    if height < 60 then
      return { { 1.00, 0.74 }, { 0.82, 0.90 }, { 0.62, 1.00 } }
    end
    return { { 1.00, 0.70 }, { 0.84, 0.84 }, { 0.68, 0.93 }, { 0.50, 1.00 } }
  end

  local function draw_building(cr, base, height, entry)
    if height < 1.4 then
      poly(cr, base)
      shared.set_hex(cr, '16161c', 0.9)
      cairo_fill_preserve(cr)
      shared.set_hex(cr, gold_dim, 0.35)
      cairo_set_line_width(cr, 0.6)
      cairo_stroke(cr)
      return
    end

    local kind = pick_kind(entry, height)
    local pal = pick_palette(entry, kind)
    local stone, side, topc = pal[1], pal[2], pal[3]
    local slim = 0.70 + 0.28 * rnd(entry, 'w')
    if kind == 'slab' then
      slim = 0.55
    elseif kind == 'house' or kind == 'shop' or kind == 'warehouse' then
      slim = 0.88 + 0.10 * rnd(entry, 'w')
    elseif kind == 'empire' then
      slim = 0.78
    end
    base = inset_quad(base, slim)

    local stages = stages_for(kind, height)
    local prev = 0
    local top
    local first = true
    local gold_trim = not (kind == 'house' or kind == 'warehouse' or kind == 'gothic')
    local cols
    if kind == 'house' or kind == 'gothic' then
      cols = 1
    elseif kind == 'shop' or kind == 'warehouse' or kind == 'walkup' then
      cols = 2
    end
    local pitch = (kind == 'house' or kind == 'shop') and 4.6 or 3.2
    local bay = (kind == 'house' or kind == 'shop') and 0.18 or 0.14

    for _, stage in ipairs(stages) do
      local inset, frac = stage[1], stage[2]
      local h = height * frac
      local slab = h - prev
      local slab_base = {}
      local inset_base = inset_quad(base, inset)
      for i, p in ipairs(inset_base) do
        slab_base[i] = { p[1], p[2] - prev }
      end
      top = prism(cr, slab_base, slab, stone, side, topc, gold_trim)
      if first then
        local wt = math.min(4.0, slab * 0.10)
        poly(cr, {
          slab_base[1], slab_base[2],
          { slab_base[2][1], slab_base[2][2] - wt },
          { slab_base[1][1], slab_base[1][2] - wt },
        })
        shared.set_hex(cr, side, 0.7)
        cairo_fill(cr)
        if kind == 'shop' then
          local aw = math.min(5.0, slab * 0.18)
          poly(cr, {
            slab_base[1], slab_base[2],
            { slab_base[2][1], slab_base[2][2] - aw },
            { slab_base[1][1], slab_base[1][2] - aw },
          })
          shared.set_hex(cr, '2a1c14', 0.9)
          cairo_fill(cr)
        end
        first = false
      end
      facade_windows(cr, slab_base, top, entry.count, entry.level, entry, bay, cols, pitch)
      prev = h
    end

    if kind == 'house' then
      pitched_roof(cr, top, math.max(6.0, height * 0.28), side)
    else
      crown(cr, top, height, entry, kind, stone, side)
    end
  end

  local function draw_deck(cr, geo)
    local pad = geo.week * (1 - fill) / 2
    local front_l = { geo.x - pad, geo.y }
    local front_r = { geo.x + geo.weeks * geo.week + pad, geo.y }
    local back_r = { front_r[1] + columns * geo.day_dx, geo.y - columns * geo.day_dy }
    local back_l = { front_l[1] + columns * geo.day_dx, back_r[2] }

    local function drop(point)
      return { point[1], point[2] + geo.deck }
    end

    poly(cr, { front_l, front_r, drop(front_r), drop(front_l) })
    shared.set_hex_shaded(cr, '0c0c10', 0.94, -0.2)
    cairo_fill(cr)

    poly(cr, { front_r, back_r, drop(back_r), drop(front_r) })
    shared.set_hex(cr, '08080c', 0.94)
    cairo_fill(cr)

    poly(cr, { front_l, front_r, back_r, back_l })
    shared.set_hex(cr, '14141a', 0.90)
    cairo_fill(cr)

    gold_edge(cr, front_l, front_r, 1.3, gold, 0.88)
    gold_edge(cr, drop(front_l), drop(front_r), 1.0, gold_dim, 0.7)
  end

  local function geometry(entries, width, height)
    local offset = weekday_offset(entries[1])
    local weeks = math.ceil((offset + #entries) / columns)
    local steps = weeks + (1 - fill) + columns * day_dx_ratio
    local week = width / steps
    local day_dx = week * day_dx_ratio
    local day_dy = week * day_dy_ratio
    local deck = week * deck_ratio

    local busiest = 0
    for _, entry in ipairs(entries) do
      if entry.count > busiest then
        busiest = entry.count
      end
    end

    local headroom = height - deck - columns * day_dy
    if headroom < 20 then
      headroom = 20
    end

    return {
      offset = offset,
      weeks = weeks,
      week = week,
      day_dx = day_dx,
      day_dy = day_dy,
      deck = deck,
      busiest = busiest,
      unit = busiest > 0 and headroom / math.sqrt(busiest) or 0,
    }
  end

  local function tower_height(geo, count)
    if count <= 0 then
      return 0
    end
    return geo.unit * math.sqrt(count)
  end

  local function cell_origin(geo, week, day)
    return geo.x + week * geo.week + day * geo.day_dx,
           geo.y - day * geo.day_dy
  end

  local function footprint(geo, week, day)
    local x, y = cell_origin(geo, week, day)
    local wx = geo.week * fill
    local dx = geo.day_dx * fill
    local dy = geo.day_dy * fill
    return {
      { x, y },
      { x + wx, y },
      { x + wx + dx, y - dy },
      { x + dx, y - dy },
    }
  end

  local function draw_skyline(cr, entries, geo)
    draw_deck(cr, geo)

    for day = columns - 1, 0, -1 do
      for week = 0, geo.weeks - 1 do
        local index = week * columns + day - geo.offset + 1
        local entry = entries[index]
        if entry then
          local base = footprint(geo, week, day)
          if entry.count > 0 then
            draw_building(cr, base, tower_height(geo, entry.count), entry)
          else
            poly(cr, base)
            shared.set_hex(cr, '16161c', 0.42)
            cairo_set_line_width(cr, 0.8)
            cairo_stroke(cr)
          end
        end
      end
    end

    local seen = {}
    for week = 0, geo.weeks - 1 do
      local entry = entries[week * columns - geo.offset + 1]
      if entry and entry.day <= 7 and not seen[entry.month] then
        seen[entry.month] = true
        local x = cell_origin(geo, week, 0)
        flat_text(cr, month_names[entry.month], x + 3, geo.y + geo.deck - 4, 6.6, gold_dim, 0.85)
      end
    end
  end

  local function log_geometry(entries, geo)
    local signature = string.format('%d/%.1f/%.1f', #entries, geo.week, geo.unit)
    if signature == logged_signature then
      return
    end
    logged_signature = signature

    local log_file = io.open(log_path, 'a')
    if not log_file then
      return
    end
    log_file:write(string.format(
      '[%s] github-tracker-renderer: city days=%d weeks=%d week_px=%.1f busiest=%d deck=%.1f\n',
      os.date('!%Y-%m-%dT%H:%M:%SZ'), #entries, geo.weeks, geo.week, geo.busiest, geo.deck))
    log_file:close()
  end

  local function draw()
    local surface, should_destroy_surface = shared.create_surface()
    if not surface then
      return
    end

    local cr = cairo_create(surface)
    local entries = parse_entries()
    if #entries == 0 then
      cairo_destroy(cr)
      if should_destroy_surface and cairo_surface_destroy then
        cairo_surface_destroy(surface)
      end
      return
    end

    local width = conky_window.width - window_inset * 2
    local height = conky_window.height - window_inset * 2
    local geo = geometry(entries, width, height)
    geo.x = window_inset
    geo.y = conky_window.height - window_inset - geo.deck

    draw_skyline(cr, entries, geo)
    log_geometry(entries, geo)

    cairo_destroy(cr)
    if should_destroy_surface and cairo_surface_destroy then
      cairo_surface_destroy(surface)
    end
  end

  return {
    draw = draw,
  }
end
