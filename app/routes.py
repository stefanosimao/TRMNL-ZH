"""
FastAPI routing and endpoints for the TRMNL-ZH backend.
Handles the main BYOS display generation, logging, and health checks.
"""
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import JSONResponse
from PIL import Image
import time
import os
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .config import settings

logger = logging.getLogger(__name__)

_ZURICH_TZ = ZoneInfo(settings.TIMEZONE)
from .cache import global_cache
from .services.searchch import fetch_stationboard
from .services.switchbot import fetch_switchbot_status
from .services.meteosuisse import fetch_meteosuisse_data, get_current_conditions, get_daily_forecast, get_sun_times, get_next_24h_series
from .renderer.screen import compose_screen
from .services.discord import send_discord_alert, check_battery_alert

router = APIRouter(prefix="/api")

def voltage_to_percent(v: float) -> int:
    """Converts LiPo battery voltage to a percentage using piecewise linear approximation."""
    curve = [
        (4.20, 100),
        (4.10, 90),
        (4.00, 80),
        (3.90, 60),
        (3.80, 40),
        (3.70, 20),
        (3.50, 10),
        (3.20, 0)
    ]
    if v >= curve[0][0]: return curve[0][1]
    if v <= curve[-1][0]: return curve[-1][1]
    
    for i in range(len(curve) - 1):
        v_high, p_high = curve[i]
        v_low, p_low = curve[i+1]
        if v_low <= v <= v_high:
            pct = p_low + (p_high - p_low) * ((v - v_low) / (v_high - v_low))
            return int(pct)
    return 0

async def verify_trmnl_request(request: Request):
    """Verify that the request comes from the authorized TRMNL device."""
    device_id = request.headers.get("ID")
    if not device_id or device_id != settings.TRMNL_DEVICE_ID:
        raise HTTPException(status_code=401, detail="Unauthorized")

def _get_refresh_rate() -> int:
    """
    Computes the correct refresh_rate: long sleep during night, normal otherwise.
    
    Returns:
        int: The number of seconds the device should sleep before the next request.
    """
    now_zh = datetime.now(_ZURICH_TZ)
    if 1 <= now_zh.hour < 5:
        wake_at = now_zh.replace(hour=5, minute=0, second=0, microsecond=0)
        return int((wake_at - now_zh).total_seconds())
    return settings.TRMNL_REFRESH_RATE


