"""
Discord webhook notifications for TRMNL-ZH server alerts.

Sends embedded messages to a Discord channel for:
  - Low battery warnings (20%) and critical alerts (10%)
  - Service errors (API failures, timeouts)

Rate-limited: each alert type is only sent once until the condition
changes (e.g., battery recovers above threshold or a new error occurs).
"""
import logging
import time
import httpx
from ..config import settings

logger = logging.getLogger(__name__)

# Rate-limiting state: tracks the last alert sent per category
# to avoid spamming the same notification on every request/job cycle.
_last_alerts: dict[str, float] = {}
_COOLDOWN_SECONDS = 1800  # 30 minutes between repeated alerts of the same type

# Battery: track the last notified threshold so we only alert once per crossing
_last_battery_threshold: int | None = None

# Embed colors by severity
_COLORS = {
    "info":    0x3498DB,  # blue
    "warning": 0xF39C12,  # orange
    "error":   0xE74C3C,  # red
}


async def send_discord_alert(
    title: str,
    message: str,
    level: str = "warning",
    alert_key: str | None = None,
    client: httpx.AsyncClient | None = None,
):
    """
    Send an embedded notification to the configured Discord webhook.

    Args:
        title:     Embed title (e.g., "Low Battery Warning").
        message:   Embed description text.
        level:     Severity — 'info', 'warning', or 'error'.
        alert_key: Deduplication key. If provided, the same key won't fire
                   again within _COOLDOWN_SECONDS.
        client:    Optional shared httpx client. A one-shot client is created
                   if not provided (e.g., during startup before app.state.client
                   exists).
    """
    url = settings.DISCORD_WEBHOOK_URL
    if not url:
        return

    # Rate-limit by alert_key
    if alert_key:
        now = time.time()
        last = _last_alerts.get(alert_key, 0)
        if now - last < _COOLDOWN_SECONDS:
            return
        _last_alerts[alert_key] = now

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": _COLORS.get(level, _COLORS["info"]),
        }]
    }

    try:
        if client:
            await client.post(url, json=payload, timeout=5.0)
        else:
            async with httpx.AsyncClient() as tmp:
                await tmp.post(url, json=payload, timeout=5.0)
    except Exception as e:
        logger.warning(f"Failed to send Discord alert: {e}")


async def check_battery_alert(
    battery_pct: int,
    client: httpx.AsyncClient | None = None,
):
    """
    Send a Discord alert if battery drops below 20% or 10%.
    Only notifies once per threshold crossing.
    """
    global _last_battery_threshold

    if battery_pct <= 10:
        threshold = 10
        level = "error"
        title = "Battery Critical"
        msg = f"Battery is at **{battery_pct}%** — charge the device soon."
    elif battery_pct <= 20:
        threshold = 20
        level = "warning"
        title = "Low Battery Warning"
        msg = f"Battery is at **{battery_pct}%**."
    else:
        # Battery is fine — reset threshold tracking
        _last_battery_threshold = None
        return

    # Only notify once per threshold crossing
    if _last_battery_threshold == threshold:
        return
    _last_battery_threshold = threshold

    await send_discord_alert(title, msg, level=level, client=client)
