import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gemini import (
    MODEL_ID,
    AuthenticationError,
    AuthorizationError,
    GenerationResult,
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
from api.app import create_app, get_gemini_client
from api.settings import ApiSettings

TOKEN = "backend-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeGeminiClient:
    def __init__(self):
        self.check_calls = 0
        self.generate_calls = []
        self.close_calls = 0
        self.check_error = None
        self.generate_error = None

    def check_connection(self):
        self.check_calls += 1
        if self.check_error:
            raise self.check_error
        return object()

    def generate_text(self, prompt):
        self.generate_calls.append(prompt)
        if self.generate_error:
            raise self.generate_error
        return GenerationResult(model=MODEL_ID, text="Hi from Gemini!")

    def close(self):
        self.close_calls += 1


def api_settings(**overrides):
    values = {
        "backend_api_token": TOKEN,
        "cors_allow_origins": "https://allowed.example",
        "max_prompt_length": 100,
        "max_request_bytes": 512,
    }
    values.update(overrides)
    return ApiSettings(**values)


@pytest.fixture
def fake_client():
    return FakeGeminiClient()


@pytest.fixture
def app(monkeypatch, fake_client):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-unit-test-key")
    return create_app(
        api_settings(),
        client_factory=lambda _settings: fake_client,
    )


def test_health_does_not_invoke_gemini(app, fake_client):
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_client.check_calls == 0
    assert fake_client.generate_calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": "Basic backend-test-token"},
    ],
)
@pytest.mark.parametrize("path", ["/ready", "/api/v1/generate"])
def test_protected_endpoints_require_valid_backend_auth(app, path, headers):
    with TestClient(app) as client:
        if path.endswith("generate"):
            response = client.post(
                path, headers=headers, json={"prompt": "hello"}
            )
        else:
            response = client.get(path, headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or missing backend credentials."
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_comparison_rejects_similar_value(app, fake_client):
    with TestClient(app) as client:
        response = client.get(
            "/ready",
            headers={"Authorization": f"Bearer {TOKEN}x"},
        )

    assert response.status_code == 401
    assert fake_client.check_calls == 0


def test_successful_readiness_response(app, fake_client):
    with TestClient(app) as client:
        response = client.get("/ready", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "model": MODEL_ID}
    assert fake_client.check_calls == 1


def test_successful_generation_response(app, fake_client):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            headers=AUTH,
            json={"prompt": "say hi"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "model": MODEL_ID,
        "text": "Hi from Gemini!",
    }
    assert fake_client.generate_calls == ["say hi"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": 123},
        {"prompt": "hello", "unexpected": True},
    ],
)
def test_invalid_generation_input_returns_sanitized_422(
    app, fake_client, payload
):
    with TestClient(app) as client:
        response = client.post("/api/v1/generate", headers=AUTH, json=payload)

    assert response.status_code == 422
    assert response.json() == {"detail": "Request validation failed."}
    assert fake_client.generate_calls == []


def test_prompt_length_limit(app, fake_client):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            headers=AUTH,
            json={"prompt": "x" * 101},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Prompt exceeds the configured limit."
    }
    assert fake_client.generate_calls == []


def test_request_byte_limit(monkeypatch, fake_client):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-unit-test-key")
    app = create_app(
        api_settings(max_request_bytes=128, max_prompt_length=1_000),
        client_factory=lambda _settings: fake_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            headers=AUTH,
            json={"prompt": "x" * 200},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request body exceeds the configured limit."
    }
    assert fake_client.generate_calls == []


def test_missing_gemini_configuration_returns_503(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = create_app(api_settings())

    with TestClient(app) as client:
        response = client.get("/ready", headers=AUTH)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Backend configuration is missing or invalid."
    }


def test_missing_backend_token_rejects_protected_access(
    monkeypatch, fake_client
):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-unit-test-key")
    app = create_app(
        ApiSettings(backend_api_token=None),
        client_factory=lambda _settings: fake_client,
    )

    with TestClient(app) as client:
        response = client.get("/ready", headers=AUTH)

    assert response.status_code == 401
    assert fake_client.check_calls == 0