async def _build_display_response(request: Request) -> dict:
    """
    Core display logic: fetch transit, read caches, render image, return metadata.
    Extracted so get_display() can wrap it with a timeout.
    
    Args:
        request: The incoming FastAPI request.
        
    Returns:
        dict: The BYOS metadata payload containing the image URL and refresh rate.
    """
    client = request.app.state.client

    now_zh = datetime.now(_ZURICH_TZ)
    is_night = 1 <= now_zh.hour < 5

    # 1. Fetch Transit LIVE (always — departure times change by the minute)
    try:
        transit_1_task = fetch_stationboard(client, settings.TRANSIT_STATION_1)
        transit_2_task = fetch_stationboard(client, settings.TRANSIT_STATION_2)
        station_1_deps, station_2_deps = await asyncio.gather(transit_1_task, transit_2_task)
        logger.info(f"Transit: {len(station_1_deps)} deps from station_1, {len(station_2_deps)} from station_2")
        for d in station_1_deps[:3]:
            logger.info(f"  S1: line={d.get('line')} dest={d.get('destination')} in={d.get('minutes')}min")
        for d in station_2_deps[:3]:
            logger.info(f"  S2: line={d.get('line')} dest={d.get('destination')} in={d.get('minutes')}min")
    except Exception as e:
        logger.error(f"Error fetching transit: {e}")
        station_1_deps, station_2_deps = [], []

    # 2. SwitchBot + MeteoSuisse: use cache during the day (scheduler keeps it
    #    fresh), but fetch live at night (01:00–04:59) when the scheduler is dormant.
    if is_night:
        # Night: fetch live in parallel, fall back to cache on error
        async def _fetch_switchbot():
            indoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
            outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
            result = {"indoor": indoor or {}, "outdoor": outdoor or {}}
            global_cache.set("switchbot", result)
            return result

        async def _fetch_meteo():
            data = await fetch_meteosuisse_data(client)
            global_cache.set("meteo", data)
            return data

        switchbot_result, meteo_result = await asyncio.gather(
            _fetch_switchbot(), _fetch_meteo(),
            return_exceptions=True,
        )

        if isinstance(switchbot_result, Exception):
            logger.warning(f"Error fetching SwitchBot live: {switchbot_result}")
            switchbot = global_cache.get("switchbot") or {}
        else:
            switchbot = switchbot_result

        if isinstance(meteo_result, Exception):
            logger.warning(f"Error fetching MeteoSuisse live: {meteo_result}")
            meteo_data = global_cache.get("meteo")
        else:
            meteo_data = meteo_result
    else:
        # Day: read from cache (scheduler updates SwitchBot every 5 min, MeteoSuisse every 30 min)
        switchbot  = global_cache.get("switchbot") or {}
        meteo_data = global_cache.get("meteo")

    # 3. Derived data from live/cached sources
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

    # Battery voltage header → approximate percentage
    battery_pct = None
    batt_voltage = request.headers.get("BATTERY_VOLTAGE")
    if batt_voltage:
        try:
            v = float(batt_voltage)
            battery_pct = voltage_to_percent(v)
            global_cache.set("battery_pct", battery_pct)
            await check_battery_alert(battery_pct, client=client)
        except (ValueError, TypeError):
            pass
    # Fallback: use battery percentage from the most recent /api/log POST
    if battery_pct is None:
        battery_pct = global_cache.get("battery_pct")

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
        img = await asyncio.to_thread(compose_screen, data_bundle)
    except Exception as e:
        logger.error(f"Error rendering screen: {e}")
        # Fallback: minimal error image so the device never gets a blank screen
        from PIL import ImageDraw
        from .renderer.fonts import get_font
        img = Image.new("1", (800, 480), 255)
        d = ImageDraw.Draw(img)
        d.text((20, 200), f"⚠ Errore rendering: {str(e)[:80]}", font=get_font(18, "Regular"), fill=0)
        d.text((20, 230), datetime.now(_ZURICH_TZ).strftime("%H:%M:%S"), font=get_font(18, "Regular"), fill=0)

    image_path = os.path.join(settings.IMAGE_DIR, "screen.png")
    # Pipeline matching the official byos_fastapi approach:
    # 1. Convert to grayscale (cleans up mode "1" drawing artifacts)
    # 2. Convert back to 1-bit with no dithering (image is already pure B&W)
    # 3. Save as uncompressed PNG (compress_level=0) — avoids bottom-row
    #    artifact caused by zlib decompression edge cases in the ESP32 decoder
    img_gray = img.convert("L")
    img_out = img_gray.convert("1", dither=Image.Dither.NONE)
    img_out.save(image_path, format="PNG", compress_level=0)
    img.close()
    img_gray.close()
    img_out.close()

    # 5. Return JSON metadata per BYOS spec
    timestamp = int(time.time())
    filename = f"screen-{timestamp}.png"
    # Ensure BASE_URL doesn't have double slash
    base_url = settings.BASE_URL.rstrip('/')
    image_url = f"{base_url}/{settings.IMAGE_DIR}/screen.png?v={timestamp}"

    return {
        "status": 0,
        "image_url": image_url,
        "filename": filename,
        "refresh_rate": _get_refresh_rate(),
        "update_firmware": False,
        "firmware_url": None,
        "reset_firmware": False
    }


@router.get("/display")
async def get_display(request: Request, _ = Depends(verify_trmnl_request)):
    """
    Main TRMNL BYOS (Bring Your Own Server) endpoint.
    This endpoint is polled by the TRMNL e-ink device to retrieve the display image.
    It fetches live transit data on the fly, combines it with asynchronously cached
    weather, sensor, and summary data, renders the final image, and returns the
    required JSON metadata payload instructing the device on what to display.

    Wrapped with a 15-second timeout. On timeout, returns a fallback response
    serving the last-rendered image with the correct refresh_rate (including
    night sleep), so the device is never left without instructions.
    """
    try:
        return await asyncio.wait_for(_build_display_response(request), timeout=15.0)
    except asyncio.TimeoutError:
        logger.error("/api/display timed out after 15s, returning fallback response")
        await send_discord_alert("Display Timeout", "/api/display timed out after 15s — serving cached image", level="error", alert_key="display_timeout")
        base_url = settings.BASE_URL.rstrip('/')
        timestamp = int(time.time())
        return {
            "status": 0,
            "image_url": f"{base_url}/{settings.IMAGE_DIR}/screen.png?v={timestamp}",
            "filename": f"screen-{timestamp}.png",
            "refresh_rate": _get_refresh_rate(),
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
    logger.info(f"TRMNL Log: {data}")
    # Extract battery voltage from log entries and cache it
    for entry in data.get("logs", []):
        bv = entry.get("battery_voltage")
        if bv is not None:
            try:
                v = float(bv)
                pct = voltage_to_percent(v)
                global_cache.set("battery_pct", pct)
                await check_battery_alert(pct)
            except (ValueError, TypeError):
                pass
            break
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
