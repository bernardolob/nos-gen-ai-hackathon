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
PDF:    o mesmo, e GET /api/pdf/current -> pdf_output (apaga as palavras)
áudio:  UI <-> src/user_validation.py -> ElevenLabs (1 vez) -> pipeline.run
                                      -> alinhamento -> ffmpeg (sons de censura)
imagem, vídeo: UI <-> src/user_validation.py -> src/media (Gemini pelo Worker,
               OpenCV, ffmpeg); a análise e a exportação correm em segundo plano
```

## Backend (`src/user_validation.py`)

FastAPI, uma só sessão em memória (um servidor local para uma pessoa). A
revisão é **ou** um texto, um áudio, uma imagem **ou** um vídeo, nunca mais
de um: enviar um novo ficheiro substitui o anterior.

| Rota | O que faz |
|---|---|
| `POST /api/document` | corpo = PDF (`application/pdf`) ou texto UTF-8 (`text/plain`, até 10 MB), ou imagem/vídeo (ver [MEDIA.md](MEDIA.md)); começa a revisão. Aceita o cabeçalho opcional `X-User-Instructions` (ver abaixo) |
| `POST /api/audio` | corpo = áudio (`audio/mpeg`, `audio/mp4`, `audio/x-m4a` ou `audio/wav`, até 25 MB); transcreve, deteta e censura; começa a revisão. Aceita o cabeçalho opcional `X-User-Instructions` |
| `GET /api/pdf/current` | o **PDF anonimizado** da versão atual (`application/pdf`, sem cache), gerado a partir do PDF enviado, com um `*` no lugar de cada palavra apagada e o layout mantido; 404 se o documento não veio de um PDF; 502 se a verificação falhar (ver [PDF.md](PDF.md)) |
| `GET /api/audio/current` | o áudio **censurado** da versão atual (`audio/mp4`, sem cache); 404 se ainda não há. Nunca devolve o original |
| `GET /api/current` | o estado (ver abaixo) |
| `POST /api/reject` | `{attempt, text, reason}`: guarda a versão, junta `reason` às instruções e gera a seguinte |
| `POST /api/approve` | aprova a versão atual |
| `GET /api/ready` | diz se a análise de imagem e vídeo está disponível (o modelo do Worker verificado) |
| `PUT /api/media/regions` | guarda as regiões multimédia editadas |
| `POST /api/media/preview` | `{attempt, time_ms, regions}`: devolve uma imagem JPEG (sem cache) com o resultado já aplicado às regiões enviadas (as do rascunho, guardadas ou não): a fotografia, ou o fotograma do vídeo em `time_ms`. Rostos desfocados, o resto pixelado, como na exportação. 409 se a versão mudou, 502 com mensagem fixa se falhar |
| `POST /api/media/track` | segue uma caixa desenhada à mão pelo vídeo, para a frente e para trás |
| `GET /api/media/source` | serve o original temporário para revisão |
| `GET /api/media/output` | serve a versão multimédia aprovada |

O **estado** (o mesmo em todas as rotas, e o que a UI mostra) tem os campos
`has_document`, `attempt`, `text`, `original_text`, `approved`, `history`,
`mode` (`model`, `rules` ou `multimodal`), `warnings`, `issues`, `kind`
(`text`, `audio`, `image` ou `video`), `pdf_url` (o PDF anonimizado, ou
`null`), `audio_url` (o áudio censurado, ou `null`), `audio_ranges` (quantos
troços foram trocados por um som) e `audio_enabled`. Para imagem e vídeo, que
correm em segundo plano, traz também `status` (`processing`, `exporting`,
`ready`, `failed`...), `progress` (etapa, feitos, total), `media` (o ficheiro:
endereços, tamanho, duração), `regions` (o que ocultar: categoria, tipo, razão,
confiança, origem, tempo e coordenadas, **nunca o texto reconhecido**), `model`
e `error`. No áudio, `text` é a **transcrição mascarada**.

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

- **Áudio guardado como `.mp4` ou `.mov`.** Uma gravação de voz com essa
  extensão é tratada como áudio, não como vídeo (ver [AUDIO.md](AUDIO.md)); o
  estado vem com `kind: "audio"`.

- **Tudo o que o ecrã mostra vem em inglês.** A UI é em inglês, e o backend
  também lhe dá em inglês as mensagens de erro (`detail`, e `error` de um
  trabalho de imagem ou vídeo) e as razões das regiões: o prompt de imagem e
  vídeo pede-as em inglês e as que o código cria ("Potentially identifiable
  face.") também. O código, os comentários e a documentação ficam em
  português; `tests/test_user_facing_english.py` falha se uma mensagem ou razão
  voltar a ficar em português. O relatório (`report.md`) e as razões dos itens
  de texto continuam em português, porque o relatório é entregue em português e
  a UI não os mostra.

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
- **A UI de imagem e vídeo.** O envio mostra o aviso de privacidade (os
  fotogramas vão para o Gemini) e uma barra de progresso real, com o nome
  da etapa em inglês (`stageLabel`). Na revisão, as regiões desenham-se por
  cima do ficheiro (caixas, ou o contorno de 32 pontos nos rostos), com a cor
  da categoria, e no vídeo seguem o tempo, com interpolação entre
  quadros-chave e uma linha temporal. Edita-se à mão: desenhar, mover,
  redimensionar, setas, apagar com "Undo", mudar o tipo e a categoria, limitar
  no tempo, **rastrear** uma caixa pelo vídeo, "Save changes" e "Discard"
  (aprovar e rejeitar ficam bloqueados com alterações por guardar). Aprovar
  exporta em segundo plano e depois aparece "Download image" ou "Download
  video" (o vídeo é sempre MP4). O contrato está em `src/lib/review/`
  (`uploadMedia`, `waitUntilSettled`, `updateRegions`, `trackRegion`,
  `mediaSourceUrl`, `mediaOutputUrl`, `stageLabel`), com um modo de
  demonstração com uma fotografia e um vídeo falsos; os testes de contrato
  verificam os campos, os limites, o vocabulário das regiões e as etapas
  contra o backend.
- **Pré-visualização do desfoque.** O botão "Hide blur" / "Show blur" (o
  desfoque vem ligado por defeito e o botão diz o que o próximo clique faz) desenha por cima da fotografia, ou do fotograma do vídeo parado, o
  resultado tal como a exportação o vai fazer: a UI pede-o ao backend com as
  regiões do rascunho, por isso as edições por guardar também se veem. Com o
  vídeo parado mostra a imagem que o backend desenhou. **Com o vídeo a tocar**
  o desfoque é desenhado ao vivo, num `canvas`, a partir dos fotogramas que o
  navegador mostra (`live-blur.tsx`): é uma aproximação (cara em elipse, o
  resto em mosaico) para o botão continuar a fazer efeito; ao parar, volta a
  imagem exata. Os controlos do vídeo (play, pausa, barra de
  tempo e som) estão numa barra própria **por baixo** da imagem
  (`VideoControls`), e não na barra do navegador: assim os contornos e o
  desfoque nunca a tapam, e desaparece o botão de ecrã inteiro, que não fazia
  nada nesta página. Com a pré-visualização ligada **não se vê nenhum
  contorno nem etiqueta** por cima da imagem, só o resultado: uma região
  continua a poder escolher-se (clicando onde está) e só então mostra o contorno,
  a etiqueta e as pegas de redimensionar; ao desenhar uma região nova vêem-se
  todos. Com o botão desligado vêem-se todos os contornos, como antes. No modo de demonstração não existe (só o backend a
  desenha). Sem ela, o desfoque só se via depois de aprovar e descarregar.
- **Descarregar o PDF.** Num documento que veio de um PDF, "Download PDF" ao
  lado de "Download .txt" gera o PDF anonimizado da versão em revisão (ver
  [PDF.md](PDF.md)).
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
cores de estado) é igual em todos. Não se verificou com um leitor de ecrã,
nem em browsers que não sejam o do painel da app.

## Testes

- Backend de texto: `tests/test_user_validation.py` (29 testes).
- Rota de áudio: `tests/test_audio_route.py`, com a transcrição, o modelo e o
  `ffmpeg` falsos (29 testes). Um teste usa o `ffmpeg` a sério e só corre se
  ele estiver instalado.
- UI: `npx tsc --noEmit`, `npx vitest run` (208 testes) e `npm run build`,
  na pasta da UI.
- PDF: `tests/test_pdf_output.py` e `tests/test_pdf_route.py` (18 testes);
  imagem e vídeo: `tests/test_media.py` (35 testes, incluindo o desfoque dos
  rostos), mais os testes de UI de edição de regiões e de descarregar o PDF.
- **Instruções iniciais:** `tests/test_initial_instructions.py` (30 testes:
  fronteiras do tamanho, codificação, falhas, segurança e CORS), mais os
  casos de texto em `test_user_validation.py`, de áudio em
  `test_audio_route.py` e de imagem/vídeo em `test_media.py`. Na UI,
  `src/test/initial-instructions.test.tsx` (o campo e o cabeçalho) e
  `src/test/instructions-requests.test.ts` (o pedido real, com o `fetch`
  falso, para documento, áudio, imagem e vídeo). Ver "Instruções iniciais:
  como se verifica" abaixo.
- **Contrato backend-UI:** `tests/test_ui_contract.py` (13 testes) lê os tipos
  e as chamadas em `src/lib/review/` e confirma que os campos do estado, do
  histórico, as rotas chamadas, os tipos de áudio e os limites coincidem com
  o backend. Se um lado mudar sem o outro, falha aqui.

## Instruções iniciais: como se verifica

O que os testes automáticos garantem:

| Garantia | Onde |
|---|---|
| O limite de 1500 conta caracteres (não bytes) depois de tirar os espaços; 1501 dá 422 e o texto nunca volta no erro | `test_initial_instructions.py` |
| Cabeçalho em branco, ausente ou com codificação inválida (`%ZZ`, `%E7`) não deita o servidor abaixo | idem |
| Um pedido recusado, um tipo não suportado ou uma falha do modelo **não** mudam as instruções da sessão | idem |
| Enviar um novo ficheiro, sem instruções, esquece as anteriores | idem |
| As instruções não fecham nem abrem os blocos do pedido (`</user_instructions>`, `<document>`) | idem |
| As instruções iniciais ficam sempre no pedido, em primeiro lugar, mesmo com muitas rejeições, e o total respeita as 2000 letras | idem |
| O preflight de CORS aceita o cabeçalho a partir da UI e não o abre a outras origens | idem |
| O cabeçalho sai no pedido real para documento, áudio, imagem e vídeo, codificado, nunca na URL nem no corpo | `instructions-requests.test.ts` |
| O nome do cabeçalho e o limite de 1500 são os mesmos na UI e no backend, e o CORS aceita o cabeçalho | `test_ui_contract.py` |

Os testes foram verificados por **mutação**: com quatro erros plantados no
backend (a rejeição esquece a instrução, o CORS sem o cabeçalho, o limite
desligado, um novo envio que herda as instruções antigas) e dois na UI (o
áudio sem o cabeçalho, o texto na URL sem codificar) falham sempre.

**Verificação manual de ponta a ponta** (feita no browser, contra o backend
real e o Gemini). A repetir quando se mexer no envio:

1. Arrancar o backend (`python src/user_validation.py`, com
   `GEMINI_GATEWAY_URL` e `GEMINI_GATEWAY_ORIGIN`) e a UI com `VITE_API_URL`.
2. Escolher um ficheiro, escrever no campo "Instructions" (com acentos e uma
   quebra de linha) e carregar em "Analyze document".
3. Ver no separador de rede que o `POST /api/document` leva o cabeçalho
   `X-User-Instructions` codificado e que a URL não tem o texto.
4. Confirmar que o resultado respeita a instrução e que o campo ficou vazio.
5. Rejeitar com uma observação e confirmar que a versão 2 respeita **as
   duas**: a observação e a instrução inicial.

Resultado da última repetição: com "Mascara também a palavra Firebase. Não
mascares o nome da faculdade", a versão 1 mascarou "Firebase" e deixou a
faculdade visível; depois de rejeitar com "Mascara também a palavra Python",
a versão 2 mascarou "Python" e continuou a mascarar "Firebase" e a deixar a
faculdade visível.

**O que isto não cobre:** o cumprimento das instruções depende do Gemini e
não é determinístico; um pedido para deixar algo visível pode não ser
cumprido à letra em todas as execuções. Não se testou em ecrã estreito nem em
modo escuro.

## Verificado e não verificado

Verificado:
- **Imagem, de ponta a ponta,** com o Gemini real pelo Worker: um cartão de
  cidadão fictício com uma cara e uma matrícula; as regiões ficam alinhadas na
  UI, e a exportação deixa o cartão, a cara e a matrícula ilegíveis.
- **Vídeo, de ponta a ponta,** com o Gemini real, o `ffmpeg` e um vídeo real
  (uma cara que se mexe e um cartão): a cara é desfocada em todos os
  fotogramas vistos e o cartão é pixelado a partir de quando o modelo o vê; o
  áudio mantém-se. Fica uma falha pequena na entrada do cartão (ver
  [MEDIA.md](MEDIA.md)).
- **PDF anonimizado,** com o PDF do desafio e o Gemini real: as palavras
  sensíveis não estão no texto do PDF e o layout mantém-se.
- O fluxo de texto de ponta a ponta, no browser, contra o backend real e o
  Gemini: enviar, rejeitar com um pedido (a tentativa 2 respeita-o), aprovar.
- As instruções iniciais de ponta a ponta, no browser: o cabeçalho sai
  codificado, a versão 1 respeita-as e a versão 2, depois de rejeitar,
  respeita-as e à observação (ver "Instruções iniciais: como se verifica").
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
