from PIL import ImageDraw, ImageFont
from .fonts import get_font

def render_transit_section(draw: ImageDraw, x: int, y: int, station_name: str, departures: list):
    """
    Renders transit section (street-timetable style).
    - station_name: Heading with black background, white text.
    - departures: Rows with line, destination, and minutes.
    """
    font_bold = get_font(13, "Bold")
    font_reg = get_font(11, "Regular")

    # Header: station name, black background
    header_height = 18
    draw.rectangle([x, y, x + 240, y + header_height], fill=0)
    draw.text((x + 4, y + 2), station_name.upper(), font=font_bold, fill=255)

    curr_y = y + header_height + 3

    for dep in departures:
        # Line badge (black filled) — width adapts to text so "80" never clips
        line = dep.get("line", "")
        text_w = int(draw.textlength(line, font=font_bold))
        line_w = max(24, text_w + 8)
        draw.rectangle([x + 2, curr_y, x + 2 + line_w, curr_y + 15], fill=0)
        draw.text((x + 5, curr_y + 1), line, font=font_bold, fill=255)

        # Destination
        dest = dep.get("destination", "").replace("Zürich, ", "")
        draw.text((x + line_w + 5, curr_y + 1), dest[:22], font=font_reg, fill=0)

        # Show scheduled time; if delayed, show scheduled+delay so the sum is the real time
        delay = dep.get("delay", 0) or 0
        if delay > 0:
            time_text = f"{dep.get('scheduled_time', dep.get('time', ''))}+{delay}"
        else:
            time_text = dep.get("time", "")
        draw.text((x + 175, curr_y + 1), time_text, font=font_bold, fill=0)

        curr_y += 18

    return curr_y
