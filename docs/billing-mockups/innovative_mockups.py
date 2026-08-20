import cairo
import math
import os

import billing_mockups as bm

HERE = os.path.dirname(__file__)


def inner_frame(cr, x, y, width, height, accent='00e5ff'):
    bm.rounded_rect(cr, x, y, width, height, 10)
    cr.set_source(bm.gradient(x, y, x, y + height, [
        (0.00, '07111f', 0.88),
        (0.24, '020817', 0.91),
        (1.00, '01040c', 0.88),
    ]))
    cr.fill_preserve()
    bm.set_hex(cr, accent, 0.20)
    cr.set_line_width(1)
    cr.stroke()


def bead(cr, x, y, radius, color, hollow=False, alpha=1):
    if not hollow:
        pattern = cairo.RadialGradient(
            x - radius * 0.32, y - radius * 0.42, radius * 0.1,
            x, y, radius,
        )
        pattern.add_color_stop_rgba(0, *bm.shaded(color, 0.62), alpha)
        pattern.add_color_stop_rgba(0.34, *bm.shaded(color, 0.16), alpha)
        pattern.add_color_stop_rgba(1, *bm.shaded(color, -0.44), alpha)
        cr.set_source(pattern)
        cr.arc(x, y, radius, 0, math.tau)
        cr.fill()
    cr.arc(x, y, radius, 0, math.tau)
    bm.set_hex(cr, color, 0.92 * alpha, 0.28)
    cr.set_line_width(1.1)
    cr.stroke()


def dart(cr, x, y, color, danger=False, alpha=1):
    cr.move_to(x + 4, y)
    cr.line_to(x - 3, y - 4)
    cr.line_to(x - 3, y + 4)
    cr.close_path()
    bm.set_hex(cr, 'f87171' if danger else color, 0.96 * alpha, 0.18)
    cr.set_line_width(1.4 if danger else 1.2)
    if danger:
        cr.fill_preserve()
        bm.set_hex(cr, 'ffffff', 0.28)
    cr.stroke()


def y_pressure(panel_y, pressure):
    if pressure <= 1:
        return panel_y + 78 + 140 * (1 - pressure)
    return panel_y + 78 - 24 * min(1, (pressure - 1) / 0.16)


WELL_STATES = {
    'safe': {
        'status': 'SAFE',
        'status_color': '39ff88',
        'series': [
            dict(name='AZURE', short='AZR', s=.214, f=.355, accent='00e5ff', now='$4.27 / $20', eom='EOM $7.10'),
            dict(name='ANTHROPIC', short='ANT', s=.302, f=.505, accent='ff8f73', now='$6.04 / $20', eom='EOM $10.10'),
            dict(name='AWS', short='AWS', s=.336, f=.528, accent='ff9f1c', now='$8.41 / $25', eom='EOM $13.20'),
        ],
        'runway': 29,
        'balance': '$12.44',
        'burn': '$0.43/D',
        'footer': '3/3 METERED  ·  PREPAID LIVE',
        'worst': 'WORST AWS 53%',
    },
    'watch': {
        'status': 'WATCH',
        'status_color': 'ffb454',
        'series': [
            dict(name='AZURE', short='AZR', s=.410, f=.620, accent='00e5ff', now='$8.20 / $20', eom='EOM $12.40'),
            dict(name='ANTHROPIC', short='ANT', s=.570, f=.840, accent='ff8f73', now='$11.40 / $20', eom='EOM $16.80'),
            dict(name='AWS', short='AWS', s=.680, f=.920, accent='ff9f1c', now='$17.00 / $25', eom='EOM $23.00'),
        ],
        'runway': 15,
        'balance': '$6.45',
        'burn': '$0.43/D',
        'footer': '3/3 METERED  ·  PREPAID LIVE',
        'worst': 'WORST AWS 92%',
    },
    'danger': {
        'status': 'DANGER',
        'status_color': 'f87171',
        'series': [
            dict(name='AZURE', short='AZR', s=.550, f=.790, accent='00e5ff', now='$11.00 / $20', eom='EOM $15.80'),
            dict(name='ANTHROPIC', short='ANT', s=.780, f=1.030, accent='ff8f73', now='$15.60 / $20', eom='EOM $20.60'),
            dict(name='AWS', short='AWS', s=.910, f=1.180, accent='ff9f1c', now='$22.75 / $25', eom='EOM $29.50'),
        ],
        'runway': 7,
        'balance': '$3.01',
        'burn': '$0.43/D',
        'footer': '2 BREACHES  ·  PREPAID SHORT',
        'worst': 'AWS · 27 AUG',
    },
}


