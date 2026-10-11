"""Secure client for the pinned Gemini model."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import errors, types

from .caching import PromptCache
from .config import GeminiSettings
from .errors import (
    AuthenticationError,
    AuthorizationError,
    GeminiConnectionError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    InvalidInputError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
)
from .models import GenerationResult, ModelInfo

LOGGER = logging.getLogger(__name__)

MODEL_ID = "gemini-3.5-flash-lite"
RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]

TIMEOUT_MESSAGE = "The Gemini request timed out after the configured retries."

# HTTP status -> (error raised, sanitized message). Any 5xx not listed here
# is a service error and any other status is a rejected request.
STATUS_ERRORS: dict[int, tuple[type[Exception], str]] = {
    401: (
        AuthenticationError,
        "Gemini authentication failed; check GEMINI_API_KEY.",
    ),
    403: (
        AuthorizationError,
        "The configured credentials cannot access the requested Gemini "
        "model.",
    ),
    404: (
        ModelUnavailableError,
        f"The required model {MODEL_ID} is unavailable; no fallback was "
        "used.",
    ),
    408: (GeminiTimeoutError, TIMEOUT_MESSAGE),
    429: (
        RateLimitError,
        "Gemini rate limits were exceeded after the configured retries.",
    ),
}
SERVICE_ERROR = (
    GeminiServiceError,
    "Gemini failed after the configured retries.",
)
REQUEST_ERROR = (
    GeminiRequestError,
    "Gemini rejected the request; provider details were omitted.",
)

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
        self._cache = PromptCache(
            self._sdk_client,
            MODEL_ID,
            ttl_seconds=settings.cache_ttl_seconds,
        )

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
            self._cache.delete()
            self._sdk_client.close()
            self._closed = True

    def check_connection(self) -> ModelInfo:
        """Validate authentication and availability without generating."""

        self._ensure_open()
        model = self._call(
            lambda: self._sdk_client.models.get(model=MODEL_ID),
        )
        provider_name = self._require_matching_model(
            getattr(model, "name", None)
        )
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

    def generate_text(self, prompt: str) -> GenerationResult:
        """Send caller-provided text to the pinned model, validate answer."""

        self._ensure_open()
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvalidInputError("The prompt must contain text.")

        response = self._call(
            lambda: self._sdk_client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
            ),
        )
        return self._validated_result(response)

    def generate_with_system_instruction(
        self,
        system_instruction: str,
        content: str,
        response_schema: Any = None,
        response_mime_type: str | None = None,
    ) -> GenerationResult:
        """Send content with a cached system instruction.

        The ``system_instruction`` is cached on the first call and
        reused in subsequent calls within the TTL, avoiding
        retokenization and reducing input costs.  If caching fails
        (e.g. below the model's minimum token count), the system
        instruction is sent inline as a fallback.
        """
        self._ensure_open()
        if not isinstance(system_instruction, str) or \
                not system_instruction.strip():
            raise InvalidInputError(
                "The system instruction must contain text."
            )
        if not isinstance(content, str) or not content.strip():
            raise InvalidInputError("The content must contain text.")

        mime_type = response_mime_type or (
            "application/json" if response_schema else None
        )
        cache_name = self._cache.ensure(system_instruction)

        if cache_name:
            LOGGER.debug("A usar cache %s para a chamada.", cache_name)
            response = self._call(
                lambda: self._sdk_client.models.generate_content(
                    model=MODEL_ID,
                    contents=content,
                    config=types.GenerateContentConfig(
                        cached_content=cache_name,
                        response_mime_type=mime_type,
                        response_schema=response_schema,
                    ),
                ),
            )
        else:
            LOGGER.debug(
                "Cache indisponível; a enviar a instrução de sistema "
                "inline."
            )
            response = self._call(
                lambda: self._sdk_client.models.generate_content(
                    model=MODEL_ID,
                    contents=content,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type=mime_type,
                        response_schema=response_schema,
                    ),
                ),
            )

        return self._validated_result(response)

    def _validated_result(self, response: Any) -> GenerationResult:
        """Extract and validate the text from a Gemini response."""
        try:
            text = response.text
            provider_model = getattr(response, "model_version", None)
        except Exception:
            raise ResponseValidationError(
                "Gemini returned an invalid text response."
            ) from None

        if provider_model is not None:
            self._require_matching_model(provider_model)
        if not isinstance(text, str) or not text.strip():
            raise ResponseValidationError(
                "Gemini returned an invalid text response."
            )
        return GenerationResult(model=MODEL_ID, text=text)

    def _call(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except errors.APIError as exc:
            self._raise_api_error(exc.code)
        except (httpx.TimeoutException, TimeoutError):
            raise GeminiTimeoutError(TIMEOUT_MESSAGE) from None
        except httpx.TransportError:
            raise GeminiConnectionError(
                "The Gemini service could not be reached after the "
                "configured retries."
            ) from None
        raise AssertionError("unreachable")

    @staticmethod
    def _raise_api_error(status_code: int) -> None:
        if status_code in STATUS_ERRORS:
            error_class, message = STATUS_ERRORS[status_code]
        elif 500 <= status_code < 600:
            error_class, message = SERVICE_ERROR
        else:
            error_class, message = REQUEST_ERROR
        raise error_class(message) from None

    @staticmethod
    def _optional_nonnegative_int(value: Any, label: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ResponseValidationError(
                f"Gemini returned invalid {label} metadata."
            )
        return value

    @staticmethod
    def _require_matching_model(provider_name: Any) -> str:
        if not isinstance(provider_name, str) or not provider_name:
            raise ResponseValidationError(
                "Gemini returned no model identity metadata."
            )
        normalized = provider_name.removeprefix("models/")
        if normalized != MODEL_ID:
            raise ModelMismatchError(
                f"Gemini reported a model other than required model "
                f"{MODEL_ID}; no fallback was used."
            )
        return provider_name

    def _ensure_open(self) -> None:
        if self._closed:
            raise GeminiConnectionError("The Gemini client is closed.")
