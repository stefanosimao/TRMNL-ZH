import hmac
import hashlib
import time
import base64
import uuid
import httpx
from ..config import settings

async def fetch_switchbot_status(client: httpx.AsyncClient, device_id: str):
    """Fetch status from SwitchBot API v1.1 with HMAC-SHA256 signature for a specific device."""
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
    
    url = f"https://api.switch-bot.com/v1.1/devices/{device_id}/status"
    
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    if data.get("statusCode") == 100:
        return {
            "temperature": data["body"]["temperature"],
            "humidity": data["body"].get("humidity"),
            "battery": data["body"].get("battery")
        }
    return None
