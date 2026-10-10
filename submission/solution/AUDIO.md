# Extra: censura de áudio

Esta funcionalidade é um **extra**, fora da numeração 1-8 do pipeline em
[ARCHITECTURE.md](ARCHITECTURE.md) (essa numeração corresponde aos critérios
dos organizadores). Objetivo: aceitar um ficheiro de áudio (mp3), detetar os
dados sensíveis falados e substituir cada palavra ocultada por um **som
personalizado** (um efeito sonoro engraçado, não silêncio nem um "bip"
genérico), devolvendo o áudio censurado.

Implementado para **mp3** (ver "Estado"); vídeo fica para depois (ver "Fora
de alcance").

## Estado

| Componente | Ficheiro | Estado |
|---|---|---|
| Transcrição (parser) | `src/audio/transcriber.py` | feito, testado com um `call_scribe` falso **e** com a API real |
| Cliente real do Scribe | `src/audio/elevenlabs_client.py` | feito e **confirmado com a API real** |
| Alinhamento | `src/audio/alignment.py` | feito e testado |
| Redação do áudio | `src/audio/redactor.py` | feito, testado com `ffmpeg` a sério |
| Ponto de entrada | `src/audio_pipeline.py` | feito e testado, de ponta a ponta com a API real |
| Rota do backend de revisão | `src/user_validation.py` | feita e testada com a transcrição e a censura falsas; **falta verificá-la com o ElevenLabs e o `ffmpeg` reais**. A UI de áudio não existe |

**Confirmado com a API real do ElevenLabs** (depois de a rede deste
ambiente passar a permitir `api.elevenlabs.io`): o esquema da resposta é o
documentado no topo de `transcriber.py`, com um exemplo real. Teste de
ponta a ponta: transcrição real de um dos sons de censura ("Pew pew, pew
pew, pew pew"), mascaramento de duas ocorrências a fingir serem
sensíveis, e substituição real por outro som via `ffmpeg` — a duração
final do áudio ficou **idêntica à original ao milissegundo** (1.812000s).
Os três valores de `type` da resposta (`word`, `spacing`, `audio_event`)
foram todos observados em exemplos reais.

## Porquê reaproveitar o pipeline de texto

```
mp3 -> Transcrição (ElevenLabs Scribe, com timestamps por palavra)
    -> linhas de texto -> pipeline.run() [sem alterações: deteção,
       regras de segurança, mascaramento, verificação, relatório]
    -> Alinhamento: cada palavra mascarada -> o seu intervalo de tempo
    -> Redação do áudio: substitui esse intervalo pelo som personalizado
    -> audio_censurado.m4a + submission.txt + report.md (reaproveitados)
```

`pipeline.run(lines, generate, user_instructions, include_values)` já faz a
deteção, as regras de segurança, o mascaramento, a verificação e o relatório
a partir de linhas de texto, sem saber de onde vêm. Dando-lhe as linhas da
transcrição em vez das do PDF, tudo isto funciona sem alterações. O único
componente novo é o que liga a transcrição com timestamps à redação do
áudio; os `*` no texto continuam a significar exatamente o mesmo.

## Componentes

| Componente | Ficheiro | Entrada | Saída |
|---|---|---|---|
| Transcrição | `src/audio/transcriber.py` | caminho do áudio, cliente (`call_scribe`) | linhas de texto + lista de palavras com `start`/`end` (segundos) |
| Alinhamento | `src/audio/alignment.py` | linhas originais, linhas mascaradas (de `pipeline.run`), palavras com tempo | lista de intervalos de tempo a substituir |
| Redação do áudio | `src/audio/redactor.py` | áudio original, intervalos, sons de substituição | ficheiro de áudio censurado |
| Ponto de entrada | `src/audio_pipeline.py` | caminho do áudio | mesma forma que `pipeline.run`, mais `lines` e `ranges` |

`audio_pipeline.run_transcript(lines, word_times, ...)` é a parte de `run` que
não toca no áudio (deteção, regras, mascaramento, alinhamento): permite
repetir a deteção sem voltar a transcrever. A rota de áudio usa-a.

### Transcrição

Cliente do **ElevenLabs Scribe**. A chave API vem de uma variável de
ambiente (`ELEVENLABS_API_KEY`, nunca no repositório, como o
`GEMINI_API_KEY` em [DEVELOPMENT.md](DEVELOPMENT.md)). Devolve o texto e,
por palavra, o instante de início e fim — é esse detalhe que torna possível
saber **quando** cada palavra sensível foi dita, não só **que** palavra é.

As linhas enviadas ao resto do pipeline agrupam as palavras por frase
(fim em `.`, `!` ou `?`), com um máximo de 20 palavras por linha quando
não há pontuação por perto — ver "Decisões tomadas".

### Alinhamento

Compara a linha original com a linha mascarada, palavra a palavra — a mesma
ideia já usada em `verification.compare_lines` para encontrar que posições
mudaram. Cada posição mascarada aponta para a palavra correspondente na
lista com timestamps, e daí para o seu intervalo `[start, end]`. Intervalos
seguidos juntam-se num só (a mesma lógica de `masking._merge`), para o som
de substituição não repetir várias vezes seguidas sem necessidade.

### Redação do áudio

Para cada intervalo, corta esse troço do áudio original e substitui-o por um
dos sons em `assets/censor_sounds/` (`censor_1.m4a` a `censor_4.m4a`, em
rotação — ver "Decisões tomadas"), cortado ou repetido (`ffmpeg
-stream_loop -1` seguido de `-t`, que serve para os dois casos) para ocupar
exatamente a duração do intervalo (a duração total do áudio não muda). Usa
o `ffmpeg` diretamente por `subprocess` — ver "Decisões tomadas" sobre
porquê não o `pydub`.

## Decisões tomadas

1. **Substituir, não silenciar nem "bipar".** Em vez de cortar o som ou pôr
   um bip genérico, a palavra sensível é trocada por um som escolhido pela
   equipa (efeito cómico). Mantém a ideia do `*` do texto — a presença da
   substituição mostra que ali havia algo sensível — mas de forma visual e
   sonoramente mais divertida para o pitch.
2. **O pipeline de texto não muda.** A deteção, as regras de segurança, o
   mascaramento, a verificação e o relatório são os mesmos para PDF e para
   áudio; só a transcrição e a redação do áudio são novas.
3. **O som personalizado é gravação própria da equipa.** Quatro variantes
   curtas (~2-3s cada), em `assets/censor_sounds/censor_1.m4a` a
   `censor_4.m4a`. Sendo gravação própria, não há questão de licença para
   um repositório open-source.
4. **Os quatro sons alternam em sequência (round-robin).** A primeira
   palavra ocultada num áudio usa `censor_1.m4a`, a segunda `censor_2.m4a`,
   e assim até `censor_4.m4a`, voltando depois a `censor_1.m4a`. Mais
   variado do que repetir sempre o mesmo som, sem a complexidade de uma
   escolha aleatória ou por categoria.
5. **`ffmpeg` por `subprocess`, não `pydub`.** O `pydub` depende do módulo
   `audioop` da biblioteca padrão, removido no Python 3.13: tentar
   instalá-lo neste ambiente falhou com
   `ModuleNotFoundError: No module named 'audioop'` (haveria o backport
   `audioop-lts` no PyPI, não testado aqui, mas seria mais uma
   dependência). Chamar o `ffmpeg` diretamente evita essa fragilidade e
   não acrescenta nenhuma dependência Python nova — só o binário do
   `ffmpeg` no sistema, como o `DEVELOPMENT.md` já pede.
6. **Agrupar a transcrição em linhas por frase, com um máximo de 20
   palavras.** Fim de frase (`.`, `!`, `?`) termina uma linha; sem
   pontuação durante muito tempo, 20 palavras também termina uma linha,
   para a deteção não receber uma linha gigante.
7. **Falha alto em vez de ocultar menos.** Se a transcrição e o
   mascaramento não alinharem (número de linhas, de palavras ou de
   marcas de tempo diferente), `alignment.py` levanta `AlignmentError` em
   vez de ignorar a palavra em silêncio. Ocultar menos do que devia é o
   erro grave aqui; um erro visível é preferível a uma fuga silenciosa.

## Decisões em aberto

Nenhuma sobre o funcionamento (ver "Estado": esquema da API já confirmado
com pedidos reais). Falta só confirmar o valor exato dos créditos por
minuto — "A confirmar" em "Custo", abaixo.

## Privacidade

- **O áudio original vai para um serviço de terceiros.** A transcrição é
  feita pelo ElevenLabs Scribe, por isso o áudio **com os dados sensíveis
  ainda por censurar** sai da máquina antes de qualquer censura. Isto
  acontece sempre, também com `--no-model`: essa opção só evita o Gemini.
- Depois, o **texto** da transcrição segue o caminho do pipeline de texto:
  passa pelo Worker e pelo Gemini (ver [GATEWAY.md](GATEWAY.md)), a menos
  que se use `--no-model`.
- Não verificámos as condições do ElevenLabs sobre retenção e treino com
  os dados enviados. Até as confirmarmos, **só se devem usar áudios
  fictícios ou com consentimento**, como os da demonstração.
- A chave (`ELEVENLABS_API_KEY`) só vem do ambiente; os erros do cliente
  nunca incluem a chave nem o áudio.
- Na revisão manual, o original e o áudio censurado ficam numa pasta
  temporária privada, apagada ao substituir o documento, ao fechar a sessão e
  ao sair do servidor. O original nunca se devolve pela API.

## Rota de áudio na revisão manual

O backend da revisão (`src/user_validation.py`) tem duas rotas de áudio, além
das de texto:

| Rota | O que faz |
|---|---|
| `POST /api/audio` | corpo = áudio (`audio/mpeg`, `audio/mp4`, `audio/x-m4a` ou `audio/wav`, até 25 MB); transcreve, deteta, censura e começa a revisão |
| `GET /api/audio/current` | o áudio **censurado** da versão atual (`audio/mp4`, sem cache). Nunca o original |

O estado devolvido ganha `kind` (`text` ou `audio`), `audio_url`,
`audio_ranges` e `audio_enabled`; no áudio, `text` é a transcrição mascarada.
Rejeitar e aprovar funcionam como no texto. Os pormenores (erros, ficheiros
temporários, falhas) estão em [REVIEW.md](REVIEW.md); a decisão de transcrever
uma só vez em [DECISIONS.md](DECISIONS.md) (15).

Requisitos: `ELEVENLABS_API_KEY` e `ffmpeg`/`ffprobe`; sem eles
`audio_enabled` é falso e `POST /api/audio` responde 503.

### O que falta da UI de áudio

A UI (Lovable) só envia texto e PDF. O contrato já está feito (em
`Lovable_UI_JunctionX/src/lib/review/`: `uploadAudio`, `uploadFile`,
`censoredAudioUrl`, os campos novos do estado e dados de demonstração com um
áudio silencioso); falta a parte visual. Precisa de:

- esconder ou desativar o envio quando `audio_enabled` é falso;
- **avisar antes de enviar** que o áudio original vai para o ElevenLabs;
- aceitar mp3, m4a e wav, e mostrar o estado de espera (vários segundos);
- um leitor com a versão censurada (`audio_url`, com `?v=<attempt>` para o
  navegador não reutilizar a versão anterior) e a transcrição mascarada por
  baixo, com `audio_ranges`;
- o mesmo fluxo de rejeição com observações e o histórico.

## Custo (créditos ElevenLabs)

Os testes previstos são para áudios **até 10 segundos** (ou o espaço
equivalente). Estimativa, a confirmar na página oficial de preços antes de
gastar créditos a sério:

- Fontes de preços de terceiros (não a página oficial, que não foi possível
  consultar daqui) indicam a transcrição (Scribe) a **cerca de 330 créditos
  por minuto**. Um clip de 10 segundos seria cerca de **55 créditos**.
- O plano Creator do cupão da JunctionX dá **131 000 créditos/mês**. A este
  preço, 55 créditos por teste é menos de 0,05% do orçamento mensal — dá para
  mais de 2000 testes de 10 segundos.
- **A confirmar:** estes números vêm de agregadores de preços, não da
  página oficial da ElevenLabs. A rede deste ambiente já permite
  `elevenlabs.io/pricing` (não permitia antes), mas a página carrega os
  valores concretos por JavaScript depois de carregar — o HTML estático
  não os tem, só as strings fixas da calculadora de preços. Confirmar os
  valores na própria página, no browser, antes de assumir este valor para
  áudios mais longos.

## Fora de alcance (por agora)

- **Vídeo.** Pedido pelo utilizador para mais tarde. Não é só mais áudio: um
  vídeo pode ter dados sensíveis visíveis (texto no ecrã, rostos), o que é
  um problema diferente (OCR, deteção de rostos) e não está planeado aqui.
- **Edição da deteção, das regras, do mascaramento, da verificação ou do
  relatório.** Todos reutilizados tal como estão.

## Relação com os outros componentes

- Usa `pipeline.run` sem alterações; a única entrada nova é a lista de
  linhas, construída a partir da transcrição em vez do PDF.
  `audio_pipeline.run` chama-o diretamente.
- `alignment.py` não importa `verification.py`: o trabalho da verificação é
  outro (confirmar que o mascaramento não teve erros de formato), não
  listar que posições mudaram.
- Usa o backend da revisão manual (`user_validation.py`, ver
  [REVIEW.md](REVIEW.md)) para a UI: a rota de áudio está lá (ver abaixo).
  É independente do `api/` (a API opcional).

## Experimentar

Pela linha de comandos, a partir de `submission/solution/src` (precisa do
`ffmpeg` instalado):

```bash
python audio_pipeline.py audio.m4a --no-model
python audio_pipeline.py audio.m4a --no-model --out saida
```

Pelo backend da revisão: `python user_validation.py` (com
`ELEVENLABS_API_KEY` definida) e `POST /api/audio` com o áudio no corpo;
ver [REVIEW.md](REVIEW.md).

Sem `--out` é um ensaio (só o resumo); com `--out DIR` escreve
`DIR/audio_censurado.m4a`, `DIR/submission.txt` e `DIR/report.md`. Sem
`--no-model`, precisa de `GEMINI_GATEWAY_URL`/`GEMINI_GATEWAY_ORIGIN` (como
`pipeline.py`) e de `ELEVENLABS_API_KEY`.
