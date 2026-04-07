"""
Gemini 2.5 Flash integration for the "Riepilogo Intelligente" panel.

Builds a structured Italian prompt from cached weather, forecast, alert,
and transit data, then calls Gemini to produce a single concise paragraph
with practical advice: what to wear, whether to carry an umbrella,
and any active weather alerts or transit disruptions.

After generation, the text is pixel-measured against the actual panel
layout (word-wrap at the summary font/width).  If it overflows or
underflows the box, up to 2 retries ask Gemini to adjust.  As a final
safety net, the text is truncated to fit the available lines.

The prompt is time-aware:
  - Daytime (05:00-21:59): focuses on the next 30 min / coming hours.
  - Night   (22:00-04:59): focuses on tomorrow morning's conditions.

Hourly temperature, precipitation, and wind data are included so the
model bases its advice on actual numbers rather than hallucinating from
daily min/max or alert titles (e.g. ground-frost alerts != air temp 0 C).

Transit disruptions are limited to lines 3 and 80 (delays and
cancellations only - departure times are already visible on the display).
"""
import asyncio
from google import genai
from google.genai import types
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ..config import settings

_ZURICH_TZ = ZoneInfo(settings.TIMEZONE)


def _get_relevant_hours(weather: dict, is_night: bool) -> dict:
    """
    Extracts hourly temp, precip, and wind for the time window Gemini
    should reason about.

    Daytime: the next 6 hours from now.
    Night:   tomorrow morning 06:00–12:00 (the period the user will
             wake up into).

    Returns {"temp": [...], "precip": [...], "wind": [...]} where each
    value is a list of (HH:MM, float) tuples.  MeteoSuisse stores times
    in UTC; they are converted to Europe/Zurich before windowing.
    """
    meteo_data = weather.get("meteo_full")
    if not meteo_data or "hourly" not in meteo_data:
        return {}

    params = {
        "temp":   "tre200h0",
        "precip": "rre150h0",
        "wind":   "fu3010h0",
    }

    now = datetime.now(_ZURICH_TZ)

    if is_night:
        target_date = (now + timedelta(days=1)).date() if now.hour >= 22 else now.date()
        start_hour, end_hour = 6, 12
    else:
        target_date = None
        start_hour = now.hour
        end_hour = now.hour + 6

    def _in_window(v_local: datetime) -> bool:
        if is_night:
            return v_local.date() == target_date and start_hour <= v_local.hour < end_hour
        return 0 <= (v_local - now).total_seconds() / 3600 <= 6

    result = {}
    for key, param in params.items():
        series = meteo_data["hourly"].get(param, [])
        values = []
        for entry in series:
            try:
                v_utc = datetime.fromisoformat(entry["valid_time"].replace("Z", "+00:00"))
                v_local = v_utc.astimezone(_ZURICH_TZ)
                if _in_window(v_local):
                    values.append((v_local.strftime("%H:%M"), entry["value"]))
            except (ValueError, KeyError):
                continue
        values.sort(key=lambda x: x[0])
        result[key] = values

    return result


