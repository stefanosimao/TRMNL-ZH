# TRMNL-ZH

A custom BYOS (Bring Your Own Server) FastAPI backend for a [TRMNL](https://usetrmnl.com) e-ink display, tailored for Zurich Albisrieden. The server aggregates weather, transit, and sensor data from multiple sources, renders an 800x480 pixel black-and-white image, and serves it to the device every 45 seconds. All UI text is in Italian.

![Preview](generated/test_preview.png)

---

## What it shows

| Section                  | Content                                                               |
| ------------------------ | --------------------------------------------------------------------- |
| Top Row                  | Date & Battery, Balcone temp, Zurich 8047 temp, Casa temp             |
| 3-day forecast           | Min/max C, weather icon, sunrise/sunset, daily precipitation          |
| Chart 1                  | 24h temperature curve + precipitation bars, current-hour marker       |
| Chart 2                  | 24h sunshine bars + wind speed line                                   |
| Transit - Albisrieden    | 5 departures: Tram 3, Bus 80 (see [Transit logic](#transit-logic))    |
| Transit - Fellenbergstr. | 2 departures: Bus 67                                                  |
| Riepilogo Intelligente   | Gemini 2.5 Flash Italian summary: weather advice, alerts, disruptions |
| Metadata Footer          | Last-refresh timestamps for SwitchBot, Transit, Meteo, and Gemini     |

---

## Architecture Overview

This is a BYOS (Bring Your Own Server) implementation. The TRMNL device communicates directly with this server, bypassing the TRMNL cloud. The backend is built with FastAPI for serving requests and APScheduler for running background tasks. Data from SwitchBot, MeteoSwiss, Wetter-Alarm, and Gemini are periodically fetched and cached in memory. Transit data is fetched live on each display request. The visual dashboard is drawn in memory using Pillow and saved as an uncompressed 1-bit grayscale PNG to prevent e-ink dithering artifacts.

```text
TRMNL device
    |  GET /api/display  (every 45s, sends MAC address in "ID" header)
    v
FastAPI server
    |-- fetch search.ch LIVE  (2 stations, async parallel, ~1-2s)
    |-- read everything else from in-memory cache:
    |       SwitchBot temps    <- background job every 5 min
    |       MeteoSwiss data    <- background job every 30 min
    |       Wetter-Alarm       <- background job every 30 min
    |       Transit snapshot   <- on each display request (also cached for Gemini)
    |       Gemini summary     <- background job every 30 min
    |                            (also triggered on alert changes)
    |-- render 800x480 1-bit image with Pillow (~300ms)
    |-- save as grayscale PNG (avoids 1-bit byte-packing artifacts on e-ink)
    '-- return { "image_url": "...", "refresh_rate": N, ... }

TRMNL device downloads image_url and displays it
```

The `/api/display` endpoint responds in ~2 seconds - invisible within a 45-second cycle.

### Night mode (01:00-05:00)

Between 01:00 and 05:00 Zurich time, the server enters quiet mode:

- **Device**: receives `refresh_rate` = seconds until 05:00, so it sleeps until then (saves battery).
- **Server**: all scheduled API calls are skipped (`_is_night_quiet` guard in `app/__init__.py`).
- **Pre-warm**: a cron job at 04:55 refreshes all caches in parallel so data is fresh when the device wakes at 05:00.

### Battery

The TRMNL device sends `battery_voltage` in its log POST payload. The server extracts it, converts voltage to percentage (linear: 3.0V = 0%, 4.2V = 100%), caches it, and displays it next to the date. The `BATTERY_VOLTAGE` header on GET `/api/display` is also checked as a primary source.

---

## Project Structure

```text
TRMNL-ZH/
├── run.py                    # Entry point: runs the Uvicorn ASGI server
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (not committed)
├── app/
│   ├── __init__.py           # App factory, lifespan events, and background scheduler
│   ├── config.py             # Pydantic settings management
│   ├── cache.py              # In-memory global cache
│   ├── routes.py             # API endpoints (/api/display, /api/log, etc.)
│   ├── services/             # External API integrations
│   │   ├── searchch.py       # Live transit departures
│   │   ├── switchbot.py      # SwitchBot temperature/humidity fetcher
│   │   ├── meteosuisse.py    # Forecast data from MeteoSwiss
│   │   ├── wetteralarm.py    # Active weather alerts
│   │   ├── gemini.py         # AI summary generator
│   │   └── discord.py        # Discord webhook notifications
│   └── renderer/             # Pillow drawing logic
│       ├── screen.py         # Main screen compositor
│       ├── charts.py         # 24h charts rendering
│       ├── transit.py        # Timetable rendering
│       ├── weather_icons.py  # MeteoSwiss pictogram drawing
│       ├── fonts.py          # Font loading and word wrapping
│       └── fonts/            # Bundled Liberation Sans fonts
└── docs/
    ├── AWS_Infra.md          # Infrastructure documentation
    └── LLM.md                # Prompt engineering notes
```

---

## Prerequisites

- Python 3.11+
- SwitchBot account with developer token and two Meter sensors (indoor + balcony)
- Google AI Studio account with Gemini API enabled
- TRMNL device in BYOS mode (no special licence required)

---

## Setup & Installation

```bash
git clone https://github.com/StefanoSimao/TRMNL-ZH
cd TRMNL-ZH
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Fonts

The renderer uses **Liberation Sans** (bundled in `app/renderer/fonts/`). No system font installation is required - the bundled font is used on all platforms for consistent rendering.

Liberation Sans is metrically identical to Arial and is open-source (SIL Open Font License). System DejaVu Sans and Arial are used as fallbacks if the bundled font is missing.

---

## Environment Variables & Configuration

Copy `.env.example` to `.env` (or create a new `.env` file) and fill in your credentials:

```env
# TRMNL Device - MAC address printed on the device label
TRMNL_DEVICE_ID="AA:BB:CC:DD:EE:FF"
TRMNL_REFRESH_RATE=45

# SwitchBot - from Developer Options in the SwitchBot app
SWITCHBOT_TOKEN=""
SWITCHBOT_SECRET=""
SWITCHBOT_DEVICE_ID_INDOOR=""
SWITCHBOT_DEVICE_ID_BALCONY=""

# Gemini - from https://aistudio.google.com/apikey
GEMINI_API_KEY=""

# Server - set to your public URL when deploying
BASE_URL="http://localhost:8000"

# Optional overrides
# TRANSIT_STATION_1="Zürich, Albisrieden"
# TRANSIT_STATION_2="Zürich, Fellenbergstrasse"
# METEO_PLZ="8047"
# WETTERALARM_POI_ID=142941
# TIMEZONE="Europe/Zurich"
```

Everything else has sensible defaults: station names, PLZ 8047, Wetter-Alarm POI 142941 (Albisrieden), timezone (Europe/Zurich), and 45-second refresh.

### Finding your SwitchBot device IDs

With `SWITCHBOT_TOKEN` set, list your devices:

```bash
curl -s -H "Authorization: $SWITCHBOT_TOKEN" \
     https://api.switch-bot.com/v1.1/devices | python3 -m json.tool
```

Look for `"deviceType": "WoIOSensor"` (Outdoor Meter) or `"Meter"` entries and copy their `deviceId` values.

---

## Running locally

```bash
source venv/bin/activate
python run.py
```

The server starts on `http://0.0.0.0:8000`. On startup it immediately runs all background jobs - SwitchBot, MeteoSwiss, transit snapshot, Wetter-Alarm, Gemini summary - before accepting requests.

Auto-reload is enabled in development. For production use `uvicorn run:app --host 0.0.0.0 --port 8000` without `--reload`.

### Preview without a device

Generate a static preview image from mock data - no credentials or API calls needed:

```bash
python tests/test_render.py
# -> generated/test_preview.png
```

Fetch real data from all APIs and render what the device will actually receive:

```bash
python tests/test_live_render.py
# -> generated/live_preview.png
```

SwitchBot credentials must be set in `.env` for the live render.

---

## Connecting the TRMNL device

1. On the device go to **Settings > Server** and set the custom server URL.
2. Point it to `http://your-server/api/display`.
3. The device will start polling every 45 seconds (as returned in `refresh_rate`).
4. Requests arrive with an `ID` header containing the device MAC address - this must match `TRMNL_DEVICE_ID` in `.env`.

For local testing, expose the server with:

```bash
ngrok http 8000
# or
cloudflared tunnel --url http://localhost:8000
```

Update `BASE_URL` in `.env` to the tunnel URL so the device can reach `image_url`.

---

## API Endpoints

| Method | Path                    | Description                                                   | Auth Requirement |
| ------ | ----------------------- | ------------------------------------------------------------- | ---------------- |
| `GET`  | `/api/display`          | Main BYOS endpoint. | Header `ID` = `TRMNL_DEVICE_ID`. |
| `POST` | `/api/log`              | Receives device log messages. Extracts battery voltage.       | None |
| `POST` | `/api/setup`            | Device provisioning - returns `{"status": "ready"}`.          | None |
| `GET`  | `/api/health`           | Health check - returns `{"status": "healthy"}`.               | None |
| `GET`  | `/generated/screen.png` | The rendered display image (served as a static file).         | None |
| `GET`  | `/docs`                 | Auto-generated OpenAPI / Swagger UI.                          | None |

### BYOS response format

```json
{
  "status": 0,
  "image_url": "http://your-server/generated/screen.png?v=1712345678",
  "filename": "screen-1712345678.png",
  "refresh_rate": 45,
  "update_firmware": false,
  "firmware_url": null,
  "reset_firmware": false
}
```

`refresh_rate` is in seconds. During the day it matches `TRMNL_REFRESH_RATE` (default 45). Between 01:00-05:00 it is dynamically set to the number of seconds until 05:00, putting the device to sleep for the night.

---

## Data Sources

| Source                                                                                               | Data                                         | Update interval                | Auth           |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------ | -------------- |
| [search.ch timetable API](https://timetable.search.ch/api/help)                                      | Live tram/bus departures                     | Every request (live)           | None           |
| [SwitchBot API v1.1](https://github.com/OpenWonderLabs/SwitchBotAPI)                                 | Temperature, humidity, battery for 2 sensors | Every 5 min                    | HMAC-SHA256    |
| [MeteoSwiss Open Data E4](https://opendatadocs.meteoswiss.ch/e-forecast-data/e4-local-forecast-data) | Hourly + daily forecast for PLZ 8047         | Every 30 min                   | None           |
| [Wetter-Alarm](https://wetteralarm.ch) - POI 142941                                                  | Active weather alerts for Albisrieden        | Every 30 min                   | None           |
| [Gemini 2.5 Flash](https://ai.google.dev)                                                            | Italian summary: weather advice, disruptions | Every 30 min (or on new alert) | Google API key |

### Rate limits and daily usage

All API calls are paused between 01:00 and 04:55 (night quiet hours), reducing daily usage by ~17%.

| Source                 | Daily limit    | Our usage                                              |
| ---------------------- | -------------- | ------------------------------------------------------ |
| search.ch stationboard | 10,080         | ~3,200 (2 stations x ~1,600 requests/day, minus night) |
| SwitchBot              | 10,000         | ~480 (2 sensors x ~240 requests/day, minus night)      |
| MeteoSwiss             | None specified | ~440 downloads/day (11 CSV files x ~40 fetches)        |
| Wetter-Alarm           | None specified | ~40 requests/day                                       |
| Gemini Flash           | Quota-based    | ~40-80 calls/day                                       |

### Transit logic

The display always shows **5 departures** for Albisrieden and **2** for Fellenbergstrasse. What fills those slots depends on the time of day:

| Time window         | Albisrieden (5 slots)                                      | Fellenbergstrasse (2 slots)                |
| ------------------- | ---------------------------------------------------------- | ------------------------------------------ |
| Normal hours        | 2x Tram 3 Klusplatz, 1x Bus 80 Triemli, 2x Bus 80 Oerlikon | 1x Bus 67 Wiedikon, 1x Bus 67 Dunkelholzli |
| Weekday 00:40-01:00 | Same (shows next-morning departures)                       | Same                                       |
| Weekend 00:40-01:00 | Gradual transition: tonight's connections + Nachtbus N3/N8 | N3 + N8                                    |
| 01:00-05:00         | No API calls (device sleeping)                             | No API calls                               |

**Weekend late-night transition**: as regular trams/buses stop running, their slots return next-morning departures (05:00+). These are replaced one-by-one with Nachtbus N3/N8 departures. For example at 00:45 on Saturday: if only 1 tram is still running tonight, the remaining 4 slots fill with night buses.

Delays are shown as `(+N') HH:MM` using the scheduled time. Cancelled departures (`dep_delay: "X"` from search.ch) are hidden from the timetable but reported to Gemini as disruptions.

### Gemini summary

The "Riepilogo Intelligente" panel shows a Gemini-generated Italian paragraph (max 320 characters) with practical weather advice. The prompt is time-aware:

- **Daytime (05:00-21:59)**: focuses on current conditions and the next few hours
- **Night (22:00-04:59)**: focuses on tomorrow morning's forecast

If the initial response exceeds 320 characters, a single retry asks Gemini to shorten it. If still too long, the text is truncated at the nearest word boundary.

The summary is regenerated every 30 minutes, and also immediately when the active weather alert set changes.

---

## Error resilience

Each data source degrades independently - the display is never blank.

| Source fails   | Behaviour                                                                                 |
| -------------- | ----------------------------------------------------------------------------------------- |
| search.ch      | Shows `--:--` timestamp next to transit section                                           |
| SwitchBot      | Shows `--` for affected temperature tiles                                                 |
| MeteoSwiss     | Shows last cached forecast (updates hourly anyway)                                        |
| Gemini         | Shows last cached summary or "Riepilogo non disponibile HH:MM"                            |
| Wetter-Alarm   | No alert shown (safe default - never false-positive)                                      |
| Renderer crash | Serves a fallback error image with error message + timestamp; device never receives a 500 |

---

## Deployment

The server is designed to run continuously on an AWS EC2 instance. Background jobs are managed entirely by APScheduler within the FastAPI application lifecycle. For more details on the infrastructure, refer to `docs/AWS_Infra.md`.
