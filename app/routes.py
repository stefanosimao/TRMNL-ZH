from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import JSONResponse
import time
import os
import asyncio
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
    Main TRMNL BYOS endpoint.
    Fetches real-time transit, merges with cached sensors/weather, 
    renders the image, and returns the metadata.
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
    
    # Merge summary if available (Phase 4)
    summary = global_cache.get("summary") or "Caricamento summary intelligente..."

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
        "meteo_full": meteo_data
    }

    # 4. Render 800x480 screen image
    try:
        img = compose_screen(data_bundle)
        
        # Save image to the static directory
        image_path = os.path.join(settings.IMAGE_DIR, "screen.png")
        img.save(image_path)
    except Exception as e:
        print(f"Error rendering screen: {e}")
        # We might want to fallback to a basic error image or return error JSON

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
