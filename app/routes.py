from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import JSONResponse
import time
import os
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .config import settings

_ZURICH_TZ = ZoneInfo("Europe/Zurich")
from .cache import global_cache
from .services.searchch import fetch_stationboard
from .services.meteosuisse import get_current_conditions, get_daily_forecast, get_sun_times, get_next_24h_series
from .renderer.screen import compose_screen

router = APIRouter(prefix="/api")

async def verify_trmnl_request(request: Request):
    """Verify that the request comes from the authorized TRMNL device."""
    device_id = request.headers.get("ID")
    if not device_id or device_id != settings.TRMNL_DEVICE_ID:
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/display")
async def get_display(request: Request, _ = Depends(verify_trmnl_request)):
    """
    Main TRMNL BYOS (Bring Your Own Server) endpoint.
    This endpoint is polled by the TRMNL e-ink device to retrieve the display image.
    It fetches live transit data on the fly, combines it with asynchronously cached 
    weather, sensor, and summary data, renders the final image, and returns the 
    required JSON metadata payload instructing the device on what to display.
    
    Args:
        request: The FastAPI request object containing headers and app state.
        _: Dependency injection to verify the TRMNL_DEVICE_ID header.
        
    Returns:
        A JSON dictionary containing the image URL, filename, and refresh rate,
        conforming to the TRMNL custom firmware specifications.
    """
    client = request.app.state.client
    
    # 1. Fetch Transit LIVE (async parallel)
    try:
        transit_1_task = fetch_stationboard(client, settings.TRANSIT_STATION_1)
        transit_2_task = fetch_stationboard(client, settings.TRANSIT_STATION_2)
        station_1_deps, station_2_deps = await asyncio.gather(transit_1_task, transit_2_task)
        print(f"Transit: {len(station_1_deps)} deps from station_1, {len(station_2_deps)} from station_2")
        for d in station_1_deps[:3]:
            print(f"  S1: line={d.get('line')} dest={d.get('destination')} in={d.get('minutes')}min")
        for d in station_2_deps[:3]:
            print(f"  S2: line={d.get('line')} dest={d.get('destination')} in={d.get('minutes')}min")
    except Exception as e:
        print(f"Error fetching transit: {e}")
        station_1_deps, station_2_deps = [], []

    # 2. Get everything else from cache
    switchbot  = global_cache.get("switchbot") or {}
    meteo_data = global_cache.get("meteo")
    current_meteo = get_current_conditions(meteo_data) if meteo_data else {}
    summary    = global_cache.get("summary") or "Caricamento riepilogo intelligente..."

    # Pre-compute derived meteo data so the renderer stays a pure display layer
    sun_times = get_sun_times()
    forecasts = [get_daily_forecast(meteo_data, i) for i in range(3)] if meteo_data else [None, None, None]
    series = {
        "temp":   get_next_24h_series(meteo_data, "tre200h0") if meteo_data else [None] * 24,
        "precip": get_next_24h_series(meteo_data, "rre150h0") if meteo_data else [None] * 24,
        "sun":    get_next_24h_series(meteo_data, "sre000h0") if meteo_data else [None] * 24,
        "wind":   get_next_24h_series(meteo_data, "fu3010h0") if meteo_data else [None] * 24,
    }

    # Battery voltage header → approximate percentage (3.0V=0%, 4.2V=100%)
    battery_pct = None
    batt_voltage = request.headers.get("BATTERY_VOLTAGE")
    if batt_voltage:
        try:
            v = float(batt_voltage)
            battery_pct = max(0, min(100, int((v - 3.0) / 1.2 * 100)))
        except (ValueError, TypeError):
            pass

    # Store transit snapshot so Gemini job can reference recent departures + record timestamp
    transit_snapshot = {"station_1": station_1_deps, "station_2": station_2_deps}
    global_cache.set("transit_snapshot", transit_snapshot)
    global_cache.set("transit", transit_snapshot)

    def _ts(key: str) -> str:
        meta = global_cache.get_with_meta(key)
        if meta and meta.get("timestamp"):
            return datetime.fromtimestamp(meta["timestamp"], tz=_ZURICH_TZ).strftime("%H:%M")
        return "--:--"

    # 3. Build data bundle for renderer
    data_bundle = {
        "weather": {
            "indoor":  switchbot.get("indoor",  {}),
            "outdoor": switchbot.get("outdoor", {}),
            "meteo":   current_meteo,
        },
        "transit": {
            "station_1": station_1_deps,
            "station_2": station_2_deps,
        },
        "summary":   summary,
        "battery":   battery_pct,
        "timestamps": {
            "switchbot": _ts("switchbot"),
            "meteo":     _ts("meteo"),
            "summary":   _ts("summary"),
            "transit":   _ts("transit"),
        },
        "sun_times":  sun_times,
        "forecasts":  forecasts,
        "series":     series,
        "meteo_full": meteo_data,
    }

    # 4. Render 800x480 screen image
    try:
        img = compose_screen(data_bundle)
    except Exception as e:
        print(f"Error rendering screen: {e}")
        # Fallback: minimal error image so the device never gets a blank screen
        from PIL import Image, ImageDraw
        from .renderer.fonts import get_font
        img = Image.new("1", (800, 480), 255)
        d = ImageDraw.Draw(img)
        d.text((20, 200), f"⚠ Errore rendering: {str(e)[:80]}", font=get_font(18, "Regular"), fill=0)
        d.text((20, 230), datetime.now(_ZURICH_TZ).strftime("%H:%M:%S"), font=get_font(18, "Regular"), fill=0)

    image_path = os.path.join(settings.IMAGE_DIR, "screen.bmp")
    # Save as BMP3 (Windows 3.x 1-bit bitmap) — the format TRMNL firmware
    # officially expects. PNG caused bottom-row artifacts on the display.
    img.convert("1").save(image_path, format="BMP")

    # 5. Return JSON metadata per BYOS spec
    timestamp = int(time.time())
    filename = f"screen-{timestamp}.bmp"
    # Ensure BASE_URL doesn't have double slash
    base_url = settings.BASE_URL.rstrip('/')
    image_url = f"{base_url}/{settings.IMAGE_DIR}/screen.bmp?v={timestamp}"

    # Night mode (01:00–04:59): tell the device to sleep until 05:00.
    # The server also stops API calls during this window (_is_night_quiet).
    # At 04:55 the pre-warm cron job refreshes all caches so data is ready
    # when the device wakes up and makes its first request at ~05:00.
    now_zh = datetime.now(_ZURICH_TZ)
    if 1 <= now_zh.hour < 5:
        wake_at = now_zh.replace(hour=5, minute=0, second=0, microsecond=0)
        refresh_rate = int((wake_at - now_zh).total_seconds())
    else:
        refresh_rate = settings.TRMNL_REFRESH_RATE

    return {
        "status": 0,
        "image_url": image_url,
        "filename": filename,
        "refresh_rate": refresh_rate,
        "update_firmware": False,
        "firmware_url": None,
        "reset_firmware": False
    }

@router.post("/log")
async def post_log(request: Request):
    """
    Receive and print device log messages.
    
    Args:
        request: The FastAPI request object containing the JSON log payload.
        
    Returns:
        dict: A status acknowledgment.
    """
    data = await request.json()
    print(f"TRMNL Log: {data}")
    return {"status": "ok"}

@router.post("/setup")
async def post_setup(request: Request):
    """
    Handle device provisioning and setup requests.
    
    Args:
        request: The FastAPI request object.
        
    Returns:
        dict: A ready status indicating successful setup.
    """
    return {"status": "ready"}

@router.get("/health")
async def health():
    """
    Health check endpoint to verify the server is running.
    
    Returns:
        dict: A healthy status indicator.
    """
    return {"status": "healthy"}
