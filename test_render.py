from app.renderer.screen import compose_screen
import os

def generate_preview():
    # Mock data for rendering
    mock_data = {
        "station": "Zürich HB",
        "departures": [
            {"line": "S2", "dest": "Zürich Flughafen", "time": "14:05"},
            {"line": "S8", "dest": "Winterthur", "time": "14:08"}
        ]
    }
    
    img = compose_screen(mock_data)
    
    if not os.path.exists("generated"):
        os.makedirs("generated")
    
    img.save("generated/screen.png")
    print("Preview saved to generated/screen.png")

if __name__ == "__main__":
    generate_preview()
