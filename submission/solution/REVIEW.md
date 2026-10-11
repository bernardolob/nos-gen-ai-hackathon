# Revisão manual (UI e backend)

O utilizador envia um **documento** (PDF ou texto), um **áudio**, uma
**fotografia** ou um **vídeo**, vê o resultado anonimizado e **aprova ou
rejeita**. Em texto vê os `*`; em imagem e vídeo pode criar, mover,
redimensionar e limitar no tempo regiões pixelizadas (ver
[MEDIA.md](MEDIA.md)). Ao rejeitar escreve observações, para ocultar mais
("Mascara também o nome do centro") ou menos ("Não mascares a informação
médica"): o utilizador tem a palavra final. Essas observações passam a ser a
**prompt do utilizador** (ver [DETECTION.md](DETECTION.md)) e a análise corre
outra vez, gerando a tentativa seguinte. As versões rejeitadas ficam no
histórico da sessão.

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
| `POST /api/document` | corpo = PDF (`application/pdf`) ou texto UTF-8 (`text/plain`, até 10 MB), ou imagem/vídeo (ver [MEDIA.md](MEDIA.md)); começa a revisão |
| `POST /api/audio` | corpo = áudio (`audio/mpeg`, `audio/mp4`, `audio/x-m4a` ou `audio/wav`, até 25 MB); transcreve, deteta e censura; começa a revisão |
| `GET /api/pdf/current` | o **PDF anonimizado** da versão atual (`application/pdf`, sem cache), gerado a partir do PDF enviado, com um `*` no lugar de cada palavra apagada e o layout mantido; 404 se o documento não veio de um PDF; 502 se a verificação falhar (ver [PDF.md](PDF.md)) |
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

- **As observações acumulam-se.** Cada pedido ao modelo leva todas as
  observações anteriores, até 2000 caracteres (ficam as mais recentes). Uma
  só observação com mais de 2000 dá erro 422.
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
| `src/components/anonymizer/steps.tsx` | só o `UploadStep` (escolher ou largar o ficheiro) |
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

## Temas (UI)

O utilizador escolhe o aspeto da UI num painel pequeno, o botão de paleta no
cabeçalho (ao lado do sol/lua). O painel tem o **modo** (claro, escuro ou o do
sistema) e uma lista de **seis temas**: Indigo & Pink (o original, por
defeito), Ocean, Forest, Sunset, Grape e Graphite. Escolher aplica logo, fica
guardado no browser e vale também ao recarregar, sem piscar.

| Ficheiro | O que tem |
|---|---|
| `src/themes.css` | as paletas: só trocam os tokens da marca (`--brand`, `--brand-2`, `--glow`, `--ring`, `--sidebar-ring`, `--accent`) |
| `src/lib/theme.ts` | a lista de temas, a validação, o armazenamento e o `useTheme()`; também o script do `<head>` |
| `src/components/theme-picker.tsx` | o painel (Popover): modo, lista de temas e pré-visualização |
| `src/routes/__root.tsx`, `src/routes/index.tsx` | o script de arranque e o botão no cabeçalho |

Como funciona:

- Um tema é o atributo `data-theme` no `<html>`; o modo é a classe `dark`. O
  tema original não tem atributo. As cores vêm só de variáveis CSS, como pede o
  `AGENTS.md` da UI. As cores das **categorias** de dados sensíveis (`--cat-*`)
  não mudam com o tema (foram escolhidas por acessibilidade), nem os
  neutros e as cores de estado.
- Duas chaves em `localStorage`: `theme` (modo: `light` ou `dark`; sem chave é o
  do sistema, como antes de haver temas) e `palette` (o tema; sem chave é o
  original). Se o armazenamento estiver bloqueado (modo privado), a escolha
  vale só até recarregar e a UI funciona na mesma.
- O script do `<head>` aplica o tema e o modo antes do primeiro desenho e
  **valida o tema guardado contra a lista**: um valor errado ou alterado nunca
  chega ao `<html>`. O botão sol/lua e o painel usam o mesmo estado
  (`useTheme`), por isso ficam sempre em sintonia, também entre separadores.
- Cada cartão do painel usa `data-swatch="<id>"`, para mostrar a paleta do
  seu tema mesmo quando a página usa outro.

**Acrescentar um tema:**

1. Em `src/themes.css`, copiar um bloco (claro e escuro) e mudar o id e as
   cores. Manter as cores da marca com lightness entre cerca de 0,50 e 0,58,
   que é onde o texto branco e o fundo escuro ainda têm contraste.
2. Acrescentar `{ id, label }` a `THEMES`, em `src/lib/theme.ts`.
3. Correr `npx vitest run`: o teste de contraste falha se uma cor não chegar.

**Contraste (medido, não estimado).** O teste lê o `themes.css` e exige, para
cada tema e modo: texto branco sobre `--brand` a 4,5:1 e sobre `--brand-2` a
3:1, as duas cores da marca a 3:1 contra o fundo claro e o escuro, e o texto
a 7:1 sobre o fundo `--accent`. Também exige que as cores novas estejam dentro
do sRGB e que o `themes.css` e a lista de temas coincidam. O tema original
passa com 4,58:1 e 3,58:1, e é o piso. Medido, os outros ficam entre 4,78 e
6,11 (texto branco sobre a cor da marca).

**Testes:** `src/test/theme-contrast.test.ts` (53), `src/test/theme.test.tsx`
(56: valores inválidos, armazenamento bloqueado, sincronização, e o script do
`<head>` corrido contra uma página falsa, incluindo valores maliciosos) e
`src/test/theme-picker.test.tsx` (19: abrir, escolher, modo, Escape, e a
sintonia com o botão sol/lua). Foram verificados por mutação: com erros
plantados (cor demasiado clara, bloco escuro em falta, tema fora da lista,
token neutro alterado, script que confia no valor guardado, tema não validado,
listener que não se remove, painel que ignora o modo) falham sempre.

**Verificado no browser:** os 12 casos (6 temas, claro e escuro) têm os valores
esperados, as cores das categorias não mudam, o painel cabe num ecrã de 375 px
sem rolar para o lado, a escolha sobrevive ao recarregar, e as setas do teclado
selecionam e aplicam o tema.

**Limites:** os temas só mexem na marca, por isso o resto da UI (neutros e
cores de estado) é igual em todos. Não se verificou com um leitor de ecrã.
O Safari antigo, sem `oklch()`, mostra as cores do navegador por defeito.

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
