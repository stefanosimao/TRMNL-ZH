from PIL import Image

def compose_screen(data: dict):
    """Main 800x480 compositor"""
    img = Image.new("L", (800, 480), 255)
    return img
