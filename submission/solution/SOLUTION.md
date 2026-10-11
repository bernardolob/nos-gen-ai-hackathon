# Solução

Sistema que deteta dados pessoais e sensíveis num documento (RGPD) e os
oculta, trocando **cada palavra sensível por um `*`**, sem mudar mais nada. Gera
também um relatório a explicar o que foi ocultado e porquê.

Foi pensado para **qualquer tipo de documento** (formulários, relatórios,
contratos, emails, registos). O documento do desafio, um relatório de admissão
hospitalar fictício, é apenas um caso de teste.

Este é o ponto de entrada da documentação da solução. O
[`submission/README.md`](../README.md) é o guia de submissão da organização e
não deve ser alterado.

## Como funciona

```
PDF -> Extração -> Deteção (Gemini) + Regras de segurança (regex)
    -> Mascaramento -> Verificação -> submission.txt + relatório
```

O Gemini só **deteta**: devolve a lista dos valores sensíveis. Quem escreve os
`*` é o código, por isso a formatação do documento nunca depende do modelo.
Pormenores em [ARCHITECTURE.md](ARCHITECTURE.md).

## Estado

Pontos do pipeline, pela ordem do fluxo:

| # | Componente | Estado |
|---|---|---|
| 1 | Extração do PDF | feito (`src/pdf_extractor.py`) |
| 2 | Prompt interna e taxonomia | feitas e testadas com o Gemini (comparação manual de execuções) |
| 3 | Deteção | feita e ligada ao Gemini pelo gateway Cloudflare |
| 4 | Regras de segurança | feito |
| 5 | Mascaramento | feito |
| 6 | Verificação | feito |
| 7 | Relatório | feito |
| 8 | Avaliação própria | **fora de âmbito** (decisão da equipa): as execuções comparam-se à mão |
| | Ponto de entrada que liga tudo | feito (`src/pipeline.py`), ligado ao Gemini pelo gateway (`src/gateway.py`), testado com o Gemini real |
| | `submission/submission.txt` | refeito com o prompt atual e as instruções iniciais (`user_instructions.txt`), ver "A submissão" abaixo |
| | `submission/prompt.txt` | preenchido: o pedido exato (prompt interno, documento e instruções iniciais); falta confirmar com a NOS que é isto que lá vai |

Sem a deteção, o pipeline já corre no documento do desafio e mascara o que as
regras de segurança apanham (data de nascimento, números de identificação,
telefones, emails, cartão, etc.). Nomes, morada e dados de saúde dependem do
Gemini.

## Documentação

| Documento | Para quê |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Componentes, contrato de dados e estrutura de pastas |
| [DECISIONS.md](DECISIONS.md) | Decisões de desenho, com as razões, e decisões em aberto |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Como instalar, testar e contribuir |
| [REVIEW.md](REVIEW.md) | Revisão manual (texto e áudio): UI, backend, rotas e rejeição com observações |
| [AUDIO.md](AUDIO.md) | Extra: censura de áudio (linha de comandos e rota do backend) |
| [GATEWAY.md](GATEWAY.md) | Como o pipeline chama o Gemini pelo Worker Cloudflare |
| [DETECTION.md](DETECTION.md) | Como a deteção pede e valida a lista de itens |
| [MASKING.md](MASKING.md) | Como o mascaramento trata cada caso |
| [taxonomy.md](taxonomy.md) | Categorias de dados sensíveis |
| [internal_prompt.txt](internal_prompt.txt) | A prompt enviada ao Gemini (versão 4, genérica) |

## Experimentar

Pela linha de comandos, a partir da pasta `submission/solution/src`
(precisa de `pip install PyMuPDF`):

```bash
python pipeline.py ../../../raw_data/document_to_anonymize.pdf --no-model
python pipeline.py ../../../raw_data/document_to_anonymize.pdf --no-model --out saida
```

Sem `--out` é um ensaio: só mostra o resumo (linhas, itens, avisos e
problemas da verificação, nunca valores). Com `--out DIR` escreve
`submission.txt` e `report.md`. `--instructions "..."` (ou
`--instructions-file`) junta as instruções do utilizador, em texto livre (ver
[DETECTION.md](DETECTION.md)), e `--include-values` mostra os valores no
relatório. Saída 0 sem problemas, 1 se a verificação encontrou problemas, 2
em erro. Sem `--no-model`, o Gemini é chamado pelo gateway Cloudflare: defina
`GEMINI_GATEWAY_URL` e
`GEMINI_GATEWAY_ORIGIN` (ver [GATEWAY.md](GATEWAY.md)); sem elas dá erro.

Em código, o `pipeline.run(lines, generate)` faz o mesmo e devolve as linhas
mascaradas, os itens, os avisos, os problemas e o relatório. Passo a passo,
sem o ponto de entrada:

A partir da raiz do repositório, com `pip install PyMuPDF`. Isto corre tudo o
que existe, sem o Gemini:

