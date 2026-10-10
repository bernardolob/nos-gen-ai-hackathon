from unittest.mock import Mock, patch

import httpx
import pytest
from google.genai import errors

from nos_anonymizer import (
    MODEL_ID,
    AuthenticationError,
    AuthorizationError,
    GeminiClient,
    GeminiConnectionError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
)
from nos_anonymizer.client import RETRYABLE_STATUS_CODES


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
    assert info.output_token_limit == 65_536


def test_connection_check_rejects_model_mismatch(settings, fake_sdk):
    fake_sdk.models.get_result.name = "models/gemini-3.6-flash"
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(ModelMismatchError, match="no fallback"):
        client.check_connection()


def test_connection_check_requires_model_identity(settings, fake_sdk):
    fake_sdk.models.get_result.name = None
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(ResponseValidationError, match="model identity"):
        client.check_connection()


@pytest.mark.parametrize("value", [-1, True, "100"])
def test_connection_check_validates_model_limits(settings, fake_sdk, value):
    fake_sdk.models.get_result.input_token_limit = value
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(ResponseValidationError, match="input token limit"):
        client.check_connection()


def test_connection_check_allows_missing_model_limits(settings, fake_sdk):
    fake_sdk.models.get_result.input_token_limit = None
    fake_sdk.models.get_result.output_token_limit = None
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    info = client.check_connection()

    assert info.input_token_limit is None
    assert info.output_token_limit is None


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
    status,
    expected,
):
    provider_message = "provider included unit-test-key and private content"
    fake_sdk.models.get_error = errors.APIError(
        status,
        {"message": provider_message, "status": "FAILED"},
    )
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(expected) as caught:
        client.check_connection()

    assert "unit-test-key" not in str(caught.value)
    assert "private content" not in str(caught.value)


@pytest.mark.parametrize(
    ("transport_error", "expected"),
    [
        (httpx.ReadTimeout("private content"), GeminiTimeoutError),
        (httpx.ConnectError("private content"), GeminiConnectionError),
    ],
)
def test_transport_errors_are_sanitized(
    settings,
    fake_sdk,
    transport_error,
    expected,
):
    fake_sdk.models.get_error = transport_error
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(expected) as caught:
        client.check_connection()

    assert "private content" not in str(caught.value)


def test_context_manager_closes_once_and_closed_client_fails(settings, fake_sdk):
    with GeminiClient(settings, _sdk_client=fake_sdk) as client:
        assert client.check_connection()
    client.close()

    assert fake_sdk.close_calls == 1
    with pytest.raises(GeminiConnectionError, match="closed"):
        client.check_connection()
