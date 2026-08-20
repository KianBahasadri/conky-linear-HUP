import cairo
import math
import os

HERE = os.path.dirname(__file__)
FONT = 'JetBrains Mono'


def rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))


def shaded(value, shade=0):
    red, green, blue = rgb(value)
    if shade > 0:
        return (
            red + (1 - red) * shade,
            green + (1 - green) * shade,
            blue + (1 - blue) * shade,
        )
    if shade < 0:
        amount = 1 + shade
        return red * amount, green * amount, blue * amount
    return red, green, blue


def set_hex(cr, value, alpha=1, shade=0):
    cr.set_source_rgba(*shaded(value, shade), alpha)


def rounded_rect(cr, x, y, width, height, radius):
    degrees = math.pi / 180
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -90 * degrees, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, 90 * degrees)
    cr.arc(x + radius, y + height - radius, radius, 90 * degrees, 180 * degrees)
    cr.arc(x + radius, y + radius, radius, 180 * degrees, 270 * degrees)
    cr.close_path()


def gradient(x0, y0, x1, y1, stops):
    pattern = cairo.LinearGradient(x0, y0, x1, y1)
    for offset, color, alpha, *shade in stops:
        pattern.add_color_stop_rgba(offset, *shaded(color, shade[0] if shade else 0), alpha)
    return pattern


def draw_wallpaper(cr, width, height):
    base = cairo.LinearGradient(0, 0, width, height)
    base.add_color_stop_rgb(0, 0.105, 0.085, 0.145)
    base.add_color_stop_rgb(0.48, 0.205, 0.165, 0.235)
    base.add_color_stop_rgb(1, 0.305, 0.245, 0.265)
    cr.set_source(base)
    cr.paint()

    glow = cairo.RadialGradient(width * 0.70, height * 0.32, 10,
                                width * 0.70, height * 0.32, width * 0.62)
    glow.add_color_stop_rgba(0, 0.30, 0.16, 0.42, 0.22)
    glow.add_color_stop_rgba(0.56, 0.08, 0.28, 0.35, 0.08)
    glow.add_color_stop_rgba(1, 0, 0, 0, 0)
    cr.set_source(glow)
    cr.paint()

    cr.set_line_width(1)
    for x in range(0, width, 64):
        cr.set_source_rgba(0.65, 0.75, 0.95, 0.018)
        cr.move_to(x + 0.5, 0)
        cr.line_to(x + 0.5, height)
        cr.stroke()
    for y in range(0, height, 64):
        cr.set_source_rgba(0.65, 0.75, 0.95, 0.014)
        cr.move_to(0, y + 0.5)
        cr.line_to(width, y + 0.5)
        cr.stroke()


def text_width(cr, label, size, weight=cairo.FONT_WEIGHT_BOLD):
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    return cr.text_extents(label).x_advance


def lit_text(cr, label, x, baseline, size, color='f8fafc', alpha=1,
             weight=cairo.FONT_WEIGHT_BOLD, relief='soft', align='left'):
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    advance = cr.text_extents(label).x_advance
    if align == 'right':
        x -= advance
    elif align == 'center':
        x -= advance / 2

    profiles = {
        'soft': (0, [(0.00, 0.50), (0.30, 0.26), (0.62, 0.02), (1.00, -0.22)]),
        'raised': (0.55, [(0.00, 0.85), (0.13, 0.60), (0.40, 0.14),
                          (0.70, -0.06), (1.00, -0.40)]),
    }
    contact, profile = profiles[relief]
    if contact:
        set_hex(cr, '000000', 0.5 * contact)
        cr.move_to(x, baseline + 2)
        cr.show_text(label)
    set_hex(cr, '000000', 0.5)
    cr.move_to(x, baseline + 1)
    cr.show_text(label)

    stops = [(offset, color, alpha, shade) for offset, shade in profile]
    cr.set_source(gradient(x, baseline - size * 0.70, x, baseline + size * 0.06, stops))
    cr.move_to(x, baseline)
    cr.show_text(label)


def flat_text(cr, label, x, baseline, size, color='f8fafc', alpha=1,
              weight=cairo.FONT_WEIGHT_BOLD, align='left'):
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    advance = cr.text_extents(label).x_advance
    if align == 'right':
        x -= advance
    elif align == 'center':
        x -= advance / 2
    set_hex(cr, color, alpha)
    cr.move_to(x, baseline)
    cr.show_text(label)


