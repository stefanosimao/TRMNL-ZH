from PIL import Image, ImageDraw
from datetime import datetime, date, timedelta
from .fonts import get_font, word_wrap
from .transit import render_transit_section
from .charts import render_weather_charts
from .weather_icons import draw_weather_icon
from ..services.meteosuisse import get_daily_forecast, get_sun_times, get_next_24h_series
from zoneinfo import ZoneInfo
from ..config import settings

# Italian abbreviated day names (Monday=0 … Sunday=6)
_IT_DAYS = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
# Italian full day names for the clock section
_IT_DAYS_FULL = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
# Italian month names (1-indexed)
_IT_MONTHS = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
              "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]

def _it_day_label(d: date) -> str:
    """Returns e.g. 'SAB 04.04'."""
    return f"{_IT_DAYS[d.weekday()]} {d.strftime('%d.%m')}"


def _it_full_date(d: date) -> str:
    """Returns e.g. 'giovedì 2 aprile 2026'."""
    return f"{_IT_DAYS_FULL[d.weekday()]} {d.day} {_IT_MONTHS[d.month]} {d.year}"


def _draw_battery(draw: ImageDraw, x: int, y: int, pct: int):
    """Draws a small battery icon (22x11 px) with fill level + percentage text."""
    # Outer case: 18x10
    draw.rectangle([x, y, x + 17, y + 9], outline=0, width=1)
    # Terminal nub on the right
    draw.rectangle([x + 18, y + 3, x + 19, y + 6], fill=0)
    # Inner fill proportional to pct (max 15px inside the 2px border)
    fill_w = max(0, int(pct * 15 / 100))
    if fill_w > 0:
        draw.rectangle([x + 2, y + 2, x + 1 + fill_w, y + 7], fill=0)
    # Percentage label to the right of the icon
    font_battery = get_font(12, "Regular")
    draw.text((x + 23, y-3), f"{pct}%", font=font_battery, fill=0)