def _build_prompt(weather: dict, transit: dict, alerts: list) -> str:
    indoor  = weather.get("indoor",  {})
    outdoor = weather.get("outdoor", {})
    meteo   = weather.get("meteo",   {})
    fc_today    = weather.get("forecast_today") or {}
    fc_tomorrow = weather.get("forecast_tomorrow") or {}

    now = datetime.now(_ZURICH_TZ)
    hour = now.hour
    is_night = hour >= 22 or hour < 5

    if is_night:
        time_context = (
            "Sono le ore notturne (dopo le 22 o prima delle 5). "
            "L'utente probabilmente non esce più stasera. "
            "Descrivi cosa aspettarsi DOMATTINA (meteo, temperatura, pioggia)."
        )
    else:
        time_context = (
            f"Sono le {now.strftime('%H:%M')}. "
            "L'utente potrebbe uscire nei prossimi 30 minuti. "
            "Digli cosa aspettarsi subito fuori (freddo, caldo, pioggia, neve, vento) "
            "e come evolverà nelle prossime ore."
        )

    lines = [
        "Sei un assistente meteo per Zurigo, zona Albisrieden.",
        "Scrivi UN paragrafo conciso in italiano (MAX 300 CARATTERI).",
        "",
        f"CONTESTO TEMPORALE: {time_context}",
        "",
        "REGOLE:",
        "- Sii pratico e diretto (puoi anche usare umorismo se vuoi): dì se serve giacca, ombrello, ecc. puoi anche menzionare se è una buona idea uscire o restare in casa (se brutto tempo e con meno di 2°C).",
        "- Sotto i 10°C, menziona la necessità di una giacca pesante. Sotto i 5°C, consiglia guanti e berretto. Sopra i 25°C, menziona che fa caldo.",
        "- Se ci sono allerte meteo attive, menzionale.",
        "- IMPORTANTE: le allerte per 'gelo al suolo' / 'Bodenfrost' riguardano la temperatura a livello del terreno, NON la temperatura dell'aria. Non dire che farà 0°C se i dati orari mostrano temperature più alte.",
        "- Basa le tue affermazioni sulle temperature SOLO sui dati orari e le previsioni fornite. Non inventare valori.",
        "- Se ci sono disruzioni sulle linee 3 o 80, menzionale brevemente.",
        "- NON menzionare orari di partenza dei mezzi (l'utente li vede già sul display).",
        "- Se non ci sono allerte né disruzioni, non menzionare trasporti.",
        "",
        "DATI ATTUALI:",
        f"  Ora: {now.strftime('%H:%M')}",
        f"  Temperatura balcone: {outdoor.get('temperature', 'n/d')}°C",
        f"  Temperatura MeteoSwiss (8047): {meteo.get('temp', 'n/d')}°C",
        f"  Temperatura casa: {indoor.get('temperature', 'n/d')}°C",
    ]

    if fc_today:
        min_t = fc_today.get('min_temp')
        max_t = fc_today.get('max_temp')
        prec  = fc_today.get('precip')
        min_s = f"{min_t:.0f}" if isinstance(min_t, float) else "n/d"
        max_s = f"{max_t:.0f}" if isinstance(max_t, float) else "n/d"
        prec_s = f"{prec:.1f}" if isinstance(prec, float) else "n/d"
        lines.append(f"  Previsione OGGI: {min_s}–{max_s}°C, precip. {prec_s} mm")

    if fc_tomorrow:
        min_t = fc_tomorrow.get('min_temp')
        max_t = fc_tomorrow.get('max_temp')
        prec  = fc_tomorrow.get('precip')
        min_s = f"{min_t:.0f}" if isinstance(min_t, float) else "n/d"
        max_s = f"{max_t:.0f}" if isinstance(max_t, float) else "n/d"
        prec_s = f"{prec:.1f}" if isinstance(prec, float) else "n/d"
        lines.append(f"  Previsione DOMANI: {min_s}–{max_s}°C, precip. {prec_s} mm")

    # Add hourly data for the relevant window (temp, precip, wind)
    hourly = _get_relevant_hours(weather, is_night)
    time_label = "DOMATTINA" if is_night else "PROSSIME ORE"
    if hourly.get("temp"):
        fmt = ", ".join(f"{h}: {v:.0f}°C" for h, v in hourly["temp"])
        lines.append(f"  TEMPERATURE ORARIE {time_label}: {fmt}")
    if hourly.get("precip"):
        fmt = ", ".join(f"{h}: {v:.1f}mm" for h, v in hourly["precip"])
        lines.append(f"  PRECIPITAZIONI ORARIE {time_label}: {fmt}")
    if hourly.get("wind"):
        fmt = ", ".join(f"{h}: {v:.0f}km/h" for h, v in hourly["wind"])
        lines.append(f"  VENTO ORARIO {time_label}: {fmt}")

    if alerts:
        lines.append("")
        lines.append("ALLERTE METEO ATTIVE:")
        for a in alerts:
            lines.append(f"  ⚠ {a}")

    # Only pass disruption info for lines 3 and 80, not timetable data
    disruptions = []
    for dep in (transit.get("station_1", []) + transit.get("station_2", [])):
        line = dep.get("line")
        if line not in ("3", "80"):
            continue
        if dep.get("cancelled"):
            disruptions.append(f"Linea {line} → {dep['destination']}: CANCELLATA")
        elif dep.get("delay", 0) > 0:
            disruptions.append(f"Linea {line} → {dep['destination']}: ritardo {dep['delay']} min")
    if disruptions:
        lines.append("")
        lines.append("DISRUZIONI TRASPORTI (linee 3 e 80):")
        for d in disruptions:
            lines.append(f"  {d}")

    lines.append("")
    lines.append(f"Rispondi SOLO con il paragrafo in italiano, senza titoli o prefissi. Il display ha {_SUMMARY_MAX_LINES} righe da ~30 caratteri ciascuna. Punta a riempire 9-10 righe (~270-300 caratteri). Se il contenuto meteo non basta, aggiungi una curiosità divertente, un fatto interessante o una buona notizia su Zurigo.")
    return "\n".join(lines)


