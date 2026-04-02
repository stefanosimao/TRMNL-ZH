import httpx
from datetime import datetime
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

async def fetch_stationboard(client: httpx.AsyncClient, station: str):
    """Fetch upcoming departures from search.ch and calculate minutes until arrival."""
    url = "https://transport.search.ch/api/stationboard.json"
    params = {
        "station": station,
        "limit": 30,  # We fetch more and then filter
        "show_prognosis": 1,
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
                    # Departure time
                    dep_time_str = conn.get("prognosis", {}).get("departure") or conn.get("departure")
                    if not dep_time_str: continue
                    
                    dep_time = datetime.fromisoformat(dep_time_str.replace('Z', '+00:00'))
                    diff = dep_time.replace(tzinfo=None) - now.replace(tzinfo=None)
                    minutes = round(diff.total_seconds() / 60)
                    
                    if minutes < 0: continue
                    
                    delay = 0
                    if conn.get("dep_delay"):
                        try:
                            delay = int(conn.get("dep_delay"))
                        except (ValueError, TypeError):
                            pass

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
