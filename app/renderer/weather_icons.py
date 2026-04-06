import math
from PIL import ImageDraw


def _draw_cloud(draw: ImageDraw, cx: int, cy: int, size: str = "large"):
    """
    Draws a cloud centred at (cx, cy) on a 1-bit canvas.

    Technique: three overlapping circles (bumps) sit on a rectangular base.
    Because Pillow's 1-bit mode has no transparency, the drawing is done in
    two passes — first fill everything white (erasing whatever is behind the
    cloud), then draw only the outlines that should be visible:
      1. White-fill base rectangle + bump circles.
      2. Draw base sides + bottom line.
      3. Draw top arcs of each bump (bottom arcs are inside the body).
      4. White-fill the interior again to erase any arc-overlap artifacts.
      5. Redraw the outlines from steps 2–3.

    size: "large" for standalone cloud icons, "small" for the partly-sunny
    combo where the cloud overlaps a sun.
    """
    if size == "small":
        # Smaller cloud, offset bottom-left for partly-sunny combo
        bumps = [
            (cx - 6, cy - 2, 7),   # left bump
            (cx + 2, cy - 5, 8),   # center bump (taller)
            (cx + 9, cy - 2, 6),   # right bump
        ]
        base = (cx - 10, cy - 1, cx + 13, cy + 6)
    else:
        bumps = [
            (cx - 8, cy - 3, 8),   # left bump
            (cx + 1, cy - 7, 9),   # center bump (taller)
            (cx + 10, cy - 3, 7),  # right bump
        ]
        base = (cx - 14, cy - 2, cx + 15, cy + 7)

    # Fill white first (all shapes), then draw outlines
    # Base rectangle fill
    draw.rectangle([base[0] + 1, base[1], base[2] - 1, base[3]], fill=255)
    # Bump fills
    for bx, by, r in bumps:
        draw.ellipse([bx - r, by - r, bx + r, by + r], fill=255)

    # Draw outlines: base bottom + sides
    draw.line([base[0], base[3], base[2], base[3]], fill=0, width=1)  # bottom
    draw.line([base[0], base[1] + 2, base[0], base[3]], fill=0, width=1)  # left side
    draw.line([base[2], base[1] + 2, base[2], base[3]], fill=0, width=1)  # right side

    # Bump outlines (top arcs only — bottom halves hidden inside cloud body)
    for bx, by, r in bumps:
        draw.arc([bx - r, by - r, bx + r, by + r], start=180, end=360, fill=0, width=1)

    # White-fill interior to clean up any arc overlap artifacts
    interior = (base[0] + 1, min(b[1] for b in bumps) + 2, base[2] - 1, base[3] - 1)
    draw.rectangle(interior, fill=255)

    # Redraw just the visible outlines
    draw.line([base[0], base[3], base[2], base[3]], fill=0, width=1)
    draw.line([base[0], base[1] + 2, base[0], base[3]], fill=0, width=1)
    draw.line([base[2], base[1] + 2, base[2], base[3]], fill=0, width=1)
    for bx, by, r in bumps:
        draw.arc([bx - r, by - r, bx + r, by + r], start=180, end=360, fill=0, width=1)