def panel_frame(cr, x, y, width, height, accent='00e5ff', secondary='8b5cf6'):
    rounded_rect(cr, x + 4, y + 7, width, height, 18)
    set_hex(cr, accent, 0.10)
    cr.fill()

    rounded_rect(cr, x + 2, y + 3, width, height, 18)
    set_hex(cr, accent, 0.15)
    cr.set_line_width(8)
    cr.stroke()

    rounded_rect(cr, x + 1, y + 2, width, height, 18)
    set_hex(cr, secondary, 0.22)
    cr.set_line_width(4)
    cr.stroke()

    rounded_rect(cr, x, y, width, height, 18)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, '0d1a30', 0.88),
        (0.06, '050d1c', 0.82),
        (0.80, '020617', 0.80),
        (1.00, '08111f', 0.85),
    ]))
    cr.fill_preserve()
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, accent, 1.00, 0.40),
        (0.40, accent, 0.80),
        (1.00, accent, 0.95, 0.08),
    ]))
    cr.set_line_width(2)
    cr.stroke()

    rounded_rect(cr, x + 8, y + 8, width - 16, height - 16, 12)
    cr.set_source(gradient(x, y + 8, x, y + height - 8, [
        (0.00, 'c4b5fd', 0.42),
        (0.35, secondary, 0.24),
        (1.00, secondary, 0.10),
    ]))
    cr.set_line_width(1)
    cr.stroke()


def chip_width(cr, label, size=12, padding=20):
    return text_width(cr, label, size) + padding


def chip(cr, label, color, x, y, size=12, height=20, padding=20):
    width = chip_width(cr, label, size, padding)
    radius = 6
    rounded_rect(cr, x + 0.5, y + 2, width, height, radius)
    set_hex(cr, '000000', 0.34)
    cr.fill()
    rounded_rect(cr, x, y + 1, width, height, radius)
    set_hex(cr, '000000', 0.28)
    cr.fill()

    rounded_rect(cr, x, y, width, height, radius)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, color, 0.94, -0.58),
        (0.20, color, 0.95, -0.86),
        (0.66, '020617', 0.95),
        (1.00, color, 0.94, -0.76),
    ]))
    cr.fill()

    cr.save()
    rounded_rect(cr, x, y, width, height, radius)
    cr.clip()
    rounded_rect(cr, x + 3, y + 2, width - 6, height * 0.42, 4)
    cr.set_source(gradient(x, y, x + width, y, [
        (0.00, 'ffffff', 0.00),
        (0.12, 'ffffff', 0.11),
        (0.62, 'ffffff', 0.05),
        (1.00, 'ffffff', 0.00),
    ]))
    cr.fill()
    cr.restore()

    rounded_rect(cr, x, y, width, height, radius)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, color, 0.95, 0.45),
        (0.50, color, 0.74),
        (1.00, color, 0.88, 0.12),
    ]))
    cr.set_line_width(1.5)
    cr.stroke()
    lit_text(cr, label, x + padding / 2, y + height * 0.75, size, color)
    return width


def title_chips(cr, specs, x, y, width):
    gap = 7
    widths = [chip_width(cr, label, size, 20) for label, color, size in specs]
    cursor = x + (width - sum(widths) - gap * (len(widths) - 1)) / 2
    for (label, color, size), item_width in zip(specs, widths):
        chip(cr, label, color, cursor, y - 9, size=size, height=20, padding=20)
        cursor += item_width + gap


def divider(cr, x1, x2, y, color='8b5cf6', alpha=0.20):
    cr.set_source(gradient(x1, y, x2, y, [
        (0.00, color, 0.00),
        (0.12, color, alpha),
        (0.88, color, alpha),
        (1.00, color, 0.00),
    ]))
    cr.set_line_width(1)
    cr.move_to(x1, y + 0.5)
    cr.line_to(x2, y + 0.5)
    cr.stroke()


