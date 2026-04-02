from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # search.ch
    SEARCH_CH_API_KEY: str
    STATION_NAME: str = "Zürich, HB"
    
    # SwitchBot
    SWITCHBOT_TOKEN: str
    SWITCHBOT_SECRET: str
    SWITCHBOT_DEVICE_ID: str

    # TRMNL Auth
    TRMNL_API_KEY: str
    
    CACHE_TTL: int = 300
    DEBUG: bool = False

settings = Settings()
