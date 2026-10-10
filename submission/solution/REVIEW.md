# Revisão manual (UI e backend)

O utilizador envia o documento, vê o texto anonimizado com os `*` destacados
e **aprova ou rejeita**. Ao rejeitar escreve observações, para ocultar mais ("Mascara também
o nome do centro") ou menos ("Não mascares a informação médica"): o
utilizador tem a palavra final. Essas observações passam a ser a **prompt do
utilizador** (ver [DETECTION.md](DETECTION.md)) e o pipeline corre outra vez,
gerando a tentativa seguinte. As versões rejeitadas ficam no histórico da sessão.

```
UI (Lovable_UI_JunctionX/) <-> src/user_validation.py -> pipeline.run -> Gemini (gateway)
```

## Backend (`src/user_validation.py`)

FastAPI, uma só sessão em memória (um servidor local para uma pessoa).

| Rota | O que faz |
|---|---|
| `POST /api/document` | corpo = PDF (`application/pdf`) ou texto UTF-8 (`text/plain`); corre o pipeline e começa a revisão (até 10 MB) |
| `GET /api/current` | `has_document`, `attempt`, `text`, `approved`, `history`, `mode` (`model` ou `rules`), `warnings`, `issues` |
| `POST /api/reject` | `{attempt, text, reason}`: guarda a versão, junta `reason` às instruções e gera a seguinte |
| `POST /api/approve` | aprova a versão atual |

Comportamento:

- **As observações acumulam-se.** Cada pedido ao modelo leva todas as
  observações anteriores, até 2000 caracteres (ficam as mais recentes). Uma
  só observação com mais de 2000 dá erro 422.
- **Uma rejeição que falha não muda nada.** Se o modelo ou o gateway falham, a
  resposta é 502 com uma mensagem fixa, a versão continua em revisão e a
  observação não fica guardada.
- **Versão desatualizada.** Se o `attempt` enviado não é o atual, 409.
- **Sem o Gemini** (`GEMINI_GATEWAY_URL` por definir) só correm as regras de
  segurança, e as observações não alteram o texto. A UI indica-o.
- **Demora.** Com o Gemini, gerar uma versão demora cerca de um minuto; a UI
  mostra "A gerar…".

Privacidade: escuta só em `127.0.0.1` e o CORS só aceita as origens da UI
(`REVIEW_UI_ORIGINS`, separadas por vírgulas; por defeito `localhost` e
`127.0.0.1` nas portas 8080, 5173 e 3000; `*` não é aceite). O documento
fica só em memória e perde-se ao reiniciar. As mensagens de erro nunca
incluem o texto.

## Arranque

```bash
# backend, a partir de submission/solution/src
pip install -r ../requirements.txt
export GEMINI_GATEWAY_URL=...  GEMINI_GATEWAY_ORIGIN=...   # opcional
python user_validation.py            # http://127.0.0.1:8000

# UI, a partir de submission/solution/Lovable_UI_JunctionX
npm install
npm run dev
```

A UI procura o backend em `http://127.0.0.1:8000`; muda-se com
`VITE_API_URL`.

## Verificado a correr

Com o backend só em regras (sem Gemini) e a UI em `npm run dev`
(`http://localhost:8080`): enviar um texto, ver o NIF mascarado, rejeitar com
observações (a tentativa 1 fica no histórico) e aprovar. `npx tsc --noEmit` e
`npm run build` passam e a consola do browser não mostra erros.

Faltavam em `src/lib/` quatro ficheiros que os componentes importam
(`utils.ts` e três de tratamento de erros do Lovable). A regra `lib/` do
`.gitignore` (pensada para Python) deixava-os de fora, por isso a UI não
compilava num clone limpo. Foram recriados (a regra tem agora uma exceção
para essa pasta). Os de erros são versões mínimas: registam na consola e
mostram uma página de erro simples.

## O que não está verificado

- Nunca correu com o Gemini real (quota): o texto novo gerado a partir das
  observações só se vê com o modelo ligado.
- Só uma sessão de cada vez: dois separadores partilham o mesmo documento.
- O envio de um PDF pela UI não foi experimentado no browser (o do backend
  tem teste).
