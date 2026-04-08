import os
import sys
from datetime import date, timedelta, datetime

# Ensure project root is on sys.path when running as `python tests/test_render.py`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.renderer.screen import compose_screen
from app.config import settings


def generate_preview():
    today = date.today()

    # Temperature profile: cool morning, warmer midday, cool evening
    temp_profile = [8, 8, 7, 7, 8, 9, 10, 11, 12, 13, 14, 15, 15, 14, 13, 12, 11, 10, 9, 9, 8, 8, 8, 8]
    # Precipitation: light rain in the afternoon
    precip_profile = [0]*12 + [0, 0, 0.2, 0.8, 1.2, 0.5, 0.1, 0, 0, 0, 0, 0]
    # Sunshine: morning and early afternoon
    sun_profile = [0]*6 + [10, 30, 45, 55, 60, 50, 40, 20, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    # Wind: mild throughout
    wind_profile = [8, 8, 7, 6, 6, 7, 8, 10, 12, 14, 15, 14, 13, 12, 11, 10, 9, 9, 8, 8, 7, 7, 7, 7]

    mock_data = {
        "weather": {
            "indoor":  {"temperature": 22.5, "humidity": 45, "battery": 100},
            "outdoor": {"temperature": 10.7, "humidity": 60, "battery": 90},
            "meteo":   {"temp": 11.2, "plz": "8047"},
        },
        "battery": 78,
        "timestamps": {
            "switchbot": "10:03",
            "meteo":     "09:30",
            "summary":   "09:31",
        },
        "sun_times": {"sunrise": "06:15", "sunset": "20:05"},
        "forecasts": [
            {"date": today,                  "max_temp": 15.0, "min_temp":  7.5, "precip": 2.8, "pictogram": 5.0},
            {"date": today + timedelta(1),   "max_temp": 13.0, "min_temp":  6.0, "precip": 0.0, "pictogram": 3.0},
            {"date": today + timedelta(2),   "max_temp": 17.0, "min_temp":  5.0, "precip": 0.0, "pictogram": 2.0},
        ],
        "series": {
            "temp":   temp_profile,
            "precip": precip_profile,
            "sun":    sun_profile,
            "wind":   wind_profile,
        },
        "transit": {
            "station_1": [
                {"line": "3",  "destination": "Klusplatz", "minutes": 4,  "delay": 0, "time": "10:12", "scheduled_time": "10:12"},
                {"line": "3",  "destination": "Klusplatz", "minutes": 12, "delay": 2, "time": "10:22", "scheduled_time": "10:20"},
                {"line": "80", "destination": "Triemli",   "minutes": 7,  "delay": 0, "time": "10:15", "scheduled_time": "10:15"},
                {"line": "80", "destination": "Oerlikon",  "minutes": 3,  "delay": 0, "time": "10:11", "scheduled_time": "10:11"},
                {"line": "80", "destination": "Oerlikon",  "minutes": 18, "delay": 0, "time": "10:26", "scheduled_time": "10:26"},
            ],
            "station_2": [
                {"line": "67", "destination": "Wiedikon",      "minutes": 9,  "delay": 0, "time": "10:17", "scheduled_time": "10:17"},
                {"line": "67", "destination": "Dunkelhölzli",  "minutes": 14, "delay": 1, "time": "10:23", "scheduled_time": "10:22"},
            ],
        },
        "summary": (
            "Oggi fresco e nuvoloso, 10.7°C. Pioggia leggera prevista verso le 18. Porta giacca e ombrello per stasera. Domani coperto ma asciutto. ⚠ Tram 3: +4min ritardo (Hardplatz). Se vai a Oerlikon, bus 80 tra 5 min. Questo è un test che non significa nulla. Voglio capire quante lettere ci stanno nel box. Così dovrebbe bastare."
        ),
    }

    print("Generating 800x480 preview...")
    img = compose_screen(mock_data)

    os.makedirs(settings.IMAGE_DIR, exist_ok=True)
    output_path = os.path.join(settings.IMAGE_DIR, "test_preview.png")
    img.save(output_path)
    print(f"Preview saved to {output_path}")
    print("Open this file to inspect the layout at 800x480 resolution.")


if __name__ == "__main__":
    generate_preview()
