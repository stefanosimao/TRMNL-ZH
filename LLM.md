# TRMNL-ZH: Project Specification & Status

## 1. Project Overview
A custom BYOS (Bring Your Own Server) backend for a TRMNL e-ink display (800×480). Aggregates Zürich-specific data (MeteoSuisse, search.ch, SwitchBot, Wetter-Alarm) and renders a 1-bit B&W image. Includes an AI-generated Italian summary via Gemini 2.5 Flash.

**Owner**: Stefano
**Location**: Zürich PLZ 8047 (Albisrieden)
**Language**: All UI text in Italian.

---

## 2. Current Implementation Status (April 2026)

The project is in a **Mature/Maintenance** state. All core services from the original plan are implemented and functional.

| Component | Status | Implementation Detail |
|-----------|--------|-----------------------|
| **Framework** | ✅ Complete | FastAPI with `lifespan` for background jobs. |
| **Transit** | ✅ Complete | `search.ch` Live fetching with line/direction filtering. |
| **Weather** | ✅ Complete | `MeteoSuisse` E4 CSV parsing for PLZ 8047. |
| **Sensors** | ✅ Complete | `SwitchBot` API v1.1 with HMAC-SHA256 signing. |
| **Alerts** | ✅ Complete | `Wetter-Alarm` POI 142941 integration. |
| **AI Summary** | ✅ Complete | `Gemini 2.5 Flash` with time-aware prompting. |
| **Renderer** | ✅ Complete | Pillow-based 800×480 1-bit compositor with custom charts. |
| **Caching** | ✅ Complete | In-memory cache with per-source timestamps & error state. |

---

## 3. Screen Layout (Actual)

**Resolution**: 800×480 pixels, 1-bit B&W.

### Left Panel (555px)
- **Top Row**: 4 tiles [Date/Battery] [Balcone Temp] [Zürich Temp] [Casa Temp].
- **Forecast Row**: 3 tiles (Oggi, Domani, Day+2) with icons, min/max, sun times, and rain mm.
- **Chart 1**: 24h Temperature line + Precipitation bars.
- **Chart 2**: 24h Sunshine bars + Wind speed dashed line.

### Right Panel (245px)
- **Transit Section 1**: ALBISRIEDEN (5 slots: Tram 3, Bus 80).
- **Transit Section 2**: FELLENBERGSTR. (2 slots: Bus 67).
- **AI Summary**: "Riepilogo Intelligente" (Italian paragraph, max 395 chars).
- **Footer**: Last-refresh timestamps for all 4 data categories (SB/T/M/G).

---

## 4. Deployment Architecture (AWS EC2)

The recommended hosting strategy is **AWS EC2 (Free Tier)** for the first 12 months.

### Infrastructure Components
- **Server**: EC2 `t3.micro` (Ubuntu 24.04 LTS).
- **Static IP**: AWS Elastic IP (pointing to the instance).
- **Web Server**: `nginx` as a reverse proxy (handling SSL via Certbot/Let's Encrypt).
- **Process Manager**: `systemd` to manage the Uvicorn/FastAPI process.

### Deployment Table
| Option | Cost/month | Notes |
|---|---|---|
| **AWS EC2** | **$0** (12mo) | 750 hrs/mo free. Best for starting out. |
| **Hetzner** | **€3.79** | Zürich DC. Lowest latency to Swiss APIs. |
| **Raspberry Pi** | **$0** | Best for local/offline control via Cloudflare Tunnel. |

---

## 5. Technical Environment (.env)
```env
TRMNL_DEVICE_ID="AA:BB:CC:DD:EE:FF"
TRMNL_REFRESH_RATE=45
SWITCHBOT_TOKEN="..."
SWITCHBOT_SECRET="..."
SWITCHBOT_DEVICE_ID_INDOOR="..."
SWITCHBOT_DEVICE_ID_BALCONY="..."
GEMINI_API_KEY="..."
BASE_URL="http://your-aws-ip-or-domain"
```

---

## 6. Known Logic & Constraints
- **Night Quiet (01:00–05:00)**: Device sleeps, API calls pause.
- **Pre-warm (04:55)**: Cron job refreshes all caches before 05:00 wakeup.
- **Transit Filtering**: Lines 3, 67, 80 only. Weekend night bus (N3/N8) transition logic implemented.
- **Safety**: Fallback error image rendered if `compose_screen` fails.
