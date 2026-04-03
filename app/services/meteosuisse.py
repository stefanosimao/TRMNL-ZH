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
    Uses STAC API to find the latest available CSV files.
    Returns structured hourly and daily data.
    """
    stac_url = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-local-forecasting/items?limit=1"
    
    results = {
        "hourly": {},
        "daily": {},
        "last_updated": datetime.now().isoformat()
    }
    
    try:
        # 1. Get the latest STAC item to find the current CSV URLs
        stac_response = await client.get(stac_url)
        stac_response.raise_for_status()
        stac_data = stac_response.json()
        
        if not stac_data.get("features"):
            print("No STAC features found")
            return results
            
        assets = stac_data["features"][0].get("assets", {})
        
    except Exception as e:
        print(f"Error fetching STAC metadata: {e}")
        return results
        
    plz = settings.METEO_PLZ
    print(f"Fetching MeteoSuisse data for PLZ: {plz}")
    
    for param in HOURLY_PARAMS + DAILY_PARAMS:
        # Find the asset that ends with .{param}.csv
        target_asset = None
        for asset_key, asset_val in assets.items():
            if asset_key.endswith(f".{param}.csv"):
                target_asset = asset_val
                break
        
        if not target_asset:
            print(f"Could not find asset for param {param}")
            continue
            
        url = target_asset["href"]
        try:
            response = await client.get(url)
            if response.status_code != 200:
                print(f"Error fetching {param}: {response.status_code}")
                continue
                
            content = response.content.decode('latin-1')
            reader = csv.DictReader(io.StringIO(content), delimiter=';')
            
            param_data = []
            row_idx = 0
            for row in reader:
                row_idx += 1
                # Filter by point_type_id=2 (ZIP) and point_id=plz
                p_type = row.get('point_type_id')
                p_id = row.get('point_id')
                
                if row_idx < 5:
                    print(f"DEBUG {param}: Row {row_idx} type={p_type} id={p_id}")
                
                if p_type == '2' and p_id == plz:
                    # New format: 'Date' instead of 'valid_time', and column name is the param itself
                    raw_date = row.get('Date')
                    val_str = row.get(param)
                    
                    if raw_date and val_str:
                        try:
                            # Convert YYYYMMDDHHMM to ISO format YYYY-MM-DDTHH:MM:00Z
                            iso_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}T{raw_date[8:10]}:{raw_date[10:12]}:00Z"
                            param_data.append({
                                "valid_time": iso_date,
                                "value": float(val_str) if val_str.strip() else 0.0
                            })
                        except ValueError:
                            continue
            
            if param_data:
                print(f"SUCCESS: Found {len(param_data)} entries for {param}")
                if param in HOURLY_PARAMS:
                    results["hourly"][param] = param_data
                else:
                    results["daily"][param] = param_data
            else:
                print(f"FAILURE: No matching point_id={plz} found in {row_idx} rows for {param}")
                
        except Exception as e:
            print(f"Error fetching MeteoSuisse param {param} from {url}: {e}")
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

def get_current_conditions(meteo_data: dict) -> dict:
    """
    Extracts the current hour's temperature and conditions from the 
    MeteoSwiss hourly forecast data series.
    
    Args:
        meteo_data: The full parsed dictionary containing 'hourly' and 'daily' keys.
        
    Returns:
        dict: A dictionary containing 'temp' and 'plz', or an empty dictionary if unavailable.
    """
    if not meteo_data or "hourly" not in meteo_data:
        return {}
        
    temp_series = meteo_data["hourly"].get("tre200h0", [])
    if not temp_series:
        return {}
        
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
