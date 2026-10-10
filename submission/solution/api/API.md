# API

Pasta da API HTTP da solução. Serve a interface (Lovable) e qualquer outro
cliente. O pipeline (`../src/`) continua a funcionar sem esta pasta: a API é
uma camada por cima, nunca uma dependência do núcleo.

Estado: **apenas desenho**. Ainda não há código aqui.

## Âmbito

- Receber um documento (PDF ou texto) e devolver os itens detetados, o texto
  mascarado e o relatório.
- Não guarda documentos nem texto submetido. Não regista corpos de pedidos,
  prompts, respostas do fornecedor nem credenciais.
- A chave do Gemini lê-se só da variável de ambiente `GEMINI_API_KEY`.

## Endpoints previstos

Seguem o contrato que a interface espera (ver o prompt do Lovable).

| Método | Caminho | Corpo | Resposta |
|---|---|---|---|
| `GET` | `/health` | | `{"status": "ok"}` (público, não chama o Gemini) |
| `POST` | `/api/v1/analyze` | PDF (multipart, campo `file`) ou texto | `{"text", "items": [{"id", "line", "text", "category", "reason", "confidence", "source"}]}` |
| `POST` | `/api/v1/anonymize` | `{"text", "decisions": [{"id", "mask"}]}` | `{"anonymized", "report_md", "warnings"}` |

- `analyze`: extração, deteção (Gemini) e regras de segurança.
- `anonymize`: mascaramento com as decisões da revisão manual, verificação e
  relatório.
- O relatório da API não inclui os valores originais (`include_values=False`).

## O que vem do branch `Ai-studios-connection`

| Do branch | Vai para | Nota |
|---|---|---|
| `client.py`, `config.py`, `errors.py`, `models.py` | `../src/` | É a ligação ao Gemini: pertence ao núcleo (ponto 3 do pipeline), não à API |
| `api.py`, `api_config.py`, `server.py` | esta pasta | Gateway FastAPI: autenticação, CORS, limites, cabeçalhos de segurança |
| `Dockerfile`, `cloudflare/`, `wrangler.jsonc`, `package*.json`, `tsconfig.json` | `deploy/` (a decidir) | Só se a equipa quiser publicar a API; não é preciso para o desafio |
| `docs/*.md` | esta pasta | Juntar num só documento, sem repetir |
| `tests/test_api.py` | `tests/` desta pasta | |

## Pontos a tratar antes de integrar

Resultado da revisão do branch (ver a mensagem do pull request).

1. **O cliente não serve ainda a deteção.** `generate_text(prompt)` só envia
   texto. A deteção precisa de `system_instruction` (a prompt interna),
   `temperature=0` e resposta em JSON.
2. **O modelo está fixo no código** (`gemini-3.5-flash`, sem alternativa).
   Confirmar que a chave do hackathon o aceita, e tornar o nome configurável.
3. **O limite de prompt da API é 10 000 caracteres.** Hoje a prompt interna
   (6 284) mais o documento do desafio (3 004) dão cerca de 9 300. Fica no
   limite e rejeita documentos maiores. Subir o limite ou medir só o documento.
4. **A rota `/api/v1/generate` é uma passagem genérica** para o Gemini. Deve
   dar lugar a `analyze` e `anonymize`, que não aceitam prompts livres.
5. **O token de acesso não pode ir para o JavaScript da interface.** O próprio
   guia do branch o diz. A interface precisa de um intermediário no servidor,
   ou de sessões de utilizador.
6. **Código repetido a fatorizar:**
   - os dois `BaseSettings` (`GeminiSettings`, `ApiSettings`) repetem o mesmo
     bloco `model_config`;
   - `api.py` repete duas listas longas de exceções, que uma hierarquia de
     erros (transitórios, de resposta, de pedido) tornaria desnecessárias;
   - `_raise_api_error` é uma cadeia de `elif` que um dicionário de códigos
     resolve, e a mensagem de timeout aparece escrita duas vezes;
   - os cinco cabeçalhos de segurança estão em `api.py` e em `worker.ts`;
   - as variáveis `BACKEND_*` repetem-se em até cinco sítios
     (`api_config.py`, `.env.example`, `wrangler.jsonc`, `worker.ts`,
     `Dockerfile`), por isso acrescentar uma definição obriga a mexer em
     todos.
7. **Estilo e CI.** O branch traz um `.flake8` com 88 colunas e altera o
   `lint.yml` original. Ficamos com o limite de 79 do repositório, sem mexer
   no `lint.yml`: reformatar o código em vez de mudar a regra.
8. **README da raiz.** O branch acrescenta uma secção ao `README.md` da
   organização. Esse texto deve viver nesta pasta.
