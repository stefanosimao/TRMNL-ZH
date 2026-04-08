"""
Font management, loading, caching, and text measurement utilities.
"""
import os
from PIL import ImageFont, ImageDraw, Image
from functools import lru_cache

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

_FONT_VARIANTS = {
    "Regular": [
        os.path.join(_FONTS_DIR, "LiberationSans-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ],
    "Bold": [
        os.path.join(_FONTS_DIR, "LiberationSans-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/DejaVuSans-Bold.ttf",
        "/Library/Fonts/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ],
}

@lru_cache(maxsize=32)
def get_font(size: int, weight: str = "Regular"):
    """Loads a font at the specified size and weight, with caching."""
    paths = _FONT_VARIANTS.get(weight, _FONT_VARIANTS["Regular"])
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# Shared 1x1 image for text measurement (avoids creating one per call)
_measure_draw = ImageDraw.Draw(Image.new("1", (1, 1)))


def word_wrap(text: str, font: ImageFont.FreeTypeFont, max_px: int) -> list[str]:
    """Word-wrap *text* to fit within *max_px* pixels using *font* metrics."""
    lines, current = [], ""
    for word in text.split():
        test = (current + " " + word).strip()
        if _measure_draw.textlength(test, font=font) <= max_px:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
