"""Public content and detection models."""

from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class StrictModel(BaseModel):
    """Base model that rejects unexpected fields and mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TextBlock(StrictModel):
    """Text plus opaque provenance produced by a source adapter."""

    block_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, repr=False)
    metadata: Mapping[str, JsonValue] = Field(default_factory=dict, repr=False)

    @field_validator("block_id")
    @classmethod
    def validate_block_id(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError(
                "block_id must be trimmed and contain no control characters"
            )
        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain non-whitespace content")
        return value


class EntityCategory(str, Enum):
    """Stable categories used by detection and future redaction."""

    PERSON_NAME = "person_name"
    DATE_OF_BIRTH = "date_of_birth"
    PHONE_NUMBER = "phone_number"
    EMAIL_ADDRESS = "email_address"
    POSTAL_ADDRESS = "postal_address"
    PRECISE_LOCATION = "precise_location"
    NATIONAL_ID = "national_id"
    TAX_ID = "tax_id"
    SOCIAL_SECURITY_ID = "social_security_id"
    PASSPORT_ID = "passport_id"
    DRIVER_LICENSE_ID = "driver_license_id"
    HEALTHCARE_ID = "healthcare_id"
    FINANCIAL_ACCOUNT = "financial_account"
    PAYMENT_CARD = "payment_card"
    VEHICLE_ID = "vehicle_id"
    ONLINE_IDENTIFIER = "online_identifier"
    AUTHENTICATION_SECRET = "authentication_secret"
    OTHER_PERSONAL_IDENTIFIER = "other_personal_identifier"


class SensitiveEntity(StrictModel):
    """A verified, redaction-ready span within a text block."""

    block_id: str = Field(min_length=1, max_length=200)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text: str = Field(min_length=1, repr=False)
    category: EntityCategory
    reason: str = Field(min_length=1, max_length=240)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must contain non-whitespace content")
        return value


class SensitiveEntityResponse(StrictModel):
    """Schema requested from Gemini before local semantic validation."""

    entities: tuple[SensitiveEntity, ...]


class TokenUsage(StrictModel):
    """Token consumption reported for a completed detection call."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    thought_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class DetectionResult(StrictModel):
    """Validated detection output and its operational metadata."""

    model: str
    entities: tuple[SensitiveEntity, ...]
    usage: TokenUsage


class ModelInfo(StrictModel):
    """Safe metadata returned by the connection check."""

    requested_model: str
    provider_name: str
    input_token_limit: int | None = Field(default=None, ge=0)
    output_token_limit: int | None = Field(default=None, ge=0)
