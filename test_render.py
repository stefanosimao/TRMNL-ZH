from app.renderer.screen import compose_screen
from app.config import settings
import os
from datetime import datetime, date, timedelta

def _make_hourly_series(date_str: str, values: list) -> list:
    """Build 24-entry hourly series for the given date."""
    return [
        {"valid_time": f"{date_str}T{h:02d}:00:00Z", "value": values[h % len(values)]}
        for h in range(24)
    ]

def _make_daily_series(value: float, days: int = 3) -> list:
    today = date.today()
    return [
        {"valid_time": (today + timedelta(days=i)).strftime("%Y-%m-%dT00:00:00"), "value": value}
        for i in range(days)
    ]

def generate_preview():
    today = date.today().strftime("%Y-%m-%d")

    # Temperature profile: cool morning, warmer midday, cool evening
    temp_profile = [8, 8, 7, 7, 8, 9, 10, 11, 12, 13, 14, 15, 15, 14, 13, 12, 11, 10, 9, 9, 8, 8, 8, 8]
    # Precipitation: light rain in the afternoon
    precip_profile = [0]*12 + [0, 0, 0.2, 0.8, 1.2, 0.5, 0.1, 0, 0, 0, 0, 0]
    # Sunshine: morning and early afternoon
    sun_profile = [0]*6 + [10, 30, 45, 55, 60, 50, 40, 20, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    # Wind: mild throughout
    wind_profile = [8, 8, 7, 6, 6, 7, 8, 10, 12, 14, 15, 14, 13, 12, 11, 10, 9, 9, 8, 8, 7, 7, 7, 7]

    mock_meteo_full = {
        "hourly": {
            "tre200h0": _make_hourly_series(today, temp_profile),
            "rre150h0": _make_hourly_series(today, precip_profile),
            "sre000h0": _make_hourly_series(today, sun_profile),
            "fu3010h0": _make_hourly_series(today, wind_profile),
            "dkl010h0": _make_hourly_series(today, [200] * 24),
            "jww003i0": _make_hourly_series(today, [5] * 24),
        },
        "daily": {
            "tre200px": _make_daily_series(15.0),
            "tre200pn": _make_daily_series(7.5),
            "rka150p0": _make_daily_series(2.8),
            "jp2000d0": [
                {"valid_time": date.today().strftime("%Y-%m-%dT00:00:00"), "value": 5.0},
                {"valid_time": (date.today() + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00"), "value": 3.0},
                {"valid_time": (date.today() + timedelta(days=2)).strftime("%Y-%m-%dT00:00:00"), "value": 2.0},
            ],
        },
        "last_updated": datetime.now().isoformat(),
    }

    mock_data = {
        "weather": {
            "indoor": {"temperature": 22.5, "humidity": 45, "battery": 100},
            "outdoor": {"temperature": 10.7, "humidity": 60, "battery": 90},
            "meteo": {"temp": 11.2, "plz": "8047"}
        },
        "transit": {
            "station_1": [
                {"line": "3", "destination": "Klusplatz", "minutes": 4, "delay": 0},
                {"line": "3", "destination": "Klusplatz", "minutes": 12, "delay": 2},
                {"line": "80", "destination": "Oerlikon", "minutes": 7, "delay": 0}
            ],
            "station_2": [
                {"line": "3", "destination": "Klusplatz", "minutes": 2, "delay": 0},
                {"line": "67", "destination": "Wiedikon", "minutes": 9, "delay": 0},
                {"line": "67", "destination": "Milchbuck", "minutes": 15, "delay": 1}
            ]
        },
        "summary": "Oggi fresco e nuvoloso, 10.7°C. Pioggia leggera prevista verso le 18. Porta giacca e ombrello per stasera. Domani coperto ma asciutto. ⚠ Tram 3: +4min ritardo (Hardplatz). Se vai a Oerlikon, bus 80 tra 5 min è l'opzione migliore.",
        "meteo_full": mock_meteo_full,
    }
    
    print("Generating 800x480 preview...")
    img = compose_screen(mock_data)
    
    # Ensure generated directory exists
    if not os.path.exists(settings.IMAGE_DIR):
        os.makedirs(settings.IMAGE_DIR)
    
    output_path = os.path.join(settings.IMAGE_DIR, "test_preview.png")
    img.save(output_path)
    print(f"Preview saved to {output_path}")
    print(f"Open this file to inspect the layout at 800x480 resolution.")

if __name__ == "__main__":
    generate_preview()
