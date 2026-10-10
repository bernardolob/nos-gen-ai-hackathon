"""Cliente real do ElevenLabs Scribe.

Chama a API HTTP diretamente com ``httpx`` (já uma dependência do
projeto), em vez do SDK oficial, para não acrescentar mais uma
dependência só para um único pedido. A chave vem de
``ELEVENLABS_API_KEY`` (variável de ambiente, nunca no repositório, como
``GEMINI_API_KEY`` em ``DEVELOPMENT.md``).

**Por testar com a chave real.** Não foi possível alcançar
``api.elevenlabs.io`` desde o ambiente onde isto foi escrito (rede
bloqueada), por isso nem o endereço, nem ``MODEL_ID``, nem os nomes dos
parâmetros do pedido foram confirmados contra um pedido real. Ver a nota
em ``transcriber.py``.
"""

import os

import httpx

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL_ID = "scribe_v2"  # por confirmar: nome exato do modelo
DEFAULT_TIMEOUT = 60


class ConfigurationError(Exception):
    """Falta a variável de ambiente da chave."""


class ScribeRequestError(Exception):
    """O pedido ao Scribe falhou. Nunca inclui a chave nem o áudio."""


def from_env(timeout=DEFAULT_TIMEOUT):
    """``call_scribe`` a partir de ``ELEVENLABS_API_KEY``.

    Levanta ``ConfigurationError`` se a variável não estiver definida.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ConfigurationError("falta a variável ELEVENLABS_API_KEY")
    return make_client(api_key, timeout)


def make_client(api_key, timeout=DEFAULT_TIMEOUT):
    """Devolve ``call_scribe(audio_bytes)``, para ``transcriber.transcribe``.
    """
    def call_scribe(audio_bytes):
        try:
            response = httpx.post(
                API_URL,
                headers={"xi-api-key": api_key},
                data={
                    "model_id": MODEL_ID,
                    "timestamps_granularity": "word",
                },
                files={"file": ("audio", audio_bytes)},
                timeout=timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ScribeRequestError(
                "pedido ao Scribe falhou (%s)" % type(error).__name__
            ) from error
        return response.json()
    return call_scribe
