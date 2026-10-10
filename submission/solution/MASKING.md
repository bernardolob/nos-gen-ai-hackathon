# Mascaramento: como tratamos cada caso

Este documento explica como o módulo `src/masking.py` decide quantos `*`
escrever e onde. As regras valem para qualquer tipo de documento.

`mask_lines(lines, items)` recebe as linhas do documento (com a pontuação
original) e a lista de itens sensíveis, e devolve `(linhas_mascaradas, avisos)`.
Cada item tem `line` (a contar de 1), `text` e, opcionalmente, `occurrence`.

## Regra geral

**Um `*` por palavra** de cada valor sensível. A estrutura da linha não muda:
os espaços, a pontuação nas pontas e as linhas ficam como estavam.

## O que conta como uma palavra

Uma palavra é uma sequência de caracteres entre separadores. Há duas famílias
de separadores:

1. **Espaços** (um ou vários). Mantêm-se tal e qual na saída.
2. **Vírgula, ponto e vírgula e barra** (`,` `;` `/`), mesmo colados às
   palavras. O separador mantém-se na saída. Exceção: **não separam quando
   estão entre dois dígitos**, porque aí fazem parte de um número ou de uma
   data.

Tudo o resto (ponto, hífen, `@`, `+`, `€`, `:`) **não** separa palavras. Há
duas exceções à regra das barras, que são **uma só palavra** apesar delas:

- os **endereços web** (`https://...`, `www....`);
- as **datas com o mês escrito**: `12/mar/1978`, `12/março`, `mar/1978`. Só
  contam meses verdadeiros, em português ou em inglês (`jan`, `fev`, `março`,
  `sept`...). Uma palavra qualquer entre barras continua a separar:
  `12/xyz/1978` dá `*/*/*` e `Rui/2` dá `*/*`.

