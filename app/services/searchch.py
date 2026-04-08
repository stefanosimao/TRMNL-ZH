"""
Transit data integration using the search.ch stationboard API.
Handles fetching, filtering, and nighttime transition logic for local public transit.
"""
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ..config import settings

_ZURICH_TZ = ZoneInfo(settings.TIMEZONE)

# ── Filter configuration ─────────────────────────────────────────────────
# Each filter specifies a line, allowed terminal names (empty = any direction),
# and how many departures to collect.  The sum of counts per station must
# match _TARGET_COUNT so the display layout is always fully populated.
#
# Regular filters are used during normal service hours and weekday late
# nights (where morning departures simply fill the slots).
# Night filters are used on weekend late nights (Fri→Sat, Sat→Sun) between
# 00:40 and 01:00 to show Nachtbus departures in place of next-morning
# regular service.

_REGULAR_FILTERS = {
    "station_1": [
        {"line": "3",  "terminals": ["Klusplatz"], "count": 2},
        {"line": "80", "terminals": ["Triemli"],   "count": 1},
        {"line": "80", "terminals": ["Oerlikon"],  "count": 2},
    ],
    "station_2": [
        {"line": "67", "terminals": ["Wiedikon"],      "count": 1},
        {"line": "67", "terminals": ["Dunkelhölzli"],  "count": 1},
    ],
}

_NIGHT_FILTERS = {
    "station_1": [
        {"line": "N3", "terminals": [], "count": 5},
        {"line": "N8", "terminals": [], "count": 5},
    ],
    "station_2": [
        {"line": "N3", "terminals": [], "count": 2},
        {"line": "N8", "terminals": [], "count": 2},
    ],
}

# Target number of departures per station
_TARGET_COUNT = {"station_1": 5, "station_2": 2}


def _station_key(station: str) -> str:
    if station == settings.TRANSIT_STATION_1:
        return "station_1"
    return "station_2"


def _is_late_night_weekend(now: datetime) -> bool:
    """True between 00:40 and 00:59 on Sat/Sun morning (i.e. Fri/Sat night)."""
    return now.hour == 0 and now.minute >= 40 and now.weekday() in (5, 6)


def _is_morning_departure(dep: dict) -> bool:
    """A departure is 'morning' if its scheduled time is 05:00 or later."""
    hour = int(dep["time"][:2])
    return hour >= 5


def _match_connections(connections: list, now: datetime, filters: list) -> list:
    """
    Matches raw search.ch connections against a list of filters.
    Returns departure dicts sorted by minutes, respecting per-filter counts.

    Each filter is tried in order.  For every filter, connections are scanned
    sequentially (they arrive from the API sorted by departure time) and
    matched by line number and terminal name.  An empty terminals list means
    any direction is accepted — used for Nachtbus lines where we don't care
    about the direction.

    Delay handling: search.ch returns dep_delay as a string — "X" means
    cancelled, "+3" or "+ 3" means 3 minutes late.  Cancelled departures
    are kept (flagged) so they can be surfaced as disruptions by Gemini.
    """
    results = []

    for f in filters:
        count = 0
        for conn in connections:
            if str(conn.get("line", "")) != str(f["line"]):
                continue

            terminal = conn.get("terminal", {}).get("name", "")
            if f["terminals"] and not any(t.lower() in terminal.lower() for t in f["terminals"]):
                continue

            dep_time_str = conn.get("time")
            if not dep_time_str:
                continue

            try:
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
                    clean_delay = str(raw_delay).replace(" ", "").replace("+", "")
                    delay = int(clean_delay)
                    dep_time = dep_time + timedelta(minutes=delay)
                except (ValueError, TypeError):
                    pass

            diff = dep_time - now
            minutes = int(diff.total_seconds() / 60)
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

    results.sort(key=lambda x: x["minutes"])
    return results


async def fetch_stationboard(client: httpx.AsyncClient, station: str) -> list:
    """
    Fetches upcoming public transit departures for a given station.

    After 00:40 on weekend nights (Fri→Sat, Sat→Sun): fetches regular lines
    first, then replaces any morning departures (05:00+) with Nachtbus N3/N8
    departures, gradually filling slots as regular service winds down.

    Always targets 5 departures for station 1 and 2 for station 2.
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
    key = _station_key(station)
    target = _TARGET_COUNT[key]

    # Always start with regular filters
    regular = _match_connections(connections, now, _REGULAR_FILTERS[key])

    if not _is_late_night_weekend(now):
        return regular

    # ── Weekend late-night gradual transition ────────────────────────────
    # As regular trams/buses stop running for the night, the API starts
    # returning next-morning departures (05:00+).  Those aren't useful at
    # 00:45, so we replace them with Nachtbus (N3, N8) departures.
    #
    # Example at 00:45 on a Saturday with 5 target slots:
    #   regular = [Tram3 00:50, Bus80 05:30, Bus80 05:31, Tram3 05:40, Bus80 06:00]
    #   tonight = [Tram3 00:50]                         → 1 slot used
    #   remaining = 4                                   → fill with N3/N8
    #   result  = [Tram3 00:50, N3 01:15, N8 01:30, N3 02:15, N8 02:30]
    tonight = [d for d in regular if not _is_morning_departure(d)]
    remaining = target - len(tonight)

    if remaining <= 0:
        return tonight[:target]

    night = _match_connections(connections, now, _NIGHT_FILTERS[key])
    # Deduplicate: a Nachtbus line might already appear in tonight's results
    tonight_keys = {(d["line"], d["time"]) for d in tonight}
    night = [d for d in night if (d["line"], d["time"]) not in tonight_keys]

    combined = tonight + night[:remaining]
    combined.sort(key=lambda x: x["minutes"])
    return combined
