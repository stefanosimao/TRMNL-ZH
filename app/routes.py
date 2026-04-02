from fastapi import APIRouter, Response

router = APIRouter(prefix="/api")

@router.get("/display")
async def get_display():
    """Generates and returns the 800x480 screen image."""
    return {"message": "Image would be returned here"}

@router.get("/log")
async def get_log():
    return {"status": "ok"}

@router.get("/setup")
async def get_setup():
    return {"status": "ready"}

@router.get("/health")
async def health():
    return {"status": "healthy"}
