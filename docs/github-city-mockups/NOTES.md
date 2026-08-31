# Contribution city study

Art-deco buildings on the GitHub contribution calendar, at the **shipped
overlay camera**, drawn in Cairo. Quiet days are houses and shops; busy
days are Empire / Chrysler / setback towers. Nothing here is wired into
Conky.

```bash
uv run --with pycairo python docs/github-city-mockups/render_city.py
```

Gallery: [city-gallery.html](city-gallery.html).

## Camera

```
week += (week_px, 0)
day  += (week_px * 0.015, -week_px * 0.095)
```

Weekdays stack up the screen. Height is `sqrt(count)`.

## Plates

| File | What |
| --- | --- |
| `00-shipped.png` | Live overlay, for the camera |
| `artdeco-cairo-types.png` | Type sheet |
| `artdeco-shipped.png` | Full year, 1000×200 overlay box |
| `artdeco-shipped-zoom.png` | Last 14 weeks |
| `artdeco-cairo-closeup.png` | Last 8 weeks |

`pick_kind` hashes the date against height. Palettes are cream / sand /
brick / grey. Tops are volumes, not masts: hip, mansard, dome, barrel,
penthouse, lantern, tank, arcade, sawtooth, billboard, HVAC.

PixelLab whole-building stamps and part composites were tried and
dropped: ¾ isometric art on this camera reads as noise or glued-on toys.