def draw_trajectory_well(cr, x, y, state_name='safe'):
    data = WELL_STATES[state_name]
    panel_w, panel_h = 424, 338
    bm.panel_frame(cr, x, y, panel_w, panel_h)
    bm.title_chips(cr, [
        ('AUG 19', '00e5ff', 12),
        (data['status'], data['status_color'], 12),
    ], x, y, panel_w)

    # The metered trajectory well and the prepaid day rail are separate units.
    inner_frame(cr, x + 16, y + 38, 284, 198)
    inner_frame(cr, x + 308, y + 38, 100, 198, 'a78bfa')

    plot_x0, plot_x1 = x + 52, x + 288
    plot_top, plot_bottom = y + 54, y + 218
    now_x = x + 196.5

    # Overshoot band.
    cr.rectangle(plot_x0, plot_top, plot_x1 - plot_x0, y + 78 - plot_top)
    bm.set_hex(cr, 'f87171', 0.055 if state_name == 'safe' else 0.085)
    cr.fill()

    # Grid and axis labels.
    grid_levels = [(0, plot_bottom), (25, y + 183), (50, y + 148),
                   (75, y + 113), (100, y + 78)]
    for level, grid_y in grid_levels:
        bm.set_hex(cr, 'f8fafc', 0.065)
        cr.set_line_width(1)
        cr.move_to(plot_x0, grid_y + .5)
        cr.line_to(plot_x1, grid_y + .5)
        cr.stroke()
        label = 'CAP' if level == 100 else str(level)
        bm.flat_text(cr, label, x + 43, grid_y + 3, 7,
                     'f87171' if level == 100 else '94a3b8',
                     0.62 if level == 100 else 0.44, align='right')

    for day in (7, 14, 21, 28):
        week_x = plot_x0 + (plot_x1 - plot_x0) * day / 31
        bm.set_hex(cr, 'f8fafc', 0.055)
        cr.move_to(week_x + .5, plot_top)
        cr.line_to(week_x + .5, plot_bottom)
        cr.stroke()

    # On-pace diagonal.
    bm.set_hex(cr, 'f8fafc', 0.15)
    cr.set_dash([3, 3])
    cr.set_line_width(1)
    cr.move_to(plot_x0, plot_bottom)
    cr.line_to(plot_x1, y + 78)
    cr.stroke()
    cr.set_dash([])

    # Ceiling and today wire are the two stable laws.
    ceiling_alpha = 0.70 if state_name == 'danger' else (0.50 if state_name == 'watch' else 0.24)
    bm.set_hex(cr, 'f87171', ceiling_alpha)
    cr.set_line_width(1.5 if state_name == 'danger' else 1)
    cr.move_to(plot_x0, y + 78)
    cr.line_to(plot_x1, y + 78)
    cr.stroke()

    bm.set_hex(cr, 'facc15', 0.46)
    cr.set_line_width(1)
    cr.move_to(now_x, plot_top)
    cr.line_to(now_x, plot_bottom)
    cr.stroke()
    bm.flat_text(cr, 'NOW', now_x + 4, y + 65, 7, 'facc15', 0.76)
    bm.flat_text(cr, '1', plot_x0, y + 231, 7, '94a3b8', 0.48)
    bm.flat_text(cr, 'DAY', (plot_x0 + plot_x1) / 2, y + 231, 7,
                 '94a3b8', 0.38, align='center')
    bm.flat_text(cr, '31', plot_x1, y + 231, 7, '94a3b8', 0.48, align='right')

    # Series use only the two measured points: now and month-end forecast.
    for series in sorted(data['series'], key=lambda item: item['f']):
        current_y = y_pressure(y, series['s'])
        forecast_y = y_pressure(y, series['f'])
        dangerous = series['f'] >= 1
        line_color = 'f87171' if dangerous else series['accent']
        pattern = cairo.LinearGradient(now_x, current_y, plot_x1, forecast_y)
        pattern.add_color_stop_rgba(0, *bm.shaded(line_color, -0.16), 0.76)
        pattern.add_color_stop_rgba(1, *bm.shaded(line_color, 0.20), 0.98)
        cr.set_source(pattern)
        cr.set_line_width(2 if dangerous else 1.6)
        cr.move_to(now_x, current_y)
        cr.line_to(plot_x1, forecast_y)
        cr.stroke()
        bead(cr, now_x, current_y, 4.5, series['accent'])
        dart(cr, plot_x1, forecast_y, series['accent'], danger=dangerous)

    # Prepaid day rail: position, not a disguised filled bar.
    rail_x = x + 358
    runway = data['runway']
    runway_y = y + 218 - 164 * min(40, runway) / 40
    gate_y = y + 218 - 164 * 12 / 40
    bm.flat_text(cr, 'OPENROUTER', x + 316, y + 58, 8, 'a78bfa', 0.92)
    bm.lit_text(cr, data['balance'], x + 316, y + 78, 15, 'f8fafc')
    bm.flat_text(cr, data['burn'], x + 316, y + 93, 8, '94a3b8', 0.66)

    for days in (0, 20, 40):
        scale_y = y + 218 - 164 * days / 40
        bm.flat_text(cr, str(days), x + 316, scale_y + 3, 7, '94a3b8', 0.42)
        bm.set_hex(cr, 'f8fafc', 0.07)
        cr.move_to(x + 338, scale_y + .5)
        cr.line_to(x + 396, scale_y + .5)
        cr.stroke()

    bm.set_hex(cr, 'facc15', 0.58)
    cr.set_line_width(1.5)
    cr.move_to(x + 338, gate_y)
    cr.line_to(x + 396, gate_y)
    cr.stroke()
    bm.flat_text(cr, '12D LEFT', x + 394, gate_y - 4, 7, 'facc15', 0.82, align='right')

    rail_color = 'f87171' if runway < 12 else 'c084fc'
    bm.set_hex(cr, rail_color, 0.52)
    cr.set_line_width(1.6)
    cr.move_to(rail_x, y + 218)
    cr.line_to(rail_x, runway_y)
    cr.stroke()
    bead(cr, rail_x, runway_y, 5, rail_color)
    bm.flat_text(cr, f'{runway}D', rail_x + 9, runway_y + 3, 8, rail_color, 0.94)

    # Metered legend: dollars live here, not in a dishonest aggregate hero.
    legend_xs = [x + 22, x + 156, x + 290]
    legend_series = [
        next(item for item in data['series'] if item['name'] == 'AWS'),
        next(item for item in data['series'] if item['name'] == 'AZURE'),
        next(item for item in data['series'] if item['name'] == 'ANTHROPIC'),
    ]
    for legend_x, series in zip(legend_xs, legend_series):
        bead(cr, legend_x + 3, y + 255, 3, series['accent'])
        bm.lit_text(cr, series['name'], legend_x + 11, y + 259, 8, series['accent'], relief='raised')
        bm.lit_text(cr, series['now'], legend_x, y + 277, 9.5, 'f8fafc')
        eom_color = 'f87171' if series['f'] >= 1 else ('ffb454' if series['f'] >= .8 else series['accent'])
        bm.flat_text(cr, series['eom'], legend_x, y + 291, 8, eom_color, 0.86)

    bm.divider(cr, x + 18, x + panel_w - 18, y + 302)
    bm.flat_text(cr, data['footer'], x + 22, y + 322, 7.5,
                 data['status_color'], 0.76)
    bm.flat_text(cr, data['worst'], x + panel_w - 22, y + 322, 7.5,
                 data['status_color'], 0.90, align='right')
    return panel_w, panel_h


