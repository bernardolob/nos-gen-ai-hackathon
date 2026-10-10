import pytest

from gemini import (
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
from gemini.client import (
    REQUEST_ERROR,
    SERVICE_ERROR,
    STATUS_ERRORS,
    TIMEOUT_MESSAGE,
)

UNAVAILABLE = [
    AuthenticationError,
    AuthorizationError,
    ModelUnavailableError,
    RateLimitError,
    GeminiTimeoutError,
    GeminiConnectionError,
    GeminiServiceError,
]
BAD_RESPONSE = [ModelMismatchError, ResponseValidationError]


@pytest.mark.parametrize("error", UNAVAILABLE)
def test_unavailable_group(error):
    assert issubclass(error, UnavailableError)
    assert issubclass(error, UpstreamError)
    assert not issubclass(error, BadResponseError)


@pytest.mark.parametrize("error", BAD_RESPONSE)
def test_bad_response_group(error):
    assert issubclass(error, BadResponseError)
    assert issubclass(error, UpstreamError)
    assert not issubclass(error, UnavailableError)


def test_request_error_is_upstream_but_in_no_subgroup():
    assert issubclass(GeminiRequestError, UpstreamError)
    assert not issubclass(GeminiRequestError, UnavailableError)
    assert not issubclass(GeminiRequestError, BadResponseError)


@pytest.mark.parametrize("error", [ConfigurationError, InvalidInputError])
def test_local_errors_are_not_upstream(error):
    assert issubclass(error, GeminiIntegrationError)
    assert not issubclass(error, UpstreamError)


def test_every_error_is_an_integration_error():
    for error in UNAVAILABLE + BAD_RESPONSE + [GeminiRequestError]:
        assert issubclass(error, GeminiIntegrationError)


def test_status_table_maps_to_the_expected_errors():
    assert {code: cls for code, (cls, _) in STATUS_ERRORS.items()} == {
        401: AuthenticationError,
        403: AuthorizationError,
        404: ModelUnavailableError,
        408: GeminiTimeoutError,
        429: RateLimitError,
    }
    assert SERVICE_ERROR[0] is GeminiServiceError
    assert REQUEST_ERROR[0] is GeminiRequestError


def test_timeout_message_is_shared():
    assert STATUS_ERRORS[408][1] == TIMEOUT_MESSAGE
