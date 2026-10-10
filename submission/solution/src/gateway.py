"""Ligação ao Gemini pelo gateway Cloudflare (``cloudflare/worker.ts``).

A chave do Gemini fica no Worker; esta parte nunca a vê. Só usa a biblioteca
padrão, por isso o pipeline corre sem instalar mais nada.

O Worker aceita apenas ``{"prompt": "..."}``. A instrução de sistema e o
documento seguem juntos num só texto, sem ``temperature`` nem modo JSON: a
deteção já tolera blocos de código e repete uma vez uma resposta inválida.

Variáveis de ambiente (ver ``from_env``):

- ``GEMINI_GATEWAY_URL``: endereço do Worker, sem o caminho.
- ``GEMINI_GATEWAY_ORIGIN``: um ``Origin`` que conste de ``PUBLIC_APP_ORIGINS``
  do Worker (o Worker recusa pedidos sem ele).
- ``GEMINI_GATEWAY_MAX_PROMPT`` (10000) e ``GEMINI_GATEWAY_TIMEOUT`` (90 s).

As mensagens de erro são fixas: nunca incluem o texto enviado, a resposta nem
o corpo do erro.
"""

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

GENERATE_PATH = "/api/v1/generate"
DEFAULT_MAX_PROMPT = 10000
DEFAULT_TIMEOUT = 90.0
DEFAULT_ATTEMPTS = 3
DEFAULT_DELAY = 2.0
USER_AGENT = "nos-anonymizer/1.0"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")
# Estados em que vale a pena repetir: tempo esgotado, limite de pedidos e
# falhas do serviço (503 e 502 são o "Gemini indisponível" do Worker).
RETRY_STATUS = (408, 429, 500, 502, 503, 504)


class GatewayError(Exception):
    """Base dos erros do gateway; as mensagens são seguras de mostrar."""


class GatewayConfigError(GatewayError):
    """Configuração em falta ou inválida, ou prompt acima do limite."""


class GatewayUnavailable(GatewayError):
    """O gateway ou o Gemini não responderam, mesmo após as tentativas."""


class GatewayRejected(GatewayError):
    """O gateway recusou o pedido; repetir não ajuda."""


def make_generate(
    url,
    origin,
    timeout=DEFAULT_TIMEOUT,
    max_prompt_length=DEFAULT_MAX_PROMPT,
    attempts=DEFAULT_ATTEMPTS,
    delay=DEFAULT_DELAY,
    sleep=time.sleep,
):
    """Devolve ``generate(sistema, conteúdo)`` para o ``detection.detect``."""
    endpoint = _endpoint(url)
    if not origin or not origin.strip():
        raise GatewayConfigError("Falta o Origin do gateway.")
    origin = origin.strip()
    attempts = max(1, attempts)

    def generate(system_prompt, content):
        prompt = "%s\n\n%s" % (system_prompt, content)
        if len(prompt) > max_prompt_length:
            raise GatewayConfigError(
                "O pedido tem %d caracteres e o gateway aceita %d."
                % (len(prompt), max_prompt_length))
        body = json.dumps({"prompt": prompt}).encode("utf-8")
        request = urllib.request.Request(
            endpoint, data=body, method="POST", headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": origin,
                "User-Agent": USER_AGENT,
            })
        for attempt in range(1, attempts + 1):
            try:
                return _send(request, timeout)
            except GatewayUnavailable:
                if attempt == attempts:
                    raise
                sleep(delay * attempt)

    return generate


def from_env(environ=None):
    """Cria o ``generate`` a partir do ambiente, ou None sem gateway.

    Devolve None se ``GEMINI_GATEWAY_URL`` não estiver definida. Se estiver,
    o resto da configuração tem de ser válido.
    """
    env = os.environ if environ is None else environ
    url = env.get("GEMINI_GATEWAY_URL", "").strip()
    if not url:
        return None
    return make_generate(
        url,
        env.get("GEMINI_GATEWAY_ORIGIN", ""),
        timeout=_number(env, "GEMINI_GATEWAY_TIMEOUT", DEFAULT_TIMEOUT),
        max_prompt_length=int(_number(
            env, "GEMINI_GATEWAY_MAX_PROMPT", DEFAULT_MAX_PROMPT)),
    )


def _number(env, name, default):
    value = env.get(name, "").strip()
    if not value:
        return default
    try:
        number = float(value)
    except ValueError:
        number = 0
    if number <= 0:
        raise GatewayConfigError("%s tem de ser um número positivo." % name)
    return number


def _endpoint(url):
    parts = urllib.parse.urlsplit(url.strip())
    local = parts.hostname in [h.strip("[]") for h in LOCAL_HOSTS]
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise GatewayConfigError("O endereço do gateway não é válido.")
    if parts.scheme == "http" and not local:
        raise GatewayConfigError("O gateway tem de usar https.")
    return url.strip().rstrip("/") + GENERATE_PATH


def _send(request, timeout):
    """Um pedido: devolve o texto ou levanta um erro do gateway."""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        error.close()
        raise _status_error(error.code) from None
    except (socket.timeout, TimeoutError):
        raise GatewayUnavailable(
            "O gateway não respondeu a tempo.") from None
    except (urllib.error.URLError, OSError):
        raise GatewayUnavailable(
            "Não foi possível ligar ao gateway.") from None
    return _text(data)


def _status_error(status):
    if status in RETRY_STATUS:
        return GatewayUnavailable(
            "O gateway ou o Gemini estão indisponíveis (HTTP %d)." % status)
    return GatewayRejected(
        "O gateway recusou o pedido (HTTP %d)." % status)


def _text(data):
    try:
        value = json.loads(data.decode("utf-8"))
        text = value["text"]
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        text = None
    if not isinstance(text, str) or not text.strip():
        raise GatewayRejected("O gateway devolveu uma resposta inválida.")
    return text
