import cairo
import sys

ops_file, out_png, width, height = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
cr = cairo.Context(surface)
cr.set_operator(cairo.OPERATOR_SOURCE)
cr.set_source_rgba(0, 0, 0, 0)
cr.paint()
cr.set_operator(cairo.OPERATOR_OVER)

patterns = {}
for line in open(ops_file):
    line = line.rstrip('\n')
    if not line:
        continue
    fields = line.split('\t')
    op = fields[0]
    number = lambda index: float(fields[index])
    if op == 'move_to': cr.move_to(number(1), number(2))
    elif op == 'line_to': cr.line_to(number(1), number(2))
    elif op == 'curve_to': cr.curve_to(number(1), number(2), number(3), number(4), number(5), number(6))
    elif op == 'rectangle': cr.rectangle(number(1), number(2), number(3), number(4))
    elif op == 'arc': cr.arc(number(1), number(2), number(3), number(4), number(5))
    elif op == 'arc_negative': cr.arc_negative(number(1), number(2), number(3), number(4), number(5))
    elif op == 'new_path': cr.new_path()
    elif op == 'new_sub_path': cr.new_sub_path()
    elif op == 'close_path': cr.close_path()
    elif op == 'fill': cr.fill()
    elif op == 'fill_preserve': cr.fill_preserve()
    elif op == 'stroke': cr.stroke()
    elif op == 'clip': cr.clip()
    elif op == 'save': cr.save()
    elif op == 'restore': cr.restore()
    elif op == 'line_width': cr.set_line_width(number(1))
    elif op == 'line_cap':
        cr.set_line_cap(cairo.LINE_CAP_ROUND if int(number(1)) == 1 else cairo.LINE_CAP_BUTT)
    elif op == 'rgba': cr.set_source_rgba(number(1), number(2), number(3), number(4))
    elif op == 'antialias':
        cr.set_antialias(cairo.ANTIALIAS_NONE if int(number(1)) == 1 else cairo.ANTIALIAS_DEFAULT)
    elif op == 'font_face':
        cr.select_font_face(
            fields[1], cairo.FONT_SLANT_NORMAL,
            cairo.FONT_WEIGHT_BOLD if int(fields[3]) == 1 else cairo.FONT_WEIGHT_NORMAL,
        )
    elif op == 'font_size': cr.set_font_size(number(1))
    elif op == 'show_text': cr.show_text(fields[1] if len(fields) > 1 else '')
    elif op == 'pattern': patterns[fields[1]] = cairo.LinearGradient(number(2), number(3), number(4), number(5))
    elif op == 'stop': patterns[fields[1]].add_color_stop_rgba(number(2), number(3), number(4), number(5), number(6))
    elif op == 'source_pattern': cr.set_source(patterns[fields[1]])
    elif op == 'pattern_destroy': patterns.pop(fields[1], None)
    else: raise SystemExit('unknown op: ' + op)

surface.write_to_png(out_png)
print('wrote', out_png)