def tube(cr, x, y, width, used, accent, secondary, pace=None, forecast=None,
         forecast_color='f8fafc', height=8):
    radius = height / 2
    fill_width = width * max(0, min(100, used)) / 100
    rounded_rect(cr, x + 0.5, y + 2, width, height, radius)
    set_hex(cr, '000000', 0.38)
    cr.fill()
    rounded_rect(cr, x, y + 1, width, height, radius)
    set_hex(cr, '000000', 0.30)
    cr.fill()

    rounded_rect(cr, x, y, width, height, radius)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, '32415c', 0.95),
        (0.16, '0b1424', 0.96),
        (0.55, '01040c', 0.97),
        (0.86, '060d1a', 0.96),
        (1.00, '1b2942', 0.95),
    ]))
    cr.fill()

    cr.save()
    rounded_rect(cr, x, y, width, height, radius)
    cr.clip()

    cr.rectangle(x, y, width, height * 0.55)
    cr.set_source(gradient(x, y, x, y + height * 0.55, [
        (0.00, '000000', 0.45),
        (1.00, '000000', 0.00),
    ]))
    cr.fill()

    if fill_width > 0:
        active_width = max(height, fill_width)
        rounded_rect(cr, x, y, active_width, height, radius)
        cr.set_source(gradient(x, y, x, y + height, [
            (0.00, accent, 1, -0.38),
            (0.18, accent, 1, 0.46),
            (0.34, accent, 1, 0.10),
            (0.52, accent, 1),
            (0.84, accent, 1, -0.52),
            (0.94, accent, 1, -0.56),
            (1.00, accent, 1, -0.18),
        ]))
        cr.fill()
        if height < fill_width < width - 1:
            cr.set_source(gradient(x, y, x, y + height, [
                (0.00, accent, 0.00, 0.70),
                (0.35, accent, 0.90, 0.85),
                (1.00, accent, 0.10, 0.40),
            ]))
            cr.set_line_width(1)
            cr.move_to(x + active_width - 1, y)
            cr.line_to(x + active_width - 1, y + height)
            cr.stroke()

    if forecast is not None and forecast > used:
        forecast_width = width * min(100, forecast) / 100
        cr.rectangle(x + fill_width, y, max(0, forecast_width - fill_width), height)
        cr.set_source(gradient(x + fill_width, y, x + forecast_width, y, [
            (0.00, accent, 0.25),
            (0.82, accent, 0.15),
            (1.00, accent, 0.04),
        ]))
        cr.fill()
        marker_x = round(x + forecast_width)
        cr.set_source(gradient(marker_x, y, marker_x, y + height, [
            (0.00, forecast_color, 0.26),
            (0.45, forecast_color, 0.90),
            (1.00, forecast_color, 0.26),
        ]))
        cr.rectangle(marker_x, y, 1, height)
        cr.fill()

    for index in (1, 2, 3):
        tick_x = x + index * width / 4
        cr.set_source(gradient(x, y, x, y + height, [
            (0.00, secondary, 0.04),
            (0.45, secondary, 0.30),
            (1.00, secondary, 0.04),
        ]))
        cr.set_line_width(1)
        cr.move_to(tick_x, y)
        cr.line_to(tick_x, y + height)
        cr.stroke()

    streak_height = max(1.2, height * 0.17)
    rounded_rect(cr, x + radius * 0.8, y + height * 0.13,
                 width - radius * 1.6, streak_height, streak_height / 2)
    cr.set_source(gradient(x, y, x + width, y, [
        (0.00, 'ffffff', 0.00),
        (0.09, 'ffffff', 0.13),
        (0.55, 'ffffff', 0.08),
        (0.92, 'ffffff', 0.03),
        (1.00, 'ffffff', 0.00),
    ]))
    cr.fill()

    rounded_rect(cr, x, y, width, height, radius)
    cr.set_source(gradient(x, y, x + width, y, [
        (0.00, '000000', 0.34),
        (0.05, '000000', 0.00),
        (0.95, '000000', 0.00),
        (1.00, '000000', 0.30),
    ]))
    cr.fill()

    if pace is not None:
        marker_x = round(x + width * max(0, min(100, pace)) / 100)
        cr.set_source(gradient(marker_x, y, marker_x, y + height, [
            (0.00, 'ff9f1c', 0.35),
            (0.45, 'ff9f1c', 0.96),
            (1.00, 'ff9f1c', 0.35),
        ]))
        cr.rectangle(marker_x, y, 1, height)
        cr.fill()
    cr.restore()

    rounded_rect(cr, x, y, width, height, radius)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, accent, 0.62, 0.45),
        (0.45, accent, 0.20),
        (1.00, accent, 0.45, 0.20),
    ]))
    cr.set_line_width(1)
    cr.stroke()


PROVIDERS = {
    'AWS': ('ffb454', 'b45309'),
    'AZURE': ('38bdf8', '2563eb'),
    'OPENROUTER': ('a78bfa', '6d28d9'),
    'ANTHROPIC': ('ff8f73', 'c85f49'),
}