def compose_screen(data: dict) -> Image.Image:
    """
    Main 800x480 image compositor for the TRMNL e-ink display.

    Left panel (555px): current temperatures, 3-day forecast, 24h charts.
    Right panel (245px): transit departures, AI summary, clock/metadata.
    """
    img  = Image.new("1", (800, 480), 255)
    draw = ImageDraw.Draw(img)

    font_bold    = get_font(18, "Bold")
    font_reg     = get_font(16, "Bold")
    font_small   = get_font(14, "Regular")
    font_tiny    = get_font(11, "Bold")

    # Vertical divider
    draw.line([555, 0, 555, 480], fill=0, width=1)

    LX     = 3    # left-panel x offset (bezel clearance)
    tile_w_1 = 137.3
    tile_w_2 = 183

    weather    = data.get("weather", {})
    meteo_full = data.get("meteo_full")
    today      = date.today()

    # ── Row 1: Date box + 3 temperature tiles ─────────────────────────────────
    # Box 0: date + battery 
    x0 = LX
    draw.rectangle([x0 + 4, 4, x0 + tile_w_1 - 4, 50], outline=0, width=1)
    draw.text((x0 + 8, 9), _it_day_label(today), font=font_bold, fill=0)
    battery_pct = data.get("battery")
    if battery_pct is not None:
        _draw_battery(draw, x0 + 8, 34, int(battery_pct))

    # Box 1: BALCONE, Box 2: ZÜRICH, Box 3: CASA
    for i, (label, val) in enumerate([
        ("BALCONE", weather.get("outdoor", {}).get("temperature")),
        ("ZÜRICH",  weather.get("meteo",   {}).get("temp")),
        ("CASA",    weather.get("indoor",  {}).get("temperature")),
    ]):
        x = (i + 1) * tile_w_1 + LX
        draw.rectangle([x + 4, 4, x + tile_w_1 - 4, 50], outline=0, width=1)
        draw.text((x + 8, 7), label, font=font_small, fill=0)
        temp_str = f"{val:.1f}°C" if isinstance(val, (int, float)) else "--"
        draw.text((x + 8, 25), temp_str, font=font_bold, fill=0)

    # ── Row 2: 3-day forecast tiles ───────────────────────────────────────────
    forecast_labels = ["OGGI", "DOMANI", _it_day_label(today + timedelta(days=2))]
    for i, label in enumerate(forecast_labels):
        x = i * tile_w_2 + LX
        draw.rectangle([x + 4, 54, x + tile_w_2 - 4, 137], outline=0, width=1)
        draw.text((x + 8, 57), label, font=font_small, fill=0)

        forecast = get_daily_forecast(meteo_full, days_offset=i)
        if forecast:
            draw_weather_icon(draw, x + 15, 80, forecast.get("pictogram"))

            min_t = forecast.get("min_temp")
            max_t = forecast.get("max_temp")
            min_s = f"{min_t:.0f}" if isinstance(min_t, (int, float)) else "--"
            max_s = f"{max_t:.0f}" if isinstance(max_t, (int, float)) else "--"
            draw.text((x + 66, 72), f"{min_s} / {max_s}°", font=font_reg, fill=0)

            day_sun = get_sun_times(today + timedelta(days=i))
            draw.text((x + 66, 94), f"↑{day_sun['sunrise']} ↓{day_sun['sunset']}", font=font_small, fill=0)

            precip = forecast.get("precip") or 0
            draw.text((x + 67, 113), f"{precip:.1f} mm", font=get_font(14, "Bold"), fill=0)

    # ── Rows 3+4: Charts ──────────────────────────────────────────────────────
    series = data.get("series", {})
    if not series and meteo_full:
        series = {
            "temp":   get_next_24h_series(meteo_full, "tre200h0"),
            "precip": get_next_24h_series(meteo_full, "rre150h0"),
            "sun":    get_next_24h_series(meteo_full, "sre000h0"),
            "wind":   get_next_24h_series(meteo_full, "fu3010h0"),
        }

    _now_zh = datetime.now(ZoneInfo(settings.TIMEZONE))
    start_hour = (_now_zh.hour - 1) % 24
    sun_times = get_sun_times(today)
    render_weather_charts(
        draw, LX, 140,
        temp_data=series.get("temp",   [None] * 24),
        prec_data=series.get("precip", [None] * 24),
        sun_data=series.get("sun",     [None] * 24),
        wind_data=series.get("wind",   [None] * 24),
        start_hour=start_hour,
    )

    ts = data.get("timestamps", {})

    # ── RIGHT SIDE ────────────────────────────────────────────────────────────
    rx = 560

    # Transit sections
    transit = data.get("transit", {})
    y = render_transit_section(draw, rx, 4, "ALBISRIEDEN", transit.get("station_1", []))
    y = render_transit_section(draw, rx, y + 8, "FELLENBERGSTRASSE", transit.get("station_2", []))

    # ── Summary tile (extends to near bottom) ─────────────────────────────────
    summary_y      = y + 8
    summary_bottom = 433
    draw.rectangle([rx, summary_y, 793, summary_bottom], outline=0, width=1)

    draw.rectangle([rx, summary_y, 793, summary_y + 19], fill=0)
    draw.text((rx + 4, summary_y+1), "RIEPILOGO INTELLIGENTE", font=get_font(14, "Bold"), fill=255)
    draw.text((rx + 4, summary_y + 22),
              f"AGGIORNATO {ts.get('summary', '--:--')}", font=font_tiny, fill=0)

    # Word-wrap summary text using the same font for measuring and drawing
    summary_text = data.get("summary", "Caricamento riepilogo intelligente...")
    summary_font = get_font(14, "Bold")
    summary_max_px = 793 - rx - 8
    lines = word_wrap(summary_text, summary_font, summary_max_px)
    max_lines = (summary_bottom - 4 - (summary_y + 36)) // 17

    text_y = summary_y + 36
    for i, line in enumerate(lines[:max_lines]):
        is_last_visible = (i == max_lines - 1) and len(lines) > max_lines
        display_line = line.rstrip(".,;:!? ") + "…" if is_last_visible else line
        draw.text((rx + 4, text_y), display_line, font=summary_font, fill=0)
        text_y += 17

    # ── Timestamps footer (below summary) ────────────────────────────────────
    ts_line = (f"S {ts.get('switchbot', '--')} "
               f"/ T {ts.get('transit', '--')} "
               f"/ M {ts.get('meteo', '--')} "
               f"/ G {ts.get('summary', '--')}")
    draw.text((rx, summary_bottom + 4), ts_line, font=get_font(13, "Regular"), fill=0)

    return img
