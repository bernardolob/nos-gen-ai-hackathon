"""Validated domain models returned by the Gemini integration."""

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Immutable base model that rejects unexpected provider fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelInfo(StrictModel):
    """Safe metadata returned by the connection check."""

    requested_model: str
    provider_name: str
    input_token_limit: int | None = Field(default=None, ge=0)
    output_token_limit: int | None = Field(default=None, ge=0)


class GenerationResult(StrictModel):
    """Validated text returned from the pinned Gemini model."""

    model: str
    text: str = Field(min_length=1, repr=False)