@pytest.mark.parametrize(
    "error",
    [
        AuthenticationError("provider secret"),
        AuthorizationError("provider secret"),
        ModelUnavailableError("provider secret"),
        ModelMismatchError("provider secret"),
        GeminiTimeoutError("provider secret"),
        RateLimitError("provider secret"),
        GeminiConnectionError("provider secret"),
        GeminiServiceError("provider secret"),
        GeminiRequestError("provider secret"),
        ResponseValidationError("provider secret"),
    ],
)
def test_readiness_failures_are_sanitized_503(app, fake_client, error):
    fake_client.check_error = error

    with TestClient(app) as client:
        response = client.get("/ready", headers=AUTH)

    assert response.status_code == 503
    assert response.json() == {"detail": "Gemini readiness check failed."}
    assert "provider secret" not in response.text


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AuthenticationError("provider secret"), 503),
        (AuthorizationError("provider secret"), 503),
        (ModelUnavailableError("provider secret"), 503),
        (GeminiTimeoutError("provider secret"), 503),
        (RateLimitError("provider secret"), 503),
        (GeminiConnectionError("provider secret"), 503),
        (GeminiServiceError("provider secret"), 503),
        (ResponseValidationError("provider secret"), 502),
        (ModelMismatchError("provider secret"), 502),
        (GeminiRequestError("provider secret"), 502),
        (InvalidInputError("submitted text"), 422),
    ],
)
def test_generation_failures_are_sanitized(
    app, fake_client, error, expected_status
):
    fake_client.generate_error = error

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            headers=AUTH,
            json={"prompt": "private prompt"},
        )

    assert response.status_code == expected_status
    assert "provider secret" not in response.text
    assert "submitted text" not in response.text
    assert "private prompt" not in response.text


def test_cors_allowlist_and_security_headers(app):
    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/generate",
            headers={
                "Origin": "https://allowed.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        denied = client.options(
            "/api/v1/generate",
            headers={
                "Origin": "https://denied.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        health = client.get("/health")

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "https://allowed.example"
    )
    assert "access-control-allow-origin" not in denied.headers
    assert health.headers["cache-control"] == "no-store"
    assert health.headers["content-security-policy"] == "default-src 'none'"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["x-request-id"]


def test_responses_and_logs_do_not_leak_secrets_or_submitted_text(
    app,
    fake_client,
    caplog,
):
    submitted = "Sensitive Person sensitive@example.test"
    provider_secret = "gemini-unit-test-key"
    fake_client.generate_error = RuntimeError(f"{submitted} {provider_secret}")
    app.dependency_overrides[get_gemini_client] = lambda: fake_client

    with caplog.at_level(logging.ERROR, logger="api.app"):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/generate",
                headers=AUTH,
                json={"prompt": submitted},
            )

    combined = response.text + caplog.text
    assert response.status_code == 500
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert submitted not in combined
    assert provider_secret not in combined
    assert TOKEN not in combined


def test_lifespan_closes_gemini_client(app, fake_client):
    with TestClient(app):
        assert fake_client.close_calls == 0

    assert fake_client.close_calls == 1


def test_production_disables_public_documentation(monkeypatch, fake_client):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-unit-test-key")
    app = create_app(
        api_settings(production=True),
        client_factory=lambda _settings: fake_client,
    )

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").headers["strict-transport-security"] == (
            "max-age=31536000; includeSubDomains"
        )


@pytest.mark.parametrize(
    "value",
    ["*", "javascript:alert(1)", "https://user:password@example.test"],
)
def test_cors_rejects_wildcards_and_invalid_origins(value):
    settings = api_settings(cors_allow_origins=value)
    with pytest.raises(ValueError):
        _ = settings.allowed_origins


def test_api_settings_hide_backend_token():
    settings = api_settings()
    assert TOKEN not in repr(settings)


def test_api_settings_reject_empty_backend_token():
    with pytest.raises(ValidationError):
        ApiSettings(backend_api_token="")
