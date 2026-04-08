"""
Chart drawing utilities for temperature, precipitation, sunshine, and wind data.
"""
from PIL import ImageDraw
from typing import List, Optional
from .fonts import get_font
import math


def draw_24h_grid(draw: ImageDraw, x: int, y: int, width: int, height: int, start_hour: int = 0):
    """Draws the X-axis grid line and 3-hour tick marks with labels."""
    font_tiny = get_font(11, "Bold")

    draw.line([x, y + height, x + width, y + height], fill=0)

    for h in range(0, 25, 3):
        lx = x + (h * width // 24)
        draw.line([lx, y + height, lx, y + height + 4], fill=0)
        label_hour = (start_hour + h) % 24
        label = f"{label_hour:02d}" if h < 24 else f"{start_hour:02d}"
        draw.text((lx - 5, y + height + 5), label, font=font_tiny, fill=0)


def draw_y_axis(draw: ImageDraw, x: int, y: int, height: int,
                min_v: float, max_v: float, unit: str, right: bool = False, precision: int = 0):
    """Draws Y-axis ticks and labels (left or right side)."""
    font_tiny = get_font(11, "Bold")
    steps = 4
    for i in range(steps + 1):
        val = min_v + (max_v - min_v) * i / steps
        if abs(val) < 1e-9:
            val = 0.0
        vy = y + height - int(i * height / steps)
        label = f"{val:.{precision}f}"
        if not right:
            text_w = int(draw.textlength(label, font=font_tiny))
            lx = x - 3 - text_w  # right-align against the tick
        else:
            lx = x + 6
        draw.text((lx, vy - 6), label, font=font_tiny, fill=0)
    # Unit label — right-aligned on left axis, left-aligned on right axis
    if not right:
        unit_w = int(draw.textlength(unit, font=font_tiny))
        ux = x - 2 - unit_w
    else:
        ux = x + 4
    draw.text((ux, y - 20), unit, font=font_tiny, fill=0)


def draw_dashed_vline(draw: ImageDraw, x: int, y: int, height: int, dash: int = 4):
    """Draws a vertical dashed line (alternating filled/empty segments)."""
    for dy in range(0, height, dash * 2):
        y0 = y + dy
        y1 = min(y + dy + dash, y + height)
        draw.line([x, y0, x, y1], fill=0, width=2)


def draw_h_grid(draw: ImageDraw, x: int, y: int, width: int, height: int, steps: int = 4):
    """Draws dashed horizontal grid lines at each Y-axis step (skip bottom border, include top)."""
    for i in range(1, steps + 1):
        vy = y + height - int(i * height / steps)
        for dx in range(0, width, 8):
            x0 = x + dx
            x1 = min(x + dx + 4, x + width)
            draw.line([x0, vy, x1, vy], fill=0, width=1)


def draw_chart_title(draw: ImageDraw, x: int, y: int, title: str):
    font_small = get_font(12, "Bold")
    draw.text((x, y - 18), title.upper(), font=font_small, fill=0)


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
                draw.line([sx0, sy0, sx1, sy1], fill=color, width=2)
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
                          start_hour: int = 0):
    """
    Renders two dual-axis 24-hour charts stacked vertically.

    Chart 1 — Temperature + Precipitation:
      Left axis:  temperature line (°C), auto-scaled with ±5° padding.
      Right axis: precipitation bars (mm/h), floor 0–10, grows if data exceeds 5 mm.

    Chart 2 — Sunshine + Wind:
      Left axis:  sunshine bars (min/h), fixed 0–60.
      Right axis: wind speed dashed line (km/h), floor 0–20, grows dynamically.

    Both charts share a 24-hour X axis with 3-hour tick labels starting at
    start_hour (typically current_hour − 1).  A dashed "ORA" (now) marker
    is drawn at index 1 (1 hour into the series = current hour).

    The data arrays are 24 elements each, produced by get_next_24h_series()
    which returns 1 past hour + 23 forecast hours.
    """
    font_tiny      = get_font(11, "Regular")


    LEFT_PAD  = 28  # space for left Y-axis labels
    RIGHT_PAD = 32  # space for right Y-axis labels
    chart_w   = (555 - x) - LEFT_PAD - RIGHT_PAD  # fills left panel from x to divider
    chart_h   = 120
    cx        = x + LEFT_PAD

    # ── Chart 1: Temperatura + Precipitazioni ─────────────────────────────────
    c1y = y + 22
    draw_chart_title(draw, cx+125, c1y-2, "Temperatura (°C) + Precipitazioni (mm/h)")
    draw_24h_grid(draw, cx, c1y, chart_w, chart_h, start_hour=start_hour)

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

    draw_h_grid(draw, cx, c1y, chart_w, chart_h)
    draw_bar_chart(draw, cx, c1y, chart_w, chart_h, prec_data, max_v=p_max, fill=True)
    draw_line_chart(draw, cx, c1y, chart_w, chart_h, temp_data, min_v=t_min, max_v=t_max, color=0)

    draw_y_axis(draw, cx, c1y, chart_h, t_min, t_max, "°C", right=False)
    # Use 1 decimal if p_max is small to avoid rounded 1,1,0,0 labels
    prec_precision = 1 if p_max <= 10.0 else 0
    draw_y_axis(draw, cx + chart_w, c1y, chart_h, 0, p_max, "mm", right=True, precision=prec_precision)

    # "ORA" marker — vertical dashed line at index 1 in the 24-element array.
    # The series starts 1 hour before now (index 0 = past hour), so index 1
    # aligns with the current hour.
    ora_x = cx + (1 * chart_w // 24)
    draw_dashed_vline(draw, ora_x, c1y, chart_h)
    draw.text((ora_x -11, c1y-15), "ORA", font=font_tiny, fill=0)

    # ── Chart 2: Sole + Vento ─────────────────────────────────────────────────
    c2y = c1y + chart_h + 40
    draw_chart_title(draw, cx+165, c2y-2, "Sole (min/h) + Vento (km/h)")
    draw_24h_grid(draw, cx, c2y, chart_w, chart_h, start_hour=start_hour)

    s_max = 60.0
    valid_winds = [v for v in wind_data if v is not None]
    w_max = max(20.0, (max(valid_winds) + 5.0) if valid_winds else 20.0)

    draw_h_grid(draw, cx, c2y, chart_w, chart_h)
    draw_bar_chart(draw, cx, c2y, chart_w, chart_h, sun_data,  max_v=s_max, fill=False)
    draw_line_chart(draw, cx, c2y, chart_w, chart_h, wind_data, min_v=0, max_v=w_max, color=0, dashed=True)

    draw_y_axis(draw, cx, c2y, chart_h, 0, s_max, "min", right=False)
    draw_y_axis(draw, cx + chart_w, c2y, chart_h, 0, w_max, "km/h", right=True)

    # ORA marker at index 1 (same as Chart 1)
    draw_dashed_vline(draw, ora_x, c2y, chart_h)
