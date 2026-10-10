"""Environment-only configuration for the HTTP boundary."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Validated HTTP settings that never read a dotenv file."""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    backend_api_token: SecretStr | None = Field(
        default=None,
        validation_alias="BACKEND_API_TOKEN",
        repr=False,
    )
    host: str = Field(default="0.0.0.0", validation_alias="BACKEND_HOST")
    port: int = Field(default=8080, ge=1, le=65535, validation_alias="BACKEND_PORT")
    workers: int = Field(default=1, ge=1, le=32, validation_alias="BACKEND_WORKERS")
    production: bool = Field(default=False, validation_alias="BACKEND_PRODUCTION")
    cors_allow_origins: str = Field(
        default="",
        validation_alias="BACKEND_CORS_ALLOW_ORIGINS",
    )
    max_prompt_length: int = Field(
        default=10_000,
        ge=1,
        le=10_000_000,
        validation_alias="BACKEND_MAX_PROMPT_LENGTH",
    )
    max_request_bytes: int = Field(
        default=1_048_576,
        ge=128,
        le=100_000_000,
        validation_alias="BACKEND_MAX_REQUEST_BYTES",
    )

    @field_validator("backend_api_token")
    @classmethod
    def reject_empty_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value():
            raise ValueError("BACKEND_API_TOKEN must not be empty")
        return value

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """Return normalized HTTP origins from the comma-separated setting."""

        origins: list[str] = []
        for raw_origin in self.cors_allow_origins.split(","):
            origin = raw_origin.strip().rstrip("/")
            if not origin:
                continue
            parsed = urlsplit(origin)
            valid = (
                origin != "*"
                and parsed.scheme in {"http", "https"}
                and bool(parsed.netloc)
                and not parsed.username
                and not parsed.password
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            )
            if not valid:
                raise ValueError(
                    "BACKEND_CORS_ALLOW_ORIGINS must contain only explicit "
                    "HTTP(S) origins"
                )
            if origin not in origins:
                origins.append(origin)
        return tuple(origins)
