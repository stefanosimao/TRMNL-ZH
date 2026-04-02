from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import JSONResponse
import time
import os
import asyncio
from datetime import datetime
from .config import settings
from .cache import global_cache
from .services.searchch import fetch_stationboard
from .services.meteosuisse import get_current_conditions
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
    except Exception as e:
        print(f"Error fetching transit: {e}")
        station_1_deps, station_2_deps = [], []

    # 2. Get everything else from cache
    switchbot = global_cache.get("switchbot") or {}
    meteo_data = global_cache.get("meteo")
    current_meteo = get_current_conditions(meteo_data) if meteo_data else {}
    
    summary = global_cache.get("summary") or "Caricamento riepilogo intelligente..."

    # Battery voltage header → approximate percentage (3.0V=0%, 4.2V=100%)
    battery_pct = None
    batt_voltage = request.headers.get("BATTERY_VOLTAGE")
    if batt_voltage:
        try:
            v = float(batt_voltage)
            battery_pct = max(0, min(100, int((v - 3.0) / 1.2 * 100)))
        except (ValueError, TypeError):
            pass

    # Store transit snapshot so Gemini job can reference recent departures
    transit_snapshot = {"station_1": station_1_deps, "station_2": station_2_deps}
    global_cache.set("transit_snapshot", transit_snapshot)

    # 3. Build data bundle for renderer
    data_bundle = {
        "weather": {
            "indoor": switchbot.get("indoor", {}),
            "outdoor": switchbot.get("outdoor", {}),
            "meteo": current_meteo
        },
        "transit": {
            "station_1": station_1_deps,
            "station_2": station_2_deps
        },
        "summary": summary,
        "meteo_full": meteo_data,
        "battery": battery_pct,
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
        d.text((20, 230), datetime.now().strftime("%H:%M:%S"), font=get_font(18, "Regular"), fill=0)

    image_path = os.path.join(settings.IMAGE_DIR, "screen.png")
    img.save(image_path)

    # 5. Return JSON metadata per BYOS spec
    timestamp = int(time.time())
    filename = f"screen-{timestamp}.png"
    # Ensure BASE_URL doesn't have double slash
    base_url = settings.BASE_URL.rstrip('/')
    image_url = f"{base_url}/{settings.IMAGE_DIR}/screen.png?v={timestamp}"
    
    return {
        "image_url": image_url,
        "filename": filename,
        "refresh_rate": settings.TRMNL_REFRESH_RATE,
        "update_firmware": False,
        "firmware_url": None,
        "reset_firmware": False
    }

@router.post("/log")
async def post_log(request: Request):
    """Receive device log messages."""
    data = await request.json()
    print(f"TRMNL Log: {data}")
    return {"status": "ok"}

@router.post("/setup")
async def post_setup(request: Request):
    """Device provisioning/setup."""
    return {"status": "ready"}

@router.get("/health")
async def health():
    return {"status": "healthy"}
