from PIL import ImageDraw
from typing import List, Optional
from datetime import datetime
from .fonts import get_font


def draw_24h_grid(draw: ImageDraw, x: int, y: int, width: int, height: int):
    """Draws the X-axis grid line and 3-hour tick marks with labels."""
    font_tiny = get_font(10, "Regular")

    draw.line([x, y + height, x + width, y + height], fill=0)

    for h in range(0, 25, 3):
        lx = x + (h * width // 24)
        draw.line([lx, y + height, lx, y + height + 4], fill=0)
        label = f"{h:02d}" if h < 24 else "00"
        draw.text((lx - 5, y + height + 5), label, font=font_tiny, fill=0)


def draw_y_axis(draw: ImageDraw, x: int, y: int, height: int,
                min_v: float, max_v: float, unit: str, right: bool = False):
    """Draws Y-axis ticks and labels (left or right side)."""
    font_tiny = get_font(10, "Regular")
    steps = 4
    for i in range(steps + 1):
        val = min_v + (max_v - min_v) * i / steps
        vy = y + height - int(i * height / steps)
        tick_x0, tick_x1 = (x - 3, x) if not right else (x, x + 3)
        draw.line([tick_x0, vy, tick_x1, vy], fill=0)
        label = f"{val:.0f}"
        lx = x - 28 if not right else x + 5
        draw.text((lx, vy - 5), label, font=font_tiny, fill=0)
    # Unit label
    ux = x - 28 if not right else x + 5
    draw.text((ux, y - 12), unit, font=font_tiny, fill=0)


def draw_dashed_vline(draw: ImageDraw, x: int, y: int, height: int, dash: int = 4):
    """Draws a vertical dashed line (alternating filled/empty segments)."""
    for dy in range(0, height, dash * 2):
        y0 = y + dy
        y1 = min(y + dy + dash, y + height)
        draw.line([x, y0, x, y1], fill=0, width=1)


def draw_chart_title(draw: ImageDraw, x: int, y: int, title: str):
    font_small = get_font(11, "Bold")
    draw.text((x, y - 14), title.upper(), font=font_small, fill=0)


def draw_line_chart(draw: ImageDraw, x: int, y: int, width: int, height: int,
                    data: List[Optional[float]], color: int = 0, dashed: bool = False):
    """Draws a connected line chart. dashed=True uses dotted segments."""
    valid_points = [(i, v) for i, v in enumerate(data) if v is not None]
    if not valid_points:
        return

    min_v = min(v for _, v in valid_points)
    max_v = max(v for _, v in valid_points)
    if max_v == min_v:
        max_v += 1
        min_v -= 1

    def sy(v):
        return y + height - int((v - min_v) * height / (max_v - min_v))

    def sx(i):
        return x + (i * width // 23)

    points = [(sx(i), sy(v)) for i, v in valid_points]

    if dashed:
        for j in range(len(points) - 1):
            p1, p2 = points[j], points[j + 1]
            # Approximate dash by splitting each segment into 3 sub-segments
            for k in range(0, 3, 2):
                t0, t1 = k / 3, (k + 1) / 3
                sx0 = int(p1[0] + (p2[0] - p1[0]) * t0)
                sy0 = int(p1[1] + (p2[1] - p1[1]) * t0)
                sx1 = int(p1[0] + (p2[0] - p1[0]) * t1)
                sy1 = int(p1[1] + (p2[1] - p1[1]) * t1)
                draw.line([sx0, sy0, sx1, sy1], fill=color, width=1)
    else:
        draw.line(points, fill=color, width=2)

    return min_v, max_v


def draw_bar_chart(draw: ImageDraw, x: int, y: int, width: int, height: int,
                   data: List[Optional[float]], fill: bool = True):
    """Draws a bar chart (e.g. precipitation or sunshine)."""
    valid_values = [v for v in data if v is not None and v > 0]
    if not valid_values:
        return None, None

    max_v = max(valid_values)
    bar_width = max(1, (width // 24) - 2)

    for i, v in enumerate(data):
        if v is None or v <= 0:
            continue
        bx = x + (i * width // 24) + 1
        bh = int(v * height / max_v)
        if fill:
            draw.rectangle([bx, y + height - bh, bx + bar_width, y + height], fill=0)
        else:
            draw.rectangle([bx, y + height - bh, bx + bar_width, y + height], outline=0)

    return 0.0, max_v


def render_weather_charts(draw: ImageDraw, x: int, y: int,
                          temp_data: list, prec_data: list,
                          sun_data: list, wind_data: list,
                          sunrise: str | None = None, sunset: str | None = None):
    """
    Renders both 24h charts. All series are passed in as pre-computed lists of
    24 values (one per hour) so the renderer stays decoupled from data services.

    Args:
        temp_data:  24h temperature series (°C).
        prec_data:  24h precipitation series (mm/h).
        sun_data:   24h sunshine duration series (min/h).
        wind_data:  24h wind speed series (km/h).
        sunrise:    "HH:MM" string for sunrise marker on Chart 2, or None.
        sunset:     "HH:MM" string for sunset marker on Chart 2, or None.
    """
    font_tiny = get_font(10, "Regular")

    LEFT_PAD  = 32  # space for left Y-axis labels
    RIGHT_PAD = 28  # space for right Y-axis labels
    chart_w   = 530 - LEFT_PAD - RIGHT_PAD
    chart_h   = 85
    cx        = x + LEFT_PAD  # chart area origin X

    # ── Chart 1: Temperatura + Precipitazioni ─────────────────────────────────
    c1y = y + 16
    draw_chart_title(draw, cx, c1y, "Temperatura (°C) + Precipitazioni (mm/h)")
    draw_24h_grid(draw, cx, c1y, chart_w, chart_h)

    prec_range = draw_bar_chart(draw, cx, c1y, chart_w, chart_h, prec_data, fill=True)
    temp_range = draw_line_chart(draw, cx, c1y, chart_w, chart_h, temp_data, color=0)

    # Y-axes
    if temp_range:
        draw_y_axis(draw, cx, c1y, chart_h, temp_range[0], temp_range[1], "°C", right=False)
    if prec_range and prec_range[1]:
        draw_y_axis(draw, cx + chart_w, c1y, chart_h, 0, prec_range[1], "mm", right=True)

    # ORA dashed vertical line + label
    now_h = datetime.now().hour
    ox = cx + (now_h * chart_w // 24)
    draw_dashed_vline(draw, ox, c1y, chart_h)
    draw.text((ox + 2, c1y + 2), "ORA", font=font_tiny, fill=0)

    # ── Chart 2: Sole + Vento ─────────────────────────────────────────────────
    c2y = c1y + chart_h + 30
    draw_chart_title(draw, cx, c2y, "Sole (min/h) + Vento (km/h)")
    draw_24h_grid(draw, cx, c2y, chart_w, chart_h)

    sun_range  = draw_bar_chart(draw, cx, c2y, chart_w, chart_h, sun_data,  fill=False)
    wind_range = draw_line_chart(draw, cx, c2y, chart_w, chart_h, wind_data, color=0, dashed=True)

    if sun_range and sun_range[1]:
        draw_y_axis(draw, cx, c2y, chart_h, 0, sun_range[1], "min", right=False)
    if wind_range:
        draw_y_axis(draw, cx + chart_w, c2y, chart_h, wind_range[0], wind_range[1], "km/h", right=True)

    # Sunrise / Sunset markers on the time axis (passed in from screen.py)
    for symbol, time_str in [("↑", sunrise), ("↓", sunset)]:
        if not time_str:
            continue
        try:
            h, m = map(int, time_str.split(":"))
            hour_frac = h + m / 60
            mx = cx + int(hour_frac * chart_w / 24)
            draw.line([mx, c2y + chart_h - 6, mx, c2y + chart_h], fill=0, width=1)
            draw.text((mx - 3, c2y + chart_h + 16), symbol, font=font_tiny, fill=0)
        except (ValueError, AttributeError):
            pass
