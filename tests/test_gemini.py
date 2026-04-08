import asyncio
import httpx
import logging
from app.config import settings
from app.services.gemini import generate_summary
from app.cache import global_cache

logging.basicConfig(level=logging.INFO)

async def test_gemini():
    print(f"Testing Gemini with key: {settings.GEMINI_API_KEY[:10]}...")
    client = httpx.AsyncClient()
    
    # Mock data
    weather = {
        "indoor": {"temperature": 22.5},
        "outdoor": {"temperature": 10.2},
        "meteo": {"temp": 11.0},
        "forecast_today": {"min_temp": 5, "max_temp": 15, "precip": 0.5},
        "forecast_tomorrow": {"min_temp": 4, "max_temp": 12, "precip": 0.0},
    }
    transit = {"station_1": [], "station_2": []}
    alerts = ["Allerta pioggia"]
    
    try:
        result = await generate_summary(weather, transit, alerts)
        print("\n--- Gemini Result ---")
        print(result)
        print("----------------------\n")
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_gemini())