def budget_row(cr, x, baseline, width, name, amount, used, forecast, cap,
               eom, pace=61, lower=None):
    accent, secondary = PROVIDERS[name]
    lit_text(cr, name, x, baseline, 12, accent, relief='raised')
    lit_text(cr, amount, x + width, baseline, 12, 'f8fafc', align='right')
    tube(cr, x, baseline + 10, width, used, accent, secondary,
         pace=pace, forecast=forecast)
    detail = lower or f'BUDGET ${cap:.0f}  ·  EOM ${eom:.2f}'
    flat_text(cr, detail, x, baseline + 31, 8, accent, 0.74,
              weight=cairo.FONT_WEIGHT_NORMAL)
    flat_text(cr, f'{used:.0f}% USED', x + width, baseline + 31, 8, '94a3b8', 0.72,
              weight=cairo.FONT_WEIGHT_NORMAL, align='right')


def credit_row(cr, x, baseline, width):
    name = 'OPENROUTER'
    accent, secondary = PROVIDERS[name]
    lit_text(cr, name, x, baseline, 12, accent, relief='raised')
    lit_text(cr, '$12.44 LEFT', x + width, baseline, 12, 'f8fafc', align='right')
    tube(cr, x, baseline + 10, width, 50, accent, secondary, pace=None, forecast=None)
    flat_text(cr, 'CREDIT RESERVE  ·  -$0.43/D', x, baseline + 31, 8, accent, 0.76,
              weight=cairo.FONT_WEIGHT_NORMAL)
    flat_text(cr, '29D RUNWAY', x + width, baseline + 31, 8, '39ff88', 0.90,
              align='right')


def draw_balanced(cr, x, y):
    width, height = 424, 328
    panel_frame(cr, x, y, width, height)
    title_chips(cr, [
        ('SPEND WATCH', '00e5ff', 12),
        ('AUG', '8b5cf6', 12),
        ('SAFE', '39ff88', 12),
    ], x, y, width)

    flat_text(cr, 'TRACKED MTD', x + 24, y + 38, 8, '94a3b8', 0.76)
    lit_text(cr, '$18.72', x + 24, y + 64, 23, '00e5ff')
    flat_text(cr, 'EOM FORECAST', x + 206, y + 38, 8, '94a3b8', 0.76)
    lit_text(cr, '$31.40', x + 206, y + 64, 23, 'a78bfa')
    divider(cr, x + 18, x + width - 18, y + 78)

    row_x, row_width = x + 24, width - 48
    budget_row(cr, row_x, y + 99, row_width, 'AWS', '$8.41 / $25.00',
               33.6, 52.8, 25, 13.20)
    budget_row(cr, row_x, y + 147, row_width, 'AZURE', '$4.27 / $20.00',
               21.4, 35.5, 20, 7.10)
    credit_row(cr, row_x, y + 195, row_width)
    budget_row(cr, row_x, y + 243, row_width, 'ANTHROPIC', '$6.04 / $20.00',
               30.2, 50.5, 20, 10.10)

    divider(cr, x + 18, x + width - 18, y + 287)
    flat_text(cr, '4/4 LIVE', x + 24, y + 311, 8, '39ff88', 0.90)
    flat_text(cr, 'OLDEST AWS 9H  ·  NEXT 30M', x + width - 24, y + 311,
              8, '94a3b8', 0.66, weight=cairo.FONT_WEIGHT_NORMAL, align='right')
    return width, height


def compact_row(cr, x, baseline, width, name, amount, used, forecast=None, pace=61,
                detail=''):
    accent, secondary = PROVIDERS[name]
    lit_text(cr, name, x, baseline, 10, accent, relief='raised')
    bar_x = x + 88
    bar_width = width - 178
    tube(cr, bar_x, baseline - 7, bar_width, used, accent, secondary,
         pace=pace, forecast=forecast, height=8)
    lit_text(cr, amount, x + width, baseline, 10, 'f8fafc', align='right')
    if detail:
        flat_text(cr, detail, bar_x, baseline + 12, 7, accent, 0.68,
                  weight=cairo.FONT_WEIGHT_NORMAL)


