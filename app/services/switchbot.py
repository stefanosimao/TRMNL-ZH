import hmac
import hashlib
import time
import base64
import uuid
import httpx
from typing import Optional
from ..config import settings

async def fetch_switchbot_status(client: httpx.AsyncClient, device_id: str) -> Optional[dict]:
    """
    Fetches the current sensor readings from a specific SwitchBot Meter.
    Implements the SwitchBot API v1.1 HMAC-SHA256 request signing mechanism.
    
    Args:
        client: Shared HTTPX async client.
        device_id: The MAC address or ID of the SwitchBot device.
        
    Returns:
        Optional[dict]: A dictionary containing 'temperature', 'humidity', and 'battery', 
                        or None if the request fails or returns a non-100 status code.
    """
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
            "temperature": data["body"].get("temperature"),
            "humidity": data["body"].get("humidity"),
            "battery": data["body"].get("battery")
        }
    return None
