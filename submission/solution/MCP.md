# Servidor MCP para o Lovable

Deixa o Lovable **ver o nosso backend** enquanto trabalha na UI. É um servidor
MCP (`src/mcp_server.py`) de **só leitura** que usa **dados fictícios**: nunca
processa documentos reais nem chama o Gemini.

```
Lovable (chat) --HTTPS + token--> túnel --> mcp_server.py (127.0.0.1:8765)
```

## O que o Lovable pode pedir

| Ferramenta | Devolve |
|---|---|
| `frontend_brief` | O que a UI faz, onde estão os ficheiros (`review-workspace.tsx`, `styles.css`...), restrições e ideias |
| `describe_backend` | As 4 rotas da API da revisão (corpo, resposta, notas), os campos do estado, os erros e as rotas reais da aplicação |
| `sample_response(step)` | Uma resposta de exemplo de cada passo: `empty`, `uploaded`, `rejected`, `approved`, `errors` |

Os exemplos são gerados pelo **próprio backend** (`ReviewSession`) com um
documento fictício e um modelo falso, por isso não ficam desatualizados em
relação aos campos. Um teste confirma que os campos documentados são os que o
backend devolve e que as rotas documentadas existem.

## Arranque

A partir de `submission/solution/src`, com `pip install -r ../requirements.txt`:

```bash
MCP_TOKEN=um-token-longo-e-secreto python mcp_server.py
```

Escuta em `http://127.0.0.1:8765/mcp`. Sem `MCP_TOKEN`, gera um token
aleatório e mostra-o uma vez no terminal.

## Ligar ao Lovable

O Lovable corre na cloud e não vê o `127.0.0.1`, por isso o endereço tem de
ser público e em HTTPS. Com um túnel (por exemplo `cloudflared`):

```bash
cloudflared tunnel --url http://127.0.0.1:8765
```

O túnel dá um endereço `https://alguma-coisa.trycloudflare.com`. O servidor só
aceita cabeçalhos `Host` conhecidos (proteção contra DNS rebinding), por isso
diga-lhe qual é e arranque-o assim:

```bash
MCP_TOKEN=um-token-longo-e-secreto MCP_ALLOWED_HOSTS=alguma-coisa.trycloudflare.com python mcp_server.py
```

No Lovable (documentação: <https://docs.lovable.dev/integrations/custom-mcp>):

1. Connectors, no fim da lista, cartão **Custom MCP**.
2. Nome à vontade; URL `https://alguma-coisa.trycloudflare.com/mcp`.
3. Autenticação: **bearer token / API key** e o valor de `MCP_TOKEN`.
4. **Add server**.

Depois, no chat do Lovable, peça por exemplo: *"Usa o frontend_brief e o
describe_backend e melhora a UI de revisão"*.

## Segurança

- **Token obrigatório** em todos os pedidos (comparação em tempo constante);
  a resposta 401 não diz nada sobre ele.
- **Só leitura e dados fictícios**: não há ferramentas que recebam um
  documento ou chamem o modelo. Não acrescente nenhuma com dados reais sem
  repensar a exposição pública.
- O endereço do túnel é público enquanto o túnel estiver ativo; feche-o
  quando acabar. O token roda-se mudando `MCP_TOKEN`.
- `MCP_ALLOWED_HOSTS` não aceita `*`.

## O que isto não faz

- **Os conectores do Lovable são pessoais e não fazem parte da app
  publicada**: a UI publicada fala com o backend diretamente, não por MCP.
- **O Lovable não consegue correr o backend**: só vê a descrição e os
  exemplos. Para testar a UI contra o backend real, continua a ser
  `python user_validation.py` e `npm run dev` na máquina de quem trabalha.
- Não há rota para o relatório nem para o texto original; o `frontend_brief`
  di-lo, para o Lovable não inventar chamadas que não existem.

## Verificado e não verificado

Verificado (13 testes e um arranque real com `curl`): autenticação, lista de
ferramentas, respostas, recusa de `Host` estranho, e que os campos e as rotas
documentadas coincidem com o backend.

**Não verificado:** a ligação do Lovable ao servidor (não temos acesso à conta
do Lovable desta máquina) e o túnel `cloudflared` (não está instalado aqui).
Os passos do Lovable seguem a sua documentação.
