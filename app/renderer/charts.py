from PIL import ImageDraw, ImageFont
from typing import List, Optional
from datetime import datetime
from .fonts import get_font

def draw_24h_grid(draw: ImageDraw, x: int, y: int, width: int, height: int):
    """Draws the X-axis grid for 24 hours."""
    font_tiny = get_font(10, "Regular")
    
    # Bottom line
    draw.line([x, y + height, x + width, y + height], fill=0)
    
    # Vertical lines for 3h intervals
    for h in range(0, 25, 3):
        lx = x + (h * width // 24)
        # Draw tick
        draw.line([lx, y + height, lx, y + height + 4], fill=0)
        # Draw label
        label = f"{h:02d}" if h < 24 else "00"
        draw.text((lx - 5, y + height + 6), label, font=font_tiny, fill=0)

def draw_chart_title(draw: ImageDraw, x: int, y: int, title: str):
    font_small = get_font(12, "Bold")
    draw.text((x, y - 18), title.upper(), font=font_small, fill=0)

def draw_line_chart(draw: ImageDraw, x: int, y: int, width: int, height: int, 
                    data: List[Optional[float]], color: int = 0, dashed: bool = False):
    """Draws a line chart."""
    valid_points = [(i, v) for i, v in enumerate(data) if v is not None]
    if not valid_points:
        return
        
    min_v = min(v for i, v in valid_points)
    max_v = max(v for i, v in valid_points)
    
    # Ensure some range
    if max_v == min_v:
        max_v += 1
        min_v -= 1
        
    def scale_y(v):
        return y + height - int((v - min_v) * height / (max_v - min_v))
        
    def scale_x(i):
        return x + (i * width // 23)

    points = []
    for i, v in valid_points:
        points.append((scale_x(i), scale_y(v)))
        
    if len(points) > 1:
        if dashed:
            # Simple dashed line
            for j in range(len(points) - 1):
                p1, p2 = points[j], points[j+1]
                # In reality, Pillow doesn't do dashed easily, so we just draw solid for now
                draw.line([p1, p2], fill=color, width=1)
        else:
            draw.line(points, fill=color, width=2)

def draw_bar_chart(draw: ImageDraw, x: int, y: int, width: int, height: int, 
                    data: List[Optional[float]], fill: bool = True):
    """Draws a bar chart (e.g. for precipitation or sunshine)."""
    valid_values = [v for v in data if v is not None]
    if not valid_values:
        return
        
    max_v = max(valid_values)
    if max_v <= 0:
        return # Nothing to draw
        
    bar_width = (width // 24) - 2
    
    for i, v in enumerate(data):
        if v is None or v <= 0:
            continue
            
        bx = x + (i * width // 24) + 1
        bh = int(v * height / max_v)
        
        if fill:
            draw.rectangle([bx, y + height - bh, bx + bar_width, y + height], fill=0)
        else:
            # Stippled/outline for sunshine
            draw.rectangle([bx, y + height - bh, bx + bar_width, y + height], outline=0)

def render_weather_charts(draw: ImageDraw, x: int, y: int, meteo_data: dict):
    """
    Renders the two 24h charts as per specification.
    """
    from ..services.meteosuisse import get_24h_series
    
    width = 530
    chart_h = 100
    
    # 1. TEMP + PREC (OGGI)
    chart1_y = y + 20
    draw_chart_title(draw, x, chart1_y, "Temperatura (°C) + Precipitazioni (mm/h)")
    draw_24h_grid(draw, x, chart1_y, width, chart_h)
    
    temp_data = get_24h_series(meteo_data, "tre200h0")
    prec_data = get_24h_series(meteo_data, "rre150h0")
    
    draw_bar_chart(draw, x, chart1_y, width, chart_h, prec_data, fill=True)
    draw_line_chart(draw, x, chart1_y, width, chart_h, temp_data, color=0)
    
    # Current hour marker "ORA"
    now_h = datetime.now().hour
    ox = x + (now_h * width // 24)
    draw.line([ox, chart1_y, ox, chart1_y + chart_h], fill=0, width=1)
    
    # 2. SOLE + VENTO
    chart2_y = chart1_y + chart_h + 50
    draw_chart_title(draw, x, chart2_y, "Sole (min/h) + Vento (km/h)")
    draw_24h_grid(draw, x, chart2_y, width, chart_h)
    
    sun_data = get_24h_series(meteo_data, "sre000h0")
    wind_data = get_24h_series(meteo_data, "fu3010h0")
    
    draw_bar_chart(draw, x, chart2_y, width, chart_h, sun_data, fill=False)
    draw_line_chart(draw, x, chart2_y, width, chart_h, wind_data, color=0, dashed=True)
