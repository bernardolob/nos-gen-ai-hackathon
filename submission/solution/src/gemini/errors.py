"""Sanitized domain exceptions for the Gemini integration.

The hierarchy groups the failures by what a caller can do about them, so the
callers (CLI, HTTP API) catch a group instead of repeating long lists:

    GeminiIntegrationError
    +-- ConfigurationError          missing or invalid configuration
    +-- InvalidInputError           bad input, rejected before any request
    +-- UpstreamError               anything that goes wrong with Gemini
        +-- UnavailableError        cannot be used now; try again later
        |   +-- AuthenticationError, AuthorizationError,
        |       ModelUnavailableError, RateLimitError,
        |       GeminiTimeoutError, GeminiConnectionError,
        |       GeminiServiceError
        +-- BadResponseError        answered with something unusable
        |   +-- ModelMismatchError, ResponseValidationError
        +-- GeminiRequestError      the request itself was rejected
"""


class GeminiIntegrationError(Exception):
    """Base class for errors safe to show to an operator."""


class ConfigurationError(GeminiIntegrationError):
    """Raised when required configuration is missing or invalid."""


class InvalidInputError(GeminiIntegrationError):
    """Raised before Gemini is called when caller input is invalid."""


class UpstreamError(GeminiIntegrationError):
    """Base class for failures that involve the Gemini service."""


class UnavailableError(UpstreamError):
    """Gemini cannot be used right now; the caller may try again later."""


class BadResponseError(UpstreamError):
    """Gemini answered, but the answer cannot be trusted or used."""


class AuthenticationError(UnavailableError):
    """Raised when the configured API key is not accepted."""


class AuthorizationError(UnavailableError):
    """Raised when the caller lacks permission for the requested operation."""


class ModelUnavailableError(UnavailableError):
    """Raised when the pinned model cannot be used."""


class RateLimitError(UnavailableError):
    """Raised after retryable quota or rate-limit responses are exhausted."""


class GeminiTimeoutError(UnavailableError):
    """Raised after a request exceeds its configured timeout."""


class GeminiConnectionError(UnavailableError):
    """Raised when the Gemini service cannot be reached."""


class GeminiServiceError(UnavailableError):
    """Raised after retryable server failures are exhausted."""


class ModelMismatchError(BadResponseError):
    """Raised when the provider reports a model other than the pinned model."""


class ResponseValidationError(BadResponseError):
    """Raised when a response is structurally or semantically invalid."""


class GeminiRequestError(UpstreamError):
    """Raised for a non-retryable request rejected by Gemini."""