```python
import sys

sys.path[:0] = ["submission/solution/src"]

import masking
import pdf_extractor
import report
import safety_rules

text = pdf_extractor.extract_and_prepare_text(
    "raw_data/document_to_anonymize.pdf"
)
lines = text.split("\n")

items = safety_rules.find_sensitive(lines)          # 4 regras de segurança
masked, warnings = masking.mask_lines(lines, items)  # 5 mascaramento
markdown = report.build_report(items, warnings)      # 7 relatório

print("\n".join(masked))
print(markdown)
```

No documento do desafio isto dá 60 linhas, 18 itens e 0 avisos.

## Deteção

`detection.detect(lines, generate)` envia ao modelo a prompt interna e o documento
com as linhas numeradas, e valida a resposta em JSON contra o contrato de
dados. O cliente do modelo entra como parâmetro (`generate`), por isso a
deteção já se testa sem o Gemini. Um elemento mal formado fica de fora e gera
um aviso; uma resposta que não seja uma lista JSON é repetida uma vez.
Detalhes em [DETECTION.md](DETECTION.md).

## Regras de segurança

`safety_rules.find_sensitive(lines)` devolve itens com os mesmos campos da
deteção, mais `source: "regex"`. Apanha, entre outros:

- emails, telefones (com e sem indicativo `+351`), endereços web e IP;
- NIF, Cartão de Cidadão e BI, passaporte, Segurança Social, números de
  registo ou cédula profissional (`CRM`, `OA`, `Cédula`...), matrículas;
- data de nascimento, código postal;
- cartão de crédito, validade, CVV, apólice, IBAN;
- identificadores biométricos, **quando têm etiqueta** (`Impressão
  digital: ID-BIO-1`).

Os números só são apanhados com a etiqueta ao lado (`NIF:`), porque um número
de 9 dígitos sozinho pode ser um telefone, um NIF ou uma apólice. Os padrões
mais ambíguos (telefone sem indicativo, matrícula, código postal, endereço
web, IP) têm confiança `provavel`; os outros têm `certo`. Pressupõe texto com
a pontuação original.

## Mascaramento

`masking.mask_lines(lines, items)` devolve `(linhas_mascaradas, avisos)`.

- Cada palavra (separada por espaços) de um valor sensível passa a `*`:
  `Maria Conceição Oliveira Santos` passa a `* * * *`.
- A pontuação nas pontas de cada palavra mantém-se: `Santos,` passa a `*,`.
- A vírgula, o ponto e vírgula e a barra separam palavras mesmo sem espaço:
  `João,Ana` dá `*,*` e `Rui/Ana` dá `*/*`. Entre dois dígitos não separam:
  `1,68m` e `12/03/1978` ficam com um único `*`. Uma data com o mês
  escrito (`12/mar/1978`) é uma só palavra, e um hífen liga duas palavras
  (`Ana-Maria` é uma só: um valor dentro dela mascara-a por inteiro).
- Os espaços e a estrutura das linhas não mudam.
- O item é procurado como **palavra inteira** (`Ana` em `Anabela e Ana` é a
  última palavra, não o início de `Anabela`), na linha indicada, depois nas
  vizinhas e depois no documento todo; só sem palavra inteira se aceita um
  pedaço de palavra. Se não for encontrado, gera um aviso em vez de falhar.
