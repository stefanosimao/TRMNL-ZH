from PIL import Image, ImageDraw
from datetime import datetime, date, timedelta
from .fonts import get_font
from .transit import render_transit_section
from .charts import render_weather_charts
from .weather_icons import draw_weather_icon
from ..services.meteosuisse import get_daily_forecast, get_sun_times

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


def compose_screen(data: dict) -> Image.Image:
    """
    Main 800x480 image compositor for the TRMNL e-ink display.

    Left panel (555px): current temperatures, 3-day forecast, 24h charts.
    Right panel (245px): transit departures, AI summary, clock/metadata.

    Args:
        data: dict with keys:
            weather       – {indoor, outdoor, meteo} temperature dicts
            transit       – {station_1, station_2} departure lists
            summary       – Italian summary string from Gemini
            meteo_full    – full MeteoSuisse data dict
            battery       – int percentage or None
            timestamps    – {switchbot, meteo, summary} "HH:MM" strings
    """
    img  = Image.new("1", (800, 480), 255)
    draw = ImageDraw.Draw(img)

    font_bold_lg = get_font(28, "Bold")
    font_bold    = get_font(18, "Bold")
    font_reg     = get_font(16, "Regular")
    font_small   = get_font(14, "Regular")
    font_tiny    = get_font(11, "Regular")

    # Vertical divider
    draw.line([555, 0, 555, 480], fill=0, width=1)

    # ── Row 1: Temperature tiles ──────────────────────────────────────────────
    weather = data.get("weather", {})
    temps = [
        ("DENTRO",      weather.get("indoor",  {}).get("temperature")),
        ("BALCONE",     weather.get("outdoor", {}).get("temperature")),
        ("ZÜRICH 8047", weather.get("meteo",   {}).get("temp")),
    ]

    tile_w = 555 // 3
    for i, (label, val) in enumerate(temps):
        x = i * tile_w
        draw.rectangle([x + 4, 4, x + tile_w - 4, 58], outline=0, width=1)
        draw.text((x + 8, 7), label, font=font_tiny, fill=0)
        temp_str = f"{val:.1f}°C" if isinstance(val, (int, float)) else "--"
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

            min_t = forecast.get("min_temp")
            max_t = forecast.get("max_temp")
            min_s = f"{min_t:.0f}" if isinstance(min_t, float) else "--"
            max_s = f"{max_t:.0f}" if isinstance(max_t, float) else "--"
            draw.text((x + 55, 80), f"{min_s}/{max_s}°", font=font_reg, fill=0)

            if i == 0:
                draw.text((x + 55, 102),
                          f"↑{sun_times['sunrise']} ↓{sun_times['sunset']}",
                          font=font_tiny, fill=0)

            precip = forecast.get("precip") or 0
            draw.text((x + 55, 120), f"{precip:.1f}mm", font=font_tiny, fill=0)

    # ── Rows 3+4: Charts ──────────────────────────────────────────────────────
    if meteo_full:
        render_weather_charts(
            draw, 10, 158, meteo_full,
            sunrise=sun_times.get("sunrise"),
            sunset=sun_times.get("sunset"),
        )
    else:
        draw.text((20, 175), "Dati MeteoSuisse non disponibili", font=font_reg, fill=0)

    # ── Footer (left side) ───────────────────────────────────────────────────
    ts = data.get("timestamps", {})
    footer = (f"SwitchBot: {ts.get('switchbot', '--:--')} · "
              f"Meteo: {ts.get('meteo', '--:--')} · "
              f"Riepilogo: {ts.get('summary', '--:--')} · "
              f"Fonte: MeteoSwiss PLZ 8047")
    draw.text((6, 466), footer, font=font_tiny, fill=0)

    # ── RIGHT SIDE ────────────────────────────────────────────────────────────
    rx = 560

    # Transit sections
    transit = data.get("transit", {})
    y = render_transit_section(draw, rx, 4, "ALBISRIEDEN", transit.get("station_1", []))
    y = render_transit_section(draw, rx, y + 8, "FELLENBERGSTR.", transit.get("station_2", []))

    # ── Summary tile ─────────────────────────────────────────────────────────
    summary_y      = y + 8
    summary_bottom = 390
    draw.rectangle([rx, summary_y, 796, summary_bottom], outline=0, width=1)

    draw.rectangle([rx, summary_y, 796, summary_y + 18], fill=0)
    draw.text((rx + 4, summary_y + 2), "RIEPILOGO INTELLIGENTE", font=font_tiny, fill=255)
    draw.text((rx + 4, summary_y + 22),
              f"aggiornato {ts.get('summary', '--:--')}", font=font_tiny, fill=0)

    # Word-wrap summary text using actual pixel width measurement
    summary_text = data.get("summary", "Caricamento riepilogo intelligente...")
    max_px = 796 - rx - 8
    lines, current_line = [], ""
    for word in summary_text.split():
        test = (current_line + " " + word).strip()
        w = draw.textlength(test, font=font_tiny)
        if w <= max_px:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    text_y = summary_y + 36
    for line in lines[:7]:
        draw.text((rx + 4, text_y), line, font=font_tiny, fill=0)
        text_y += 13

    # ── Clock + date section ──────────────────────────────────────────────────
    clock_y = summary_bottom + 6
    now = datetime.now()

    draw.text((rx, clock_y), now.strftime("%H:%M"), font=font_bold_lg, fill=0)
    draw.text((rx, clock_y + 34), _it_full_date(today), font=font_small, fill=0)

    battery = data.get("battery")
    detail_y = clock_y + 50
    if battery is not None:
        draw.text((rx, detail_y), f"Batteria: {battery}%", font=font_tiny, fill=0)
        detail_y += 14

    draw.text((rx, detail_y), f"ultimo agg.: {now.strftime('%H:%M:%S')}", font=font_tiny, fill=0)

    return img
