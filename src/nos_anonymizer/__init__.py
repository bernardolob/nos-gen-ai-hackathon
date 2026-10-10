"""Secure sensitive-entity detection powered by Google Gemini."""

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
    InvalidInputError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
)
from .models import (
    DetectionResult,
    EntityCategory,
    ModelInfo,
    SensitiveEntity,
    TextBlock,
    TokenUsage,
)

__all__ = [
    "MODEL_ID",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "DetectionResult",
    "EntityCategory",
    "GeminiClient",
    "GeminiConnectionError",
    "GeminiIntegrationError",
    "GeminiRequestError",
    "GeminiServiceError",
    "GeminiSettings",
    "GeminiTimeoutError",
    "InvalidInputError",
    "ModelInfo",
    "ModelMismatchError",
    "ModelUnavailableError",
    "RateLimitError",
    "ResponseValidationError",
    "SensitiveEntity",
    "TextBlock",
    "TokenUsage",
]