# Panel layout constants (must match screen.py)
_SUMMARY_PANEL_WIDTH_PX = 793 - 560 - 8   # 225px
_SUMMARY_LINE_HEIGHT    = 17               # px per wrapped line
_SUMMARY_MAX_LINES      = 10
_MIN_LINES              = 8
_GEMINI_MODEL           = "gemini-2.5-flash"


def _count_lines(text: str) -> int:
    """Count how many wrapped lines *text* produces in the summary panel."""
    from ..renderer.fonts import get_font, word_wrap
    font = get_font(14, "Bold")
    return len(word_wrap(text, font, _SUMMARY_PANEL_WIDTH_PX))


async def generate_summary(weather: dict, transit: dict, alerts: list) -> str:
    """
    Calls Gemini 2.5 Flash to produce the Italian summary paragraph.

    The synchronous google-genai client is wrapped in asyncio.to_thread
    so it doesn't block the event loop.  After generation, the text is
    measured against the actual panel layout (pixel word-wrap).  If it
    overflows or underflows the box, up to 2 retries adjust the length.
    As a last resort, the text is truncated at the nearest word boundary.
    """
    if not settings.GEMINI_API_KEY:
        return "Gemini API key non configurata."

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = _build_prompt(weather, transit, alerts)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=_GEMINI_MODEL,
            contents=prompt,
        )
        text = response.text.strip()

        # Convergence loop: retry up to 2 times to fit the panel
        for attempt in range(2):
            n_lines = _count_lines(text)
            if _MIN_LINES <= n_lines <= _SUMMARY_MAX_LINES:
                break

            if n_lines > _SUMMARY_MAX_LINES:
                print(f"Gemini summary too long ({n_lines} lines, attempt {attempt + 1}), requesting shorter version...")
                shorten_prompt = (
                    f"Il seguente testo occupa {n_lines} righe sul display ma ne abbiamo solo {_SUMMARY_MAX_LINES}. "
                    f"Riscrivilo più corto in modo che stia in {_SUMMARY_MAX_LINES} righe (~{_SUMMARY_MAX_LINES * 30} caratteri max). "
                    f"Rispondi SOLO con il testo riscritto, senza commenti.\n\n{text}"
                )
                retry_response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=_GEMINI_MODEL,
                    contents=shorten_prompt,
                )
                text = retry_response.text.strip()

            elif n_lines < _MIN_LINES:
                print(f"Gemini summary too short ({n_lines} lines, attempt {attempt + 1}), requesting expansion...")
                search_tool = types.Tool(google_search=types.GoogleSearch())
                expand_prompt = (
                    f"Il seguente testo occupa solo {n_lines} righe ma il display ne contiene {_SUMMARY_MAX_LINES}. "
                    f"Espandilo fino a {_SUMMARY_MAX_LINES} righe (~{_SUMMARY_MAX_LINES * 30} caratteri). "
                    f"Cerca online e aggiungi un fatto curioso, una buona notizia o qualcosa di interessante e positivo su Zurigo oggi. "
                    f"Rispondi SOLO con il testo riscritto, senza commenti.\n\n{text}"
                )
                expand_response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=_GEMINI_MODEL,
                    contents=expand_prompt,
                    config=types.GenerateContentConfig(tools=[search_tool]),
                )
                text = expand_response.text.strip()

        # Final safety net: truncate to fit the panel
        lines = _count_lines(text)
        if lines > _SUMMARY_MAX_LINES:
            print(f"Gemini summary still too long after retries ({lines} lines), truncating.")
            from ..renderer.fonts import get_font, word_wrap
            font = get_font(14, "Bold")
            wrapped = word_wrap(text, font, _SUMMARY_PANEL_WIDTH_PX)
            text = " ".join(wrapped[:_SUMMARY_MAX_LINES])

        return text
    except Exception as e:
        print(f"Gemini error: {e}")
        return f"Riepilogo non disponibile ({datetime.now(_ZURICH_TZ).strftime('%H:%M')})."
