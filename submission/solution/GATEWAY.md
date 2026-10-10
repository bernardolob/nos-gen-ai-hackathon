# Gateway: como o pipeline chama o Gemini

A chave do Gemini é um segredo do Worker Cloudflare
(`cloudflare/worker.ts`, ver [CLOUDFLARE.md](CLOUDFLARE.md)). O pipeline não a
vê: `src/gateway.py` envia o pedido ao Worker, que chama o Gemini.

```
pipeline.py -> gateway.make_generate -> Worker (POST /api/v1/generate) -> Gemini
```

## Configuração

Variáveis de ambiente (nunca em ficheiros):

| Variável | Por defeito | Para quê |
|---|---|---|
| `GEMINI_GATEWAY_URL` | (sem ela, o pipeline pede `--no-model`) | endereço do Worker, sem o caminho |
| `GEMINI_GATEWAY_ORIGIN` | obrigatória com a URL | um `Origin` da lista `PUBLIC_APP_ORIGINS` do Worker |
| `GEMINI_GATEWAY_MAX_PROMPT` | 10000 | limite de caracteres do Worker (`MAX_PROMPT_LENGTH`) |
| `GEMINI_GATEWAY_TIMEOUT` | 90 | segundos por pedido |

PowerShell:

```powershell
$env:GEMINI_GATEWAY_URL = "https://nos-gemini-gateway.<subdominio>.workers.dev"
$env:GEMINI_GATEWAY_ORIGIN = "http://localhost:5173"
python pipeline.py ../../../raw_data/document_to_anonymize.pdf --out saida
```

Fora de `localhost`, o endereço tem de ser `https`.

## O que o Worker aceita (e as consequências)

- **Só `{"prompt": "..."}`.** A instrução de sistema e o documento seguem
  juntos num só texto; não há `temperature=0` nem modo JSON. A deteção
  tolera blocos de código e repete uma vez uma resposta inválida. As
  respostas podem variar entre execuções.
- **10 000 caracteres.** O documento do desafio cabe (a prompt interna mais o
  documento dão cerca de 9 500). Um documento maior é recusado **antes** de
  ser enviado, com uma mensagem a dizer o tamanho. Para documentos maiores
  é preciso subir `MAX_PROMPT_LENGTH` em `wrangler.jsonc`.
- **Origem e ritmo.** Sem `Origin` autorizado o Worker responde 403; passa
  10 pedidos por minuto por IP.

## Erros

| Erro | Quando | Repete? |
|---|---|---|
| `GatewayConfigError` | URL ou origem inválidas, prompt acima do limite | não |
| `GatewayUnavailable` | sem ligação, tempo esgotado, HTTP 408/429/5xx | até 3 vezes, com pausa crescente |
| `GatewayRejected` | 403, 415, 422, resposta que não é `{"text": ...}` | não |

As mensagens são fixas: não incluem o documento, a resposta nem o corpo do
erro. O pipeline termina com código 2 e não escreve nada.

## Privacidade

O texto do documento passa pelo Worker e pelo Gemini. O Worker não regista
corpos e envia `store: false`. Para documentos reais convém confirmar os
termos do Gemini (ver CLOUDFLARE.md).

## Testes

`tests/test_gateway.py` usa um Worker falso local (valida o `Origin`, o corpo
e responde com os estados HTTP), por isso corre sem chave nem rede.
