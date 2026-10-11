# Arquitetura

Como o sistema está organizado, o que cada componente recebe e devolve, e em
que estado está. O ponto de entrada da documentação é o
[SOLUTION.md](SOLUTION.md).

## Princípios

- **O modelo deteta, o código mascara.** O Gemini só devolve a lista de itens
  sensíveis; quem escreve os `*` é o código. Assim a formatação e o número de
  asteriscos não dependem do modelo, e cada passo pode ser testado sozinho.
- **Genérico.** Nada no desafio limita o sistema a dados médicos. As categorias
  e as regras valem para qualquer documento; o que é específico de um
  documento vai para as instruções do utilizador.
- **Os mesmos dados em todos os passos.** Todos os componentes trocam o mesmo
  tipo de item (ver "Contrato de dados").
- **Núcleo sem dependências.** As regras de segurança, o mascaramento e o
  relatório só usam a biblioteca padrão do Python.

## Fluxo

```
PDF
 -> 1 Extração ----------------------> linhas de texto
 -> 2 Prompt interna + 3 Deteção -----> itens (Gemini)
 -> 4 Regras de segurança ------------> itens (regex)
 -> 5 Mascaramento -------------------> linhas mascaradas + avisos
 -> 6 Verificação --------------------> problemas (lista vazia = tudo certo)
 -> 7 Relatório ----------------------> relatório em Markdown

 -> submission.txt (as linhas mascaradas)

8 Avaliação própria: compara a saída com um documento anonimizado à mão.
```

Os itens do passo 3 e do passo 4 juntam-se numa só lista antes do
mascaramento. Se os dois apanham o mesmo valor, o relatório junta-os num só.

## Componentes

| # | Componente | Ficheiro | Entrada | Saída | Estado |
|---|---|---|---|---|---|
| 1 | Extração | `src/pdf_extractor.py` | caminho do PDF | texto, sem linhas vazias nem espaços no fim, com pontuação e acentos originais | feito |
| 2 | Prompt interna | `internal_prompt.txt` | | instruções enviadas ao Gemini | feita, testada com o Gemini |
| 3 | Deteção | `src/detection.py` | linhas numeradas e um cliente | itens e avisos | feito, ligado ao Gemini pelo gateway |
| 4 | Regras de segurança | `src/safety_rules.py` | linhas | itens | feito |
| 5 | Mascaramento | `src/masking.py` | linhas e itens | linhas mascaradas e avisos | feito |
| 6 | Verificação | `src/verification.py` | linhas originais e mascaradas | lista de problemas | feito |
| 7 | Relatório | `src/report.py` | itens e avisos | texto em Markdown | feito |
| 8 | Avaliação própria | `eval/evaluate.py` | saída e documento de referência | precisão e recall por palavra | **fora de âmbito** (decisão da equipa) |

O pipeline de texto fala com o Gemini pelo **gateway Cloudflare** (`src/gateway.py`,
só biblioteca padrão): a chave fica no Worker e nunca chega a este código.
O cliente direto do Gemini (`src/gemini/`) e a API HTTP opcional (`api/`) são
alternativas para desenvolvimento local. Imagens e fotogramas de vídeo usam o
cliente multimodal direto, exclusivamente no backend local, porque o gateway
de texto não aceita bytes. A arquitetura e os contratos estão em
[MEDIA.md](MEDIA.md).

O **ponto de entrada** é `src/pipeline.py`: lê o PDF (ou texto), chama cada
passo, verifica o resultado e grava `submission.txt` e `report.md`. O modelo
entra como a função `generate`; sem ela corre só com as regras de segurança
(`--no-model`). Como se usa está no [SOLUTION.md](SOLUTION.md).

## Contrato de dados

Todos os números de linha **começam em 1** e referem-se às linhas devolvidas
pela extração.

**Item** (deteção, regras de segurança, mascaramento e relatório):

| Campo | Tipo | Descrição |
|---|---|---|
| `line` | inteiro | Linha onde o valor aparece |
| `text` | texto | O valor sensível, copiado letra a letra do documento (sem a etiqueta que o precede) |
| `category` | texto | Um dos 9 ids da taxonomia (ver [taxonomy.md](taxonomy.md)) |
| `reason` | texto | Uma frase a explicar porque é sensível |
| `confidence` | texto | `certo`, `provavel` ou `incerto` |
| `occurrence` | inteiro, opcional | Qual ocorrência de `text` na linha, quando há várias |
| `source` | texto, opcional | `gemini` ou `regex`; sem este campo assume-se `gemini` |

**Aviso** (devolvido pelo mascaramento): `line`, `text` e `problem`. Surge
quando um item não é encontrado no documento ou tem texto vazio.

**Problema** (devolvido pela verificação): `type` e os campos do problema.
Os tipos são `line_count_mismatch`, `blank_line`, `word_count_mismatch` e
`unexpected_word_change`.

O texto dos itens tem de coincidir **exatamente** com o do documento,
incluindo a forma dos acentos. Convém normalizar para Unicode NFC na extração
e na deteção.

## Responsabilidades

1. **Extração.** Lê o PDF com o PyMuPDF e devolve o texto original sem linhas
   vazias e sem espaços no fim de cada linha. Não remove acentos nem
   pontuação, ao contrário do notebook do tutorial.
2. **Prompt interna.** Instruções para o Gemini: o que é sensível, o que não
   é, como devolver a lista. Genérica, para qualquer tipo de documento. O
   documento vai numerado e é tratado como dados, nunca como instruções.
