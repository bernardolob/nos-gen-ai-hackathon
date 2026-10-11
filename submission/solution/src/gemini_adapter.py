"""Adaptador entre o ``GeminiClient`` (SDK) e o ``detection.detect``.

O ``detection.detect`` espera uma função ``generate(sistema, conteúdo)``
que devolve texto.  O ``gateway.py`` dá-lhe isso via Cloudflare Worker;
este módulo faz o mesmo usando o cliente SDK direto, **com context
caching**: a instrução de sistema é cacheada na primeira chamada e
reutilizada nas seguintes, poupando tokens de input.

Uso::

    from gemini_adapter import make_cached_generate

    generate = make_cached_generate()      # lê GEMINI_API_KEY do env
    items, warnings = detection.detect(lines, generate)

Variáveis de ambiente:

- ``GEMINI_API_KEY``: obrigatória.
- ``GEMINI_CACHE_TTL_SECONDS``: duração do cache (3600 s por defeito).
- As restantes variáveis do ``GeminiSettings``.

Se ``GEMINI_API_KEY`` não estiver definida, ``make_cached_generate``
devolve ``None`` (como o ``gateway.from_env``).
"""

import detection
from gemini import GeminiClient, GeminiSettings
from gemini.errors import ConfigurationError
from pydantic import BaseModel
from typing import Optional


class DetectionItem(BaseModel):
    line: int
    text: str
    category: str
    reason: Optional[str] = None
    confidence: str
    occurrence: Optional[int] = None


def make_cached_generate(settings=None, client=None, response_schema=None):
    """Devolve ``generate(sistema, conteúdo)`` com cache, ou None.

    Devolve None se as variáveis de ambiente não estiverem definidas
    (mesma convenção do ``gateway.from_env``).

    O ``client`` pode ser passado para reutilizar um já existente
    (por exemplo o da API FastAPI). Nesse caso o chamador é
    responsável por fechar o cliente.
    """
    if client is None:
        if settings is None:
            try:
                settings = GeminiSettings.from_env()
            except ConfigurationError:
                return None
        client = GeminiClient(settings)

    schema = (
        detection.load_response_schema() if response_schema is None
        else response_schema)

    def generate(system_prompt, content):
        result = client.generate_with_system_instruction(
            system_prompt,
            content,
            response_schema=schema,
            response_mime_type="application/json",
        )
        return result.text

    # Guardar referência para limpeza, se necessário.
    generate.client = client
    return generate
