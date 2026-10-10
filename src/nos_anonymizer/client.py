"""Secure Gemini client for validated sensitive-entity detection."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

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
from .models import (
    DetectionResult,
    ModelInfo,
    SensitiveEntity,
    SensitiveEntityResponse,
    TextBlock,
    TokenUsage,
)
from .prompting import SYSTEM_INSTRUCTION, build_detection_input

MODEL_ID = "gemini-3.5-flash"
RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]

T = TypeVar("T")


class GeminiClient:
    """Synchronous, stateless integration with the pinned Gemini model."""

    def __init__(
        self,
        settings: GeminiSettings,
        *,
        _sdk_client: Any | None = None,
    ) -> None:
        self._settings = settings
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

    def count_tokens(self, blocks: Sequence[TextBlock]) -> int:
        """Count tokens for the exact system instruction and serialized blocks."""

        self._ensure_open()
        normalized = self._normalize_blocks(blocks)
        response = self._call(
            lambda: self._sdk_client.models.count_tokens(
                model=MODEL_ID,
                contents=build_detection_input(normalized),
                config=types.CountTokensConfig(system_instruction=SYSTEM_INSTRUCTION),
            ),
        )
        return self._required_nonnegative_int(
            getattr(response, "total_tokens", None),
            "token count",
        )

    def detect_sensitive_entities(
        self,
        blocks: Sequence[TextBlock],
    ) -> DetectionResult:
        """Detect and locally validate sensitive spans in text blocks."""

        self._ensure_open()
        normalized = self._normalize_blocks(blocks)
        interaction = self._call(
            lambda: self._sdk_client.interactions.create(
                model=MODEL_ID,
                input=build_detection_input(normalized),
                store=False,
                system_instruction=SYSTEM_INSTRUCTION,
                generation_config={"thinking_level": "medium"},
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": SensitiveEntityResponse.model_json_schema(),
                },
                timeout=self._settings.timeout_seconds,
            ),
        )

        if getattr(interaction, "status", None) != "completed":
            raise ResponseValidationError(
                "Gemini did not return a completed detection response."
            )
        returned_model = getattr(interaction, "model", None)
        if returned_model is not None:
            self._require_matching_model(returned_model)

        output_text = getattr(interaction, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ResponseValidationError(
                "Gemini returned no structured detection data."
            )

        try:
            response = SensitiveEntityResponse.model_validate_json(output_text)
        except (ValidationError, ValueError):
            raise ResponseValidationError(
                "Gemini returned an invalid structured detection response."
            ) from None

        entities = self._validate_entities(response.entities, normalized)
        usage = self._validate_usage(getattr(interaction, "usage", None))
        return DetectionResult(model=MODEL_ID, entities=entities, usage=usage)

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
                "Gemini rejected the request; no source data was included "
                "in this error."
            )
        raise error from None

    @staticmethod
    def _normalize_blocks(blocks: Sequence[TextBlock]) -> tuple[TextBlock, ...]:
        try:
            normalized = tuple(blocks)
        except TypeError:
            raise InvalidInputError(
                "blocks must be a sequence of TextBlock values."
            ) from None
        if not normalized:
            raise InvalidInputError("At least one text block is required.")
        if any(not isinstance(block, TextBlock) for block in normalized):
            raise InvalidInputError("Every item must be a TextBlock.")
        block_ids = [block.block_id for block in normalized]
        if len(block_ids) != len(set(block_ids)):
            raise InvalidInputError("Text block IDs must be unique.")
        return normalized

    @classmethod
    def _validate_entities(
        cls,
        entities: tuple[SensitiveEntity, ...],
        blocks: tuple[TextBlock, ...],
    ) -> tuple[SensitiveEntity, ...]:
        block_map = {block.block_id: block for block in blocks}
        block_order = {block.block_id: index for index, block in enumerate(blocks)}

        for entity in entities:
            block = block_map.get(entity.block_id)
            if block is None:
                raise ResponseValidationError(
                    "Gemini referenced an unknown text block."
                )
            if entity.start_char >= entity.end_char or entity.end_char > len(
                block.text
            ):
                raise ResponseValidationError("Gemini returned an invalid entity span.")
            if block.text[entity.start_char : entity.end_char] != entity.text:
                raise ResponseValidationError(
                    "Gemini returned an entity that does not match its source span."
                )

        ordered = tuple(
            sorted(
                entities,
                key=lambda item: (
                    block_order[item.block_id],
                    item.start_char,
                    item.end_char,
                    item.category.value,
                ),
            )
        )
        previous_by_block: dict[str, SensitiveEntity] = {}
        for entity in ordered:
            previous = previous_by_block.get(entity.block_id)
            if previous is not None and entity.start_char < previous.end_char:
                raise ResponseValidationError(
                    "Gemini returned duplicate or overlapping entity spans."
                )
            previous_by_block[entity.block_id] = entity
        return ordered

    @classmethod
    def _validate_usage(cls, usage: Any) -> TokenUsage:
        if usage is None:
            raise ResponseValidationError("Gemini returned no token usage metadata.")
        return TokenUsage(
            input_tokens=cls._required_nonnegative_int(
                getattr(usage, "total_input_tokens", None),
                "input token usage",
            ),
            output_tokens=cls._required_nonnegative_int(
                getattr(usage, "total_output_tokens", None),
                "output token usage",
            ),
            thought_tokens=cls._optional_nonnegative_int(
                getattr(usage, "total_thought_tokens", None),
                "thought token usage",
            )
            or 0,
            total_tokens=cls._required_nonnegative_int(
                getattr(usage, "total_tokens", None),
                "total token usage",
            ),
        )

    @staticmethod
    def _required_nonnegative_int(value: Any, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ResponseValidationError(f"Gemini returned invalid {label} metadata.")
        return value

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
