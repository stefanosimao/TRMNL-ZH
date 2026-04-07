"""
Gemini 2.5 Flash integration for the "Riepilogo Intelligente" panel.

Builds a structured Italian prompt from cached weather, forecast, alert,
and transit data, then calls Gemini to produce a single concise paragraph
(max 320 characters) with practical advice: what to wear, whether to
carry an umbrella, and any active weather alerts or transit disruptions.

If the response exceeds the limit, a single retry asks Gemini to shorten
it. As a final safety net, the text is truncated at the nearest word
boundary.

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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ..config import settings

_ZURICH_TZ = ZoneInfo("Europe/Zurich")


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
        "Scrivi UN paragrafo conciso in italiano (MAX 320 CARATTERI).",
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
    lines.append("Rispondi SOLO con il paragrafo in italiano, senza titoli o prefissi. Stai entro i 320 caratteri.")
    return "\n".join(lines)


def _truncate_at_word_boundary(text: str, limit: int) -> str:
    """Truncate text at the last word boundary within `limit` characters."""
    if len(text) <= limit:
        return text
    truncated = text[:limit - 1]  # leave room for "…"
    # Find last space to avoid cutting mid-word
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip(".,;:!? ") + "…"


_MAX_CHARS = 320


async def generate_summary(weather: dict, transit: dict, alerts: list) -> str:
    """
    Calls Gemini 2.5 Flash to produce the Italian summary paragraph.

    The synchronous google-genai client is wrapped in asyncio.to_thread
    so it doesn't block the event loop.  If the response exceeds 320
    characters, a single retry asks Gemini to shorten it.  As a last
    resort, the text is truncated at the nearest word boundary.
    """
    if not settings.GEMINI_API_KEY:
        return "Gemini API key non configurata."

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = _build_prompt(weather, transit, alerts)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()

        # If too long, ask Gemini once to shorten it
        if len(text) > _MAX_CHARS:
            print(f"Gemini summary too long ({len(text)} chars), requesting shorter version...")
            shorten_prompt = (
                f"Il seguente testo è troppo lungo ({len(text)} caratteri). "
                f"Riscrivilo in massimo {_MAX_CHARS} caratteri mantenendo il significato. "
                f"Rispondi SOLO con il testo riscritto, senza commenti.\n\n{text}"
            )
            retry_response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=shorten_prompt,
            )
            text = retry_response.text.strip()

        # Final safety net: truncate at word boundary
        if len(text) > _MAX_CHARS:
            print(f"Gemini summary still too long after retry ({len(text)} chars), truncating.")
            text = _truncate_at_word_boundary(text, _MAX_CHARS)

        return text
    except Exception as e:
        print(f"Gemini error: {e}")
        return f"Riepilogo non disponibile ({datetime.now(_ZURICH_TZ).strftime('%H:%M')})."