Um **hífen entre duas palavras** liga-as: `Ana-Maria` é uma só. Isto conta
também quando se procura o valor no resto do documento (ver "Outras
ocorrências").

A definição vive em `src/words.py`, partilhada com a verificação.

## Tabela de casos

O valor é o texto do item que o módulo recebe. Todos os resultados vêm da
execução do código.

| Caso | Linha original | Resultado |
|---|---|---|
| Várias palavras | `Nome: Maria Conceição Oliveira Santos` | `Nome: * * * *` |
| Número com espaços | `Telefone: +351 912 345 678` | `Telefone: * * * *` |
| Vírgula sem espaço | `Filhos: João,Ana` | `Filhos: *,*` |
| Vírgula com espaço | `Filhos: João, Ana` | `Filhos: *, *` |
| Ponto e vírgula | `Contactos: Rui;Ana;Rita` | `Contactos: *;*;*` |
| Apelido primeiro | `Nome: Santos,Maria` | `Nome: *,*` |
| Barra entre palavras | `Pessoas: Rui/Ana` | `Pessoas: */*` |
| Vírgula entre letra e dígito | `Rua das Flores,123` | `* * *,*` |
| Decimal com vírgula | `Altura: 1,68m` | `Altura: *` |
| Milhares e decimais | `Salário: 2.350,50` | `Salário: *` |
| Data com barras | `Data: 12/03/1978` | `Data: *` |
| Tensão arterial | `Pressão: 145/90 mmHg` | `Pressão: * *` |
| Data com mês escrito | `Data: 12/mar/1978` | `Data: *` |
| Nome composto com hífen | `Nome: Ana-Maria Silva` | `Nome: * *` |
| Email | `Email: ana.silva@x.pt` | `Email: *` |
| Endereço web | `Site: https://www.x.pt/perfil/ana.` | `Site: *.` |
| Símbolo de moeda | `Salário: €62.500` | `Salário: *` |
| Espaços repetidos | `Nome:  Maria   Santos` | `Nome:  *   *` |

## Pontuação

- **Nas pontas de cada palavra, mantém-se.** `Santos,` passa a `*,`;
  `(João,` passa a `(*,`; `Mendes.` passa a `*.`. Caracteres tratados como
  pontuação: `, ; : . ! ? ( ) [ ] { } " '`.
- **Símbolos como `+` e `€` não são pontuação.** Fazem parte da palavra:
  `+351` e `€62.500` passam a um `*`.
- **Um símbolo isolado, sem letras nem dígitos, não é uma palavra.** Em
  `Admissão - Centro` o hífen mantém-se: `* - *`.
- **Títulos como `Dr.` só são mascarados se o item os incluir.** Com o item
  `Carlos Mendes`, `Dr. Carlos Mendes.` passa a `Dr. * *.`.

## Endereços web

Os endereços que começam por `http://`, `https://` ou `www.` são **uma só
palavra**, apesar das barras. O ponto final de uma frase fica de fora:
`https://www.x.pt/perfil/ana.` passa a `*.`.

## Onde está o valor na linha

O módulo procura o `text` do item em duas rondas. Em cada uma, a ordem das
linhas é: a indicada em `line`, as vizinhas (anterior e seguinte) e depois o
documento todo.

1. **Primeiro, como palavra inteira.** `Ana` é a palavra em `Anabela e Ana`,
   não o início de `Anabela`: o resultado é `Anabela e *`. Uma palavra inteira
   numa linha mais longe ganha a um pedaço de palavra na linha indicada.
2. **Só se não houver nenhuma palavra inteira, como pedaço de palavra.** Assim
   o valor fica protegido, mesmo que o resto da palavra fique visível:
   `12345` em `ID12345` dá `ID*`.

Uma "palavra inteira" é uma ocorrência sem letras, dígitos ou `_` colados de
um lado nem do outro. Se o item traz `occurrence`, conta só as ocorrências da
primeira ronda quando as há (`7` na linha `7 e 70 e 7`, com `occurrence` 2, é
o último `7`, não o de `70`). Se pedirem uma ocorrência que não existe, usa-se
a primeira.

Se não o encontrar, não falha: devolve um **aviso** (`line`, `text`,
`problem`) e deixa o texto como está. Os avisos vão para o relatório e para a
verificação.

Também geram aviso os itens com texto vazio ou só com espaços.

## Outras ocorrências do mesmo valor

Depois de localizar um item, o módulo mascara também as **outras ocorrências**
do mesmo valor no documento, se:

- aparecem como **palavra inteira** (`Ana` não apanha `Anabela`);
- o valor tem pelo menos **3 caracteres**, quando contém letras, ou pelo menos
  **4**, quando só tem dígitos. Assim um `2` isolado não mascara outros `2`
  sem relação.

Para valores curtos só com números, usa-se `occurrence` para escolher qual.

### Nomes compostos com hífen

Um valor não se propaga para dentro de um nome ligado por hífen: com o item
`Ana`, a linha `Nome: Ana-Maria Silva` mantém-se e só `Mãe: Ana` é mascarada.
Mascarar só `Ana` deixaria `Maria` visível (`*-Maria`). Se o valor é o nome
composto inteiro (`Ana-Maria Silva`), mascara-se por completo (`* *`). Pela
mesma razão, `1234` não se propaga para dentro de `1234-05-06`.

## Itens sobrepostos

Se dois itens se sobrepõem na mesma linha (por exemplo `Maria Conceição` e
`Conceição Santos`), os intervalos juntam-se e a palavra em comum só é
mascarada uma vez.

## Limitações conhecidas

- **Um pedaço de palavra ainda é mascarado, e a verificação assinala-o.** Se o
  valor só existe dentro de outra palavra (`ID12345`), mascara-se esse
  pedaço, e a verificação marca `unexpected_word_change` porque a palavra
  não ficou mascarada por completo. É um aviso útil: o modelo devolveu um
  valor que não é uma palavra do documento. O mesmo acontece com um valor
  propagado para dentro de uma palavra ligada por símbolos (`€:Ana`).
- **O texto do item tem de coincidir letra a letra com o do documento.** Se o
  Gemini devolver o mesmo texto com os acentos decompostos (Unicode NFD), o
  item não é encontrado e gera um aviso. Convém normalizar para NFC na
  extração e na deteção.
- **Só os meses conhecidos tornam uma data numa palavra.** `12/mar/1978` dá um
  só `*`, mas uma abreviatura que não esteja na lista (`12/sep./1978` está,
  `12/mrç/1978` não) continua a dar três.
- **O hífen nunca separa.** `Ana-Maria` é uma palavra, mas um intervalo como
  `Lisboa-Porto` também. Se o item é só `Ana` e a única ocorrência é
  `Ana-Maria`, mascara-se esse pedaço (`*-Maria`), para o valor ficar
  protegido, e a verificação assinala-o.
- **Os caracteres de pontuação ficam na saída.** Um item como
  `Rua das Flores, 123, Apt 45` mantém as vírgulas: `* * *, *, * *`.
  A pontuação em si não é dado sensível.

## Relação com os outros componentes

- **Recebe** as linhas da extração e os itens da deteção e das regras de
  segurança, todos com o mesmo [contrato de dados](ARCHITECTURE.md).
- **Devolve** as linhas mascaradas e os avisos. O relatório usa os itens e os
  avisos; a verificação confere as linhas.
- A definição de palavra está em `src/words.py`, partilhada com a
  verificação: as duas não podem discordar.
- Usa só a biblioteca padrão do Python.

## Como testar

Os casos desta tabela estão em `tests/test_masking.py`. Não precisam de
bibliotecas externas:

```bash
python -m unittest discover -s submission/solution/tests -v
```

O guia completo está em [DEVELOPMENT.md](DEVELOPMENT.md).
