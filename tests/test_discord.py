"""
Manual test script for Discord webhook notifications.

Usage:
    python test_discord.py

Requires DISCORD_WEBHOOK_URL to be set in .env.
Sends one test message per alert type with a 2-second pause between each,
so you can see them arrive in Discord one by one.
"""
import asyncio
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.services import discord


async def main():
    url = settings.DISCORD_WEBHOOK_URL
    if not url:
        print("DISCORD_WEBHOOK_URL is not set in .env — nothing to test.")
        return

    print(f"Webhook URL: {url[:50]}...")
    print()

    # Bypass rate-limiting for this test
    discord._last_alerts.clear()
    discord._last_battery_threshold = None
    discord._COOLDOWN_SECONDS = 0

    async with httpx.AsyncClient() as client:

        # 1. Info-level alert
        print("[1/5] Sending INFO alert...")
        await discord.send_discord_alert(
            title="Test: Info Alert",
            message="This is a test **info** notification from TRMNL-ZH.",
            level="info",
            client=client,
        )
        print("      Sent!")
        await asyncio.sleep(2)

        # 2. Warning-level alert
        print("[2/5] Sending WARNING alert...")
        await discord.send_discord_alert(
            title="Test: Warning Alert",
            message="This is a test **warning** notification (e.g., API fallback).",
            level="warning",
            client=client,
        )
        print("      Sent!")
        await asyncio.sleep(2)

        # 3. Error-level alert
        print("[3/5] Sending ERROR alert...")
        await discord.send_discord_alert(
            title="Test: Error Alert",
            message="This is a test **error** notification (e.g., SwitchBot API down).",
            level="error",
            client=client,
        )
        print("      Sent!")
        await asyncio.sleep(2)

        # 4. Battery warning (20%)
        print("[4/5] Sending battery WARNING (15%)...")
        discord._last_battery_threshold = None  # reset
        await discord.check_battery_alert(15, client=client)
        print("      Sent!")
        await asyncio.sleep(2)

        # 5. Battery critical (10%)
        print("[5/5] Sending battery CRITICAL (8%)...")
        discord._last_battery_threshold = None  # reset
        await discord.check_battery_alert(8, client=client)
        print("      Sent!")

    print()
    print("All 5 test alerts sent. Check your Discord channel!")


if __name__ == "__main__":
    asyncio.run(main())
