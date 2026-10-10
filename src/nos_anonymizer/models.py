"""Validated metadata returned by the Gemini connection check."""

from pydantic import BaseModel, ConfigDict, Field


class ModelInfo(BaseModel):
    """Safe metadata returned by the connection check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_model: str
    provider_name: str
    input_token_limit: int | None = Field(default=None, ge=0)
    output_token_limit: int | None = Field(default=None, ge=0)
