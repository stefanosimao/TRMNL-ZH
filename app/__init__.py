import httpx
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from .cache import global_cache
from .services.switchbot import fetch_switchbot_status
from .services.meteosuisse import fetch_meteosuisse_data
from .services.wetteralarm import fetch_alerts, format_alerts_for_prompt
from .services.searchch import fetch_stationboard
from .services.gemini import generate_summary

_ZURICH_TZ = ZoneInfo("Europe/Zurich")

# Shared scheduler
scheduler = AsyncIOScheduler()


def _is_night_quiet() -> bool:
    """Returns True between 01:00 and 04:54 Zurich time (quiet hours)."""
    now = datetime.now(_ZURICH_TZ)
    return 1 <= now.hour < 5 and not (now.hour == 4 and now.minute >= 55)


async def update_switchbot_cache(client: httpx.AsyncClient):
    """Job: update indoor and outdoor sensor data (every 5 min)."""
    if _is_night_quiet():
        return
    try:
        indoor  = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
        outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
        global_cache.set("switchbot", {"indoor": indoor, "outdoor": outdoor})
    except Exception as e:
        global_cache.set_error("switchbot", str(e))


async def update_transit_snapshot(client: httpx.AsyncClient):
    """Job: fetch transit departures so Gemini has disruption data."""
    if _is_night_quiet():
        return
    try:
        import asyncio
        s1, s2 = await asyncio.gather(
            fetch_stationboard(client, settings.TRANSIT_STATION_1),
            fetch_stationboard(client, settings.TRANSIT_STATION_2),
        )
        global_cache.set("transit_snapshot", {"station_1": s1, "station_2": s2})
    except Exception as e:
        print(f"Transit snapshot error: {e}")


async def update_meteo_cache(client: httpx.AsyncClient):
    """Job: download MeteoSuisse E4 forecast CSVs (every 30 min)."""
    if _is_night_quiet():
        return
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
    if _is_night_quiet():
        return
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

        from .services.meteosuisse import get_current_conditions, get_daily_forecast, get_sun_times
        current_meteo = get_current_conditions(meteo_data) if meteo_data else {}

        weather = {
            "indoor":           switchbot.get("indoor",  {}),
            "outdoor":          switchbot.get("outdoor", {}),
            "meteo":            current_meteo,
            "forecast_today":   get_daily_forecast(meteo_data, 0) if meteo_data else None,
            "forecast_tomorrow": get_daily_forecast(meteo_data, 1) if meteo_data else None,
            "sun_times":        get_sun_times(),
            "meteo_full":       meteo_data,
        }
        alert_strings = format_alerts_for_prompt(alerts)
        summary = await generate_summary(weather, transit, alert_strings)
        global_cache.set("summary", summary)
    except Exception as e:
        global_cache.set_error("summary", str(e))


async def update_gemini_summary(client: httpx.AsyncClient):
    """Job: regenerate Italian summary (every 60 min)."""
    if _is_night_quiet():
        return
    await _run_gemini_summary(client)


async def _prewarm_all_caches(client: httpx.AsyncClient):
    """Job: runs at 04:55 to refresh all caches before the device wakes at 05:00."""
    import asyncio
    print("Pre-warming all caches for 05:00 wake-up...")

    async def _switchbot():
        indoor  = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
        outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
        global_cache.set("switchbot", {"indoor": indoor, "outdoor": outdoor})

    async def _transit():
        s1, s2 = await asyncio.gather(
            fetch_stationboard(client, settings.TRANSIT_STATION_1),
            fetch_stationboard(client, settings.TRANSIT_STATION_2),
        )
        global_cache.set("transit_snapshot", {"station_1": s1, "station_2": s2})

    async def _meteo():
        data = await fetch_meteosuisse_data(client)
        global_cache.set("meteo", data)

    async def _alerts():
        alerts = await fetch_alerts(client)
        global_cache.set("alerts", alerts)

    results = await asyncio.gather(
        _switchbot(), _meteo(), _transit(), _alerts(),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            print(f"Pre-warm error: {r}")

    await _run_gemini_summary(client)
    print("Pre-warm complete.")


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
        await update_transit_snapshot(app.state.client)
    except Exception as e:
        print(f"Startup Transit snapshot error (non-fatal): {e}")

    try:
        await update_alerts_and_maybe_summary(app.state.client)
    except Exception as e:
        print(f"Startup Wetter-Alarm error (non-fatal): {e}")

    try:
        await update_gemini_summary(app.state.client)
    except Exception as e:
        print(f"Startup Gemini error (non-fatal): {e}")

    # Schedule recurring jobs (each skips 01:00–04:54 via _is_night_quiet)
    scheduler.add_job(update_switchbot_cache,             'interval', minutes=5,  args=[app.state.client])
    scheduler.add_job(update_meteo_cache,                 'interval', minutes=30, args=[app.state.client])
    scheduler.add_job(update_alerts_and_maybe_summary,    'interval', minutes=30, args=[app.state.client])
    scheduler.add_job(update_gemini_summary,              'interval', minutes=60, args=[app.state.client])
    # Pre-warm all caches at 04:55 so data is fresh when the device wakes at 05:00
    scheduler.add_job(_prewarm_all_caches,                'cron', hour=4, minute=55, args=[app.state.client],
                      timezone='Europe/Zurich')

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
