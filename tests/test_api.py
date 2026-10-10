import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nos_anonymizer import (
    MODEL_ID,
    AuthenticationError,
    AuthorizationError,
    DetectionResult,
    GeminiConnectionError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
    SensitiveEntity,
    TokenUsage,
)
from nos_anonymizer.api import create_app, get_gemini_client
from nos_anonymizer.api_config import ApiSettings

TOKEN = "backend-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeGeminiClient:
    def __init__(self):
        self.check_calls = 0
        self.detect_calls = []
        self.close_calls = 0
        self.check_error = None
        self.detect_error = None

    def check_connection(self):
        self.check_calls += 1
        if self.check_error:
            raise self.check_error
        return object()

    def detect_sensitive_entities(self, blocks):
        self.detect_calls.append(blocks)
        if self.detect_error:
            raise self.detect_error
        return DetectionResult(
            model=MODEL_ID,
            entities=(
                SensitiveEntity(
                    block_id="paragraph-1",
                    start_char=8,
                    end_char=13,
                    text="Maria",
                    category="person_name",
                    reason="Direct personal identifier",
                ),
            ),
            usage=TokenUsage(
                input_tokens=20,
                output_tokens=10,
                thought_tokens=0,
                total_tokens=30,
            ),
        )

    def close(self):
        self.close_calls += 1


def api_settings(**overrides):
    values = {
        "backend_api_token": TOKEN,
        "cors_allow_origins": "https://allowed.example",
        "max_block_count": 2,
        "max_text_length": 100,
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


def detection_payload(text="Contact Maria at maria@example.com."):
    return {"blocks": [{"block_id": "paragraph-1", "text": text}]}


def test_health_does_not_invoke_gemini(app, fake_client):
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_client.check_calls == 0
    assert fake_client.detect_calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": "Basic backend-test-token"},
    ],
)
@pytest.mark.parametrize("path", ["/ready", "/api/v1/detect"])
def test_protected_endpoints_require_valid_backend_auth(app, path, headers):
    with TestClient(app) as client:
        if path.endswith("detect"):
            response = client.post(path, headers=headers, json=detection_payload())
        else:
            response = client.get(path, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing backend credentials."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_successful_readiness(app, fake_client):
    with TestClient(app) as client:
        response = client.get("/ready", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "model": MODEL_ID}
    assert fake_client.check_calls == 1


def test_successful_detection_uses_domain_models(app, fake_client):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/detect",
            headers=AUTH,
            json=detection_payload(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "model": MODEL_ID,
        "entities": [
            {
                "block_id": "paragraph-1",
                "start_char": 8,
                "end_char": 13,
                "text": "Maria",
                "category": "person_name",
                "reason": "Direct personal identifier",
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 10,
            "thought_tokens": 0,
            "total_tokens": 30,
        },
    }
    blocks = fake_client.detect_calls[0]
    assert blocks[0].block_id == "paragraph-1"
    assert blocks[0].text == "Contact Maria at maria@example.com."
    assert blocks[0].metadata == {}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"blocks": []},
        {"blocks": [{"block_id": "paragraph-1", "text": "   "}]},
        {
            "blocks": [
                {"block_id": "one", "text": "one"},
                {"block_id": "two", "text": "two"},
                {"block_id": "three", "text": "three"},
            ]
        },
        {
            "blocks": [
                {"block_id": "same", "text": "one"},
                {"block_id": "same", "text": "two"},
            ]
        },
        detection_payload("x" * 101),
    ],
)
def test_invalid_and_limit_exceeding_input_returns_422(app, payload):
    with TestClient(app) as client:
        response = client.post("/api/v1/detect", headers=AUTH, json=payload)

    assert response.status_code == 422


def test_oversized_request_body_returns_422(app):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/detect",
            headers={**AUTH, "Content-Type": "application/json"},
            content=b"{" + (b"x" * 600) + b"}",
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request body exceeds the configured limit."
    }


def test_missing_gemini_configuration_returns_503(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = create_app(api_settings())

    with TestClient(app) as client:
        response = client.get("/ready", headers=AUTH)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Backend configuration is missing or invalid."
    }


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
    ],
)
def test_detection_failures_are_sanitized(app, fake_client, error, expected_status):
    fake_client.detect_error = error

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/detect",
            headers=AUTH,
            json=detection_payload(),
        )

    assert response.status_code == expected_status
    assert "provider secret" not in response.text


def test_cors_allowlist_and_security_headers(app):
    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/detect",
            headers={
                "Origin": "https://allowed.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        denied = client.options(
            "/api/v1/detect",
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
    fake_client.detect_error = RuntimeError(f"{submitted} {provider_secret}")
    app.dependency_overrides[get_gemini_client] = lambda: fake_client

    with caplog.at_level(logging.ERROR, logger="nos_anonymizer.api"):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/detect",
                headers=AUTH,
                json=detection_payload(submitted),
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
