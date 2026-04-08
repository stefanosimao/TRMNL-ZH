"""
Application factory, lifespan events, and background scheduler setup.
Initializes FastAPI, sets up APScheduler jobs, and mounts static files.
"""
import asyncio
import httpx
import logging
import os
import subprocess
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
from .services.discord import send_discord_alert

logger = logging.getLogger(__name__)

_ZURICH_TZ = ZoneInfo(settings.TIMEZONE)

scheduler = AsyncIOScheduler()


def _is_night_quiet() -> bool:
    """
    Returns True during night quiet hours: 01:00–04:54 Zurich time.

    During this window all scheduled jobs are skipped to avoid unnecessary
    API calls while the device is sleeping. The window ends at 04:55 (not
    05:00) because _prewarm_all_caches runs at 04:55 via a separate cron
    trigger and must NOT be blocked by this guard.
    """
    now = datetime.now(_ZURICH_TZ)
    return 1 <= now.hour < 5 and not (now.hour == 4 and now.minute >= 55)


async def update_switchbot_cache(client: httpx.AsyncClient):
    """Job: update indoor and outdoor sensor data (every 5 min)."""
    if _is_night_quiet():
        return
    logger.info("Updating SwitchBot cache...")
    try:
        indoor  = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
        outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
        global_cache.set("switchbot", {"indoor": indoor, "outdoor": outdoor})
        logger.info("SwitchBot cache updated successfully.")
    except Exception as e:
        logger.error(f"SwitchBot update failed: {e}")
        global_cache.set_error("switchbot", str(e))
        await send_discord_alert("SwitchBot Error", str(e), level="error", alert_key="switchbot_error", client=client)


async def update_transit_snapshot(client: httpx.AsyncClient):
    """Job: fetch transit departures so Gemini has disruption data."""
    if _is_night_quiet():
        return
    logger.info("Updating transit snapshot...")
    try:
        import asyncio
        s1, s2 = await asyncio.gather(
            fetch_stationboard(client, settings.TRANSIT_STATION_1),
            fetch_stationboard(client, settings.TRANSIT_STATION_2),
        )
        global_cache.set("transit_snapshot", {"station_1": s1, "station_2": s2})
        logger.info("Transit snapshot updated.")
    except Exception as e:
        logger.error(f"Transit snapshot error: {e}")


async def update_meteo_cache(client: httpx.AsyncClient):
    """Job: download MeteoSuisse E4 forecast CSVs (every 30 min)."""
    if _is_night_quiet():
        return
    logger.info("Updating MeteoSuisse cache...")
    try:
        data = await fetch_meteosuisse_data(client)
        global_cache.set("meteo", data)
        logger.info("MeteoSuisse cache updated.")
    except Exception as e:
        logger.error(f"MeteoSuisse update failed: {e}")
        global_cache.set_error("meteo", str(e))
        await send_discord_alert("MeteoSuisse Error", str(e), level="error", alert_key="meteo_error", client=client)


async def update_alerts_and_maybe_summary(client: httpx.AsyncClient):
    """
    Job: fetch Wetter-Alarm alerts (every 30 min).
    If the alert set changed, immediately re-run the Gemini summary.
    """
    if _is_night_quiet():
        return
    logger.info("Checking for weather alerts...")
    try:
        alerts = await fetch_alerts(client)
        previous = global_cache.get("alerts") or []
        global_cache.set("alerts", alerts)
        logger.info(f"Weather alerts check complete. {len(alerts)} active.")

        # Re-trigger summary if alert set changed
        prev_ids = {a.get("title") for a in previous}
        curr_ids = {a.get("title") for a in alerts}
        if prev_ids != curr_ids:
            logger.info("Alerts changed, re-triggering Gemini summary...")
            await _run_gemini_summary(client)
    except Exception as e:
        logger.error(f"Wetter-Alarm update failed: {e}")
        global_cache.set_error("alerts", str(e))
        await send_discord_alert("Wetter-Alarm Error", str(e), level="error", alert_key="alerts_error", client=client)


async def _run_gemini_summary(client: httpx.AsyncClient):
    """
    Assembles weather, forecast, alert, and transit data from the cache,
    then calls Gemini to produce a concise Italian summary paragraph.
    Used by the hourly scheduler job, the alert-change trigger, and the
    04:55 pre-warm routine.
    """
    logger.info("Generating Gemini summary...")
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
        logger.info("Gemini summary generated successfully.")
    except Exception as e:
        logger.error(f"Gemini summary failed: {e}")
        global_cache.set_error("summary", str(e))


