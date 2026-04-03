import asyncio
import httpx
from app.config import settings
from app.services.switchbot import fetch_switchbot_status
from app.services.meteosuisse import fetch_meteosuisse_data
from app.services.searchch import fetch_stationboard

async def test_all():
    """Fetches and prints data from all three core services to verify API health."""
    print(f"DEBUG: Indoor ID from settings: '{settings.SWITCHBOT_DEVICE_ID_INDOOR}'")
    async with httpx.AsyncClient() as client:
        # 1. Test Transit (search.ch)
        print("--- Testing Transit (search.ch) ---")
        try:
            transit = await fetch_stationboard(client, settings.TRANSIT_STATION_1)
            if transit:
                print(f"✅ Success! Found {len(transit)} departures for {settings.TRANSIT_STATION_1}")
                for d in transit[:2]:
                    print(f"  - Line {d['line']} to {d['destination']} in {d['minutes']} min")
            else:
                print("⚠️  Transit returned 0 results (check if the station name is exact)")
        except Exception as e:
            print(f"❌ Transit Error: {e}")

        # 2. Test SwitchBot
        print("\n--- Testing SwitchBot ---")
        try:
            indoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_INDOOR)
            if indoor:
                print(indoor)  # Debug print to show the raw data
                print(f"✅ Success! Indoor: {indoor['temperature']}°C, {indoor['humidity']}% humidity")
                print(f"  - Battery: {indoor['battery']}%")
            else:
                print("⚠️  SwitchBot returned None (verify your Device ID, Token, and Secret)")
        except Exception as e:
            print(f"❌ SwitchBot Error: {e}")
        try:
            outdoor = await fetch_switchbot_status(client, settings.SWITCHBOT_DEVICE_ID_BALCONY)
            if outdoor:
                print(outdoor)  # Debug print to show the raw data
                print(f"✅ Success! Outdoor: {outdoor['temperature']}°C, {outdoor['humidity']}% humidity")
                print(f"  - Battery: {outdoor['battery']}%")
            else:
                print("⚠️  SwitchBot returned None (verify your Device ID, Token, and Secret)")
        except Exception as e:
            print(f"❌ SwitchBot Error: {e}")

        # 3. Test MeteoSuisse
        print("\n--- Testing MeteoSuisse ---")
        try:
            # This downloads several CSVs from geo.admin.ch
            data = await fetch_meteosuisse_data(client)
            if data and data.get("hourly"):
                print(f"✅ Success! Downloaded hourly/daily forecasts for PLZ {settings.METEO_PLZ}")
                # Print current temp if available
                from app.services.meteosuisse import get_current_conditions
                curr = get_current_conditions(data)
                if curr:
                    print(f"  - Current external temp: {curr.get('temp')}°C")
            else:
                print("⚠️  MeteoSuisse returned empty data")
        except Exception as e:
            print(f"❌ MeteoSuisse Error: {e}")

if __name__ == "__main__":
    print(f"🚀 Starting API connectivity tests for {settings.TRANSIT_STATION_1}...\n")
    asyncio.run(test_all())
