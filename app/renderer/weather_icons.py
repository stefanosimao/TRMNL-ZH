import math
from PIL import ImageDraw


def draw_weather_icon(draw: ImageDraw, x: int, y: int, pictogram_id):
    """
    Draws a 40x40 1-bit weather icon for MeteoSwiss jp2000d0 pictogram codes.

    Category mapping:
      1        → Clear/Sunny
      2, 3, 26 → Partly sunny
      4, 5     → Cloudy/Overcast
      6        → Fog
      7, 11    → Light rain
      8, 12    → Rain
      9, 13    → Heavy rain
      10, 14   → Thunderstorm
      15-21    → Snow
      22-25    → Sleet (mixed rain/snow)
      27-40    → mapped to nearest category above
    """
    if pictogram_id is None:
        return

    p = int(pictogram_id)

    # Normalise less-common codes to nearest base category
    if p in (27, 28):
        p = 2   # sunny intervals
    elif p in (29, 30):
        p = 8   # rain showers
    elif p in (31, 32, 33):
        p = 10  # thundery showers
    elif p in (34, 35, 36):
        p = 20  # snow showers → snow
    elif p in (37, 38, 39, 40):
        p = 23  # sleet showers → sleet

    cx, cy = x + 20, y + 20  # icon centre

    if p == 1:
        # ── Clear: circle + 8 rays ──────────────────────────────────────────
        r = 8
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, width=2)
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            x0 = int(cx + math.cos(rad) * (r + 3))
            y0 = int(cy + math.sin(rad) * (r + 3))
            x1 = int(cx + math.cos(rad) * (r + 7))
            y1 = int(cy + math.sin(rad) * (r + 7))
            draw.line([x0, y0, x1, y1], fill=0, width=1)

    elif p in (2, 3, 26):
        # ── Partly sunny: small sun top-right + cloud bottom-left ──────────
        # Sun
        sx, sy, sr = cx + 7, cy - 7, 6
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], outline=0, width=1)
        for deg in (0, 45, 90, 135, 180, 225, 270, 315):
            rad = math.radians(deg)
            draw.line([
                int(sx + math.cos(rad) * (sr + 2)), int(sy + math.sin(rad) * (sr + 2)),
                int(sx + math.cos(rad) * (sr + 5)), int(sy + math.sin(rad) * (sr + 5)),
            ], fill=0, width=1)
        # Cloud (overlapping)
        _draw_cloud(draw, cx - 5, cy + 5, 14, 9)

    elif p in (4, 5):
        # ── Cloudy/Overcast: large cloud ────────────────────────────────────
        _draw_cloud(draw, cx, cy + 2, 18, 12)

    elif p == 6:
        # ── Fog: horizontal dashed lines ────────────────────────────────────
        for row in range(4):
            fy = cy - 8 + row * 6
            for seg in range(3):
                fx = cx - 14 + seg * 10
                draw.line([fx, fy, fx + 7, fy], fill=0, width=1)

    elif p in (7, 11):
        # ── Light rain: cloud + 2 drops ─────────────────────────────────────
        _draw_cloud(draw, cx, cy - 4, 16, 9)
        for dx in (-5, 5):
            draw.line([cx + dx, cy + 8, cx + dx, cy + 13], fill=0, width=1)

    elif p in (8, 12):
        # ── Rain: cloud + 3 drops ───────────────────────────────────────────
        _draw_cloud(draw, cx, cy - 4, 16, 9)
        for dx in (-8, 0, 8):
            draw.line([cx + dx, cy + 8, cx + dx, cy + 14], fill=0, width=1)

    elif p in (9, 13):
        # ── Heavy rain: cloud + 4 drops ─────────────────────────────────────
        _draw_cloud(draw, cx, cy - 4, 16, 9)
        for dx in (-9, -3, 3, 9):
            draw.line([cx + dx, cy + 8, cx + dx, cy + 15], fill=0, width=2)

    elif p in (10, 14):
        # ── Thunderstorm: cloud + lightning bolt ─────────────────────────────
        _draw_cloud(draw, cx, cy - 6, 16, 9)
        bolt = [(cx + 3, cy + 6), (cx - 1, cy + 12), (cx + 2, cy + 12), (cx - 3, cy + 19)]
        draw.line(bolt, fill=0, width=2)

    elif 15 <= p <= 21:
        # ── Snow: cloud + 3 snowflake crosses ───────────────────────────────
        _draw_cloud(draw, cx, cy - 4, 16, 9)
        for dx in (-6, 0, 6):
            sx, sy = cx + dx, cy + 11
            draw.line([sx - 3, sy, sx + 3, sy], fill=0, width=1)
            draw.line([sx, sy - 3, sx, sy + 3], fill=0, width=1)

    elif 22 <= p <= 25:
        # ── Sleet: cloud + alternating drop and dot ──────────────────────────
        _draw_cloud(draw, cx, cy - 4, 16, 9)
        draw.line([cx - 6, cy + 8, cx - 6, cy + 13], fill=0, width=1)   # drop
        dot_x, dot_y = cx, cy + 11
        draw.ellipse([dot_x - 2, dot_y - 2, dot_x + 2, dot_y + 2], fill=0)  # snow
        draw.line([cx + 6, cy + 8, cx + 6, cy + 13], fill=0, width=1)   # drop

    else:
        # ── Fallback: simple rectangle ───────────────────────────────────────
        draw.rectangle([x + 10, y + 10, x + 30, y + 30], outline=0)


def _draw_cloud(draw: ImageDraw, cx: int, cy: int, w: int, h: int):
    """Draws a cloud shape centred at (cx, cy) with given half-width/height.
    Bumps are drawn as top-arcs only to avoid internal line artifacts."""
    # Bumps: top arc only (180→360 = left→top→right in PIL clockwise coords)
    draw.arc([cx - w + 2, cy - h - 4, cx - 2, cy + 2], start=180, end=360, fill=0, width=1)
    draw.arc([cx - 2, cy - h - 2, cx + w - 4, cy + 2], start=180, end=360, fill=0, width=1)
    # Main body ellipse
    draw.ellipse([cx - w, cy - h, cx + w, cy + h], outline=0, width=1)
    # White fill to hide internal bump lines inside the body
    draw.rectangle([cx - w + 1, cy - h + 1, cx + w - 1, cy - 1], fill=255)
    # Redraw top arc of body (was whited out)
    draw.arc([cx - w, cy - h, cx + w, cy + h], start=180, end=360, fill=0, width=1)
    # White fill bottom half interior
    draw.rectangle([cx - w + 1, cy, cx + w - 1, cy + h - 1], fill=255)
    # Redraw bottom arc
    draw.arc([cx - w, cy - h, cx + w, cy + h], start=0, end=180, fill=0, width=1)
