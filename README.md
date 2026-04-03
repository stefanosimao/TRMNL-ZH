# TRMNL-ZH

A custom BYOS (Bring Your Own Server) backend for a [TRMNL](https://usetrmnl.com) e-ink display. The server aggregates personal data from multiple sources, renders an 800×480 pixel black-and-white image, and serves it to the device every 45 seconds.

![Preview](generated/test_preview.png)

---

## What it shows

| Section | Content |
|---------|---------|
| Temperature row | Indoor (SwitchBot), balcony (SwitchBot), Zürich 8047 (MeteoSwiss) |
| 3-day forecast | Min/max °C, weather icon, sunrise/sunset, daily precipitation |
| Chart 1 | 24h temperature curve + precipitation bars, current-hour marker |
| Chart 2 | 24h sunshine bars + wind speed line, sunrise/sunset markers |
| Transit — Albisrieden | Tram 3 → Klusplatz ×2, Bus 80 → Triemli ×1, Bus 80 → Oerlikon ×2 |
| Transit — Fellenbergstr. | Tram 3 → Klusplatz ×2, Bus 67 → Wiedikon ×2, Bus 67 → Milchbuck ×2 |
| Riepilogo Intelligente | Gemini 2.5 Flash Italian summary: weather advice, alerts, transit tips |
| Clock | HH:MM (large), Italian date, battery %, last-refresh timestamp |

All UI text is in Italian.

---

## Architecture

Full BYOS — the TRMNL cloud is not involved. The device talks directly to this server.

```
TRMNL device
    │  GET /api/display  (every 45s, sends MAC address in "ID" header)
    ▼
FastAPI server
    ├── fetch search.ch LIVE  (2 stations, async parallel, ~1-2s)
    ├── read everything else from in-memory cache:
    │       SwitchBot temps    ← background job every 5 min
    │       MeteoSwiss data    ← background job every 30 min
    │       Wetter-Alarm       ← background job every 30 min
    │       Gemini summary     ← background job every 60 min
    │                            (also triggered on new alerts)
    ├── render 800×480 1-bit PNG with Pillow (~300ms)
    └── return { "image_url": "...", "refresh_rate": 45, ... }

TRMNL device downloads image_url and displays it
```

The `/api/display` endpoint responds in ~2 seconds — invisible within a 45-second cycle.

---

## Requirements

- Python 3.11+
- DejaVu Sans fonts (see [Font setup](#font-setup))
- SwitchBot account with two Meter sensors (indoor + balcony)
- Google AI Studio account with Gemini API enabled
- TRMNL device in BYOS mode (no special licence required)

---

## Installation

```bash
git clone https://github.com/StefanoSimao/TRMNL-ZH
cd TRMNL-ZH
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Font setup

The renderer uses DejaVu Sans. On Ubuntu/Debian:

```bash
sudo apt-get install fonts-dejavu-core
```

On macOS, the font loader checks `/System/Library/Fonts/Supplemental/DejaVuSans.ttf` automatically. If no font file is found, Pillow's built-in bitmap font is used as a fallback — the server will not crash.

---

## Configuration

Copy `.env` and fill in your credentials:

```env
# TRMNL Device — MAC address printed on the device label
TRMNL_DEVICE_ID="AA:BB:CC:DD:EE:FF"
TRMNL_REFRESH_RATE=45

# SwitchBot — from Developer Options in the SwitchBot app
SWITCHBOT_TOKEN=""
SWITCHBOT_SECRET=""
SWITCHBOT_DEVICE_ID_INDOOR=""
SWITCHBOT_DEVICE_ID_BALCONY=""

# Gemini — from https://aistudio.google.com/apikey
GEMINI_API_KEY=""

# Server — set to your public URL when deploying
BASE_URL="http://localhost:8000"
```

Everything else has sensible defaults: station names, PLZ 8047, Wetter-Alarm POI 142941 (Albisrieden), 45-second refresh.

### Finding your SwitchBot device IDs

With `SWITCHBOT_TOKEN` set, list your devices:

```bash
curl -s -H "Authorization: $SWITCHBOT_TOKEN" \
     https://api.switch-bot.com/v1.1/devices | python3 -m json.tool
```

Look for `"deviceType": "WoIOSensor"` (Outdoor Meter) or `"Meter"` entries and copy their `deviceId` values.

---

## Running

```bash
source venv/bin/activate
python run.py
```

The server starts on `http://0.0.0.0:8000`. On startup it immediately runs all background jobs — SwitchBot fetch, MeteoSwiss download, Wetter-Alarm check, Gemini summary — before accepting requests.

Auto-reload is enabled in development. For production use `uvicorn app:app --host 0.0.0.0 --port 8000` without `--reload`.

### Preview without a device

Generate a static preview image from mock data — no credentials or API calls needed:

```bash
python test_render.py
# → generated/test_preview.png
```

Fetch real data from all APIs and render what the device will actually receive:

```bash
python test_live_render.py
# → generated/live_preview.png
```

SwitchBot credentials must be set in `.env` for the live render. Gemini summary shows a placeholder — start the full server for that.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/display` | Main BYOS endpoint. Requires `ID` header = `TRMNL_DEVICE_ID`. |
| `POST` | `/api/log` | Receives device log messages (printed to stdout). |
| `POST` | `/api/setup` | Device provisioning — returns `{"status": "ready"}`. |
| `GET` | `/api/health` | Health check — returns `{"status": "healthy"}`. |
| `GET` | `/generated/screen.png` | The rendered display image (served as a static file). |
| `GET` | `/docs` | Auto-generated OpenAPI / Swagger UI. |

### BYOS response format

```json
{
  "image_url": "http://your-server/generated/screen.png?v=1712345678",
  "filename": "screen-1712345678.png",
  "refresh_rate": 45,
  "update_firmware": false,
  "firmware_url": null,
  "reset_firmware": false
}
```

`refresh_rate` is in seconds. The default of 45 matches `TRMNL_REFRESH_RATE` in `.env`.

---

## Data Sources

| Source | Data | Update interval | Auth |
|--------|------|-----------------|------|
| [search.ch timetable API](https://timetable.search.ch/api/help) | Live tram/bus departures | Every request (live) | None |
| [SwitchBot API v1.1](https://github.com/OpenWonderLabs/SwitchBotAPI) | Temperature, humidity, battery for 2 sensors | Every 5 min | HMAC-SHA256 |
| [MeteoSwiss Open Data E4](https://opendatadocs.meteoswiss.ch/e-forecast-data/e4-local-forecast-data) | Hourly + daily forecast for PLZ 8047 | Every 30 min | None |
| [Wetter-Alarm](https://wetteralarm.ch) — POI 142941 | Active weather alerts for Albisrieden | Every 30 min | None |
| [Gemini 2.5 Flash](https://ai.google.dev) | Italian summary paragraph | Every 60 min (or on new alert) | Google API key |

### Rate limits and daily usage

| Source | Daily limit | Our usage |
|--------|-------------|-----------|
| search.ch stationboard | 10,080 | ~3,840 (2 stations × 1,920 requests/day at 45s) |
| SwitchBot | 10,000 | ~576 (2 sensors × 288 requests/day) |
| MeteoSwiss | None specified | 528 downloads/day (11 CSV files × 48 fetches) |
| Wetter-Alarm | None specified | 48 requests/day |
| Gemini Flash | Quota-based | ~24–48 calls/day |

### Transit lines

**Zürich, Albisrieden** — next departures shown:
- Tram 3 → Klusplatz (next 2)
- Bus 80 → Triemli (next 1)
- Bus 80 → Oerlikon (next 2)

**Zürich, Fellenbergstrasse** — next departures shown:
- Tram 3 → Klusplatz (next 2)
- Bus 67 → Wiedikon (next 2)
- Bus 67 → Milchbuck (next 2)

Delays are shown inline (e.g. `12+2 min`). The minutes value already accounts for the delay — it reflects when the tram actually leaves.

---

## Project Structure

```
TRMNL-ZH/
├── run.py                    Entry point: uvicorn server
├── test_render.py            Offline layout preview with mock data (no credentials needed)
├── test_live_render.py       Live layout preview — fetches real data, saves generated/live_preview.png
├── test_services.py          API connectivity check for all external services
├── requirements.txt
├── .env                      Credentials — do not commit
│
└── app/
    ├── __init__.py           App factory, lifespan context, background scheduler
    ├── config.py             Pydantic settings (loaded from .env)
    ├── cache.py              In-memory cache with per-source timestamps + error state
    ├── routes.py             /api/display, /api/log, /api/setup, /api/health
    │
    ├── services/
    │   ├── searchch.py       search.ch stationboard API — live transit departures
    │   ├── switchbot.py      SwitchBot API v1.1 — HMAC-SHA256 signed requests
    │   ├── meteosuisse.py    MeteoSwiss E4 — STAC CSV download and parsing
    │   ├── wetteralarm.py    Wetter-Alarm — active alert fetch for POI 142941
    │   └── gemini.py         Gemini 2.5 Flash — Italian summary generation
    │
    └── renderer/
        ├── screen.py         Main compositor — stitches all sections into 800×480
        ├── transit.py        Street-timetable style departure rows
        ├── charts.py         24h temperature/precipitation/sunshine/wind charts
        ├── weather_icons.py  B&W geometric icons from MeteoSwiss pictogram codes
        └── fonts.py          DejaVu Sans loader with LRU cache and bitmap fallback
```

---

## Connecting the TRMNL device

1. On the device go to **Settings → Server** and set the custom server URL.
2. Point it to `http://your-server/api/display`.
3. The device will start polling every 45 seconds (as returned in `refresh_rate`).
4. Requests arrive with an `ID` header containing the device MAC address — this must match `TRMNL_DEVICE_ID` in `.env`.

For local testing, expose the server with:

```bash
ngrok http 8000
# or
cloudflared tunnel --url http://localhost:8000
```

Update `BASE_URL` in `.env` to the tunnel URL so the device can reach `image_url`.

---

## Deployment

The server must be always-on — APScheduler runs background jobs continuously. Serverless / Lambda won't work.

| Platform | Cost | Notes |
|----------|------|-------|
| [Fly.io](https://fly.io) | Free (256 MB VM) | `flyctl launch && flyctl deploy` |
| [Hetzner Cloud](https://hetzner.com) | ~€4/mo | CX11 in Zürich — lowest latency to search.ch |
| [AWS Lightsail](https://aws.amazon.com/lightsail/) | $3.50/mo | 3-month free trial |

Set secrets via your platform's secret manager (e.g. `flyctl secrets set KEY=value`) rather than committing `.env`.

---

## Error resilience

Each data source degrades independently — the display is never blank.

| Source fails | Behaviour |
|-------------|-----------|
| search.ch | Shows `--:--` timestamp next to transit section |
| SwitchBot | Shows `--` for affected temperature tiles |
| MeteoSwiss | Shows last cached forecast (updates hourly anyway) |
| Gemini | Shows last cached summary or "Riepilogo non disponibile HH:MM" |
| Wetter-Alarm | No alert shown (safe default — never false-positive) |
| Renderer crash | Serves a fallback error image with error message + timestamp; device never receives a 500 |

---

## Battery

The TRMNL device sends a `BATTERY_VOLTAGE` header on every request. The server converts voltage to percentage (linear: 3.0 V = 0%, 4.2 V = 100%) and displays it in the clock section. At a 45-second refresh rate, a 2500 mAh battery lasts approximately 6 days per charge.
