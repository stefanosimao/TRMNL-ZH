from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import JSONResponse
from .services.searchch import fetch_stationboard
from .services.switchbot import fetch_switchbot_status
from .config import settings

router = APIRouter(prefix="/api")

async def verify_trmnl_request(request: Request):
    """Simple TRMNL authentication check."""
    token = request.headers.get("ID") or request.headers.get("Authorization")
    if not token or token != settings.TRMNL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/display")
async def get_display(request: Request, _ = Depends(verify_trmnl_request)):
    """Generates and returns JSON data for TRMNL display."""
    client = request.app.state.client
    
    try:
        departures = await fetch_stationboard(client)
        switchbot_data = await fetch_switchbot_status(client)
        
        # Merge data into TRMNL-expected JSON format
        # This structure depends on how you set up your Liquid template in TRMNL
        data = {
            "status": "ok",
            "weather": {
                "temperature": switchbot_data.get("temperature") if switchbot_data else "N/A",
                "battery": switchbot_data.get("battery") if switchbot_data else "N/A"
            },
            "station": settings.STATION_NAME,
            "departures": departures
        }
        
        return data
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@router.get("/log")
async def get_log():
    return {"status": "ok"}

@router.get("/setup")
async def get_setup():
    return {"status": "ready"}

@router.get("/health")
async def health():
    return {"status": "healthy"}
