"""Secure connection verification for Google Gemini."""

from .client import MODEL_ID, GeminiClient
from .config import GeminiSettings
from .errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    GeminiConnectionError,
    GeminiIntegrationError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
)
from .models import ModelInfo

__all__ = [
    "MODEL_ID",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "GeminiClient",
    "GeminiConnectionError",
    "GeminiIntegrationError",
    "GeminiRequestError",
    "GeminiServiceError",
    "GeminiSettings",
    "GeminiTimeoutError",
    "ModelInfo",
    "ModelMismatchError",
    "ModelUnavailableError",
    "RateLimitError",
    "ResponseValidationError",
]
