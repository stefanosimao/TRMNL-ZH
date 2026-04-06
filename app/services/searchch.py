import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ..config import settings

_ZURICH_TZ = ZoneInfo("Europe/Zurich")

def _get_filters(now: datetime) -> dict:
    """
    Returns the transit filters for each station.
    Station 2 is configured to show only the next Bus 67 in each direction.
    Station 1 includes the N3 Nachtbus during weekend late nights (0 AM - 4 AM).
    """
    filters = {
        settings.TRANSIT_STATION_1: [
            {"line": "3",  "terminals": ["Klusplatz"], "count": 2},
            {"line": "80", "terminals": ["Triemli"],   "count": 1},
            {"line": "80", "terminals": ["Oerlikon"],  "count": 2},
        ],
        settings.TRANSIT_STATION_2: [
            {"line": "67", "terminals": ["Wiedikon"],      "count": 1},
            {"line": "67", "terminals": ["Dunkelhölzli"],  "count": 1},
        ],
    }
    
    # Nachtbus N3 logic: Saturday morning or Sunday morning, 0 AM - 4 AM
    # weekday(): 5 = Saturday, 6 = Sunday
    if now.weekday() in (5, 6) and 0 <= now.hour < 4:
        filters[settings.TRANSIT_STATION_1].append(
            {"line": "N3", "terminals": ["Bahnhofplatz"], "count": 1}
        )
    
    return filters


async def fetch_stationboard(client: httpx.AsyncClient, station: str) -> list:
    """
    Fetches upcoming public transit departures for a given station using the search.ch API.
    Applies station-specific filtering and calculates minutes until actual departure.
    """
    url = "https://timetable.search.ch/api/stationboard.json"
    params = {
        "stop": station,
        "limit": 40,
        "show_delays": 1,
        "transportation_types": "tram,bus",
    }

    response = await client.get(url, params=params, timeout=5.0)
    response.raise_for_status()
    data = response.json()

    connections = data.get("connections", [])
    now = datetime.now(_ZURICH_TZ)
    filters = _get_filters(now).get(station, [])

    results = []

    for f in filters:
        count = 0
        for conn in connections:
            if str(conn.get("line", "")) != str(f["line"]):
                continue

            terminal = conn.get("terminal", {}).get("name", "")
            if not any(t.lower() in terminal.lower() for t in f["terminals"]):
                continue

            dep_time_str = conn.get("time")
            if not dep_time_str:
                continue

            try:
                # search.ch returns naive local Swiss time
                dep_time = datetime.fromisoformat(dep_time_str).replace(tzinfo=_ZURICH_TZ)
            except ValueError:
                continue

            delay = 0
            cancelled = False
            scheduled_time = dep_time
            raw_delay = conn.get("dep_delay")
            if raw_delay == "X":
                cancelled = True
            elif raw_delay:
                try:
                    # search.ch delays can include spaces (e.g., "+ 3")
                    clean_delay = str(raw_delay).replace(" ", "").replace("+", "")
                    delay = int(clean_delay)
                    dep_time = dep_time + timedelta(minutes=delay)
                except (ValueError, TypeError):
                    pass

            diff = dep_time - now
            minutes = int(diff.total_seconds() / 60)  # floor, never rounds up
            if not cancelled and minutes < 2:
                continue

            results.append({
                "line":           str(conn.get("line", "")),
                "destination":    terminal.replace("Zürich, ", ""),
                "minutes":        minutes,
                "delay":          delay,
                "cancelled":      cancelled,
                "time":           dep_time.strftime("%H:%M"),
                "scheduled_time": scheduled_time.strftime("%H:%M"),
            })
            count += 1
            if count >= f["count"]:
                break

    # Sort results by minutes until departure
    results.sort(key=lambda x: x["minutes"])
    return results