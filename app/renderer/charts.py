from PIL import ImageDraw
from typing import List, Optional
from datetime import datetime
from .fonts import get_font
import math


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
                min_v: float, max_v: float, unit: str, right: bool = False, precision: int = 0):
    """Draws Y-axis ticks and labels (left or right side)."""
    font_tiny = get_font(10, "Regular")
    steps = 4
    for i in range(steps + 1):
        val = min_v + (max_v - min_v) * i / steps
        vy = y + height - int(i * height / steps)
        tick_x0, tick_x1 = (x - 3, x) if not right else (x, x + 3)
        draw.line([tick_x0, vy, tick_x1, vy], fill=0)
        
        if precision == 0:
            label = f"{val:.0f}"
        else:
            label = f"{val:.{precision}f}"
            
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
                    data: List[Optional[float]], min_v: float, max_v: float, 
                    color: int = 0, dashed: bool = False):
    """Draws a connected line chart within fixed min/max vertical bounds."""
    valid_points = [(i, v) for i, v in enumerate(data) if v is not None]
    if not valid_points:
        return

    if max_v == min_v:
        max_v += 1
        min_v -= 1

    def sy(v):
        v_clipped = max(min_v, min(max_v, v))
        return y + height - int((v_clipped - min_v) * height / (max_v - min_v))

    def sx(i):
        return x + (i * width // 23)

    points = [(sx(i), sy(v)) for i, v in valid_points]

    if dashed:
        for j in range(len(points) - 1):
            p1, p2 = points[j], points[j + 1]
            dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            num_steps = max(2, int(dist / 4))
            for k in range(0, num_steps, 2):
                t0, t1 = k / num_steps, min(1.0, (k + 1) / num_steps)
                sx0 = int(p1[0] + (p2[0] - p1[0]) * t0)
                sy0 = int(p1[1] + (p2[1] - p1[1]) * t0)
                sx1 = int(p1[0] + (p2[0] - p1[0]) * t1)
                sy1 = int(p1[1] + (p2[1] - p1[1]) * t1)
                draw.line([sx0, sy0, sx1, sy1], fill=color, width=1)
    else:
        draw.line(points, fill=color, width=2)


def draw_bar_chart(draw: ImageDraw, x: int, y: int, width: int, height: int,
                   data: List[Optional[float]], max_v: float, fill: bool = True):
    """Draws a bar chart within fixed vertical bounds."""
    if max_v <= 0:
        max_v = 1.0
    bar_width = max(1, (width // 24) - 2)

    for i, v in enumerate(data):
        if v is None or v <= 0:
            continue
        bx = x + (i * width // 24) + 1
        v_clipped = min(max_v, v)
        bh = int(v_clipped * height / max_v)
        if fill:
            draw.rectangle([bx, y + height - bh, bx + bar_width, y + height], fill=0)
        else:
            draw.rectangle([bx, y + height - bh, bx + bar_width, y + height], outline=0)


def render_weather_charts(draw: ImageDraw, x: int, y: int,
                          temp_data: list, prec_data: list,
                          sun_data: list, wind_data: list,
                          sunrise: str | None = None, sunset: str | None = None):
    """
    Renders both 24h charts with specific scaling rules:
    - Temp: min-5 to max+5
    - Precipitation: min 0-10, or max+5 if higher
    - Sunshine: fixed 0-60
    - Wind: minimum 0-20, dynamic if higher
    """
    font_tiny = get_font(10, "Regular")

    LEFT_PAD  = 32  # space for left Y-axis labels
    RIGHT_PAD = 28  # space for right Y-axis labels
    chart_w   = 530 - LEFT_PAD - RIGHT_PAD
    chart_h   = 110
    cx        = x + LEFT_PAD

    # ── Chart 1: Temperatura + Precipitazioni ─────────────────────────────────
    c1y = y + 16
    draw_chart_title(draw, cx, c1y, "Temperatura (°C) + Precipitazioni (mm/h)")
    draw_24h_grid(draw, cx, c1y, chart_w, chart_h)

    # Temp scale
    valid_temps = [v for v in temp_data if v is not None]
    if valid_temps:
        t_min, t_max = min(valid_temps) - 5, max(valid_temps) + 5
    else:
        t_min, t_max = 0, 30
    
    # Precipitation scale: Min 10, or max+5
    valid_precs = [v for v in prec_data if v is not None and v > 0]
    p_max = 10.0
    if valid_precs:
        p_real_max = max(valid_precs)
        if p_real_max > 5.0: # if it gets close to 10, grow it
            p_max = max(10.0, p_real_max + 5.0)

    draw_bar_chart(draw, cx, c1y, chart_w, chart_h, prec_data, max_v=p_max, fill=True)
    draw_line_chart(draw, cx, c1y, chart_w, chart_h, temp_data, min_v=t_min, max_v=t_max, color=0)

    draw_y_axis(draw, cx, c1y, chart_h, t_min, t_max, "°C", right=False)
    # Use 1 decimal if p_max is small to avoid rounded 1,1,0,0 labels
    prec_precision = 1 if p_max <= 10.0 else 0
    draw_y_axis(draw, cx + chart_w, c1y, chart_h, 0, p_max, "mm", right=True, precision=prec_precision)

    # ORA dashed vertical line
    now_h = datetime.now().hour
    ox = cx + (now_h * chart_w // 24)
    draw_dashed_vline(draw, ox, c1y, chart_h)
    draw.text((ox + 2, c1y + 2), "ORA", font=font_tiny, fill=0)

    # ── Chart 2: Sole + Vento ─────────────────────────────────────────────────
    c2y = c1y + chart_h + 30
    draw_chart_title(draw, cx, c2y, "Sole (min/h) + Vento (km/h)")
    draw_24h_grid(draw, cx, c2y, chart_w, chart_h)

    s_max = 60.0
    valid_winds = [v for v in wind_data if v is not None]
    w_max = max(20.0, (max(valid_winds) + 5.0) if valid_winds else 20.0)

    draw_bar_chart(draw, cx, c2y, chart_w, chart_h, sun_data,  max_v=s_max, fill=False)
    draw_line_chart(draw, cx, c2y, chart_w, chart_h, wind_data, min_v=0, max_v=w_max, color=0, dashed=True)

    draw_y_axis(draw, cx, c2y, chart_h, 0, s_max, "min", right=False)
    draw_y_axis(draw, cx + chart_w, c2y, chart_h, 0, w_max, "km/h", right=True)

    # Sunrise / Sunset markers
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
