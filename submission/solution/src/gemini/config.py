"""Environment-based configuration with secret-safe representations."""

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import ConfigurationError


class EnvSettings(BaseSettings):
    """Base class for settings read only from the process environment.

    Settings are immutable, never read a dotenv file and ignore variables
    that they do not declare.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )


class GeminiSettings(EnvSettings):
    """Validated runtime settings loaded exclusively from the environment."""

    api_key: SecretStr = Field(
        min_length=1,
        validation_alias="GEMINI_API_KEY",
        repr=False,
    )
    timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=600,
        validation_alias="GEMINI_TIMEOUT_SECONDS",
    )
    retry_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        validation_alias="GEMINI_RETRY_ATTEMPTS",
    )
    retry_initial_delay_seconds: float = Field(
        default=1.0,
        ge=0,
        le=60,
        validation_alias="GEMINI_RETRY_INITIAL_DELAY_SECONDS",
    )
    retry_max_delay_seconds: float = Field(
        default=8.0,
        ge=0,
        le=120,
        validation_alias="GEMINI_RETRY_MAX_DELAY_SECONDS",
    )

    @model_validator(mode="after")
    def validate_retry_delays(self) -> "GeminiSettings":
        if self.retry_max_delay_seconds < self.retry_initial_delay_seconds:
            raise ValueError(
                "maximum retry delay must not be less than initial delay"
            )
        return self

    @classmethod
    def from_env(cls) -> "GeminiSettings":
        """Load settings without exposing Pydantic input details on failure."""

        try:
            return cls()
        except ValidationError:
            raise ConfigurationError(
                "Gemini configuration is missing or invalid; check the "
                "documented environment variables."
            ) from None
