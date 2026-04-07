import httpx
import csv
import io
from astral import LocationInfo
from astral.sun import sun
from datetime import datetime, date, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo
from ..config import settings

_ZURICH_TZ = ZoneInfo("Europe/Zurich")

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
        
    target_date = datetime.now(_ZURICH_TZ).date() + timedelta(days=days_offset)
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

def get_sun_times(target_date: Optional[date] = None) -> dict:
    """
    Calculates sunrise and sunset times for Zurich (47.37N, 8.52E).
    
    Args:
        target_date (Optional[date]): The date to calculate sun times for. Defaults to today.

    Returns:
        dict: A dictionary containing 'sunrise' and 'sunset' formatted as 'HH:MM'.
    """
    target_date = target_date or datetime.now(_ZURICH_TZ).date()
    city = LocationInfo("Zurich", "Switzerland", "Europe/Zurich", 47.37, 8.52)
    s = sun(city.observer, date=target_date, tzinfo=_ZURICH_TZ)
    return {
        "sunrise": s["sunrise"].strftime("%H:%M"),
        "sunset": s["sunset"].strftime("%H:%M")
    }

async def _resolve_point_ids(client: httpx.AsyncClient, plz: str) -> set:
    """
    Downloads the collection-level station metadata CSV and returns the set of
    point_id values that correspond to the given postal code.
    """
    meta_url = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-local-forecasting/ogd-local-forecasting_meta_point.csv"
    try:
        r = await client.get(meta_url)
        r.raise_for_status()
        content = r.content.decode('latin-1')
        reader = csv.DictReader(io.StringIO(content), delimiter=';')
        ids = {row['point_id'] for row in reader if row.get('postal_code') == plz}
        print(f"Resolved PLZ {plz} → point_ids: {ids}")
        return ids
    except Exception as e:
        print(f"Error resolving point_ids for PLZ {plz}: {e}")
        return set()


async def fetch_meteosuisse_data(client: httpx.AsyncClient):
    """
    Downloads forecast CSVs for all parameters for the configured PLZ.
    Uses STAC API to find the latest available CSV files and the collection
    metadata to resolve the numeric point_id(s) for the PLZ.
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

    # 2. Resolve the numeric point_id(s) for this PLZ from the metadata CSV
    point_ids = await _resolve_point_ids(client, plz)
    if not point_ids:
        print(f"Could not resolve any point_id for PLZ {plz}")
        return results

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
            for row in reader:
                if row.get('point_id') in point_ids:
                    raw_date = row.get('Date')
                    val_str = row.get(param)

                    if raw_date and val_str:
                        try:
                            # MeteoSwiss E4 dates are in UTC (YYYYMMDDHHMM)
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
                print(f"FAILURE: No data found for {param} (point_ids={point_ids})")

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
        
    target_date = target_date or datetime.now(_ZURICH_TZ)
    date_str = target_date.strftime("%Y-%m-%d")
    
    # Initialize 24 slots
    day_data = [None] * 24
    
    for entry in series:
        # valid_time is UTC: "2026-04-02T15:00:00Z" → convert to Zurich local time.
        # MeteoSwiss timestamps mark the END of the aggregation interval, so we
        # subtract 1 hour to get the start of the interval for chart display.
        try:
            v_utc = datetime.fromisoformat(entry["valid_time"].replace("Z", "+00:00"))
            v_local = v_utc.astimezone(_ZURICH_TZ)
            display_hour = v_local - timedelta(hours=1)
            if display_hour.strftime("%Y-%m-%d") == date_str:
                day_data[display_hour.hour] = entry["value"]
        except (ValueError, KeyError):
            continue
                
    return day_data

def get_next_24h_series(meteo_data: dict, param: str, lookback: int = 1) -> List[Optional[float]]:
    """
    Returns 24 values: `lookback` past hours + (24 - lookback) future hours.
    Index `lookback` is always the current hour (ORA).
    Spans yesterday/today/tomorrow as needed.
    """
    now = datetime.now(_ZURICH_TZ)
    start = now - timedelta(hours=lookback)
    result = []
    for offset in range(24):
        target_dt = start + timedelta(hours=offset)
        day_series = get_24h_series(meteo_data, param, target_dt)
        result.append(day_series[target_dt.hour])
    return result


def get_current_conditions(meteo_data: dict) -> dict:
    """
    Extracts the current hour's temperature by aligning local Zurich time
    with the UTC valid_time in the MeteoSuisse data.
    """
    if not meteo_data or "hourly" not in meteo_data:
        return {}
        
    temp_series = meteo_data["hourly"].get("tre200h0", [])
    if not temp_series:
        return {}
        
    now_zurich = datetime.now(_ZURICH_TZ)
    
    # Find the entry closest to the current time in Zurich
    current_temp = None
    min_diff = timedelta(hours=24)
    
    for entry in temp_series:
        # valid_time: "2026-04-02T15:00:00Z"
        v_time_utc = datetime.fromisoformat(entry["valid_time"].replace("Z", "+00:00"))
        diff = abs(now_zurich - v_time_utc)
        if diff < min_diff:
            min_diff = diff
            current_temp = entry["value"]
    
    return {
        "temp": current_temp,
        "plz": settings.METEO_PLZ
    }
