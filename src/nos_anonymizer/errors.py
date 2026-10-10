"""Sanitized domain exceptions for the Gemini integration."""


class GeminiIntegrationError(Exception):
    """Base class for errors safe to show to an operator."""


class ConfigurationError(GeminiIntegrationError):
    """Raised when required configuration is missing or invalid."""


class AuthenticationError(GeminiIntegrationError):
    """Raised when the configured API key is not accepted."""


class AuthorizationError(GeminiIntegrationError):
    """Raised when the caller lacks permission for the requested operation."""


class ModelUnavailableError(GeminiIntegrationError):
    """Raised when the pinned model cannot be used."""


class ModelMismatchError(GeminiIntegrationError):
    """Raised when the provider reports a model other than the pinned model."""


class RateLimitError(GeminiIntegrationError):
    """Raised after retryable quota or rate-limit responses are exhausted."""


class GeminiTimeoutError(GeminiIntegrationError):
    """Raised after a request exceeds its configured timeout."""


class GeminiConnectionError(GeminiIntegrationError):
    """Raised when the Gemini service cannot be reached."""


class GeminiServiceError(GeminiIntegrationError):
    """Raised after retryable server failures are exhausted."""


class GeminiRequestError(GeminiIntegrationError):
    """Raised for a non-retryable request rejected by Gemini."""


class ResponseValidationError(GeminiIntegrationError):
    """Raised when a response is structurally or semantically invalid."""
