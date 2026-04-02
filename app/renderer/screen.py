from PIL import Image, ImageDraw
from datetime import datetime, date, timedelta
from .fonts import get_font
from .transit import render_transit_section
from .charts import render_weather_charts
from .weather_icons import draw_weather_icon
from ..services.meteosuisse import get_daily_forecast, get_sun_times

def compose_screen(data: dict):
    """
    Main 800x480 compositor as per section 5 of specification.
    - Left 2/3 (555px): Weather tiles + Forecast + Charts.
    - Right 1/3 (245px): Transit + Summary.
    """
    img = Image.new("1", (800, 480), 255) # 1-bit mode, White
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_bold = get_font(24, "Bold")
    font_reg = get_font(18, "Regular")
    font_small = get_font(14, "Regular")
    font_tiny = get_font(12, "Regular")
    
    # Draw Divider (555px from left)
    draw.line([555, 0, 555, 480], fill=0, width=1)
    
    # 1. Weather Tiles (Top Left Row)
    # 3 tiles, top row (Inside, Balcony, Zurich)
    weather = data.get("weather", {})
    temps = [
        ("DENTRO", weather.get("indoor", {}).get("temperature", "--")),
        ("BALCONE", weather.get("outdoor", {}).get("temperature", "--")),
        ("ZÜRICH 8047", weather.get("meteo", {}).get("temp", "--"))
    ]
    
    tile_w = 555 // 3
    for i, (label, val) in enumerate(temps):
        x = i * tile_w
        draw.rectangle([x + 4, 4, x + tile_w - 4, 60], outline=0, width=1)
        draw.text((x + 10, 8), label, font=font_small, fill=0)
        draw.text((x + 10, 24), f"{val}°C", font=font_bold, fill=0)
        
    # 2. Forecast Tiles (Second Row)
    meteo_full = data.get("meteo_full")
    sun_times = get_sun_times()
    
    days = ["OGGI", "DOMANI", (date.today() + timedelta(days=2)).strftime("%a %d.%m").upper()]
    for i, label in enumerate(days):
        x = i * tile_w
        draw.rectangle([x + 4, 65, x + tile_w - 4, 150], outline=0, width=1)
        draw.text((x + 10, 68), label, font=font_small, fill=0)
        
        forecast = get_daily_forecast(meteo_full, days_offset=i)
        if forecast:
            draw_weather_icon(draw, x + 10, 85, forecast.get("pictogram"))
            
            # Temps (Min/Max)
            min_t, max_t = forecast.get("min_temp", "--"), forecast.get("max_temp", "--")
            draw.text((x + 55, 85), f"{min_t}/{max_t}°", font=font_reg, fill=0)
            
            # Sun times (for today)
            if i == 0:
                draw.text((x + 55, 110), f"↑{sun_times['sunrise']} ↓{sun_times['sunset']}", font=font_tiny, fill=0)
            
            # Rain
            precip = forecast.get("precip", 0)
            draw.text((x + 55, 128), f"Rain: {precip}mm", font=font_tiny, fill=0)

    # 3. Charts (MeteoSuisse)
    if meteo_full:
        render_weather_charts(draw, 10, 160, meteo_full)
    else:
        draw.text((20, 180), "Dati MeteoSuisse non disponibili", font=font_reg, fill=0)
    
    # ... (Rest of the right-side rendering for transit/summary)
    # 4. Transit (Right Side, 245px wide)
    transit = data.get("transit", {})
    y = render_transit_section(draw, 555 + 5, 10, "ALBISRIEDEN", transit.get("station_1", []))
    y = render_transit_section(draw, 555 + 5, y + 15, "FELLENBERGSTR.", transit.get("station_2", []))
    
    # 5. Summary (Bottom Right)
    summary_y = y + 15
    draw.rectangle([555 + 5, summary_y, 795, 460], outline=0)
    draw.text((565, summary_y + 4), "RIEPILOGO", font=font_bold, fill=0)
    summary_text = data.get("summary", "Caricamento summary...")
    draw.text((565, summary_y + 35), summary_text[:120] + "...", font=font_small, fill=0)
    
    # Metadata/Clock
    now_str = datetime.now().strftime("%H:%M")
    draw.text((10, 460), f"Ultimo aggiornamento: {now_str} · {datetime.now().strftime('%d.%m.%Y')}", font=font_small, fill=0)
    
    return img
