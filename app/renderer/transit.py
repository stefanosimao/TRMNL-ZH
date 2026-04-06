from PIL import ImageDraw, ImageFont
from .fonts import get_font

# Short display names for known terminals
_DEST_SHORT = {
    "klusplatz":    "Klusplatz",
    "oerlikon":     "Oerlikon",
    "triemli":      "Triemli",
    "wiedikon":     "Wiedikon",
    "dunkelhölzli": "Dunkelholzli",
    "bahnhofplatz": "Bahnhofplatz",
}

def _shorten_dest(dest: str) -> str:
    d = dest.lower()
    for key, short in _DEST_SHORT.items():
        if key in d:
            return short
    return dest


def render_transit_section(draw: ImageDraw, x: int, y: int, station_name: str, departures: list):
    """
    Renders transit section (street-timetable style).
    - station_name: Heading with black background, white text.
    - departures: Rows with line, destination, and minutes.
    """
    font_bold = get_font(17, "Bold")
    font_reg  = get_font(15, "Regular")

    PANEL_W      = 233  # rx=560 to x=793
    header_height = 22
    row_height    = 22

    # Header: station name, black background
    draw.rectangle([x, y, x + PANEL_W, y + header_height], fill=0)
    draw.text((x + 4, y + 2), station_name.upper(), font=font_bold, fill=255)

    curr_y = y + header_height + 2

    for dep in (d for d in departures if not d.get("cancelled")):
        # Line badge (black filled) — width adapts to text so "80" never clips
        line = str(dep.get("line", ""))
        text_w = int(draw.textlength(line, font=font_bold))
        line_w = max(24, text_w + 8)
        if line == "3":
            draw.rectangle([x, curr_y, x + 4 + line_w, curr_y + row_height - 2], fill=0)
            draw.text((x + 9.5, curr_y + 1), line, font=font_bold, fill=255)
        else:
            draw.rectangle([x, curr_y, x + 2 + line_w, curr_y + row_height - 2], fill=0)
            draw.text((x + 6, curr_y + 1), line, font=font_bold, fill=255)

        # Destination (shortened to terminal name)
        dest = _shorten_dest(dep.get("destination", "").replace("Zürich, ", ""))
        draw.text((x + line_w + 8, curr_y - 1 ), dest, font=font_reg, fill=0)

        # Time: right-aligned; if delayed show scheduled+delay
        delay = dep.get("delay", 0) or 0
        if delay > 0:
            time_text = f"(+{delay}') {dep.get('scheduled_time', dep.get('time', ''))}"
        else:
            time_text = dep.get("time", "")
        time_w = int(draw.textlength(time_text, font=font_bold))
        draw.text((x + PANEL_W - time_w - 8, curr_y + 2), time_text, font=font_bold, fill=0)

        curr_y += row_height

    return curr_y