3. **Deteção.** Envia a prompt e o documento ao Gemini (`temperature=0`) e
   valida o JSON devolvido. Recebe o cliente como parâmetro, por isso testa-se
   sem o Gemini. Ver [DETECTION.md](DETECTION.md). A chave vem de uma
   variável de ambiente e nunca é guardada no repositório.
4. **Regras de segurança.** Padrões fixos (regex) para dados com formato
   conhecido. Apanham o que o modelo deixe passar e garantem um mínimo se a
   API falhar.
5. **Mascaramento.** Localiza cada item na sua linha e troca cada palavra por
   `*`. A definição de palavra está em `src/words.py`. Ver
   [MASKING.md](MASKING.md).
6. **Verificação.** Confirma, comparando o original com o resultado, que
   o número de linhas e de palavras por linha não mudou, que não há linhas
   vazias e que cada palavra ou ficou igual ou foi mascarada por completo,
   com a mesma definição de palavra do mascaramento (`src/words.py`).
7. **Relatório.** Para cada item mascarado indica linha, categoria, razão,
   confiança e origem. Por defeito **não mostra os valores originais**, para
   o relatório não revelar o que foi ocultado.
8. **Avaliação própria (fora de âmbito).** Mediria o efeito de cada alteração
   à prompt contra um documento anonimizado à mão. A equipa decidiu não a
   fazer: as execuções comparam-se à mão.

## Extras

Fora da numeração 1-8 acima (essa numeração segue os critérios dos
organizadores). Um extra pode reaproveitar o pipeline de texto sem lhe
tocar.

| Extra | Ficheiros | Estado |
|---|---|---|
| Saída em PDF | `src/pdf_output.py` | feito e testado, ver [PDF.md](PDF.md) |
| Imagem e vídeo | `src/media/` (análise, regiões, rastreio, exportação) | feito e testado com o Gemini e um vídeo reais, ver [MEDIA.md](MEDIA.md) |
| Resposta em JSON obrigada | `detection_schema.json`, `cloudflare/worker.ts` (`format: "detection"`), `src/gemini_adapter.py` | feito, ver [DETECTION.md](DETECTION.md) |
| Cache do prompt | `src/gemini_adapter.py`, `src/gemini/caching.py` | feito; só com `GEMINI_API_KEY` local, ver [GEMINI.md](GEMINI.md) |
| Censura de áudio | `src/audio/`, `src/audio_pipeline.py` | feito e testado com a API real do ElevenLabs, ver [AUDIO.md](AUDIO.md) |
| Rota de áudio da revisão | `src/user_validation.py` (`/api/audio`) | feita e testada com a transcrição falsa e o `ffmpeg` real; a UI de áudio existe (visto em modo demonstração), ver [REVIEW.md](REVIEW.md) |

## Estrutura de pastas

```
submission/
  prompt.txt                  o pedido exato (prompt interno, documento, instruções)
  submission.txt              a saída do sistema para o documento do desafio
  solution/
    SOLUTION.md               ponto de entrada da documentação
    ARCHITECTURE.md           este documento
    DECISIONS.md              decisões de desenho e as razões
    DEVELOPMENT.md            como trabalhar no projeto
    DETECTION.md              deteção e validação da resposta
    MASKING.md                regras do mascaramento
    AUDIO.md                  extra: censura de áudio
    MEDIA.md                  extra: imagem e vídeo
    PDF.md                    extra: saída em PDF
    GATEWAY.md, CLOUDFLARE.md, GEMINI.md   o Worker e os clientes do Gemini
    REVIEW.md                 revisão manual: UI, backend e rotas
    user_instructions.txt     as instruções iniciais da submissão
    detection_schema.json     o esquema da resposta do modelo (Worker e SDK)
    taxonomy.md               categorias de dados sensíveis
    internal_prompt.txt       2 Prompt interna
    src/
      pdf_extractor.py        1 Extração (usa o PyMuPDF)
      categories.py           categorias e confiança (partilhado)
      words.py                o que é uma palavra (partilhado)
      detection.py            3 Deteção
      safety_rules.py         4 Regras de segurança
      masking.py              5 Mascaramento
      verification.py         6 Verificação
      report.py               7 Relatório
      pipeline.py             ponto de entrada que liga tudo
      gateway.py              liga o pipeline ao Gemini pelo Worker
      labels.py               deixa as etiquetas visíveis (itens do modelo)
      visibility.py           valores que o utilizador pediu para ficarem visíveis
      user_validation.py      backend da revisão manual: texto, PDF, áudio, imagem e vídeo (FastAPI)
      pdf_output.py           extra: o PDF anonimizado
      media/                  extra: imagem e vídeo (Gemini, OpenCV, ffmpeg)
      gemini/                 cliente direto do Gemini (alternativa)
      gemini_adapter.py       esse cliente como `generate`, com cache do prompt
      audio/                  extra: transcrição, alinhamento e redação
      audio_pipeline.py       extra: ponto de entrada da censura de áudio
    assets/
      censor_sounds/          extra: sons de substituição (censor_1 a 4.m4a)
    api/                      API HTTP opcional
    Lovable_UI_JunctionX/     UI da revisão manual (React)
    tests/                    testes de tudo o que está acima
```

Fora de âmbito: `eval/` (8), a avaliação própria.

## Problemas conhecidos

- **O `import fitz` está obsoleto** no PyMuPDF atual; a alternativa é
  `import pymupdf`.
