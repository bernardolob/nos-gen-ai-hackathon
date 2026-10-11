"""Gestão de cache de contexto para a instrução de sistema do Gemini.

O ``PromptCache`` guarda a instrução de sistema (``internal_prompt.txt``)
como conteúdo cacheado no Gemini.  Os pedidos subsequentes referem o cache
em vez de reenviar a prompt: os tokens cacheados são cobrados a um preço
muito inferior ao dos tokens de input normais.

O cache é criado uma vez e reutilizado durante o TTL configurado (por
defeito 1 hora).  Se o conteúdo ficar abaixo do mínimo de tokens exigido
pelo modelo, o cache não se cria e a chamada usa a instrução de sistema
normal (sem desconto, mas sem falhar).

Variáveis de ambiente (opcionais):

- ``GEMINI_CACHE_TTL_SECONDS``: duração do cache em segundos (3600).

As mensagens de erro nunca incluem o conteúdo da prompt.
"""

from __future__ import annotations

import logging
import time
from google import genai
from google.genai import types

LOGGER = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 3600
MIN_CACHE_TOKENS = 4096


class PromptCache:
    """Cache reutilizável para a instrução de sistema.

    Uso típico::

        cache = PromptCache(sdk_client, model_id)
        cache.ensure(system_prompt)          # cria ou reutiliza
        name = cache.name                    # None se não se criou
        cache.delete()                       # limpeza explícita
    """

    def __init__(
        self,
        sdk_client: genai.Client,
        model_id: str,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = sdk_client
        self._model = model_id
        self._ttl = max(60, ttl_seconds)
        self._cache_name: str | None = None
        self._prompt_hash: int | None = None
        self._created_at: float = 0.0

    @property
    def name(self) -> str | None:
        """Nome do cache ativo, ou ``None`` se não existe."""
        if self._cache_name and not self._expired():
            return self._cache_name
        return None

    @property
    def active(self) -> bool:
        """True se há um cache válido e não expirado."""
        return self.name is not None

    def ensure(self, system_prompt: str) -> str | None:
        """Cria o cache se necessário; devolve o nome ou ``None``.

        Se o cache já existir com a mesma prompt e não tiver expirado,
        reutiliza-o.  Se a prompt mudar, apaga o antigo e cria um novo.
        Devolve ``None`` (sem falhar) se o Gemini recusar o cache (por
        exemplo por estar abaixo do mínimo de tokens).
        """
        prompt_hash = hash(system_prompt)

        # Reutilizar o cache existente.
        if (
            self._cache_name
            and self._prompt_hash == prompt_hash
            and not self._expired()
        ):
            LOGGER.debug("A reutilizar o cache %s.", self._cache_name)
            return self._cache_name

        # A prompt mudou ou o cache expirou: apagar o antigo.
        self._delete_quiet()

        # Tentar criar um novo cache.
        try:
            cache = self._client.caches.create(
                model=self._model,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_prompt,
                    ttl="%ds" % self._ttl,
                ),
            )
            self._cache_name = cache.name
            self._prompt_hash = prompt_hash
            self._created_at = time.monotonic()
            LOGGER.info(
                "Cache criado: %s (TTL %ds).", self._cache_name, self._ttl
            )
            return self._cache_name
        except Exception as exc:
            # O Gemini pode recusar se os tokens estiverem abaixo do
            # mínimo.  Não é erro fatal: a chamada usa a prompt normal.
            LOGGER.warning(
                "Não foi possível criar o cache (a prompt será enviada "
                "normalmente): %s",
                type(exc).__name__,
            )
            self._cache_name = None
            self._prompt_hash = None
            return None

    def delete(self) -> None:
        """Apaga o cache, se existir.  Seguro para chamar várias vezes."""
        self._delete_quiet()

    def _delete_quiet(self) -> None:
        """Apaga sem levantar exceções."""
        if not self._cache_name:
            return
        name = self._cache_name
        self._cache_name = None
        self._prompt_hash = None
        try:
            self._client.caches.delete(name=name)
            LOGGER.info("Cache apagado: %s.", name)
        except Exception:
            LOGGER.debug(
                "Não foi possível apagar o cache %s (pode já ter expirado).",
                name,
            )

    def _expired(self) -> bool:
        """True se o cache já passou do TTL local."""
        if not self._created_at:
            return True
        return (time.monotonic() - self._created_at) >= self._ttl
