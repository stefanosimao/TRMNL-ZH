"""
Gemini Flash 2.5 integration.
Generates a short Italian weather + transit summary paragraph.
"""
import asyncio
from google import genai
from datetime import datetime
from ..config import settings


def _build_prompt(weather: dict, transit: dict, alerts: list) -> str:
    indoor  = weather.get("indoor",  {})
    outdoor = weather.get("outdoor", {})
    meteo   = weather.get("meteo",   {})
    fc_today    = weather.get("forecast_today") or {}
    fc_tomorrow = weather.get("forecast_tomorrow") or {}
    sun         = weather.get("sun_times") or {}

    lines = [
        "Sei un assistente meteo per Zurigo, zona Albisrieden (PLZ 8047).",
        "Scrivi UN paragrafo conciso in italiano (MAX 450 CARATTERI) con:",
        "- Condizioni attuali e previsioni per oggi/domani",
        "- Consigli abbigliamento / ombrello",
        "- Eventuali allerte meteo attive",
        "- Eventuali ritardi/disruzioni nei trasporti con consiglio pratico",
        "",
        "DATI ATTUALI:",
        f"  Temperatura interna: {indoor.get('temperature', 'n/d')}°C",
        f"  Temperatura balcone: {outdoor.get('temperature', 'n/d')}°C",
        f"  Temperatura MeteoSwiss ora (8047): {meteo.get('temp', 'n/d')}°C",
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

    if sun.get("sunrise"):
        lines.append(f"  Alba {sun['sunrise']} · Tramonto {sun.get('sunset', 'n/d')}")

    if alerts:
        lines.append("")
        lines.append("ALLERTE METEO ATTIVE:")
        for a in alerts:
            lines.append(f"  ⚠ {a}")
    else:
        lines.append("Nessuna allerta meteo attiva.")

    s1 = transit.get("station_1", [])
    s2 = transit.get("station_2", [])
    if s1 or s2:
        lines.append("")
        lines.append("PARTENZE IMMINENTI (Albisrieden + Fellenbergstr.):")
        for dep in (s1 + s2)[:6]:
            delay_str = f" (+{dep['delay']}min)" if dep.get("delay") else ""
            lines.append(f"  Linea {dep['line']} → {dep['destination']}: {dep['minutes']} min{delay_str}")

    lines.append("")
    lines.append("Rispondi SOLO con il paragrafo in italiano, senza titoli o prefissi. Stai entro i 450 caratteri.")
    return "\n".join(lines)


async def generate_summary(weather: dict, transit: dict, alerts: list) -> str:
    """
    Calls the Gemini 2.5 Flash API to generate an Italian weather and transit summary.
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
        # Safety truncate if model ignores prompt instruction
        if len(text) > 450:
            text = text[:447] + "..."
        return text
    except Exception as e:
        print(f"Gemini error: {e}")
        return f"Riepilogo non disponibile ({datetime.now().strftime('%H:%M')})."
