from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WARDROBE_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )

    # Localhost only by default (NFR-010); remote access needs an explicit override.
    host: str = "127.0.0.1"
    port: int = 8000

    data_dir: Path = BACKEND_DIR / "data"
    db_path: Path | None = None
    storage_root: Path | None = None
    log_dir: Path | None = None
    model_dir: Path | None = None  # weights live outside the repo

    log_level: str = "INFO"
    device: Literal["auto", "cuda", "cpu"] = "auto"

    @model_validator(mode="after")
    def _derive_paths(self) -> "Settings":
        self.data_dir = self.data_dir.resolve()
        self.db_path = self.db_path or self.data_dir / "wardrobe.db"
        self.storage_root = self.storage_root or self.data_dir / "images"
        self.log_dir = self.log_dir or self.data_dir / "logs"
        self.model_dir = self.model_dir or self.data_dir / "models"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
