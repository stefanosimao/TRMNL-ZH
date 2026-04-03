from PIL import ImageDraw, ImageFont
from .fonts import get_font

def render_transit_section(draw: ImageDraw, x: int, y: int, station_name: str, departures: list):
    """
    Renders transit section (street-timetable style).
    - station_name: Heading with black background, white text.
    - departures: Rows with line, destination, and minutes.
    """
    font_bold = get_font(18, "Bold")
    font_reg = get_font(16, "Regular")
    
    # Header: station name, black background
    header_height = 24
    draw.rectangle([x, y, x + 245, y + header_height], fill=0) # Black
    draw.text((x + 4, y + 2), station_name.upper(), font=font_bold, fill=255) # White
    
    curr_y = y + header_height + 4
    
    for dep in departures:
        # Line badge (black filled) — width adapts to text so "80" never clips
        line = dep.get("line", "")
        text_w = int(draw.textlength(line, font=font_bold))
        line_w = max(30, text_w + 10)
        draw.rectangle([x + 2, curr_y, x + 2 + line_w, curr_y + 20], fill=0)
        draw.text((x + 5, curr_y + 2), line, font=font_bold, fill=255)
        
        # Destination
        dest = dep.get("destination", "").replace("Zürich, ", "")
        draw.text((x + line_w + 5, curr_y + 2), dest[:18], font=font_reg, fill=0)
        
        # Minutes
        mins = str(dep.get("minutes"))
        delay = dep.get("delay", 0)
        
        min_text = f"{mins} min"
        if delay > 0:
            min_text = f"{mins}+{delay} min"
            
        draw.text((x + 190, curr_y + 2), min_text, font=font_bold, fill=0)
        
        curr_y += 24
    
    return curr_y