- O mesmo valor é mascarado nas outras ocorrências (por exemplo, "Maria
  Santos" no texto corrido).

Todos os casos, com exemplos, estão em [MASKING.md](MASKING.md).

## Relatório

`report.build_report(items, warnings=None, include_values=False)` devolve o
relatório em Markdown: um resumo (por categoria, origem e confiança), a
tabela dos itens e os avisos. Por defeito **não mostra os valores originais**:
um relatório que lista o nome ocultado deixava de ser anónimo. Para uso
interno, `include_values=True` mostra-os. Se o Gemini e as regras de
segurança apanham o mesmo valor na mesma linha, aparece uma só vez, com as
duas origens e a maior confiança.

## Extra: censura de áudio

Aceita um ficheiro de áudio, transcreve-o com a ElevenLabs Scribe
(timestamps por palavra), corre o mesmo `pipeline.run` sobre a
transcrição, e substitui cada palavra ocultada por um som personalizado
(não silêncio) no áudio. Reaproveita o pipeline de texto sem alterações —
só a transcrição e a redação do áudio são novas. Feito e verificado com a
API real do ElevenLabs na linha de comandos (`audio_pipeline.py`).

O backend da revisão manual tem também a **rota de áudio** (`POST
/api/audio` e `GET /api/audio/current`, ver [REVIEW.md](REVIEW.md)): envia-se
um áudio, ouve-se a versão censurada e rejeita-se com observações, como no
texto, sem voltar a enviar o áudio ao ElevenLabs. Testada com a transcrição e
a censura falsas e com o `ffmpeg` real. A **UI de áudio** existe (envio com
aviso de privacidade, leitor, rejeição e histórico) e foi vista em modo
demonstração; nunca correu com áudio real de ponta a ponta. Nota de
privacidade: o áudio original, ainda com os dados sensíveis, vai para o
ElevenLabs.
Detalhes, decisões e custo estimado em [AUDIO.md](AUDIO.md).

## Como a solução responde aos critérios

| Critério (peso) | Onde está | Estado |
|---|---|---|
| Precisão (10%) | Regras de segurança, prompt, taxonomia | sem avaliação própria (fora de âmbito); comparação manual de execuções |
| Prompt (10%) | [internal_prompt.txt](internal_prompt.txt), [taxonomy.md](taxonomy.md) | testada com o Gemini |
| Qualidade da anonimização (5%) | [MASKING.md](MASKING.md) | formatação preservada; contexto por medir |
| Explicabilidade (5%) | Relatório, campo `reason` de cada item | feito |
| Eficiência (5%) | Uma chamada ao modelo; o resto é código | por medir |
| GitHub (5%) e Colaboração (30%) | Um branch por componente, pull requests com merge commit, testes | ver [DEVELOPMENT.md](DEVELOPMENT.md) |
| Documentação (10%) | Esta pasta | em curso |
| Pitch (20%) | Extra: censura de áudio ([AUDIO.md](AUDIO.md)) | por preparar |

## Problemas conhecidos

- **O áudio passa pelo Worker da Cloudflare e vai para o ElevenLabs**, ainda
  com os dados sensíveis (o Worker não o guarda). Sem o gateway nem uma chave
  o áudio fica desligado e o resto funciona. A transcrição local (Whisper) é
  a evolução que resolveria o problema (ver [DECISIONS.md](DECISIONS.md), 16).
- **O `import fitz` está obsoleto** no PyMuPDF atual; a alternativa é
  `import pymupdf`.

## A submissão

Os três ficheiros da submissão vêm de uma só execução, com o Gemini pelo
gateway:

| Ficheiro | O que é |
|---|---|
| `submission/submission.txt` | o documento do desafio, mascarado |
| `submission/prompt.txt` | o pedido exato: o prompt interno ([internal_prompt.txt](internal_prompt.txt)), o documento com os números de linha e as instruções iniciais, pela ordem em que o gateway os recebe |
| [user_instructions.txt](user_instructions.txt) | as instruções iniciais do utilizador, o texto entre `<user_instructions>` |

As instruções iniciais pedem para mascarar também **toda a informação de saúde**
(o notebook dos organizadores trata-a como sensível) e as datas e durações que
fazem parte de um facto sensível ("desde 2018", "há 5 anos", "parou há 3
anos"), e deixam como estão os cabeçalhos das secções, as etiquetas, o título, a data
do relatório e a referência, como no exemplo oficial. Só **acrescentam**
máscaras; o Sexo fica visível porque não consta da lista dos organizadores.

Para refazer a submissão, a partir de `submission/solution/src`:

```bash
export GEMINI_GATEWAY_URL=... GEMINI_GATEWAY_ORIGIN=...
python pipeline.py ../../../raw_data/document_to_anonymize.pdf \
    --instructions-file ../user_instructions.txt --out saida
cp saida/submission.txt ../../submission.txt
```

Depois, o `prompt.txt` tem de voltar a ser o pedido exato. O teste
`tests/test_submission_prompt.py` falha se o prompt interno, o documento ou as
instruções mudarem e o ficheiro ficar desatualizado.

**Medido (3 execuções):** 95, 96 e 95 itens e 203, 204 e 203 `*`, sem avisos
nem problemas na verificação, com as datas e durações dos factos sensíveis
sempre mascaradas. Sem as instruções, o mesmo documento deu entre 182 e 204
`*` e deixava anos como "desde 2018" visíveis. O modelo não é determinístico:
outra execução pode diferir em poucas palavras (por exemplo "mulher").

**Limites:** o backend de revisão arranca a primeira versão sem instruções (só
as rejeições seguintes as levam), por isso esta submissão sai da linha de
comandos e não da UI. O pedido real ao gateway leva ainda o esquema JSON de
resposta (`response_format`), que não está em `prompt.txt`.

## Pontos em aberto

- Confirmar com a NOS que `submission/prompt.txt` pode conter o pedido exato
  (prompt interno, documento e instruções iniciais), uma vez que o documento
  final é produzido pelo código a partir do JSON. Está preenchido assim.
- Confirmar com a NOS onde entregar o relatório explicativo: o guia de
  submissão só pede `submission.txt`, `prompt.txt` e o código.
- Decisões da taxonomia (exames e sintomas, sexo ou género, nome da
  organização): ver o fim de [taxonomy.md](taxonomy.md).
- Mais em [DECISIONS.md](DECISIONS.md).
