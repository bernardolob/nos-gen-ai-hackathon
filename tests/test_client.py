import json
from unittest.mock import Mock, patch

import httpx
import pytest
from google.genai import errors

from nos_anonymizer import (
    MODEL_ID,
    AuthenticationError,
    AuthorizationError,
    EntityCategory,
    GeminiClient,
    GeminiConnectionError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    InvalidInputError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
    TextBlock,
)
from nos_anonymizer.client import RETRYABLE_STATUS_CODES

from conftest import completed_interaction


def entity(block_id="page:1", start=0, end=4, text="José", category="person_name"):
    return {
        "block_id": block_id,
        "start_char": start,
        "end_char": end,
        "text": text,
        "category": category,
        "reason": "Direct personal identifier",
    }


def test_sdk_client_configuration(settings):
    sdk = Mock()
    with patch("nos_anonymizer.client.genai.Client", return_value=sdk) as constructor:
        result = GeminiClient._create_sdk_client(settings)

    assert result is sdk
    kwargs = constructor.call_args.kwargs
    assert kwargs["enterprise"] is False
    assert kwargs["api_key"] == "unit-test-key"
    options = kwargs["http_options"]
    assert options.timeout == 60_000
    assert options.retry_options.attempts == 3
    assert options.retry_options.http_status_codes == RETRYABLE_STATUS_CODES


def test_connection_check_uses_exact_model(settings, fake_sdk):
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    info = client.check_connection()

    assert fake_sdk.models.get_calls == [{"model": MODEL_ID}]
    assert info.requested_model == MODEL_ID
    assert info.provider_name == f"models/{MODEL_ID}"
    assert info.input_token_limit == 1_048_576


def test_connection_check_rejects_model_mismatch(settings, fake_sdk):
    fake_sdk.models.get_result.name = "models/gemini-3.6-flash"
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(ModelMismatchError, match="no fallback"):
        client.check_connection()


def test_count_tokens_uses_exact_payload(settings, fake_sdk, blocks):
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    total = client.count_tokens(blocks)

    assert total == 42
    call = fake_sdk.models.count_calls[0]
    assert call["model"] == MODEL_ID
    assert "secret_adapter_note" not in call["contents"]
    assert call["config"].system_instruction


def test_detection_is_stateless_structured_and_redaction_ready(
    settings,
    fake_sdk,
    blocks,
):
    fake_sdk.interactions.result = completed_interaction(
        [
            entity(
                start=6,
                end=22,
                text="+351 912 345 678",
                category="phone_number",
            ),
            entity(),
        ]
    )
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    result = client.detect_sensitive_entities(blocks)

    call = fake_sdk.interactions.calls[0]
    assert call["model"] == MODEL_ID
    assert call["store"] is False
    assert call["generation_config"] == {"thinking_level": "medium"}
    assert call["response_format"]["mime_type"] == "application/json"
    assert "secret_adapter_note" not in call["input"]
    assert [item.category for item in result.entities] == [
        EntityCategory.PERSON_NAME,
        EntityCategory.PHONE_NUMBER,
    ]
    assert result.entities[0].text == "José"
    assert result.usage.input_tokens == 20
    assert result.usage.thought_tokens == 0


def test_detection_accepts_empty_entity_list(settings, fake_sdk, blocks):
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    result = client.detect_sensitive_entities(blocks)

    assert result.entities == ()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "failed"}, "completed"),
        ({"model": "gemini-3.6-flash"}, "no fallback"),
        ({"model": None}, None),
        ({"output_text": ""}, "structured"),
        ({"output_text": "not-json"}, "invalid structured"),
        ({"output_text": "{}"}, "invalid structured"),
        ({"output_text": json.dumps({"entities": [], "extra": 1})}, "invalid"),
        ({"usage": None}, "usage"),
    ],
)
def test_detection_rejects_invalid_interaction(
    settings,
    fake_sdk,
    blocks,
    overrides,
    message,
):
    fake_sdk.interactions.result = completed_interaction(**overrides)
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    if overrides == {"model": None}:
        result = client.detect_sensitive_entities(blocks)
        assert result.model == MODEL_ID
    else:
        with pytest.raises(
            (ResponseValidationError, ModelMismatchError), match=message
        ):
            client.detect_sensitive_entities(blocks)


@pytest.mark.parametrize(
    "bad_entity",
    [
        entity(block_id="missing"),
        entity(start=4, end=4, text=""),
        entity(start=0, end=100, text="José"),
        entity(start=0, end=4, text="João"),
        {**entity(), "category": "unknown"},
    ],
)
def test_detection_rejects_invalid_entities(settings, fake_sdk, blocks, bad_entity):
    fake_sdk.interactions.result = completed_interaction([bad_entity])
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(ResponseValidationError):
        client.detect_sensitive_entities(blocks)


def test_detection_rejects_overlapping_entities(settings, fake_sdk, blocks):
    fake_sdk.interactions.result = completed_interaction(
        [entity(), entity(start=1, end=4, text="osé")]
    )
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(ResponseValidationError, match="overlapping"):
        client.detect_sensitive_entities(blocks)


@pytest.mark.parametrize(
    "bad_blocks",
    [(), ("not-a-block",)],
)
def test_client_rejects_invalid_block_sequences(settings, fake_sdk, bad_blocks):
    client = GeminiClient(settings, _sdk_client=fake_sdk)
    with pytest.raises(InvalidInputError):
        client.count_tokens(bad_blocks)


def test_client_rejects_duplicate_block_ids(settings, fake_sdk):
    blocks = (
        TextBlock(block_id="same", text="one"),
        TextBlock(block_id="same", text="two"),
    )
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(InvalidInputError, match="unique"):
        client.count_tokens(blocks)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthenticationError),
        (403, AuthorizationError),
        (404, ModelUnavailableError),
        (408, GeminiTimeoutError),
        (429, RateLimitError),
        (500, GeminiServiceError),
        (400, GeminiRequestError),
    ],
)
def test_api_errors_are_mapped_and_sanitized(
    settings,
    fake_sdk,
    blocks,
    status,
    expected,
):
    secret_provider_message = "provider included unit-test-key and private source"
    fake_sdk.models.count_error = errors.APIError(
        status,
        {"message": secret_provider_message, "status": "FAILED"},
    )
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(expected) as caught:
        client.count_tokens(blocks)

    assert "unit-test-key" not in str(caught.value)
    assert "private source" not in str(caught.value)


@pytest.mark.parametrize(
    ("transport_error", "expected"),
    [
        (httpx.ReadTimeout("private source"), GeminiTimeoutError),
        (httpx.ConnectError("private source"), GeminiConnectionError),
    ],
)
def test_transport_errors_are_sanitized(
    settings,
    fake_sdk,
    blocks,
    transport_error,
    expected,
):
    fake_sdk.models.count_error = transport_error
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(expected) as caught:
        client.count_tokens(blocks)

    assert "private source" not in str(caught.value)


def test_usage_metadata_must_be_nonnegative_integers(settings, fake_sdk, blocks):
    fake_sdk.interactions.result.usage.total_tokens = True
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(ResponseValidationError, match="total token"):
        client.detect_sensitive_entities(blocks)


def test_context_manager_closes_once_and_closed_client_fails(settings, fake_sdk):
    with GeminiClient(settings, _sdk_client=fake_sdk) as client:
        assert client.check_connection()
    client.close()

    assert fake_sdk.close_calls == 1
    with pytest.raises(GeminiConnectionError, match="closed"):
        client.check_connection()
