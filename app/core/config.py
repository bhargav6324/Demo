from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LIBRARY_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Smart Library Backend"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./library.db"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, values: list[str]) -> list[str]:
        from urllib.parse import urlsplit

        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in value
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
            # Validate an explicitly supplied port as well.
            _ = parsed.port
        return values
