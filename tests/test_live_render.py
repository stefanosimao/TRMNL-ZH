"""
Live render test: fetches real data from all services, renders the 800x480 screen,
and saves it to generated/live_preview.png — no server or device needed.
This is the exact same data path as /api/display.
"""
import asyncio
import httpx
import os
import sys
from datetime import datetime

# Ensure project root is on sys.path when running as `python tests/test_live_render.py`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.services.switchbot import fetch_switchbot_status
from app.services.meteosuisse import (
    fetch_meteosuisse_data, get_current_conditions,
    get_daily_forecast, get_sun_times, get_next_24h_series,
)
from app.services.searchch import fetch_stationboard
from app.services.wetteralarm import fetch_alerts, format_alerts_for_prompt
from app.services.gemini import generate_summary
from app.renderer.screen import compose_screen


async def main():
    async with httpx.AsyncClient() as client:
        timestamps = {}

        # SwitchBot
        print("Fetching SwitchBot...")
        try:
            indoor  = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
            outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
            switchbot = {"indoor": indoor or {}, "outdoor": outdoor or {}}
            timestamps["switchbot"] = datetime.now().strftime("%H:%M")
            print(f"  indoor={indoor and indoor.get('temperature')}°C  outdoor={outdoor and outdoor.get('temperature')}°C")
        except Exception as e:
            print(f"  ERROR: {e}")
            switchbot = {}

        # MeteoSuisse
        print("Fetching MeteoSuisse...")
        try:
            meteo_data = await fetch_meteosuisse_data(client)
            timestamps["meteo"] = datetime.now().strftime("%H:%M")
            current = get_current_conditions(meteo_data)
            print(f"  current={current.get('temp')}°C")
        except Exception as e:
            print(f"  ERROR: {e}")
            meteo_data = None
            current = {}

        # Transit (live)
        print("Fetching transit...")
        try:
            s1, s2 = await asyncio.gather(
                fetch_stationboard(client, settings.TRANSIT_STATION_1),
                fetch_stationboard(client, settings.TRANSIT_STATION_2),
            )
            timestamps["transit"] = datetime.now().strftime("%H:%M")
            print(f"  station_1={len(s1)} deps  station_2={len(s2)} deps")
        except Exception as e:
            print(f"  ERROR: {e}")
            s1, s2 = [], []

        # Wetter-Alarm
        print("Fetching Wetter-Alarm...")
        try:
            alerts = await fetch_alerts(client)
            alert_strings = format_alerts_for_prompt(alerts)
            print(f"  alerts={len(alerts)}")
        except Exception as e:
            print(f"  ERROR: {e}")
            alert_strings = []

        # Gemini Summary
        print("Generating Gemini summary...")
        try:
            weather = {
                "indoor":  switchbot.get("indoor",  {}),
                "outdoor": switchbot.get("outdoor", {}),
                "meteo":   current,
            }
            transit_snapshot = {"station_1": s1, "station_2": s2}
            summary = await generate_summary(weather, transit_snapshot, alert_strings)
            timestamps["summary"] = datetime.now().strftime("%H:%M")
            print(f"  summary length={len(summary)} chars")
        except Exception as e:
            print(f"  ERROR: {e}")
            summary = "Riepilogo non disponibile."
            timestamps["summary"] = "--:--"

        # Derive display data (same as routes.py)
        sun_times = get_sun_times()
        series = {
            "temp":   get_next_24h_series(meteo_data, "tre200h0") if meteo_data else [None] * 24,
            "precip": get_next_24h_series(meteo_data, "rre150h0") if meteo_data else [None] * 24,
            "sun":    get_next_24h_series(meteo_data, "sre000h0") if meteo_data else [None] * 24,
            "wind":   get_next_24h_series(meteo_data, "fu3010h0") if meteo_data else [None] * 24,
        }

        data_bundle = {
            "weather": {
                "indoor":  switchbot.get("indoor",  {}),
                "outdoor": switchbot.get("outdoor", {}),
                "meteo":   current,
            },
            "transit":    {"station_1": s1, "station_2": s2},
            "summary":    summary,
            "meteo_full": meteo_data,
            "battery":    None,
            "timestamps": timestamps,
            "sun_times":  sun_times,
            "series":     series,
        }

        # Save API responses for debugging
        import json
        debug_path = os.path.join(settings.IMAGE_DIR, "api_responses.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            # We filter out the full meteo_full to keep it readable, or keep it if requested
            json.dump(data_bundle, f, indent=2, default=str)
        print(f"Debug data saved → {debug_path}")

        print("\nRendering screen...")
        img = compose_screen(data_bundle)

        os.makedirs(settings.IMAGE_DIR, exist_ok=True)
        output = os.path.join(settings.IMAGE_DIR, "live_preview.png")
        img.save(output)
        print(f"Saved → {output}")


if __name__ == "__main__":
    asyncio.run(main())
