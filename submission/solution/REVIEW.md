# Revisão manual (UI e backend)

O utilizador envia um **documento** (PDF ou texto), um **áudio**, uma
**fotografia** ou um **vídeo**, vê o resultado anonimizado e **aprova ou
rejeita**. Em texto vê os `*`; em imagem e vídeo pode criar, mover,
redimensionar e limitar no tempo regiões pixelizadas (ver
[MEDIA.md](MEDIA.md)). Ao rejeitar escreve observações, para ocultar mais
("Mascara também o nome do centro") ou menos ("Não mascares a informação
médica"): o utilizador tem a palavra final. Essas observações passam a ser a
**prompt do utilizador** (ver [DETECTION.md](DETECTION.md)) e a análise corre
outra vez, gerando a tentativa seguinte. O utilizador pode também escrever
**instruções iniciais** ao enviar o ficheiro, num campo opcional, e elas valem
logo na primeira versão. As versões rejeitadas ficam no histórico da sessão.

```
texto:  UI <-> src/user_validation.py -> pipeline.run -> Gemini (gateway)
áudio:  UI <-> src/user_validation.py -> ElevenLabs (1 vez) -> pipeline.run
                                      -> alinhamento -> ffmpeg (sons de censura)
```

## Backend (`src/user_validation.py`)

FastAPI, uma só sessão em memória (um servidor local para uma pessoa). A
revisão é **ou** um texto, um áudio, uma imagem **ou** um vídeo, nunca mais
de um: enviar um novo ficheiro substitui o anterior.

| Rota | O que faz |
|---|---|
| `POST /api/document` | corpo = PDF (`application/pdf`) ou texto UTF-8 (`text/plain`, até 10 MB), ou imagem/vídeo (ver [MEDIA.md](MEDIA.md)); começa a revisão. Aceita o cabeçalho opcional `X-User-Instructions` (ver abaixo) |
| `POST /api/audio` | corpo = áudio (`audio/mpeg`, `audio/mp4`, `audio/x-m4a` ou `audio/wav`, até 25 MB); transcreve, deteta e censura; começa a revisão. Aceita o cabeçalho opcional `X-User-Instructions` |
| `GET /api/audio/current` | o áudio **censurado** da versão atual (`audio/mp4`, sem cache); 404 se ainda não há. Nunca devolve o original |
| `GET /api/current` | o estado (ver abaixo) |
| `POST /api/reject` | `{attempt, text, reason}`: guarda a versão, junta `reason` às instruções e gera a seguinte |
| `POST /api/approve` | aprova a versão atual |
| `PUT /api/media/regions` | guarda as regiões multimédia editadas |
| `GET /api/media/source` | serve o original temporário para revisão |
| `GET /api/media/output` | serve a versão multimédia aprovada |

O **estado** (o mesmo em todas as rotas, e o que a UI mostra) tem os campos
`has_document`, `attempt`, `text`, `approved`, `history`, `mode` (`model` ou
`rules`), `warnings`, `issues` e, desde o áudio, `kind` (`text` ou `audio`),
`audio_url` (o caminho do áudio censurado, ou `null`), `audio_ranges`
(quantos troços foram trocados por um som) e `audio_enabled` (a censura de
áudio está disponível). No áudio, `text` é a **transcrição mascarada**.

Comportamento:

- **Instruções iniciais.** O cabeçalho `X-User-Instructions` leva o texto que
  o utilizador escreveu ao enviar o ficheiro, em percent-encoding (como o
  `X-File-Name`), até **1500 caracteres** (mais dá 422 sem chamar o modelo, e
  o texto nunca vem na mensagem de erro). Valem na primeira versão (texto,
  áudio, imagem e vídeo) e **em todas as seguintes**: vão sempre no pedido,
  em primeiro lugar, e nunca são descartadas. Enviar um novo ficheiro
  esquece-as. Vão num cabeçalho, e não na URL, para não aparecerem no registo
  de acessos. Em branco ou ausente, nada muda.
- **As observações acumulam-se.** Cada pedido ao modelo leva todas as
  observações anteriores, até 2000 caracteres no total, contando as
  instruções iniciais (das observações ficam as mais recentes). Uma só
  observação que, com as instruções iniciais, passe das 2000 dá erro 422.
- **Uma rejeição que falha não muda nada.** Se o modelo, o gateway ou a
  censura do áudio falham, a resposta é 502 com uma mensagem fixa, a versão
  (e o seu áudio) continuam em revisão e a observação não fica guardada.
- **Versão desatualizada.** Se o `attempt` enviado não é o atual, 409.
- **Sem o Gemini** (`GEMINI_GATEWAY_URL` por definir) só correm as regras de
  segurança, e as observações não alteram o texto. A UI indica-o.
- **Demora.** Com o Gemini, gerar uma versão demora alguns segundos; o áudio
  demora mais (transcrição e `ffmpeg`).

### Áudio

- **Disponível só com** o gateway da Cloudflare (ou `ELEVENLABS_API_KEY`) e
  `ffmpeg`/`ffprobe` instalados. A chave do ElevenLabs está no Worker, não em
  quem usa a UI: o utilizador só envia o áudio (ver
  [DECISIONS.md](DECISIONS.md), 16).
  Sem eles `audio_enabled` é `false` e `POST /api/audio` responde 503; a UI
  deve esconder ou desativar o envio de áudio.
- **O áudio original sai da máquina.** Vai para o ElevenLabs, **ainda com os
  dados sensíveis**, antes de ser censurado (ver [AUDIO.md](AUDIO.md)). A UI
  de áudio tem de avisar o utilizador antes do envio.
- **Transcreve-se uma só vez por sessão.** Rejeitar repete só a deteção e a
  censura, a partir da transcrição guardada: não volta a enviar o áudio nem a
  gastar créditos (`audio_pipeline.run_transcript`).
- **Ficheiros temporários.** O original e o áudio censurado vivem numa pasta
  temporária privada, que se apaga quando se envia outro documento, ao fechar
  a sessão e ao sair do servidor. O áudio censurado de uma versão antiga
  apaga-se quando a seguinte fica pronta; o histórico guarda só o texto.
- **Falha alto.** Se a transcrição e o mascaramento não alinham, 502 e nada
  é censurado, em vez de deixar uma palavra por censurar.
- **Erros.** 415 (tipo), 413 (tamanho), 422 (áudio vazio ou sem fala), 502
  (transcrição, alinhamento, modelo ou `ffmpeg`), 503 (sem chave ou sem
  `ffmpeg`). As mensagens são fixas e nunca incluem o áudio nem a chave.

### Privacidade

Escuta só em `127.0.0.1` e o CORS só aceita as origens da UI
(`REVIEW_UI_ORIGINS`, separadas por vírgulas; por defeito `localhost` e
`127.0.0.1` nas portas 8080, 5173 e 3000; `*` não é aceite). O documento
fica só em memória (o áudio e os ficheiros multimédia só em pastas
temporárias, apagadas ao substituir a revisão ou fechar o servidor) e
perde-se ao reiniciar. As mensagens de erro nunca incluem o texto. As
amostras visuais vão ao Gemini quando a análise automática está ativa.

## UI (`Lovable_UI_JunctionX/`)

React + TanStack Start + Vite + Tailwind + shadcn, gerada pelo Lovable. A
interface está **em inglês** (decisão da equipa).

| Ficheiro | O que tem |
|---|---|
| `src/routes/index.tsx` | a página e os estados (arranque, envio, revisão) |
| `src/components/review/workspace.tsx` | o espaço de revisão: texto mascarado, contadores, aprovar/rejeitar, histórico, diálogo de feedback |
| `src/components/anonymizer/steps.tsx` | só o `UploadStep` (escolher ou largar o ficheiro e, opcionalmente, escrever as instruções iniciais) |
| `src/lib/review/api.ts`, `types.ts`, `mock.ts` | a camada de serviço: **o contrato com o backend** |
| `src/routes/__root.tsx`, `src/styles.css` | o esqueleto, o aviso de demonstração e os estilos |
| `src/components/ui/` | componentes shadcn genéricos |

- **O contrato é nosso.** O Lovable trata do aspeto, dos textos e das
  interações; os formatos dos pedidos e das respostas (`src/lib/review/`) não
  se mudam sem mudar o backend. O estado da UI é sempre o estado devolvido
  pelo backend: nunca se derivam versões localmente (ver `AGENTS.md` na pasta
  da UI).
- **Modo demonstração.** Sem `VITE_API_URL` a UI usa dados falsos e mostra um
  aviso fixo no topo. Para ligar ao backend: `cp .env.example .env`
  (`VITE_API_URL=http://127.0.0.1:8000`). Um PDF não se lê no browser em modo
  demonstração (falta o PyMuPDF), por isso qualquer ficheiro que não seja
  `.txt`/`.md` mostra o documento de exemplo mascarado em vez do ficheiro
  escolhido; a UI avisa com um alerta na página de revisão
  (`wasSampleSubstituted`, em `src/lib/review/mock.ts`) para ninguém confundir
  o exemplo com o resultado real. O mesmo vale sempre para o áudio em modo
  demonstração (a transcrição é sempre a mesma amostra).
- **Instruções iniciais.** O `UploadStep` tem um campo opcional "Instructions",
  com contador (1500 caracteres, `MAX_INSTRUCTIONS`). `uploadFile(file,
  instructions)` envia-as no cabeçalho `X-User-Instructions`
  (`instructionHeaders`, em `api.ts`) com o ficheiro, e a página limpa o campo
  depois de enviar. Em modo demonstração o campo avisa que as instruções não
  se aplicam. Testes em `src/test/initial-instructions.test.tsx`.
- **A UI do áudio.** Aceita mp3, m4a e wav no mesmo envio dos documentos e,
  antes de enviar um áudio, mostra o **aviso de privacidade** (o áudio
  original vai para o ElevenLabs) e exige marcar "I understand". Se o
  servidor não tem o áudio ligado (`audio_enabled` falso) bloqueia o envio e
  di-lo. Na revisão mostra o leitor com a versão censurada, a transcrição
  mascarada, "Replaced stretches" (`audio_ranges`), "Download audio" e o
  histórico (que guarda só o texto, "Transcript"). O contrato está em
  `src/lib/review/` (`uploadAudio`, `uploadFile`, `censoredAudioUrl`, os 4
  campos novos do estado e os dados de demonstração); a UI de áudio tem
  testes próprios (`src/test/audio-ui.test.tsx`).
- **O contrato de imagem e vídeo** (já feito, sem parte visual): `uploadMedia`,
  `waitUntilSettled` (a análise e a exportação correm em segundo plano; o
  estado traz `status` e `progress`), `updateRegions`, `trackRegion`,
  `mediaSourceUrl`, `mediaOutputUrl`, os tipos das regiões e um modo de
  demonstração com uma fotografia e um vídeo falsos. Os testes de contrato
  verificam os campos, os limites e o vocabulário das regiões contra o backend.
- **Passar o rato por um `*`** mostra a palavra que ele esconde. Para isso o
  estado traz `original_text` (o texto do documento, ou a transcrição do
  áudio): é o texto original, com os dados sensíveis, e só sai do servidor
  local para o navegador de quem enviou o ficheiro. A UI alinha cada `*` com
  a palavra por posição; se não conseguir, mostra só o `*`. Em imagem e vídeo
  `original_text` vem vazio.
- O trabalho do Lovable vem pelo branch `lovable/ui`, nunca diretamente para
  a `main`, e revê-se o diff antes de juntar.
- Gestor de pacotes: a UI traz `bun.lock`; `npm install` funciona, mas não se
  deve commitar o `package-lock.json` que gera.

## Arranque

```bash
# backend, a partir de submission/solution/src
pip install -r ../requirements.txt
export GEMINI_GATEWAY_URL=https://nos-gemini-gateway.jnhorta05.workers.dev
export GEMINI_GATEWAY_ORIGIN=http://localhost:5173

export ELEVENLABS_API_KEY=...        # opcional: sem ela, o áudio usa o gateway
python user_validation.py            # http://127.0.0.1:8000

# UI, a partir de submission/solution/Lovable_UI_JunctionX
npm install
npm run dev                          # http://localhost:8080
```

O arranque diz se o Gemini e o áudio estão ligados.

## Testes

- Backend de texto: `tests/test_user_validation.py` (21 testes).
- Rota de áudio: `tests/test_audio_route.py`, com a transcrição, o modelo e o
  `ffmpeg` falsos (26 testes). Um teste usa o `ffmpeg` a sério e só corre se
  ele estiver instalado.
- UI: `npx tsc --noEmit`, `npx vitest run` (24 testes: o contrato do áudio
  e os componentes de áudio) e `npm run build`, na pasta da UI.
- **Contrato backend-UI:** `tests/test_ui_contract.py` (7 testes) lê os tipos
  e as chamadas em `src/lib/review/` e confirma que os campos do estado, do
  histórico, as rotas chamadas, os tipos de áudio e os limites coincidem com
  o backend. Se um lado mudar sem o outro, falha aqui.

## Verificado e não verificado

Verificado:
- O fluxo de texto de ponta a ponta, no browser, contra o backend real e o
  Gemini: enviar, rejeitar com um pedido (a tentativa 2 respeita-o), aprovar.
- A rota de áudio com a transcrição falsa: estado, ficheiros temporários,
  uma só transcrição, falhas que não mudam nada, tipos e tamanhos.
- A rota de áudio com o **`ffmpeg` real**: o troço da palavra censurada é
  mesmo substituído, o resto fica igual e a duração não muda (ver
  [AUDIO.md](AUDIO.md), "Verificação da rota").

Não verificado:
- A rota de áudio com o **ElevenLabs real** (não há chave). O pipeline de
  linha de comandos foi verificado pela equipa que o fez (ver
  [AUDIO.md](AUDIO.md)).
- A **UI de áudio** só foi vista em modo demonstração (com um áudio silencioso
  falso) e contra um backend sem a chave (a UI bloqueia o envio e di-lo).
  Nunca com áudio real de ponta a ponta.
- Só uma sessão de cada vez: dois separadores partilham o mesmo documento.
