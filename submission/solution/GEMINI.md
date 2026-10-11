# Cliente Gemini (`src/gemini/`)

Ligação segura ao Gemini. É o ponto 3 do pipeline (deteção) e é também o que
a API usa. O código vem do branch `Ai-studios-connection` (Joao Horta),
reorganizado e fatorizado (ver [api/API.md](api/API.md), secção
"O que mudou").

## Garantias

- O modelo está fixo em `MODEL_ID` e **não há alternativa**: se o Gemini
  responder com outro modelo, o pedido falha.
- A chave só se lê da variável de ambiente `GEMINI_API_KEY`. Nunca vai para
  ficheiros, argumentos de linha de comandos, registos ou mensagens de erro.
- Os erros do fornecedor são convertidos em exceções com mensagens fixas. O
  corpo do erro, a chave e o texto enviado nunca aparecem nas mensagens.

## Utilização

```python
from gemini import GeminiClient, GeminiSettings

with GeminiClient(GeminiSettings.from_env()) as client:
    info = client.check_connection()      # só verifica; não gera texto
    result = client.generate_text("olá")  # devolve GenerationResult
print(result.text)
```

Verificação rápida a partir da linha de comandos, em `submission/solution`:

```bash
export GEMINI_API_KEY="a-tua-chave"
PYTHONPATH=src python -m gemini
```

PowerShell:

```powershell
$env:GEMINI_API_KEY = "a-tua-chave"
$env:PYTHONPATH = "src"
python -m gemini
```

Códigos de saída: `0` ligação bem-sucedida, `2` configuração em falta ou
inválida, `3` falha na ligação.

## Configuração

| Variável | Por defeito | Valores aceites |
|---|---:|---:|
| `GEMINI_API_KEY` | obrigatória | não vazia |
| `GEMINI_TIMEOUT_SECONDS` | 60 | maior que 0, até 600 |
| `GEMINI_RETRY_ATTEMPTS` | 3 | 1 a 10, incluindo o primeiro pedido |
| `GEMINI_RETRY_INITIAL_DELAY_SECONDS` | 1 | 0 a 60 |
| `GEMINI_RETRY_MAX_DELAY_SECONDS` | 8 | 0 a 120, não inferior ao inicial |

Há tentativas repetidas só para os códigos HTTP 408, 429, 500, 502, 503 e
504. O ficheiro `.env.example` lista todas as variáveis, incluindo as da API.

## Erros

As exceções estão agrupadas pelo que quem chama pode fazer (ver `errors.py`):

| Grupo | Exceções | Significado |
|---|---|---|
| `UnavailableError` | `AuthenticationError`, `AuthorizationError`, `ModelUnavailableError`, `RateLimitError`, `GeminiTimeoutError`, `GeminiConnectionError`, `GeminiServiceError` | O Gemini não se pode usar agora |
| `BadResponseError` | `ModelMismatchError`, `ResponseValidationError` | Respondeu, mas a resposta não é de confiança |
| `GeminiRequestError` | | O pedido foi rejeitado e não vale a pena repetir |
| (diretas) | `ConfigurationError`, `InvalidInputError` | Falham antes de qualquer pedido |

`UpstreamError` é a base dos três primeiros grupos: apanha tudo o que corre mal
com o Gemini. A tabela de códigos HTTP está em `STATUS_ERRORS` (`client.py`).

## Context Caching

O cliente suporta **context caching** nativo da instrução de sistema através de `PromptCache` (`src/gemini/caching.py`):

```python
result = client.generate_with_system_instruction(
    system_instruction=system_prompt,
    content=document_content,
)
```

- A instrução de sistema é enviada e cacheada na primeira chamada via Gemini Context Caching API.
- Chamadas seguintes reutilizam o cache dentro do TTL configurado (`GEMINI_CACHE_TTL_SECONDS`, por defeito 3600 segundos), reduzindo significativamente custos de tokens de entrada.
- Se a criação do cache falhar (por exemplo, abaixo do limite mínimo de tokens do modelo), é feito fallback automático transparente para envio inline da instrução de sistema sem falhar a execução.
- O adaptador `src/gemini_adapter.py` (`make_cached_generate`) liga este cliente com caching diretamente à interface `generate(sistema, conteúdo)` da pipeline.
