from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from dotenv import load_dotenv
import os

# Explicitly load .env file
load_dotenv()

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and/or a .env file.
    
    Utilizes Pydantic for validation, type safety, and default value management.
    Handles configuration for the TRMNL device, SwitchBot API credentials, 
    search.ch transit stations, MeteoSuisse location, Wetter-Alarm points of interest, 
    and Gemini AI summaries.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # TRMNL Device
    TRMNL_DEVICE_ID: str  # MAC address used in ID header for authentication
    TRMNL_REFRESH_RATE: int = 45  # Polling interval in seconds for the e-ink display

    # SwitchBot API (requires developer token and secret)
    SWITCHBOT_TOKEN: str
    SWITCHBOT_SECRET: str
    SWITCHBOT_DEVICE_ID_INDOOR: str
    SWITCHBOT_DEVICE_ID_BALCONY: str

    # search.ch Transit configurations
    TRANSIT_STATION_1: str = "Zürich, Albisrieden"
    TRANSIT_STATION_2: str = "Zürich, Fellenbergstrasse"

    # MeteoSuisse location (Postleitzahl)
    METEO_PLZ: str = "8047"

    # Gemini API Key for intelligent summary generation
    GEMINI_API_KEY: Optional[str] = None

    # Wetter-Alarm — POI 142941 corresponds to Zürich Albisrieden
    WETTERALARM_POI_ID: int = 142941

    # Timezone
    TIMEZONE: str = "Europe/Zurich"

    # Server / Paths
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    IMAGE_DIR: str = "generated"  # Directory to serve and store the rendered display image
    BASE_URL: str = "http://localhost:8000"  # Needed to give the TRMNL device absolute URLs
    
settings = Settings()
