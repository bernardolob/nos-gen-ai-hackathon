"""Testes do módulo de context caching (``gemini/caching.py``) e cliente."""

import pytest

from gemini import (
    MODEL_ID,
    GeminiClient,
    InvalidInputError,
    PromptCache,
)
import gemini_adapter


def test_prompt_cache_lifecycle(fake_sdk):
    cache = PromptCache(fake_sdk, MODEL_ID, ttl_seconds=600)
    assert not cache.active
    assert cache.name is None

    # 1. Criação inicial do cache
    name = cache.ensure("prompt inicial")
    assert name == "cachedContents/fake-cache-123"
    assert cache.active
    assert cache.name == name
    assert len(fake_sdk.caches.create_calls) == 1

    call = fake_sdk.caches.create_calls[0]
    assert call["model"] == MODEL_ID
    assert call["config"].system_instruction == "prompt inicial"
    assert call["config"].ttl == "600s"

    # 2. Reutilização (mesma prompt, não expirado)
    name2 = cache.ensure("prompt inicial")
    assert name2 == name
    assert len(fake_sdk.caches.create_calls) == 1  # não chamou de novo

    # 3. Mudança de prompt -> apaga antigo e cria novo
    fake_sdk.caches.create_result.name = "cachedContents/fake-cache-456"
    name3 = cache.ensure("nova prompt")
    assert name3 == "cachedContents/fake-cache-456"
    assert len(fake_sdk.caches.delete_calls) == 1
    assert (
        fake_sdk.caches.delete_calls[0]["name"]
        == "cachedContents/fake-cache-123"
    )
    assert len(fake_sdk.caches.create_calls) == 2

    # 4. Limpeza explícita
    cache.delete()
    assert not cache.active
    assert cache.name is None
    assert len(fake_sdk.caches.delete_calls) == 2


def test_prompt_cache_expiration(fake_sdk):
    cache = PromptCache(fake_sdk, MODEL_ID, ttl_seconds=60)
    cache.ensure("prompt")
    assert cache.active

    # Simular expiração
    cache._created_at = 0.0
    assert not cache.active
    assert cache.name is None

    # Chamada seguinte recria o cache
    cache.ensure("prompt")
    assert len(fake_sdk.caches.create_calls) == 2


def test_prompt_cache_handles_creation_failure_gracefully(fake_sdk):
    fake_sdk.caches.create_error = RuntimeError("Abaixo do mínimo de tokens")
    cache = PromptCache(fake_sdk, MODEL_ID)

    # Não deve levantar exceção, apenas devolver None
    name = cache.ensure("prompt pequena")
    assert name is None
    assert not cache.active


def test_client_generate_with_system_instruction_uses_cache(
    settings, fake_sdk
):
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    result = client.generate_with_system_instruction(
        system_instruction="instrucao de sistema",
        content="documento para analisar",
    )

    assert result.model == MODEL_ID
    assert result.text == "Hi from Gemini!"
    assert len(fake_sdk.caches.create_calls) == 1
    assert len(fake_sdk.models.generate_calls) == 1

    gen_call = fake_sdk.models.generate_calls[0]
    assert gen_call["model"] == MODEL_ID
    assert gen_call["contents"] == "documento para analisar"
    assert gen_call["config"].cached_content == "cachedContents/fake-cache-123"


def test_client_generate_with_system_instruction_falls_back_inline(
    settings, fake_sdk
):
    fake_sdk.caches.create_error = RuntimeError("Cache recusado")
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    result = client.generate_with_system_instruction(
        system_instruction="instrucao inline",
        content="documento",
    )

    assert result.text == "Hi from Gemini!"
    assert len(fake_sdk.models.generate_calls) == 1
    gen_call = fake_sdk.models.generate_calls[0]
    assert gen_call["config"].system_instruction == "instrucao inline"


@pytest.mark.parametrize("invalid", ["", "   ", None])
def test_client_generate_with_system_instruction_validates_inputs(
    settings, fake_sdk, invalid
):
    client = GeminiClient(settings, _sdk_client=fake_sdk)

    with pytest.raises(InvalidInputError):
        client.generate_with_system_instruction(invalid, "conteudo valido")

    with pytest.raises(InvalidInputError):
        client.generate_with_system_instruction("sistema valido", invalid)


def test_client_closes_and_cleans_cache(settings, fake_sdk):
    client = GeminiClient(settings, _sdk_client=fake_sdk)
    client.generate_with_system_instruction("sistema", "conteudo")
    assert len(fake_sdk.caches.create_calls) == 1

    client.close()
    assert len(fake_sdk.caches.delete_calls) == 1
    assert (
        fake_sdk.caches.delete_calls[0]["name"]
        == "cachedContents/fake-cache-123"
    )


def test_gemini_adapter_make_cached_generate(settings, fake_sdk):
    client = GeminiClient(settings, _sdk_client=fake_sdk)
    generate = gemini_adapter.make_cached_generate(client=client)

    assert callable(generate)
    assert generate.client is client

    text = generate("instrucao", "conteudo")
    assert text == "Hi from Gemini!"
    gen_call = fake_sdk.models.generate_calls[0]
    assert gen_call["config"].response_mime_type == "application/json"
    # The detection schema is on by default, so the prompt needs no
    # "output format" section.
    schema = gen_call["config"].response_schema
    assert schema is not None
    assert "category" in schema["items"]["properties"]
    assert "visible" in schema["items"]["properties"]


def test_gemini_adapter_returns_none_without_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    generate = gemini_adapter.make_cached_generate()
    assert generate is None