def _draw_sun(draw: ImageDraw, cx: int, cy: int, r: int = 8, ray_len: int = 5):
    """Draws a sun: filled circle + 8 rays."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255, outline=0, width=2)
    for deg in range(0, 360, 45):
        rad = math.radians(deg)
        x0 = int(cx + math.cos(rad) * (r + 2))
        y0 = int(cy + math.sin(rad) * (r + 2))
        x1 = int(cx + math.cos(rad) * (r + 2 + ray_len))
        y1 = int(cy + math.sin(rad) * (r + 2 + ray_len))
        draw.line([x0, y0, x1, y1], fill=0, width=1)


def _draw_raindrop(draw: ImageDraw, x: int, y: int, length: int = 5, width: int = 1):
    """Draws a single raindrop (angled line)."""
    draw.line([x, y, x - 2, y + length], fill=0, width=width)


def _draw_snowflake(draw: ImageDraw, x: int, y: int, size: int = 3, bold: bool = False):
    """Draws an asterisk-style snowflake."""
    w = 2 if bold else 1
    for deg in (0, 60, 120):
        rad = math.radians(deg)
        dx = int(math.cos(rad) * size)
        dy = int(math.sin(rad) * size)
        draw.line([x - dx, y - dy, x + dx, y + dy], fill=0, width=w)


def _draw_lightning(draw: ImageDraw, cx: int, y_start: int):
    """Draws a small lightning bolt."""
    bolt = [
        (cx + 2, y_start),
        (cx - 1, y_start + 6),
        (cx + 2, y_start + 6),
        (cx - 2, y_start + 13),
    ]
    draw.line(bolt, fill=0, width=2)


def draw_weather_icon(draw: ImageDraw, x: int, y: int, pictogram_id):
    """
    Draws a 40x40 1-bit weather icon for MeteoSwiss jp2000d0 pictogram codes.

    Category mapping (with intensity levels):
      1              → Clear/Sunny
      2, 3, 26       → Partly sunny
      4, 5           → Cloudy/Overcast
      6              → Fog
      7, 11          → Light rain (2 thin drops)
      8, 12          → Moderate rain (3 drops)
      9, 13          → Heavy rain (4 thick drops)
      10, 14         → Thunderstorm
      15, 16, 17     → Light snow (2 small flakes)
      18, 19         → Moderate snow (3 flakes)
      20, 21         → Heavy snow (5 flakes, larger)
      22, 23         → Light sleet (1 drop + 1 flake)
      24, 25         → Heavy sleet (2 drops + 2 flakes)
      27, 28         → Partly sunny (shower variant)
      29, 30         → Rain showers → moderate rain
      31, 32, 33     → Thundery showers → thunderstorm
      34, 35, 36     → Snow showers → moderate snow
      37, 38, 39, 40 → Sleet showers → light sleet
    """
    if pictogram_id is None:
        return

    p = int(pictogram_id)

    # Remap shower/variant codes to base categories
    if p in (27, 28):
        p = 2
    elif p in (29, 30):
        p = 8
    elif p in (31, 32, 33):
        p = 10
    elif p in (34, 35, 36):
        p = 18  # moderate snow (not all→heavy)
    elif p in (37, 38, 39, 40):
        p = 22

    cx, cy = x + 20, y + 20  # icon centre

    # ── Clear: sun ──────────────────────────────────────────────────────────
    if p == 1:
        _draw_sun(draw, cx, cy)

    # ── Partly sunny: small sun top-right + cloud bottom-left ───────────────
    elif p in (2, 3, 26):
        _draw_sun(draw, cx + 8, cy - 8, r=6, ray_len=4)
        _draw_cloud(draw, cx - 3, cy + 5, size="small")

    # ── Cloudy / Overcast ───────────────────────────────────────────────────
    elif p in (4, 5):
        _draw_cloud(draw, cx, cy + 2)

    # ── Fog: three horizontal dashed lines ──────────────────────────────────
    elif p == 6:
        for row in range(3):
            fy = cy - 6 + row * 8
            for seg in range(4):
                fx = cx - 15 + seg * 9
                draw.line([fx, fy, fx + 6, fy], fill=0, width=2)

    # ── Light rain: cloud + 2 thin drops ────────────────────────────────────
    elif p in (7, 11):
        _draw_cloud(draw, cx, cy - 4)
        _draw_raindrop(draw, cx - 5, cy + 10, length=5, width=1)
        _draw_raindrop(draw, cx + 5, cy + 10, length=5, width=1)

    # ── Moderate rain: cloud + 3 drops ──────────────────────────────────────
    elif p in (8, 12):
        _draw_cloud(draw, cx, cy - 4)
        _draw_raindrop(draw, cx - 7, cy + 10, length=6, width=1)
        _draw_raindrop(draw, cx,     cy + 10, length=6, width=1)
        _draw_raindrop(draw, cx + 7, cy + 10, length=6, width=1)

    # ── Heavy rain: cloud + 4 thick drops ───────────────────────────────────
    elif p in (9, 13):
        _draw_cloud(draw, cx, cy - 4)
        _draw_raindrop(draw, cx - 9, cy + 10, length=7, width=2)
        _draw_raindrop(draw, cx - 3, cy + 10, length=7, width=2)
        _draw_raindrop(draw, cx + 3, cy + 10, length=7, width=2)
        _draw_raindrop(draw, cx + 9, cy + 10, length=7, width=2)

    # ── Thunderstorm: cloud + lightning ─────────────────────────────────────
    elif p in (10, 14):
        _draw_cloud(draw, cx, cy - 6)
        _draw_lightning(draw, cx, cy + 5)

    # ── Light snow: cloud + 2 small flakes ──────────────────────────────────
    elif p in (15, 16, 17):
        _draw_cloud(draw, cx, cy - 4)
        _draw_snowflake(draw, cx - 5, cy + 12, size=3)
        _draw_snowflake(draw, cx + 5, cy + 12, size=3)

    # ── Moderate snow: cloud + 3 flakes at varying heights ──────────────────
    elif p in (18, 19):
        _draw_cloud(draw, cx, cy - 4)
        _draw_snowflake(draw, cx - 7, cy + 11, size=3)
        _draw_snowflake(draw, cx,     cy + 15, size=3)
        _draw_snowflake(draw, cx + 7, cy + 11, size=3)

    # ── Heavy snow: cloud + 4 flakes in two rows ─────────────────────────
    elif p in (20, 21):
        _draw_cloud(draw, cx, cy - 4)
        _draw_snowflake(draw, cx - 6, cy + 10, size=3)
        _draw_snowflake(draw, cx + 6, cy + 10, size=3)
        _draw_snowflake(draw, cx - 6, cy + 17, size=3)
        _draw_snowflake(draw, cx + 6, cy + 17, size=3)

    # ── Light sleet: cloud + 1 drop + 1 flake ──────────────────────────────
    elif p in (22, 23):
        _draw_cloud(draw, cx, cy - 4)
        _draw_raindrop(draw, cx - 5, cy + 10, length=6, width=1)
        _draw_snowflake(draw, cx + 5, cy + 13, size=3)

    # ── Heavy sleet: cloud + 2 drops + 2 flakes alternating ────────────────
    elif p in (24, 25):
        _draw_cloud(draw, cx, cy - 4)
        _draw_raindrop(draw, cx - 8, cy + 10, length=6, width=2)
        _draw_snowflake(draw, cx - 2, cy + 13, size=3)
        _draw_raindrop(draw, cx + 4, cy + 10, length=6, width=2)
        _draw_snowflake(draw, cx + 10, cy + 13, size=3)

    # ── Fallback ────────────────────────────────────────────────────────────
    else:
        draw.rectangle([x + 10, y + 10, x + 30, y + 30], outline=0)
