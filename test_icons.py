"""Render all MeteoSwiss weather icon variants to a single preview image."""
from PIL import Image, ImageDraw
from app.renderer.weather_icons import draw_weather_icon
from app.renderer.fonts import get_font

COLS = 8
CODES = list(range(1, 41))
ROWS = (len(CODES) + COLS - 1) // COLS

LABELS = {
    1: "Clear", 2: "Partly sunny", 3: "Partly sunny", 4: "Cloudy", 5: "Overcast",
    6: "Fog", 7: "Light rain", 8: "Rain", 9: "Heavy rain", 10: "Thunder",
    11: "Light rain*", 12: "Rain*", 13: "Heavy rain*", 14: "Thunder*",
    15: "Light snow", 16: "Light snow", 17: "Light snow",
    18: "Mod. snow", 19: "Mod. snow",
    20: "Heavy snow", 21: "Heavy snow",
    22: "Light sleet", 23: "Light sleet", 24: "Heavy sleet", 25: "Heavy sleet",
    26: "Partly sunny", 27: "->Partly", 28: "->Partly", 29: "->Rain", 30: "->Rain",
    31: "->Thunder", 32: "->Thunder", 33: "->Thunder",
    34: "->Mod snow", 35: "->Mod snow", 36: "->Mod snow",
    37: "->Lt sleet", 38: "->Lt sleet", 39: "->Lt sleet", 40: "->Lt sleet",
}

cell_w = 90
cell_h = 80
margin = 10
img_w = COLS * cell_w + margin * 2
img_h = ROWS * cell_h + margin * 2

img = Image.new("1", (img_w, img_h), 255)
draw = ImageDraw.Draw(img)
font = get_font(10, "Regular")
font_bold = get_font(11, "Bold")

for idx, code in enumerate(CODES):
    col = idx % COLS
    row = idx // COLS
    x = margin + col * cell_w
    y = margin + row * cell_h

    draw.rectangle([x, y, x + cell_w - 4, y + cell_h - 4], outline=0, width=1)
    draw.text((x + 4, y + 2), f"#{code}", font=font_bold, fill=0)

    icon_x = x + (cell_w - 40) // 2 - 2
    icon_y = y + 12
    draw_weather_icon(draw, icon_x, icon_y, code)

    label = LABELS.get(code, "?")
    draw.text((x + 4, y + cell_h - 18), label, font=font, fill=0)

out_path = "generated/icon_preview.png"
img.save(out_path)
print(f"Saved to {out_path} ({img_w}x{img_h})")
