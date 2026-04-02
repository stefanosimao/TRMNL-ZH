import os
from PIL import ImageFont
from functools import lru_cache

# We prioritize DejaVu Sans as per specification section 7
FONT_SEARCH_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/DejaVuSans.ttf", # macOS
    "/Library/Fonts/DejaVuSans.ttf"
]

@lru_cache(maxsize=32)
def get_font(size: int, weight: str = "Regular"):
    """Loads a font at the specified size and weight, with caching."""
    font_name = "DejaVuSans"
    if weight == "Bold":
        font_name += "-Bold"
        
    # Try searching for the font file
    font_path = None
    for path in FONT_SEARCH_PATHS:
        if weight == "Bold":
            path = path.replace("DejaVuSans", "DejaVuSans-Bold")
        if os.path.exists(path):
            font_path = path
            break
            
    try:
        if font_path:
            return ImageFont.truetype(font_path, size)
        else:
            # Fallback to default
            return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()
