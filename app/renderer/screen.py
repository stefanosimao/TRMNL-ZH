from PIL import Image, ImageDraw
from datetime import datetime, date, timedelta
from .fonts import get_font
from .transit import render_transit_section
from .charts import render_weather_charts
from .weather_icons import draw_weather_icon
from ..services.meteosuisse import get_daily_forecast, get_sun_times
from ..cache import global_cache
import time

# Italian abbreviated day names (Monday=0 … Sunday=6)
_IT_DAYS = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
# Italian full day names for the clock section
_IT_DAYS_FULL = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
# Italian month names
_IT_MONTHS = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
              "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _it_day_label(d: date) -> str:
    """Returns e.g. 'SAB 04.04' for a future date, or 'OGGI'/'DOMANI' for offset 0/1."""
    return f"{_IT_DAYS[d.weekday()]} {d.strftime('%d.%m')}"


def _it_full_date(d: date) -> str:
    """Returns e.g. 'giovedì 2 aprile 2026'."""
    return f"{_IT_DAYS_FULL[d.weekday()]} {d.day} {_IT_MONTHS[d.month]} {d.year}"


def _cache_ts(key: str) -> str:
    """Returns HH:MM of the last successful cache update for a key, or '--:--'."""
    meta = global_cache.get_with_meta(key)
    if meta and meta.get("timestamp"):
        return datetime.fromtimestamp(meta["timestamp"]).strftime("%H:%M")
    return "--:--"


def compose_screen(data: dict):
    """
    Main 800x480 compositor as per section 5 of specification.
    - Left 2/3 (555px): Weather tiles + Forecast + Charts.
    - Right 1/3 (245px): Transit + Summary + Clock.
    """
    img = Image.new("1", (800, 480), 255)  # 1-bit mode, White
    draw = ImageDraw.Draw(img)

    # Fonts
    font_bold_lg = get_font(28, "Bold")   # large clock
    font_bold    = get_font(18, "Bold")
    font_reg     = get_font(16, "Regular")
    font_small   = get_font(14, "Regular")
    font_tiny    = get_font(11, "Regular")

    # Vertical divider
    draw.line([555, 0, 555, 480], fill=0, width=1)

    # ── Row 1: Temperature tiles ──────────────────────────────────────────────
    weather = data.get("weather", {})
    temps = [
        ("DENTRO",     weather.get("indoor",  {}).get("temperature", "--")),
        ("BALCONE",    weather.get("outdoor", {}).get("temperature", "--")),
        ("ZÜRICH 8047", weather.get("meteo",  {}).get("temp", "--")),
    ]

    tile_w = 555 // 3
    for i, (label, val) in enumerate(temps):
        x = i * tile_w
        draw.rectangle([x + 4, 4, x + tile_w - 4, 58], outline=0, width=1)
        draw.text((x + 8, 7), label, font=font_tiny, fill=0)
        temp_str = f"{val}°C" if val != "--" else "--"
        draw.text((x + 8, 22), temp_str, font=font_bold, fill=0)

    # ── Row 2: 3-day forecast tiles ───────────────────────────────────────────
    meteo_full = data.get("meteo_full")
    sun_times  = get_sun_times()
    today      = date.today()

    forecast_labels = ["OGGI", "DOMANI", _it_day_label(today + timedelta(days=2))]
    for i, label in enumerate(forecast_labels):
        x = i * tile_w
        draw.rectangle([x + 4, 62, x + tile_w - 4, 152], outline=0, width=1)
        draw.text((x + 8, 65), label, font=font_tiny, fill=0)

        forecast = get_daily_forecast(meteo_full, days_offset=i)
        if forecast:
            draw_weather_icon(draw, x + 8, 80, forecast.get("pictogram"))

            min_t = forecast.get("min_temp", "--")
            max_t = forecast.get("max_temp", "--")
            min_s = f"{min_t:.0f}" if isinstance(min_t, float) else str(min_t)
            max_s = f"{max_t:.0f}" if isinstance(max_t, float) else str(max_t)
            draw.text((x + 55, 80), f"{min_s}/{max_s}°", font=font_reg, fill=0)

            if i == 0:
                draw.text((x + 55, 102), f"↑{sun_times['sunrise']} ↓{sun_times['sunset']}", font=font_tiny, fill=0)

            precip = forecast.get("precip", 0) or 0
            draw.text((x + 55, 120), f"{precip:.1f}mm", font=font_tiny, fill=0)

    # ── Rows 3+4: Charts ──────────────────────────────────────────────────────
    if meteo_full:
        render_weather_charts(draw, 10, 158, meteo_full)
    else:
        draw.text((20, 175), "Dati MeteoSuisse non disponibili", font=font_reg, fill=0)

    # ── Footer (left side) ───────────────────────────────────────────────────
    ts_transit  = _cache_ts("transit")   # transit is live so we skip or show "--"
    ts_switchbot = _cache_ts("switchbot")
    ts_meteo    = _cache_ts("meteo")
    ts_summary  = _cache_ts("summary")
    footer = (f"SwitchBot: {ts_switchbot} · Meteo: {ts_meteo} · "
              f"Riepilogo: {ts_summary} · Fonte: MeteoSwiss PLZ 8047")
    draw.text((6, 466), footer, font=font_tiny, fill=0)

    # ── RIGHT SIDE ────────────────────────────────────────────────────────────
    rx = 560  # right panel x origin

    # Transit sections
    transit = data.get("transit", {})
    y = render_transit_section(draw, rx, 4, "ALBISRIEDEN", transit.get("station_1", []))
    y = render_transit_section(draw, rx, y + 8, "FELLENBERGSTR.", transit.get("station_2", []))

    # ── Summary tile ─────────────────────────────────────────────────────────
    summary_y = y + 8
    summary_bottom = 390
    draw.rectangle([rx, summary_y, 796, summary_bottom], outline=0, width=1)

    # Header
    draw.rectangle([rx, summary_y, 796, summary_y + 18], fill=0)
    draw.text((rx + 4, summary_y + 2), "RIEPILOGO INTELLIGENTE", font=font_tiny, fill=255)

    # Timestamp
    draw.text((rx + 4, summary_y + 22), f"aggiornato {ts_summary}", font=font_tiny, fill=0)

    # Summary text — simple word-wrap at ~32 chars per line
    summary_text = data.get("summary", "Caricamento summary intelligente...")
    words = summary_text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if len(test) <= 32:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    text_y = summary_y + 36
    for line in lines[:7]:  # max 7 lines in the tile
        draw.text((rx + 4, text_y), line, font=font_tiny, fill=0)
        text_y += 13

    # ── Clock + date section ──────────────────────────────────────────────────
    clock_y = summary_bottom + 6
    now = datetime.now()

    # Large HH:MM
    draw.text((rx, clock_y), now.strftime("%H:%M"), font=font_bold_lg, fill=0)

    # Italian full date
    draw.text((rx, clock_y + 32), _it_full_date(today), font=font_small, fill=0)

    # Battery (passed in from device headers if available, else omitted)
    battery = data.get("battery")
    if battery is not None:
        draw.text((rx, clock_y + 50), f"Batteria: {battery}%", font=font_tiny, fill=0)

    # Last refresh timestamp
    draw.text((rx, clock_y + 64 if battery is not None else clock_y + 50),
              f"ultimo agg.: {now.strftime('%H:%M:%S')}", font=font_tiny, fill=0)

    return img