def draw_compact(cr, x, y):
    width, height = 424, 242
    panel_frame(cr, x, y, width, height)
    title_chips(cr, [
        ('SPEND', '00e5ff', 12),
        ('AUG', '8b5cf6', 12),
        ('SAFE', '39ff88', 12),
    ], x, y, width)

    flat_text(cr, 'MTD', x + 24, y + 39, 8, '94a3b8', 0.72)
    lit_text(cr, '$18.72', x + 54, y + 39, 15, '00e5ff')
    flat_text(cr, 'EOM', x + 226, y + 39, 8, '94a3b8', 0.72)
    lit_text(cr, '$31.40', x + width - 24, y + 39, 15, 'a78bfa', align='right')
    divider(cr, x + 18, x + width - 18, y + 55)

    row_x, row_width = x + 24, width - 48
    compact_row(cr, row_x, y + 79, row_width, 'AWS', '$8.41', 33.6, 52.8,
                detail='EOM $13.20')
    compact_row(cr, row_x, y + 116, row_width, 'AZURE', '$4.27', 21.4, 35.5,
                detail='EOM $7.10')
    compact_row(cr, row_x, y + 153, row_width, 'OPENROUTER', '$12.44', 50,
                forecast=None, pace=None, detail='29D LEFT')
    compact_row(cr, row_x, y + 190, row_width, 'ANTHROPIC', '$6.04', 30.2, 50.5,
                detail='EOM $10.10')

    divider(cr, x + 18, x + width - 18, y + 211)
    flat_text(cr, '4/4 LIVE  ·  AWS DATA 9H OLD  ·  NEXT 30M',
              x + width / 2, y + 229, 7.5, '94a3b8', 0.70,
              weight=cairo.FONT_WEIGHT_NORMAL, align='center')
    return width, height


def mini_card(cr, x, y, width, height, name, primary, secondary_text, color, points):
    rounded_rect(cr, x, y, width, height, 10)
    cr.set_source(gradient(x, y, x, y + height, [
        (0.00, color, 0.13, -0.50),
        (0.18, '07101f', 0.70),
        (1.00, '020617', 0.58),
    ]))
    cr.fill_preserve()
    set_hex(cr, color, 0.36)
    cr.set_line_width(1)
    cr.stroke()
    lit_text(cr, name, x + 12, y + 20, 9, color, relief='raised')
    lit_text(cr, primary, x + 12, y + 43, 15, 'f8fafc')
    flat_text(cr, secondary_text, x + 12, y + 57, 7, '94a3b8', 0.74,
              weight=cairo.FONT_WEIGHT_NORMAL)

    spark_x, spark_y, spark_w, spark_h = x + width - 66, y + 18, 50, 32
    set_hex(cr, '334155', 0.42)
    cr.set_line_width(1)
    cr.move_to(spark_x, spark_y + spark_h)
    cr.line_to(spark_x + spark_w, spark_y + spark_h)
    cr.stroke()
    low, high = min(points), max(points)
    spread = max(0.001, high - low)
    cr.set_source(gradient(spark_x, spark_y, spark_x + spark_w, spark_y, [
        (0.00, color, 0.35),
        (1.00, color, 0.95),
    ]))
    cr.set_line_width(1.5)
    for index, value in enumerate(points):
        px = spark_x + index * spark_w / (len(points) - 1)
        py = spark_y + spark_h - (value - low) / spread * spark_h
        if index == 0:
            cr.move_to(px, py)
        else:
            cr.line_to(px, py)
    cr.stroke()