async def update_gemini_summary(client: httpx.AsyncClient):
    """Job: regenerate Italian summary (every 30 min)."""
    if _is_night_quiet():
        return
    try:
        logger.info("Scheduled Gemini summary update starting...")
        await asyncio.wait_for(_run_gemini_summary(client), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error("Gemini summary job timed out after 120s")
        await send_discord_alert("Gemini Timeout", "Summary generation timed out after 120s", level="error", alert_key="gemini_timeout", client=client)


async def _prewarm_all_caches(client: httpx.AsyncClient):
    """
    Cron job: runs once at 04:55 Zurich time.

    Refreshes all data sources in parallel (SwitchBot, MeteoSuisse, transit,
    Wetter-Alarm) then regenerates the Gemini summary, so every cache is
    fresh when the TRMNL device wakes from its night sleep at 05:00.

    This bypasses _is_night_quiet() by calling the underlying fetchers
    directly instead of the guarded update_* wrappers.
    """
    logger.info("Pre-warming all caches for 05:00 wake-up...")

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
            logger.error(f"Pre-warm error: {r}")
            await send_discord_alert("Pre-warm Error", str(r), level="error", alert_key="prewarm_error", client=client)

    try:
        await asyncio.wait_for(_run_gemini_summary(client), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error("Pre-warm Gemini summary timed out after 120s")
        await send_discord_alert("Pre-warm Gemini Timeout", "Summary generation timed out during pre-warm", level="error", alert_key="prewarm_gemini_timeout", client=client)
    logger.info("Pre-warm complete.")


def _check_previous_crash() -> tuple[str, str]:
    """
    Check why the server was last stopped/killed.

    Returns (reason_text, level) where level is 'info', 'warning', or 'error'.
    Checks systemd exit status first, then dmesg for OOM kills.
    """
    reason_parts = []
    level = "info"

    # 1. Check systemd for previous exit status
    try:
        result = subprocess.run(
            ["systemctl", "show", "trmnl.service",
             "--property=ExecMainStatus,ExecMainCode,NRestarts"],
            capture_output=True, text=True, timeout=5,
        )
        props = {}
        for line in result.stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v

        exit_code = props.get("ExecMainStatus", "0")
        exit_type = props.get("ExecMainCode", "")
        restarts = props.get("NRestarts", "0")

        if exit_code != "0":
            if exit_type == "signal":
                signal_names = {"9": "SIGKILL (likely OOM)", "15": "SIGTERM", "11": "SIGSEGV"}
                sig = signal_names.get(exit_code, f"signal {exit_code}")
                reason_parts.append(f"Previous exit: **{sig}** (exit code {exit_code})")
                level = "error"
            else:
                reason_parts.append(f"Previous exit: code **{exit_code}**")
                level = "warning"

        if restarts != "0":
            reason_parts.append(f"Total restarts: **{restarts}**")
    except Exception:
        pass

    # 2. Check dmesg for recent OOM kills
    try:
        result = subprocess.run(
            ["dmesg", "--time-format=reltime", "-l", "err,crit"],
            capture_output=True, text=True, timeout=5,
        )
        for line in reversed(result.stdout.splitlines()):
            if "oom" in line.lower() or "killed process" in line.lower():
                reason_parts.append(f"**OOM kill detected:**\n```{line.strip()}```")
                level = "error"
                break
    except Exception:
        pass

    if not reason_parts:
        return "", "info"
    return "\n".join(reason_parts), level


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))

    # Restore persisted state from disk
    global_cache.load_persisted_battery()

    # Run initial jobs immediately (non-fatal — don't block startup on API errors)
    try:
        await update_switchbot_cache(app.state.client)
    except Exception as e:
        logger.warning(f"Startup SwitchBot error (non-fatal): {e}")

    try:
        await update_meteo_cache(app.state.client)
    except Exception as e:
        logger.warning(f"Startup MeteoSuisse error (non-fatal): {e}")

    try:
        await update_transit_snapshot(app.state.client)
    except Exception as e:
        logger.warning(f"Startup Transit snapshot error (non-fatal): {e}")

    try:
        await update_alerts_and_maybe_summary(app.state.client)
    except Exception as e:
        logger.warning(f"Startup Wetter-Alarm error (non-fatal): {e}")

    try:
        await update_gemini_summary(app.state.client)
    except Exception as e:
        logger.warning(f"Startup Gemini error (non-fatal): {e}")

    # Schedule recurring jobs (each skips 01:00–04:54 via _is_night_quiet)
    _job_opts = dict(coalesce=True, max_instances=1)
    scheduler.add_job(update_switchbot_cache,             'interval', minutes=5,  args=[app.state.client], **_job_opts)
    scheduler.add_job(update_meteo_cache,                 'interval', minutes=30, args=[app.state.client], **_job_opts)
    scheduler.add_job(update_alerts_and_maybe_summary,    'interval', minutes=30, args=[app.state.client], **_job_opts)
    scheduler.add_job(update_gemini_summary,              'interval', minutes=30, args=[app.state.client], **_job_opts)
    # Pre-warm all caches at 04:55 so data is fresh when the device wakes at 05:00
    scheduler.add_job(_prewarm_all_caches,                'cron', hour=4, minute=55, args=[app.state.client],
                      timezone=settings.TIMEZONE, **_job_opts)

    scheduler.start()

    # Notify Discord that the server (re)started
    crash_reason, level = _check_previous_crash()
    start_msg = f"Server started at {datetime.now(_ZURICH_TZ).strftime('%H:%M:%S')}."
    if crash_reason:
        start_msg += f"\n\n{crash_reason}"
    await send_discord_alert("Server Started", start_msg, level=level)

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
    os.makedirs(os.path.join(settings.IMAGE_DIR, "debug"), exist_ok=True)
    app.mount(f"/{settings.IMAGE_DIR}", StaticFiles(directory=settings.IMAGE_DIR), name=settings.IMAGE_DIR)

    from .routes import router
    app.include_router(router)

    return app
