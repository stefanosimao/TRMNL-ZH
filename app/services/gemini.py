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

    lines = [
        "Sei un assistente meteo per Zurigo, zona Albisrieden (PLZ 8047).",
        "Scrivi UN paragrafo conciso in italiano (MAX 600 CARATTERI) con:",
        "- Condizioni attuali e previsioni per oggi/domani",
        "- Consigli abbigliamento / ombrello",
        "- Eventuali allerte meteo attive",
        "- Eventuali ritardi/disruzioni nei trasporti con consiglio pratico",
        "",
        "DATI ATTUALI:",
        f"  Temperatura interna: {indoor.get('temperature', 'n/d')}°C",
        f"  Temperatura balcone: {outdoor.get('temperature', 'n/d')}°C",
        f"  Temperatura MeteoSwiss (8047): {meteo.get('temp', 'n/d')}°C",
    ]

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
    lines.append("Rispondi SOLO con il paragrafo in italiano, senza titoli o prefissi. Stai entro i 600 caratteri.")
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
        if len(text) > 700:
            text = text[:697] + "..."
        return text
    except Exception as e:
        print(f"Gemini error: {e}")
        return f"Riepilogo non disponibile ({datetime.now().strftime('%H:%M')})."
