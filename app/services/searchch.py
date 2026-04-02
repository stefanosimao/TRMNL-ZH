import httpx
from datetime import datetime
from ..config import settings

async def fetch_stationboard(client: httpx.AsyncClient, station: str = None):
    """Fetch upcoming departures from search.ch and calculate minutes until arrival."""
    station = station or settings.STATION_NAME
    url = "https://transport.search.ch/api/stationboard.json"
    params = {
        "station": station,
        "limit": 10,
        "show_prognosis": 1
    }
    
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    departures = []
    now = datetime.now()
    
    for connection in data.get("connections", []):
        # Use prognosis time if available, otherwise regular departure time
        dep_time_str = connection.get("prognosis", {}).get("departure") or connection.get("departure")
        if not dep_time_str:
            continue
            
        dep_time = datetime.fromisoformat(dep_time_str.replace('Z', '+00:00'))
        # If the response doesn't have timezone, assume local or handle carefully
        # search.ch usually returns local time or ISO strings with timezone
        
        diff = dep_time.replace(tzinfo=None) - now.replace(tzinfo=None)
        minutes = int(diff.total_seconds() / 60)
        
        if minutes < 0:
            continue
            
        departures.append({
            "line": connection.get("line"),
            "destination": connection.get("terminal"),
            "minutes": minutes,
            "time": dep_time.strftime("%H:%M")
        })
        
    return departures
