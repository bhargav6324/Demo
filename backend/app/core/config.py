import secrets
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LIBRARY_", env_file=".env", env_file_encoding="utf-8", extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "Smart Library Backend"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./library.db"
    jwt_secret: SecretStr | None = None
    jwt_access_token_minutes: int = Field(default=60, ge=1, le=1440)
    jwt_issuer: str = Field(default="smart-library-backend", min_length=1)
    jwt_audience: str = Field(default="smart-library-api", min_length=1)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    @field_validator("jwt_secret")
    @classmethod
    def strong_signing_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT signing key must contain at least 32 bytes")
        return value

    @model_validator(mode="after")
    def signing_key_for_environment(self):
        if self.jwt_secret is None:
            if self.environment == "production":
                raise ValueError("LIBRARY_JWT_SECRET is required in production")
            # A private, per-instance development key; never a shared hard-coded secret.
            self.jwt_secret = SecretStr(secrets.token_urlsafe(48))
        return self

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
