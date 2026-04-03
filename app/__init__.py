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
from .services.wetteralarm import fetch_alerts, format_alerts_for_prompt
# from .services.gemini import generate_summary

# Shared scheduler
scheduler = AsyncIOScheduler()


async def update_switchbot_cache(client: httpx.AsyncClient):
    """Job: update indoor and outdoor sensor data (every 5 min)."""
    try:
        indoor  = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
        outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
        global_cache.set("switchbot", {"indoor": indoor, "outdoor": outdoor})
    except Exception as e:
        global_cache.set_error("switchbot", str(e))


async def update_meteo_cache(client: httpx.AsyncClient):
    """Job: download MeteoSuisse E4 forecast CSVs (every 30 min)."""
    try:
        data = await fetch_meteosuisse_data(client)
        global_cache.set("meteo", data)
    except Exception as e:
        global_cache.set_error("meteo", str(e))


async def update_alerts_and_maybe_summary(client: httpx.AsyncClient):
    """
    Job: fetch Wetter-Alarm alerts (every 30 min).
    If the alert set changed, immediately re-run the Gemini summary.
    """
    try:
        alerts = await fetch_alerts(client)
        previous = global_cache.get("alerts") or []
        global_cache.set("alerts", alerts)

        # Re-trigger summary if alert set changed
        prev_ids = {a.get("title") for a in previous}
        curr_ids = {a.get("title") for a in alerts}
        if prev_ids != curr_ids:
            await _run_gemini_summary(client)
    except Exception as e:
        global_cache.set_error("alerts", str(e))


async def _run_gemini_summary(client: httpx.AsyncClient):
    """Calls Gemini and stores the result in cache. Used by both the scheduler and event triggers."""
    try:
        switchbot  = global_cache.get("switchbot") or {}
        meteo_data = global_cache.get("meteo") or {}
        alerts     = global_cache.get("alerts") or []
        transit    = global_cache.get("transit_snapshot") or {}

        from .services.meteosuisse import get_current_conditions
        current_meteo = get_current_conditions(meteo_data) if meteo_data else {}

        weather = {
            "indoor":  switchbot.get("indoor",  {}),
            "outdoor": switchbot.get("outdoor", {}),
            "meteo":   current_meteo,
        }
        alert_strings = format_alerts_for_prompt(alerts)
        summary = await generate_summary(weather, transit, alert_strings)
        global_cache.set("summary", summary)
    except Exception as e:
        global_cache.set_error("summary", str(e))


async def update_gemini_summary(client: httpx.AsyncClient):
    """Job: regenerate Italian summary (every 60 min)."""
    await _run_gemini_summary(client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.client = httpx.AsyncClient()

    # Run initial jobs immediately (non-fatal — don't block startup on API errors)
    try:
        await update_switchbot_cache(app.state.client)
    except Exception as e:
        print(f"Startup SwitchBot error (non-fatal): {e}")

    try:
        await update_meteo_cache(app.state.client)
    except Exception as e:
        print(f"Startup MeteoSuisse error (non-fatal): {e}")

    try:
        await update_alerts_and_maybe_summary(app.state.client)
    except Exception as e:
        print(f"Startup Wetter-Alarm error (non-fatal): {e}")

    try:
        await update_gemini_summary(app.state.client)
    except Exception as e:
        print(f"Startup Gemini error (non-fatal): {e}")

    # Schedule recurring jobs
    scheduler.add_job(update_switchbot_cache,             'interval', minutes=5,  args=[app.state.client])
    scheduler.add_job(update_meteo_cache,                 'interval', minutes=30, args=[app.state.client])
    scheduler.add_job(update_alerts_and_maybe_summary,    'interval', minutes=30, args=[app.state.client])
    scheduler.add_job(update_gemini_summary,              'interval', minutes=60, args=[app.state.client])

    scheduler.start()

    yield

    # Shutdown
    scheduler.shutdown()
    await app.state.client.aclose()


def create_app() -> FastAPI:
    """
    Application factory pattern. Creates and configures the FastAPI application,
    sets up the lifespan (startup/shutdown events and background jobs), mounts 
    the static image directory, and registers API routers.
    
    Returns:
        FastAPI: The configured application instance.
    """
    app = FastAPI(title="TRMNL-ZH", lifespan=lifespan)

    # Mount the generated directory for static image access by the TRMNL device
    if not os.path.exists(settings.IMAGE_DIR):
        os.makedirs(settings.IMAGE_DIR)
    app.mount(f"/{settings.IMAGE_DIR}", StaticFiles(directory=settings.IMAGE_DIR), name=settings.IMAGE_DIR)

    from .routes import router
    app.include_router(router)

    return app
