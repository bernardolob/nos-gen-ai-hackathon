"""Cliente real do ElevenLabs Scribe.

Chama a API HTTP diretamente com ``httpx`` (já uma dependência do
projeto), em vez do SDK oficial, para não acrescentar mais uma
dependência só para um único pedido.

Há dois caminhos, escolhidos por ``from_env``:

- chave própria: ``ELEVENLABS_API_KEY`` (variável de ambiente, nunca no
  repositório, como ``GEMINI_API_KEY`` em ``DEVELOPMENT.md``), para
  desenvolvimento local;
- gateway Cloudflare (``cloudflare/worker.ts``): ``GEMINI_GATEWAY_URL`` e
  ``GEMINI_GATEWAY_ORIGIN``, os mesmos do Gemini. A chave fica no Worker e
  quem corre o backend não precisa de nenhuma.

**Confirmado contra a API real** (depois de a rede deste ambiente passar
a permitir ``api.elevenlabs.io``): o endereço, ``MODEL_ID`` e os
parâmetros do pedido (``model_id``, ``timestamps_granularity=word``,
ficheiro) devolvem 200 e uma resposta no esquema que ``transcriber.py``
espera. Ver a nota lá, com um exemplo real.
"""

import os

import httpx

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
GATEWAY_PATH = "/api/v1/audio/transcribe"
MODEL_ID = "scribe_v2"
DEFAULT_TIMEOUT = 60


class ConfigurationError(Exception):
    """Falta a variável de ambiente da chave."""


class ScribeRequestError(Exception):
    """O pedido ao Scribe falhou. Nunca inclui a chave nem o áudio."""


def from_env(timeout=DEFAULT_TIMEOUT, environ=None):
    """``call_scribe`` a partir do ambiente.

    Usa ``ELEVENLABS_API_KEY`` se estiver definida; senão, o gateway
    (``GEMINI_GATEWAY_URL`` e ``GEMINI_GATEWAY_ORIGIN``). Levanta
    ``ConfigurationError`` se não houver nenhum dos dois.
    """
    env = os.environ if environ is None else environ
    api_key = env.get("ELEVENLABS_API_KEY")
    if api_key:
        return make_client(api_key, timeout)
    url = env.get("GEMINI_GATEWAY_URL", "").strip()
    origin = env.get("GEMINI_GATEWAY_ORIGIN", "").strip()
    if url and origin:
        return make_gateway_client(url, origin, timeout)
    raise ConfigurationError(
        "falta ELEVENLABS_API_KEY, ou GEMINI_GATEWAY_URL e "
        "GEMINI_GATEWAY_ORIGIN")


def make_client(api_key, timeout=DEFAULT_TIMEOUT):
    """Devolve ``call_scribe(audio_bytes)``, para ``transcriber.transcribe``.
    """
    def call_scribe(audio_bytes):
        return _post_json(
            API_URL,
            timeout,
            headers={"xi-api-key": api_key},
            data={
                "model_id": MODEL_ID,
                "timestamps_granularity": "word",
            },
            files={"file": ("audio", audio_bytes)},
        )
    return call_scribe


def make_gateway_client(gateway_url, origin, timeout=DEFAULT_TIMEOUT):
    """Como ``make_client``, mas pelo Worker, que tem a chave.

    O Worker só aceita pedidos com um ``Origin`` da sua lista e recebe o
    áudio em bruto.
    """
    endpoint = gateway_url.rstrip("/") + GATEWAY_PATH

    def call_scribe(audio_bytes):
        return _post_json(
            endpoint,
            timeout,
            headers={
                "Origin": origin,
                "Content-Type": "application/octet-stream",
            },
            content=audio_bytes,
        )
    return call_scribe


def _post_json(url, timeout, **request):
    """POST a ``url`` e devolve o JSON; erros viram ``ScribeRequestError``."""
    try:
        response = httpx.post(url, timeout=timeout, **request)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ScribeRequestError(
            "pedido ao Scribe falhou (%s)" % type(error).__name__
        ) from error
