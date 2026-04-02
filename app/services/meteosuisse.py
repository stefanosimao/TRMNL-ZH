import httpx
import csv
import io
from astral import LocationInfo
from astral.sun import sun
from datetime import datetime, date, timedelta
from typing import List, Optional
from ..config import settings

HOURLY_PARAMS = [
    "tre200h0",  # Air temperature 2m, hourly mean (°C)
    "rre150h0",  # Precipitation, hourly total (mm)
    "sre000h0",  # Sunshine duration, hourly total (minutes)
    "fu3010h0",  # Wind speed, hourly mean (km/h)
    "dkl010h0",  # Wind direction, hourly mean
    "jww003i0",  # MeteoSwiss weather icon number (3-hourly)
]

DAILY_PARAMS = [
    "tre200px",  # Daily max temperature
    "tre200pn",  # Daily min temperature
    "rka150p0",  # Daily precipitation total
    "jp2000d0",  # MeteoSwiss pictogram number (daily, daytime)
]

def get_daily_forecast(meteo_data: dict, days_offset: int = 0):
    """
    Extracts max/min temp, precipitation, and pictogram for a specific day.
    0 = Today, 1 = Tomorrow, etc.
    """
    if not meteo_data or "daily" not in meteo_data:
        return None
        
    target_date = date.today() + timedelta(days=days_offset)
    date_str = target_date.strftime("%Y-%m-%d")
    
    res = {"date": target_date, "max_temp": None, "min_temp": None, "precip": None, "pictogram": None}
    
    # Mapping of param to key
    mapping = {
        "tre200px": "max_temp",
        "tre200pn": "min_temp",
        "rka150p0": "precip",
        "jp2000d0": "pictogram"
    }
    
    for param, key in mapping.items():
        series = meteo_data["daily"].get(param, [])
        for entry in series:
            if entry["valid_time"].startswith(date_str):
                res[key] = entry["value"]
                break
                
    return res

def get_sun_times():
    """Calculates sunrise and sunset for Zurich (47.37N, 8.52E)."""
    city = LocationInfo("Zurich", "Switzerland", "Europe/Zurich", 47.37, 8.52)
    s = sun(city.observer, date=date.today())
    return {
        "sunrise": s["sunrise"].strftime("%H:%M"),
        "sunset": s["sunset"].strftime("%H:%M")
    }

async def fetch_meteosuisse_data(client: httpx.AsyncClient):
    """
    Downloads forecast CSVs for all parameters for PLZ 8047.
    Returns structured hourly and daily data.
    """
    base_url = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-local-forecasting"
    
    results = {
        "hourly": {},
        "daily": {},
        "last_updated": datetime.now().isoformat()
    }
    
    plz = settings.METEO_PLZ
    
    for param in HOURLY_PARAMS + DAILY_PARAMS:
        url = f"{base_url}/ch.meteoschweiz.ogd-local-forecasting_{param}_v1.2.csv"
        try:
            response = await client.get(url)
            if response.status_code != 200:
                continue
                
            content = response.content.decode('latin-1')
            reader = csv.DictReader(io.StringIO(content), delimiter=';')
            
            param_data = []
            for row in reader:
                if row.get('point_type_id') == '2' and row.get('point_id') == plz:
                    val_str = row.get('value')
                    param_data.append({
                        "valid_time": row.get('valid_time'),
                        "value": float(val_str) if val_str and val_str.strip() else 0.0
                    })
            
            if param in HOURLY_PARAMS:
                results["hourly"][param] = param_data
            else:
                results["daily"][param] = param_data
                
        except Exception as e:
            print(f"Error fetching MeteoSuisse param {param}: {e}")
            continue
            
    return results

def get_24h_series(meteo_data: dict, param: str, target_date: datetime = None) -> List[Optional[float]]:
    """
    Returns a list of 24 values (00:00 to 23:00) for a given parameter on target_date.
    """
    if not meteo_data or "hourly" not in meteo_data:
        return [None] * 24
    
    series = meteo_data["hourly"].get(param, [])
    if not series:
        return [None] * 24
        
    target_date = target_date or datetime.now()
    date_str = target_date.strftime("%Y-%m-%d")
    
    # Initialize 24 slots
    day_data = [None] * 24
    
    for entry in series:
        # valid_time format: "2026-04-02T15:00:00Z"
        v_time = entry["valid_time"]
        if v_time.startswith(date_str):
            try:
                hour = int(v_time.split('T')[1].split(':')[0])
                if 0 <= hour < 24:
                    day_data[hour] = entry["value"]
            except (IndexError, ValueError):
                continue
                
    return day_data

def get_current_conditions(meteo_data: dict):
    """Extracts current temperature and condition from the hourly data."""
    if not meteo_data or "hourly" not in meteo_data:
        return None
        
    temp_series = meteo_data["hourly"].get("tre200h0", [])
    if not temp_series:
        return None
        
    now = datetime.now()
    now_hour = now.hour
    date_str = now.strftime("%Y-%m-%d")
    
    current_temp = None
    for entry in temp_series:
        if entry["valid_time"].startswith(date_str):
            hour = int(entry["valid_time"].split('T')[1].split(':')[0])
            if hour == now_hour:
                current_temp = entry["value"]
                break
    
    # Fallback to first available if current hour not found
    if current_temp is None and temp_series:
        current_temp = temp_series[0]["value"]
    
    return {
        "temp": current_temp,
        "plz": settings.METEO_PLZ
    }
