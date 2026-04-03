import hmac
import hashlib
import time
import base64
import uuid
import httpx
import json
import asyncio
from app.config import settings

async def get_device_list():
    """Fetches the list of all devices from SwitchBot API v1.1."""
    if not settings.SWITCHBOT_TOKEN or not settings.SWITCHBOT_SECRET:
        print("❌ Error: SWITCHBOT_TOKEN or SWITCHBOT_SECRET missing in .env")
        return

    nonce = str(uuid.uuid4())
    timestamp = str(int(time.time() * 1000))
    data = settings.SWITCHBOT_TOKEN + timestamp + nonce
    
    signature = base64.b64encode(
        hmac.new(
            settings.SWITCHBOT_SECRET.encode('utf-8'),
            msg=data.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
    ).decode('utf-8')
    
    headers = {
        "Authorization": settings.SWITCHBOT_TOKEN,
        "sign": signature,
        "nonce": nonce,
        "t": timestamp,
        "Content-Type": "application/json; charset=utf8"
    }
    
    url = "https://api.switch-bot.com/v1.1/devices"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get("statusCode") == 100:
                devices = data["body"]["deviceList"]
                infrared = data["body"]["infraredRemoteList"]
                
                print(f"✅ Found {len(devices)} physical devices:")
                for d in devices:
                    print(f"  - {d['deviceName']} ({d['deviceType']})")
                    print(f"    ID: {d['deviceId']}")
                    print("-" * 30)
                
                if infrared:
                    print(f"\n✅ Found {len(infrared)} infrared remotes:")
                    for r in infrared:
                        print(f"  - {r['deviceName']} ({r['remoteType']})")
                        print(f"    ID: {r['deviceId']}")
                        print("-" * 30)
            else:
                print(f"❌ SwitchBot API Error: {data.get('message')}")
                
        except Exception as e:
            print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(get_device_list())
