"""Testes do cliente do Scribe (``src/audio/elevenlabs_client.py``).

Sem rede: ``httpx.post`` é substituído por um falso.
"""

import sys
from pathlib import Path
from unittest import mock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audio import elevenlabs_client  # noqa: E402
from audio.elevenlabs_client import (  # noqa: E402
    ConfigurationError, ScribeRequestError)

GATEWAY = {
    "GEMINI_GATEWAY_URL": "https://worker.example.dev/",
    "GEMINI_GATEWAY_ORIGIN": "http://localhost:5173",
}


def _response(status=200, payload=None):
    request = httpx.Request("POST", "https://x")
    return httpx.Response(
        status, json={"words": []} if payload is None else payload,
        request=request)


def test_from_env_prefers_own_key():
    env = dict(GATEWAY, ELEVENLABS_API_KEY="chave")
    with mock.patch("httpx.post", return_value=_response()) as post:
        elevenlabs_client.from_env(environ=env)(b"audio")
    assert post.call_args.args[0] == elevenlabs_client.API_URL
    assert post.call_args.kwargs["headers"] == {"xi-api-key": "chave"}


def test_from_env_uses_gateway_without_key():
    with mock.patch("httpx.post", return_value=_response()) as post:
        result = elevenlabs_client.from_env(environ=GATEWAY)(b"audio")
    assert result == {"words": []}
    assert post.call_args.args[0] == (
        "https://worker.example.dev/api/v1/audio/transcribe")
    kwargs = post.call_args.kwargs
    assert kwargs["content"] == b"audio"
    assert kwargs["headers"]["Origin"] == "http://localhost:5173"
    assert "xi-api-key" not in kwargs["headers"]


@pytest.mark.parametrize("env", [
    {},
    {"GEMINI_GATEWAY_URL": "https://worker.example.dev"},
    {"GEMINI_GATEWAY_ORIGIN": "http://localhost:5173"},
])
def test_from_env_without_key_or_complete_gateway_fails(env):
    with pytest.raises(ConfigurationError):
        elevenlabs_client.from_env(environ=env)


@pytest.mark.parametrize("status", [403, 413, 429, 503])
def test_gateway_error_status_hides_details(status):
    call = elevenlabs_client.make_gateway_client("https://w.dev", "o")
    with mock.patch("httpx.post", return_value=_response(status)):
        with pytest.raises(ScribeRequestError) as error:
            call(b"audio")
    assert "HTTPStatusError" in str(error.value)


def test_gateway_invalid_json_is_a_scribe_error():
    call = elevenlabs_client.make_gateway_client("https://w.dev", "o")
    bad = httpx.Response(
        200, content=b"nao e json", request=httpx.Request("POST", "https://x"))
    with mock.patch("httpx.post", return_value=bad):
        with pytest.raises(ScribeRequestError):
            call(b"audio")
