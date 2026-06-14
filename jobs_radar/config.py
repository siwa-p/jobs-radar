from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = None
    data_dir: Path = Path.home() / ".jobs-radar"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
