import cairo, sys

ops_file, out_png = sys.argv[1], sys.argv[2]
W, H = 1920, 700
surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
cr = cairo.Context(surf)

# Stand-in wallpaper so panel translucency reads honestly.
g = cairo.LinearGradient(0, 0, W, H)
g.add_color_stop_rgb(0, 0.20, 0.17, 0.26)
g.add_color_stop_rgb(1, 0.36, 0.30, 0.33)
cr.set_source(g)
cr.paint()

cr.select_font_face('JetBrains Mono', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
cr.set_font_size(15)
adv = cr.text_extents('MMMMMMMMMM').x_advance / 10 / 15
print(f'JetBrains Mono advance/em = {adv:.3f} (stub assumes 0.600)')

pats = {}
for line in open(ops_file):
    line = line.rstrip('\n')
    if not line:
        continue
    p = line.split('\t')
    op = p[0]
    f = lambda i: float(p[i])
    if op == 'move_to': cr.move_to(f(1), f(2))
    elif op == 'line_to': cr.line_to(f(1), f(2))
    elif op == 'rectangle': cr.rectangle(f(1), f(2), f(3), f(4))
    elif op == 'arc': cr.arc(f(1), f(2), f(3), f(4), f(5))
    elif op == 'new_sub_path': cr.new_sub_path()
    elif op == 'close_path': cr.close_path()
    elif op == 'fill': cr.fill()
    elif op == 'fill_preserve': cr.fill_preserve()
    elif op == 'stroke': cr.stroke()
    elif op == 'clip': cr.clip()
    elif op == 'save': cr.save()
    elif op == 'restore': cr.restore()
    elif op == 'line_width': cr.set_line_width(f(1))
    elif op == 'rgba': cr.set_source_rgba(f(1), f(2), f(3), f(4))
    elif op == 'antialias':
        cr.set_antialias(cairo.ANTIALIAS_NONE if int(f(1)) == 1 else cairo.ANTIALIAS_DEFAULT)
    elif op == 'font_face':
        cr.select_font_face(
            p[1], cairo.FONT_SLANT_NORMAL,
            cairo.FONT_WEIGHT_BOLD if int(p[3]) == 1 else cairo.FONT_WEIGHT_NORMAL,
        )
    elif op == 'font_size': cr.set_font_size(f(1))
    elif op == 'show_text': cr.show_text(p[1] if len(p) > 1 else '')
    elif op == 'pattern': pats[p[1]] = cairo.LinearGradient(f(2), f(3), f(4), f(5))
    elif op == 'stop': pats[p[1]].add_color_stop_rgba(f(2), f(3), f(4), f(5), f(6))
    elif op == 'source_pattern': cr.set_source(pats[p[1]])
    elif op == 'pattern_destroy': pats.pop(p[1], None)
    else: raise SystemExit('unknown op: ' + op)

surf.write_to_png(out_png)
print('wrote', out_png)
