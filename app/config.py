from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # TRMNL Device
    TRMNL_DEVICE_ID: str  # MAC address used in ID header
    TRMNL_REFRESH_RATE: int = 45

    # SwitchBot API
    SWITCHBOT_TOKEN: str
    SWITCHBOT_SECRET: str
    SWITCHBOT_DEVICE_ID_INDOOR: str
    SWITCHBOT_DEVICE_ID_BALCONY: str

    # search.ch Transit
    TRANSIT_STATION_1: str = "Zürich, Albisrieden"
    TRANSIT_STATION_2: str = "Zürich, Fellenbergstrasse"

    # MeteoSuisse
    METEO_PLZ: str = "8047"

    # Gemini Flash
    GEMINI_API_KEY: Optional[str] = None

    # Wetter-Alarm — POI 142941 = Zürich Albisrieden
    WETTERALARM_POI_ID: int = 142941

    # Server / Paths
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    IMAGE_DIR: str = "generated"
    BASE_URL: str = "http://localhost:8000"
    
    CACHE_TTL: int = 300
    DEBUG: bool = False

settings = Settings()