def draw_forecast(cr, x, y):
    width, height = 424, 338
    panel_frame(cr, x, y, width, height)
    title_chips(cr, [
        ('COST GUARD', '00e5ff', 12),
        ('FORECAST', 'a78bfa', 12),
        ('SAFE', '39ff88', 12),
    ], x, y, width)

    flat_text(cr, 'PROJECTED END-OF-MONTH', x + 24, y + 39, 8, '94a3b8', 0.76)
    lit_text(cr, '$31.40', x + 24, y + 73, 31, 'a78bfa')
    flat_text(cr, 'HEADROOM', x + width - 24, y + 40, 8, '94a3b8', 0.76, align='right')
    lit_text(cr, '$38.60', x + width - 24, y + 62, 16, '39ff88', align='right')
    flat_text(cr, '45% OF $70 CAP', x + width - 24, y + 76, 7.5, '39ff88', 0.78,
              weight=cairo.FONT_WEIGHT_NORMAL, align='right')
    tube(cr, x + 24, y + 90, width - 48, 26.7, '00e5ff', '8b5cf6',
         pace=61, forecast=44.9)
    flat_text(cr, 'ACTUAL', x + 24, y + 113, 7, '00e5ff', 0.78)
    flat_text(cr, '│ MONTH PACE', x + width / 2, y + 113, 7, 'ff9f1c', 0.80,
              align='center')
    flat_text(cr, 'FORECAST │', x + width - 24, y + 113, 7, 'f8fafc', 0.68,
              align='right')
    divider(cr, x + 18, x + width - 18, y + 126)

    card_w, card_h, gap = 181, 68, 12
    left, right = x + 24, x + 24 + card_w + gap
    mini_card(cr, left, y + 143, card_w, card_h, 'AWS', '$13.20',
              'EOM  ·  $8.41 MTD', PROVIDERS['AWS'][0], [2, 3, 3.3, 4.5, 5.1, 6.8, 8.4])
    mini_card(cr, right, y + 143, card_w, card_h, 'AZURE', '$7.10',
              'EOM  ·  $4.27 MTD', PROVIDERS['AZURE'][0], [1, 1.3, 2, 2.2, 2.8, 3.7, 4.27])
    mini_card(cr, left, y + 223, card_w, card_h, 'OPENROUTER', '$12.44',
              'BALANCE  ·  29D', PROVIDERS['OPENROUTER'][0], [15.9, 15.2, 14.7, 14.0, 13.7, 13.0, 12.44])
    mini_card(cr, right, y + 223, card_w, card_h, 'ANTHROPIC', '$10.10',
              'EOM  ·  $6.04 MTD', PROVIDERS['ANTHROPIC'][0], [1.1, 1.9, 2.3, 3.4, 4.2, 4.9, 6.04])

    divider(cr, x + 18, x + width - 18, y + 306)
    flat_text(cr, 'NO PROVIDER PROJECTED OVER CAP', x + width / 2, y + 326,
              8, '39ff88', 0.88, align='center')
    return width, height


def render_panel(filename, drawer, height):
    width = 456
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    draw_wallpaper(cr, width, height)
    drawer(cr, 16, 22)
    surface.write_to_png(os.path.join(HERE, filename))


def render_comparison():
    width, height = 1456, 476
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    draw_wallpaper(cr, width, height)

    columns = [22, 516, 1010]
    titles = [
        ('A  BALANCED', 'MTD + forecast + provider detail'),
        ('B  COMPACT', 'same signal in a quieter footprint'),
        ('C  FORECAST-FIRST', 'largest emphasis on end-of-month exposure'),
    ]
    drawers = [draw_balanced, draw_compact, draw_forecast]
    for x, (title, subtitle), drawer in zip(columns, titles, drawers):
        lit_text(cr, title, x, 29, 14, 'f8fafc', relief='raised')
        flat_text(cr, subtitle, x, 47, 8, 'cbd5e1', 0.62,
                  weight=cairo.FONT_WEIGHT_NORMAL)
        drawer(cr, x, 76)

    flat_text(cr, 'TRUE-SIZE CAIRO CONCEPTS  ·  ALL VALUES ILLUSTRATIVE',
              width / 2, height - 18, 8, '94a3b8', 0.68,
              weight=cairo.FONT_WEIGHT_NORMAL, align='center')
    surface.write_to_png(os.path.join(HERE, 'billing-comparison.png'))


def render_desktop():
    width, height = 1920, 1080
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    draw_wallpaper(cr, width, height)

    # Subtle GNOME primary-monitor bar for placement context.
    cr.set_source_rgba(0.01, 0.015, 0.03, 0.48)
    cr.rectangle(0, 0, width, 32)
    cr.fill()
    flat_text(cr, 'WED  AUG 19   8:15 PM', width / 2, 21, 9, 'f8fafc', 0.68,
              weight=cairo.FONT_WEIGHT_NORMAL, align='center')

    resource = cairo.ImageSurface.create_from_png(os.path.join(HERE, 'resource.png'))
    weather = cairo.ImageSurface.create_from_png(os.path.join(HERE, 'weather.png'))
    cr.set_source_surface(resource, 1640, 34)
    cr.paint()
    cr.set_source_surface(weather, 1446, 792)
    cr.paint()

    draw_balanced(cr, 1466, 373)

    flat_text(cr, 'RIGHT-RAIL PLACEMENT  ·  424 PX PANEL  ·  AUTO-CENTERED',
              24, height - 22, 9, 'cbd5e1', 0.46,
              weight=cairo.FONT_WEIGHT_NORMAL)
    surface.write_to_png(os.path.join(HERE, 'billing-desktop-placement.png'))


render_panel('billing-balanced.png', draw_balanced, 380)
render_panel('billing-compact.png', draw_compact, 294)
render_panel('billing-forecast.png', draw_forecast, 390)
render_comparison()
render_desktop()
print('wrote billing mockups to', HERE)
