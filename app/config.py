from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    SEARCH_CH_API_KEY: str
    CACHE_TTL: int = 300
    DEBUG: bool = False

settings = Settings()
