import httpx
from fastapi import FastAPI
from .config import settings

def create_app() -> FastAPI:
    app = FastAPI(title="TRMNL-ZH Stationboard")
    
    # Shared httpx client setup
    @app.on_event("startup")
    async def startup():
        app.state.client = httpx.AsyncClient()

    @app.on_event("shutdown")
    async def shutdown():
        await app.state.client.aclose()

    from .routes import router
    app.include_router(router)

    return app