def horizon_y(panel_y, pressure):
    return panel_y + 214 - 140 * max(0, min(1.3, pressure)) / 1.3


def draw_horizon_threads(cr, x, y):
    panel_w, panel_h = 424, 318
    bm.panel_frame(cr, x, y, panel_w, panel_h)
    bm.title_chips(cr, [
        ('AUG', '8b5cf6', 12),
        ('SAFE', '39ff88', 12),
    ], x, y, panel_w)

    bm.flat_text(cr, 'NEAREST BREACH', x + 24, y + 35, 8, '94a3b8', 0.70)
    bm.lit_text(cr, 'NO BREACH', x + 24, y + 60, 21, '39ff88')
    bm.flat_text(cr, 'WORST LANDING', x + panel_w - 24, y + 36, 8,
                 '94a3b8', 0.70, align='right')
    bm.lit_text(cr, 'AWS 53%', x + panel_w - 24, y + 58, 13,
                'ff9f1c', align='right')

    plot_x0, plot_x1 = x + 52, x + 396
    plot_y0, plot_y1 = y + 74, y + 214
    cap_y = horizon_y(y, 1.0)
    now_x = plot_x0 + (plot_x1 - plot_x0) * 19 / 31

    cr.rectangle(plot_x0, plot_y0, plot_x1 - plot_x0, cap_y - plot_y0)
    bm.set_hex(cr, 'f87171', 0.045)
    cr.fill()
    for day in (7, 14, 21, 28):
        grid_x = plot_x0 + (plot_x1 - plot_x0) * day / 31
        bm.set_hex(cr, 'f8fafc', 0.05)
        cr.move_to(grid_x, plot_y0)
        cr.line_to(grid_x, plot_y1)
        cr.stroke()
    bm.set_hex(cr, 'f87171', 0.50)
    cr.set_line_width(1)
    cr.move_to(plot_x0, cap_y)
    cr.line_to(plot_x1, cap_y)
    cr.stroke()
    bm.flat_text(cr, 'CAP', plot_x1, cap_y - 5, 7, 'f87171', 0.64, align='right')

    bm.set_hex(cr, 'f8fafc', 0.17)
    cr.move_to(now_x, plot_y0)
    cr.line_to(now_x, plot_y1)
    cr.stroke()
    bm.flat_text(cr, '19', now_x, plot_y1 + 13, 7, 'f8fafc', 0.50, align='center')

    threads = [
        dict(code='AZR', color='00e5ff', values=[.03,.06,.09,.12,.15,.18,.214], f=.355),
        dict(code='ANT', color='ff8f73', values=[.04,.08,.13,.17,.22,.26,.302], f=.505),
        dict(code='AWS', color='ff9f1c', values=[.05,.10,.14,.19,.24,.29,.336], f=.528),
    ]
    sample_days = [1, 4, 7, 10, 13, 16, 19]
    for thread in threads:
        points = []
        for day, value in zip(sample_days, thread['values']):
            points.append((plot_x0 + (plot_x1 - plot_x0) * day / 31, horizon_y(y, value)))
        bm.set_hex(cr, thread['color'], 0.15)
        cr.set_line_width(4)
        for index, (px, py) in enumerate(points):
            if index == 0: cr.move_to(px, py)
            else: cr.line_to(px, py)
        cr.stroke()
        bm.set_hex(cr, thread['color'], 0.92)
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for index, (px, py) in enumerate(points):
            if index == 0: cr.move_to(px, py)
            else: cr.line_to(px, py)
        cr.stroke()
        current_x, current_y = points[-1]
        forecast_y = horizon_y(y, thread['f'])
        bm.set_hex(cr, thread['color'], 0.56)
        cr.set_dash([3, 3])
        cr.set_line_width(1.3)
        cr.move_to(current_x, current_y)
        cr.line_to(plot_x1, forecast_y)
        cr.stroke()
        cr.set_dash([])
        bead(cr, plot_x1, forecast_y, 2.8, thread['color'])

    # A single compact key; no cards.
    bm.divider(cr, x + 18, x + panel_w - 18, y + 231)
    keys = [
        ('AWS', '53%', 'ff9f1c'), ('AZR', '36%', '00e5ff'),
        ('ANT', '51%', 'ff8f73'), ('OR', '29D', 'a78bfa'),
    ]
    positions = [(x + 24, y + 253), (x + 218, y + 253),
                 (x + 24, y + 279), (x + 218, y + 279)]
    for (code, value, color), (key_x, key_y) in zip(keys, positions):
        bead(cr, key_x + 3, key_y - 3, 3, color)
        bm.lit_text(cr, code, key_x + 12, key_y, 9, color, relief='raised')
        bm.lit_text(cr, value, key_x + 158, key_y, 10, 'f8fafc', align='right')

    bm.divider(cr, x + 18, x + panel_w - 18, y + 294)
    bm.flat_text(cr, '4/4 LIVE', x + 24, y + 310, 7, '39ff88', 0.76)
    bm.flat_text(cr, 'REAL HISTORY  ·  NEXT 30M', x + panel_w - 24, y + 310,
                 7, '94a3b8', 0.54, align='right')
    return panel_w, panel_h


