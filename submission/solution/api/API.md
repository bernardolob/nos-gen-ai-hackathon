# API (`api/`)

Gateway HTTP em FastAPI à volta do cliente Gemini (`src/gemini/`, ver
[GEMINI.md](../GEMINI.md)). É uma camada opcional: o pipeline em `src/`
funciona sem esta pasta, e nada no núcleo depende dela.

Código de origem: branch `Ai-studios-connection` (Joao Horta), reorganizado e
fatorizado.

## O que faz

| Método | Caminho | Acesso | Resposta |
|---|---|---|---|
| `GET` | `/health` | público | `{"status": "ok"}`; nunca contacta o Gemini |
| `GET` | `/ready` | token | `{"status": "ready", "model": "..."}`; verifica o Gemini |
| `POST` | `/api/v1/generate` | token | `{"model": "...", "text": "..."}` para o corpo `{"prompt": "..."}` |

Os caminhos protegidos exigem `Authorization: Bearer <BACKEND_API_TOKEN>`. Não
guarda documentos nem texto, e não regista corpos de pedidos, prompts,
respostas do fornecedor nem credenciais.

## Como correr

A partir de `submission/solution`:

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="a-tua-chave"
export BACKEND_API_TOKEN="um-token-privado-com-muita-entropia"
PYTHONPATH=src python -m api.server
```

PowerShell:

```powershell
$env:GEMINI_API_KEY = "a-tua-chave"
$env:BACKEND_API_TOKEN = "um-token-privado-com-muita-entropia"
$env:PYTHONPATH = "src"
python -m api.server
```

```bash
curl http://localhost:8080/health
curl -H "Authorization: Bearer $BACKEND_API_TOKEN" http://localhost:8080/ready
curl -X POST http://localhost:8080/api/v1/generate \
  -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"prompt":"diz olá"}'
```

## Configuração

Todas as variáveis estão em `.env.example`. As da API (`api/settings.py`):

| Variável | Por defeito | Para quê |
|---|---|---|
| `BACKEND_API_TOKEN` | nenhum | Token de acesso; sem ele os caminhos protegidos recusam tudo |
| `BACKEND_HOST` | `0.0.0.0` | Endereço de escuta |
| `BACKEND_PORT` | `8080` | Porto |
| `BACKEND_WORKERS` | `1` | Processos do Uvicorn |
| `BACKEND_PRODUCTION` | `false` | Se `true`, desliga a documentação pública e envia HSTS |
| `BACKEND_CORS_ALLOW_ORIGINS` | vazio | Origens HTTP(S) exatas, separadas por vírgulas; `*` é recusado |
| `BACKEND_MAX_PROMPT_LENGTH` | `10000` | Máximo de caracteres do prompt |
| `BACKEND_MAX_REQUEST_BYTES` | `1048576` | Máximo de bytes do corpo |

O token serve para testes privados e chamadas entre servidores. **Nunca o
coloques em JavaScript de um browser.**

## O que mudou em relação ao branch original

Refatoração, sem mudar o comportamento: os 90 testes originais passam, só com
os nomes dos módulos adaptados e a formatação a 79 colunas.

- **Grupos de erros.** O `api.py` repetia duas listas longas de exceções.
  Agora `errors.py` agrupa-as por hierarquia (`UpstreamError`,
  `UnavailableError`, `BadResponseError`) e a API apanha o grupo.
- **Tabela de códigos HTTP.** A cadeia de `elif` do `client.py` passou a uma
  tabela (`STATUS_ERRORS`), e a mensagem de timeout deixou de estar escrita
  duas vezes.
- **Configuração partilhada.** `GeminiSettings` e `ApiSettings` repetiam o
  mesmo bloco; ambos herdam agora de `EnvSettings`.
- **Cabeçalhos de segurança numa só tabela** (`SECURITY_HEADERS`), e o caminho
  limitado pelo middleware deixou de estar escrito à mão (`GENERATE_PATH`).
- **Validação de origens CORS** extraída para uma função própria.
- **Estilo.** Reformatado para 79 colunas, o limite do `lint.yml` da
  organização, em vez de alterar a regra. Sem `.flake8` próprio.
- **Estrutura.** O cliente foi para o núcleo (`src/gemini/`), a API para esta
  pasta (`api/`) e os testes para `tests/test_gemini/` e `tests/test_api/`.
- **Testes novos** para a hierarquia de erros (`tests/test_gemini/test_errors.py`).

## O que não veio

Ficou no branch `Ai-studios-connection`, por não ser preciso para o desafio:
`Dockerfile`, `cloudflare/`, `wrangler.jsonc`, `package*.json`,
`tsconfig.json`, o guia de Cloudflare e o fluxo de trabalho `test.yml`. Também
ficaram de fora as alterações ao `.flake8`, ao `lint.yml`, ao `.gitignore` e
ao `README.md` da raiz.

## Testes

A partir da raiz do repositório (os testes usam o `pytest`):

```bash
pip install -r submission/solution/requirements-dev.txt
python -m pytest submission/solution/tests
```

## Pontos em aberto

1. **`/api/v1/generate` é uma passagem livre** para o Gemini: quem tem o token
   envia qualquer prompt. Quando a deteção existir, a API deve expor
   operações do pipeline (analisar, mascarar), e não prompts livres.
2. **O limite de 10 000 caracteres por prompt** deixa pouca folga: a prompt
   interna (6 284) mais o documento do desafio (3 004) somam cerca de 9 300.
3. **O modelo está fixo no código** (ver [GEMINI.md](../GEMINI.md)).
4. **Fatorização que fica por fazer:** `check_connection` e `generate_text`
   chamam ambos `_ensure_open()`; juntá-lo em `_call` mudaria a ordem dos
   erros num cliente fechado, por isso deixei como estava.
