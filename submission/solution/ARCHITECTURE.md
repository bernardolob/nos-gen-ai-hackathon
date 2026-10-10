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
| 2 | Prompt interna | `internal_prompt.txt` | | instruções enviadas ao Gemini | feita, por testar |
| 3 | Deteção | `src/detection.py` | linhas numeradas e um cliente | itens e avisos | feito, falta ligar o cliente real do Gemini |
| 4 | Regras de segurança | `src/safety_rules.py` | linhas | itens | feito |
| 5 | Mascaramento | `src/masking.py` | linhas e itens | linhas mascaradas e avisos | feito |
| 6 | Verificação | `src/verification.py` | linhas originais e mascaradas | lista de problemas | feito |
| 7 | Relatório | `src/report.py` | itens e avisos | texto em Markdown | feito |
| 8 | Avaliação própria | `eval/evaluate.py` | saída e documento de referência | precisão e recall por palavra | por fazer |

O cliente do Gemini e uma API HTTP opcional estão em desenvolvimento no branch
`feature/api` e ainda não fazem parte da `main`.

Falta ainda o **ponto de entrada** que liga os componentes (ler o PDF,
chamar cada passo e gravar `submission.txt` e o relatório). Hoje a ligação
faz-se à mão, como se mostra no [SOLUTION.md](SOLUTION.md).

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
8. **Avaliação própria.** Mede o efeito de cada alteração à prompt contra um
   documento anonimizado à mão.

## Estrutura de pastas

```
submission/
  prompt.txt                  (a preencher: a prompt usada)
  submission.txt              (a preencher: a saída do sistema)
  solution/
    SOLUTION.md               ponto de entrada da documentação
    ARCHITECTURE.md           este documento
    DECISIONS.md              decisões de desenho e as razões
    DEVELOPMENT.md            como trabalhar no projeto
    DETECTION.md              deteção e validação da resposta
    MASKING.md                regras do mascaramento
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
    tests/                    testes de tudo o que está acima
```

Por fazer: o cliente real do Gemini para a deteção, `eval/` (8) e o ponto de
entrada.

## Problemas conhecidos

- **O `import fitz` está obsoleto** no PyMuPDF atual; a alternativa é
  `import pymupdf`.