def render_single(name, drawer, height):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 456, height)
    cr = cairo.Context(surface)
    bm.draw_wallpaper(cr, 456, height)
    drawer(cr, 16, 22)
    surface.write_to_png(os.path.join(HERE, name))


def render_state_sheet():
    width, height = 1456, 432
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    bm.draw_wallpaper(cr, width, height)
    columns = [22, 516, 1010]
    for column, state, subtitle in zip(
        columns,
        ('safe', 'watch', 'danger'),
        ('all land below their own caps', 'forecast pressure becomes visible', 'cap crossings become geometry'),
    ):
        state_data = WELL_STATES[state]
        bm.lit_text(cr, state.upper(), column, 28, 14, state_data['status_color'], relief='raised')
        bm.flat_text(cr, subtitle, column, 46, 8, 'cbd5e1', 0.62,
                     weight=cairo.FONT_WEIGHT_NORMAL)
        draw_trajectory_well(cr, column, 76, state)
    surface.write_to_png(os.path.join(HERE, 'trajectory-state-comparison.png'))


def render_concept_sheet():
    width, height = 968, 430
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    bm.draw_wallpaper(cr, width, height)
    bm.lit_text(cr, '1  TRAJECTORY WELL', 22, 28, 14, '00e5ff', relief='raised')
    bm.flat_text(cr, 'no history required · consensus recommendation', 22, 46, 8,
                 'cbd5e1', 0.62, weight=cairo.FONT_WEIGHT_NORMAL)
    draw_trajectory_well(cr, 22, 76, 'safe')
    bm.lit_text(cr, '2  HORIZON THREADS', 516, 28, 14, 'a78bfa', relief='raised')
    bm.flat_text(cr, 'calmer · becomes richer only from real daily history', 516, 46, 8,
                 'cbd5e1', 0.62, weight=cairo.FONT_WEIGHT_NORMAL)
    draw_horizon_threads(cr, 516, 76)
    surface.write_to_png(os.path.join(HERE, 'innovation-concepts.png'))


