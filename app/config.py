from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:////data/garmin-analytics.db"
    garmin_tokens: str = "/root/.garminconnect"
    initial_sync_days: int = 365
    sync_interval_minutes: int = 180
    tz: str = "Europe/Madrid"
    sync_recent_days: int = 7
    garmin_request_delay_seconds: float = 0.8
    garmin_retry_base_seconds: int = 60

    @property
    def token_file(self) -> Path:
        return Path(self.garmin_tokens) / "garmin_tokens.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
