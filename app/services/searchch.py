import httpx
from datetime import datetime, timedelta
from ..config import settings

# Station-specific filtering as per specification section 4.1
STATION_FILTERS = {
    settings.TRANSIT_STATION_1: [
        {"line": "3", "terminals": ["Klusplatz"], "count": 2},
        {"line": "80", "terminals": ["Triemli"], "count": 1},
        {"line": "80", "terminals": ["Oerlikon"], "count": 2}
    ],
    settings.TRANSIT_STATION_2: [
        {"line": "3", "terminals": ["Klusplatz"], "count": 2},
        {"line": "67", "terminals": ["Wiedikon"], "count": 2},
        {"line": "67", "terminals": ["Milchbuck"], "count": 2}
    ]
}

async def fetch_stationboard(client: httpx.AsyncClient, station: str) -> list:
    """
    Fetches upcoming public transit departures for a given station using the search.ch API.
    Applies station-specific filtering logic to only return relevant lines and destinations
    based on the STATION_FILTERS configuration. Calculates the real-time minutes until departure.
    
    Args:
        client: Shared HTTPX async client.
        station: The name of the station to query (e.g., "Zürich, Albisrieden").
        
    Returns:
        list: A list of departure dictionaries containing line, destination, minutes, delay, and time.
    """
    url = "https://transport.search.ch/api/stationboard.json"
    params = {
        "station": station,
        "limit": 30,  # We fetch more and then filter
        "show_delays": 1,
        "transportation_types": "tram,bus"
    }
    
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    connections = data.get("connections", [])
    filters = STATION_FILTERS.get(station, [])
    
    results = []
    now = datetime.now()
    
    for f in filters:
        count = 0
        for conn in connections:
            if conn.get("line") == f["line"]:
                terminal = conn.get("terminal", {}).get("name", "")
                if any(t.lower() in terminal.lower() for t in f["terminals"]):
                    # Scheduled departure time from the "time" field
                    dep_time_str = conn.get("time")
                    if not dep_time_str:
                        continue

                    try:
                        dep_time = datetime.fromisoformat(dep_time_str.replace('Z', '+00:00'))
                        dep_time = dep_time.replace(tzinfo=None)
                    except ValueError:
                        continue

                    # Parse delay and add to departure time for actual minutes calculation
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
                        "line": conn.get("line"),
                        "destination": terminal,
                        "minutes": minutes,
                        "delay": delay,
                        "time": dep_time.strftime("%H:%M")
                    })
                    count += 1
                    if count >= f["count"]:
                        break
                        
    return results
