"""Secure Gemini client for connection verification."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import errors, types

from .config import GeminiSettings
from .errors import (
    AuthenticationError,
    AuthorizationError,
    GeminiConnectionError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
)
from .models import ModelInfo

MODEL_ID = "gemini-3.5-flash"
RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]

T = TypeVar("T")


class GeminiClient:
    """Synchronous client that verifies access to the pinned Gemini model."""

    def __init__(
        self,
        settings: GeminiSettings,
        *,
        _sdk_client: Any | None = None,
    ) -> None:
        self._closed = False
        self._sdk_client = _sdk_client or self._create_sdk_client(settings)

    @staticmethod
    def _create_sdk_client(settings: GeminiSettings) -> genai.Client:
        retry_options = types.HttpRetryOptions(
            attempts=settings.retry_attempts,
            initial_delay=settings.retry_initial_delay_seconds,
            max_delay=settings.retry_max_delay_seconds,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=RETRYABLE_STATUS_CODES,
        )
        http_options = types.HttpOptions(
            timeout=round(settings.timeout_seconds * 1000),
            retry_options=retry_options,
        )
        return genai.Client(
            enterprise=False,
            api_key=settings.api_key.get_secret_value(),
            http_options=http_options,
        )

    def __enter__(self) -> GeminiClient:
        self._ensure_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Release HTTP resources; repeated calls are harmless."""

        if not self._closed:
            self._sdk_client.close()
            self._closed = True

    def check_connection(self) -> ModelInfo:
        """Validate authentication and availability without generating content."""

        self._ensure_open()
        model = self._call(
            lambda: self._sdk_client.models.get(model=MODEL_ID),
        )
        provider_name = self._require_matching_model(getattr(model, "name", None))
        return ModelInfo(
            requested_model=MODEL_ID,
            provider_name=provider_name,
            input_token_limit=self._optional_nonnegative_int(
                getattr(model, "input_token_limit", None),
                "input token limit",
            ),
            output_token_limit=self._optional_nonnegative_int(
                getattr(model, "output_token_limit", None),
                "output token limit",
            ),
        )

    def _call(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except errors.APIError as exc:
            self._raise_api_error(exc.code)
        except (httpx.TimeoutException, TimeoutError):
            raise GeminiTimeoutError(
                "The Gemini request timed out after the configured retries."
            ) from None
        except httpx.TransportError:
            raise GeminiConnectionError(
                "The Gemini service could not be reached after the configured retries."
            ) from None
        raise AssertionError("unreachable")

    @staticmethod
    def _raise_api_error(status_code: int) -> None:
        if status_code == 401:
            error = AuthenticationError(
                "Gemini authentication failed; check GEMINI_API_KEY."
            )
        elif status_code == 403:
            error = AuthorizationError(
                "The configured credentials cannot access the requested Gemini model."
            )
        elif status_code == 404:
            error = ModelUnavailableError(
                f"The required model {MODEL_ID} is unavailable; no fallback was used."
            )
        elif status_code == 408:
            error = GeminiTimeoutError(
                "The Gemini request timed out after the configured retries."
            )
        elif status_code == 429:
            error = RateLimitError(
                "Gemini rate limits were exceeded after the configured retries."
            )
        elif 500 <= status_code < 600:
            error = GeminiServiceError("Gemini failed after the configured retries.")
        else:
            error = GeminiRequestError(
                "Gemini rejected the request; provider details were omitted."
            )
        raise error from None

    @staticmethod
    def _optional_nonnegative_int(value: Any, label: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ResponseValidationError(f"Gemini returned invalid {label} metadata.")
        return value

    @staticmethod
    def _require_matching_model(provider_name: Any) -> str:
        if not isinstance(provider_name, str) or not provider_name:
            raise ResponseValidationError("Gemini returned no model identity metadata.")
        normalized = provider_name.removeprefix("models/")
        if normalized != MODEL_ID:
            raise ModelMismatchError(
                f"Gemini reported a model other than required model {MODEL_ID}; "
                "no fallback was used."
            )
        return provider_name

    def _ensure_open(self) -> None:
        if self._closed:
            raise GeminiConnectionError("The Gemini client is closed.")
