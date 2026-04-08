"""
Wetter-Alarm API integration.
Fetches active MeteoAlarm-style weather alerts for Zürich Albisrieden (POI 142941).
API: https://my.wetteralarm.ch/v7/alarms/meteo.json  (no auth required)
"""
import httpx
import logging
from datetime import datetime, timezone
from ..config import settings

logger = logging.getLogger(__name__)

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
    Filters out expired alerts using timezone-aware UTC datetime comparisons.
    Attempts to retrieve the alert text in Italian ('it'), falling back to
    German ('de') or English ('en') if unavailable.
    
    Args:
        client: Shared HTTPX async client.
        
    Returns:
        list[dict]: A list of alert dictionaries sorted by priority (most severe first),
                    or an empty list if no alerts are active or an error occurs.
    """
    poi_id = settings.WETTERALARM_POI_ID
    url = f"{_BASE_URL}/v7/alarms/meteo.json"

    try:
        response = await client.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"Wetter-Alarm fetch error: {e}")
        return []

    now = datetime.now(timezone.utc)
    active_alerts = []

    for alarm in data.get("meteo_alarms", []):
        # Only include alerts that cover our POI
        if poi_id not in alarm.get("poi_ids", []):
            continue

        # Check time validity (keep timezone-aware throughout)
        try:
            valid_from = datetime.fromisoformat(alarm["valid_from"].replace("Z", "+00:00"))
            valid_to   = datetime.fromisoformat(alarm["valid_to"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue

        if not (valid_from <= now <= valid_to):
            continue

        # Prefer Italian, fall back to German (Swiss context), then English
        lang_data = alarm.get("it") or alarm.get("de") or alarm.get("en") or {}
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
