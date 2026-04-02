from app.renderer.screen import compose_screen
from app.config import settings
import os
from datetime import datetime

def generate_preview():
    # Realistic mock data matching the data_bundle in routes.py
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
        "summary": "Oggi fresco e nuvoloso, 10.7°C. Pioggia leggera prevista verso le 18. Porta giacca e ombrello per stasera. Domani coperto ma asciutto. ⚠ Tram 3: +4min ritardo (Hardplatz). Se vai a Oerlikon, bus 80 tra 5 min è l'opzione migliore."
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
