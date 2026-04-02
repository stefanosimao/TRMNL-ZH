from PIL import ImageDraw

def draw_weather_icon(draw: ImageDraw, x: int, y: int, pictogram_id: int):
    """
    Draws a 40x40 1-bit weather icon based on MeteoSwiss jp2000d0 codes.
    1: Sun, 2: Sun/Cloud, 3: Cloud, 4: Overcast, 5: Rain, etc.
    """
    # Simple geometric icon drawing for now
    if pictogram_id is None:
        return
        
    p = int(pictogram_id)
    
    # 1: Clear/Sunny
    if p == 1:
        draw.ellipse([x+10, y+10, x+30, y+30], outline=0, width=2)
        # Rays
        for angle in range(0, 360, 45):
            # (Just simple representation)
            pass
    # 2: Mostly sunny
    elif p == 2:
        draw.ellipse([x+15, y+5, x+35, y+25], outline=0) # Sun behind
        draw.chord([x+5, y+15, x+30, y+35], 0, 360, fill=255, outline=0) # Cloud
    # 3-4: Cloudy/Overcast
    elif p in [3, 4]:
        draw.chord([x+5, y+15, x+35, y+35], 0, 360, outline=0)
    # 5-25: Rain/Snow
    elif 5 <= p <= 25:
        draw.chord([x+5, y+10, x+35, y+30], 0, 360, outline=0) # Cloud
        # Rain drops
        draw.line([x+10, y+32, x+10, y+38], fill=0)
        draw.line([x+20, y+32, x+20, y+38], fill=0)
        draw.line([x+30, y+32, x+30, y+38], fill=0)
    else:
        # Default fallback
        draw.rectangle([x+10, y+10, x+30, y+30], outline=0)