def render_desktop():
    width, height = 1920, 1080
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    bm.draw_wallpaper(cr, width, height)
    cr.set_source_rgba(0.01, 0.015, 0.03, 0.48)
    cr.rectangle(0, 0, width, 32)
    cr.fill()
    bm.flat_text(cr, 'WED  AUG 19   8:15 PM', width / 2, 21, 9, 'f8fafc', 0.68,
                 weight=cairo.FONT_WEIGHT_NORMAL, align='center')
    resource = cairo.ImageSurface.create_from_png(os.path.join(HERE, 'resource.png'))
    weather = cairo.ImageSurface.create_from_png(os.path.join(HERE, 'weather.png'))
    cr.set_source_surface(resource, 1640, 34)
    cr.paint()
    cr.set_source_surface(weather, 1446, 792)
    cr.paint()
    draw_trajectory_well(cr, 1466, 369, 'safe')
    surface.write_to_png(os.path.join(HERE, 'trajectory-desktop-placement.png'))


render_single('trajectory-well-safe.png', lambda cr, x, y: draw_trajectory_well(cr, x, y, 'safe'), 390)
render_single('trajectory-well-watch.png', lambda cr, x, y: draw_trajectory_well(cr, x, y, 'watch'), 390)
render_single('trajectory-well-danger.png', lambda cr, x, y: draw_trajectory_well(cr, x, y, 'danger'), 390)
render_single('horizon-threads.png', draw_horizon_threads, 372)
render_state_sheet()
render_concept_sheet()
render_desktop()
print('wrote innovative mockups to', HERE)
