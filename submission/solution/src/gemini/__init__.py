"""Secure connection to Google Gemini (pinned model, sanitized errors)."""

from .client import MODEL_ID, GeminiClient
from .config import EnvSettings, GeminiSettings
from .errors import (
    AuthenticationError,
    AuthorizationError,
    BadResponseError,
    ConfigurationError,
    GeminiConnectionError,
    GeminiIntegrationError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    InvalidInputError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
    UnavailableError,
    UpstreamError,
)
from .models import GenerationResult, ModelInfo, StrictModel

__all__ = [
    "MODEL_ID",
    "AuthenticationError",
    "AuthorizationError",
    "BadResponseError",
    "ConfigurationError",
    "EnvSettings",
    "GeminiClient",
    "GeminiConnectionError",
    "GeminiIntegrationError",
    "GeminiRequestError",
    "GeminiServiceError",
    "GeminiSettings",
    "GeminiTimeoutError",
    "GenerationResult",
    "InvalidInputError",
    "ModelInfo",
    "ModelMismatchError",
    "ModelUnavailableError",
    "RateLimitError",
    "ResponseValidationError",
    "StrictModel",
    "UnavailableError",
    "UpstreamError",
]
