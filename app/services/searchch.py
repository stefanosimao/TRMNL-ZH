import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ..config import settings

_ZURICH_TZ = ZoneInfo("Europe/Zurich")

# Lazily built on first call so module-level evaluation doesn't race with settings load.
_STATION_FILTERS: dict | None = None


def _get_filters() -> dict:
    global _STATION_FILTERS
    if _STATION_FILTERS is None:
        _STATION_FILTERS = {
            settings.TRANSIT_STATION_1: [
                {"line": "3",  "terminals": ["Klusplatz"], "count": 2},
                {"line": "80", "terminals": ["Triemli"],   "count": 1},
                {"line": "80", "terminals": ["Oerlikon"],  "count": 2},
            ],
            settings.TRANSIT_STATION_2: [
                {"line": "3",  "terminals": ["Klusplatz"],  "count": 2},
                {"line": "67", "terminals": ["Wiedikon"],   "count": 2},
                {"line": "67", "terminals": ["Milchbuck"],  "count": 2},
            ],
        }
    return _STATION_FILTERS


async def fetch_stationboard(client: httpx.AsyncClient, station: str) -> list:
    """
    Fetches upcoming public transit departures for a given station using the search.ch API.
    Applies station-specific filtering and calculates minutes until actual departure.

    Departure times from search.ch are in Swiss local time (Europe/Zurich).
    The comparison uses timezone-aware datetimes so the result is correct on UTC servers.
    """
    url = "https://timetable.search.ch/api/stationboard.json"
    params = {
        "stop": station,           # search.ch expects "stop", not "station"
        "limit": 30,
        "show_delays": 1,
        "transportation_types": "tram,bus",
    }

    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    connections = data.get("connections", [])
    filters = _get_filters().get(station, [])

    results = []
    now = datetime.now(_ZURICH_TZ)

    for f in filters:
        count = 0
        for conn in connections:
            if conn.get("line") != f["line"]:
                continue

            terminal = conn.get("terminal", {}).get("name", "")
            if not any(t.lower() in terminal.lower() for t in f["terminals"]):
                continue

            dep_time_str = conn.get("time")
            if not dep_time_str:
                continue

            try:
                # search.ch returns naive local Swiss time — attach the Zurich timezone
                dep_time = datetime.fromisoformat(dep_time_str).replace(tzinfo=_ZURICH_TZ)
            except ValueError:
                continue

            delay = 0
            raw_delay = conn.get("dep_delay")
            if raw_delay:
                try:
                    delay = int(raw_delay)
                    dep_time = dep_time + timedelta(minutes=delay)
                except (ValueError, TypeError):
                    pass

            diff = dep_time - now
            minutes = round(diff.total_seconds() / 60)
            if minutes < 0:
                continue

            results.append({
                "line":        conn.get("line"),
                "destination": terminal,
                "minutes":     minutes,
                "delay":       delay,
                "time":        dep_time.strftime("%H:%M"),
            })
            count += 1
            if count >= f["count"]:
                break

    return results
