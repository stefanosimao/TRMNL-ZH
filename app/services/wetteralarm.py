"""
Wetter-Alarm API integration.
Fetches active MeteoAlarm-style weather alerts for Zürich Albisrieden (POI 142941).
API: https://my.wetteralarm.ch/v7/alarms/meteo.json  (no auth required)
"""
import httpx
from datetime import datetime
from ..config import settings

_BASE_URL = "https://my.wetteralarm.ch"

# Priority → Italian severity label
_PRIORITY_LABELS = {
    1: "Allerta gialla",
    2: "Allerta arancione",
    3: "Allerta rossa",
    4: "Allerta viola (estrema)",
}


async def fetch_alerts(client: httpx.AsyncClient) -> list[dict]:
    """
    Returns a list of active alert dicts for the configured POI.
    Each dict has: title, description, priority, valid_from, valid_to.
    Returns [] when no alerts are active or on error.
    """
    poi_id = settings.WETTERALARM_POI_ID
    url = f"{_BASE_URL}/v7/alarms/meteo.json"

    try:
        response = await client.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Wetter-Alarm fetch error: {e}")
        return []

    now = datetime.utcnow()
    active_alerts = []

    for alarm in data.get("meteo_alarms", []):
        # Only include alerts that cover our POI
        if poi_id not in alarm.get("poi_ids", []):
            continue

        # Check time validity
        try:
            valid_from = datetime.fromisoformat(alarm["valid_from"].replace("Z", "+00:00")).replace(tzinfo=None)
            valid_to   = datetime.fromisoformat(alarm["valid_to"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (KeyError, ValueError):
            continue

        if not (valid_from <= now <= valid_to):
            continue

        # Prefer German title/hint (closest to local language), fall back to English
        lang_data = alarm.get("de") or alarm.get("en") or {}
        title = lang_data.get("title", "Allerta meteo")
        hint  = lang_data.get("hint", "")

        priority = alarm.get("priority", 1)
        severity = _PRIORITY_LABELS.get(priority, f"Priorità {priority}")

        active_alerts.append({
            "title":      title,
            "description": hint,
            "severity":   severity,
            "priority":   priority,
            "valid_from": alarm.get("valid_from"),
            "valid_to":   alarm.get("valid_to"),
        })

    # Sort by priority descending (most severe first)
    active_alerts.sort(key=lambda a: a["priority"], reverse=True)
    return active_alerts


def format_alerts_for_prompt(alerts: list[dict]) -> list[str]:
    """Returns a list of short Italian strings suitable for the Gemini prompt."""
    return [
        f"{a['severity']}: {a['title']} ({a['description']})" if a["description"]
        else f"{a['severity']}: {a['title']}"
        for a in alerts
    ]
