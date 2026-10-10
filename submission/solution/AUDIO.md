# Extra: censura de áudio

Esta funcionalidade é um **extra**, fora da numeração 1-8 do pipeline em
[ARCHITECTURE.md](ARCHITECTURE.md) (essa numeração corresponde aos critérios
dos organizadores). Objetivo: aceitar um ficheiro de áudio (mp3), detetar os
dados sensíveis falados e substituir cada palavra ocultada por um **som
personalizado** (um efeito sonoro engraçado, não silêncio nem um "bip"
genérico), devolvendo o áudio censurado.

Planeado, por fases: primeiro **mp3**, depois vídeo (ver "Fora de alcance").

## Porquê reaproveitar o pipeline de texto

```
mp3 -> Transcrição (ElevenLabs Scribe, com timestamps por palavra)
    -> linhas de texto -> pipeline.run() [sem alterações: deteção,
       regras de segurança, mascaramento, verificação, relatório]
    -> Alinhamento: cada palavra mascarada -> o seu intervalo de tempo
    -> Redação do áudio: substitui esse intervalo pelo som personalizado
    -> audio_censurado.mp3 + report.md (reaproveitado) + transcript.txt
```

`pipeline.run(lines, generate, user_instructions, include_values)` já faz a
deteção, as regras de segurança, o mascaramento, a verificação e o relatório
a partir de linhas de texto, sem saber de onde vêm. Dando-lhe as linhas da
transcrição em vez das do PDF, tudo isto funciona sem alterações. O único
componente novo é o que liga a transcrição com timestamps à redação do
áudio; os `*` no texto continuam a significar exatamente o mesmo.

## Componentes novos (planeados, por fazer)

| Componente | Ficheiro previsto | Entrada | Saída |
|---|---|---|---|
| Transcrição | `src/audio/transcriber.py` | caminho do mp3 | linhas de texto + lista de palavras com `start`/`end` (segundos) |
| Alinhamento | `src/audio/alignment.py` | linhas originais, linhas mascaradas (de `pipeline.run`), palavras com tempo | lista de intervalos de tempo a substituir |
| Redação do áudio | `src/audio/redactor.py` | mp3 original, intervalos, som personalizado | mp3 censurado |
| Ponto de entrada | `src/audio_pipeline.py` | caminho do mp3 | mesma forma que `pipeline.run`, mais o mp3 censurado |

### Transcrição

Cliente do **ElevenLabs Scribe**. A chave API vem de uma variável de
ambiente (`ELEVENLABS_API_KEY`, nunca no repositório, como o
`GEMINI_API_KEY` em [DEVELOPMENT.md](DEVELOPMENT.md)). Devolve o texto e,
por palavra, o instante de início e fim — é esse detalhe que torna possível
saber **quando** cada palavra sensível foi dita, não só **que** palavra é.

As linhas enviadas ao resto do pipeline agrupam um número razoável de
palavras cada (por frase, ou um máximo de palavras por linha), para a
deteção numerar as linhas como já faz com o PDF.

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
rotação — ver "Decisões tomadas"), cortado ou repetido para ocupar
exatamente a duração do intervalo (a duração total do áudio não muda). Usa
`ffmpeg` ou `pydub` (biblioteca externa, à parte do núcleo do resto do
pipeline, tal como o PyMuPDF é só da extração).

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

## Decisões em aberto

1. **Como agrupar as palavras da transcrição em linhas.** Por frase (pontuação
   do Scribe) ou por um número fixo de palavras; decide-se ao implementar o
   `transcriber.py`, conforme o que o Scribe devolver para os primeiros
   áudios de teste.
2. **Nome exato da variável de ambiente e onde documentar o `.env.example`**
   — seguir o padrão de `GEMINI_API_KEY`.

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
- **A confirmar:** estes números vêm de agregadores de preços, não da página
  oficial da ElevenLabs (não consultável deste ambiente). Confirmar em
  [elevenlabs.io/pricing](https://elevenlabs.io/pricing) antes de assumir
  este valor para áudios mais longos.

## Fora de alcance (por agora)

- **Vídeo.** Pedido pelo utilizador para mais tarde. Não é só mais áudio: um
  vídeo pode ter dados sensíveis visíveis (texto no ecrã, rostos), o que é
  um problema diferente (OCR, deteção de rostos) e não está planeado aqui.
- **Edição da deteção, das regras, do mascaramento, da verificação ou do
  relatório.** Todos reutilizados tal como estão.

## Relação com os outros componentes

- Usa `pipeline.run` sem alterações; a única entrada nova é a lista de
  linhas, construída a partir da transcrição em vez do PDF.
- Usa a mesma ideia de comparação de `verification.py` para encontrar as
  palavras mascaradas, mas sobre as próprias linhas (não lê `verification.py`
  como módulo; refaz a comparação porque precisa de manter o alinhamento com
  as posições das palavras na transcrição).
- Independente do `api/` e do `Lovable_UI_JunctionX/` (revisão manual); pode
  vir a usar esse backend mais tarde, sem alterações a este desenho.
