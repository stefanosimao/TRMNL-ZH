import httpx
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from .cache import global_cache
from .services.switchbot import fetch_switchbot_status
from .services.meteosuisse import fetch_meteosuisse_data

# Shared scheduler
scheduler = AsyncIOScheduler()

async def update_switchbot_cache(client: httpx.AsyncClient):
    """Job to update indoor and outdoor sensor data."""
    try:
        indoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
        outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
        global_cache.set("switchbot", {"indoor": indoor, "outdoor": outdoor})
    except Exception as e:
        global_cache.set_error("switchbot", str(e))

async def update_meteo_cache(client: httpx.AsyncClient):
    """Job to update MeteoSuisse forecast data."""
    try:
        data = await fetch_meteosuisse_data(client)
        global_cache.set("meteo", data)
    except Exception as e:
        global_cache.set_error("meteo", str(e))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.client = httpx.AsyncClient()
    
    # Run initial jobs immediately
    await update_switchbot_cache(app.state.client)
    await update_meteo_cache(app.state.client)
    
    # Schedule recurring jobs
    scheduler.add_job(update_switchbot_cache, 'interval', minutes=5, args=[app.state.client])
    scheduler.add_job(update_meteo_cache, 'interval', minutes=30, args=[app.state.client])
    
    scheduler.start()
    
    yield
    
    # Shutdown
    scheduler.shutdown()
    await app.state.client.aclose()

def create_app() -> FastAPI:
    app = FastAPI(title="TRMNL-ZH Stationboard", lifespan=lifespan)
    
    # Mount the generated directory for static access (the display image)
    if not os.path.exists(settings.IMAGE_DIR):
        os.makedirs(settings.IMAGE_DIR)
    app.mount(f"/{settings.IMAGE_DIR}", StaticFiles(directory=settings.IMAGE_DIR), name=settings.IMAGE_DIR)
    
    from .routes import router
    app.include_router(router)

    return app
