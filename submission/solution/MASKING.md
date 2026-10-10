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

Um **hífen entre duas palavras** liga-as: `Ana-Maria` é uma só. Por isso, se
o valor sensível é `Ana` e aparece dentro de `Ana-Maria`, mascara-se o nome
composto **inteiro** (ver "Nomes compostos com hífen").

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

Se não encontra o valor tal como está, tenta ainda:

- **sem acentos:** `Conceicao` encontra `Conceição` (o Gemini às vezes tira
  os acentos). A palavra com os acentos certos ganha sempre à sem acentos;
- **partido por uma mudança de linha:** `Rua das Flores` com `Rua das` no fim
  de uma linha e `Flores` no início da seguinte mascara as duas partes.

Se não o encontrar, não falha: devolve um **aviso** (`line`, `text`,
`problem`) e deixa o texto como está. Os avisos vão para o relatório e para a
verificação.

Também geram aviso os itens com texto vazio ou só com espaços.

## Outras ocorrências do mesmo valor

Depois de localizar um item, o módulo mascara também as **outras ocorrências**
do mesmo valor no documento, se:

- aparecem como **palavra inteira** (`Ana` não apanha `Anabela`);
- o valor tem pelo menos **2 caracteres**, quando contém letras, ou pelo menos
  **4**, quando só tem dígitos. Assim um `2` isolado não mascara outros `2`
  sem relação;
- **não é uma palavra isolada a seguir a `Centro`, `Hospital`, `Clínica`,
  `Instituto`, `Universidade`...** (até 3 palavras antes). `Lisboa` marcada na
  morada não mascara o título `Centro Médico Lisboa`. Fica um aviso por cada
  ocorrência deixada de fora, para a revisão humana a ver. Os valores com
  várias palavras ou números propagam-se sempre, e a ocorrência indicada pelo
  modelo é sempre mascarada.

Para valores curtos só com números, usa-se `occurrence` para escolher qual.

### Nomes compostos com hífen

Um nome ligado por hífen é **uma palavra**, e uma palavra mascara-se por
inteiro. Quando o valor sensível (com letras) aparece dentro de um nome
composto, o mascaramento cobre o nome composto todo, e não só o pedaço:

| Itens | `Nome: Ana-Maria Silva` e `Mãe: Ana` |
|---|---|
| só `Ana` | `Nome: * Silva` e `Mãe: *` |
| `Ana-Maria Silva` (o nome completo) | `Nome: * *` e `Mãe: Ana` |
| `Ana-Maria Silva` e `Ana` | `Nome: * *` e `Mãe: *` |
| `Ana` e `Silva` | `Nome: * *` e `Mãe: *` |

Valem as mesmas regras para o fim do composto (`João-Ana`), para compostos
com mais partes (`Ana-Maria-José`) e para os hífens Unicode. Um hífen que
não liga duas palavras (`Ana - Maria`, `- Ana`, `Ana-`) não alarga nada.

**A `Silva` só é mascarada se for apontada.** O código não sabe que `Silva`
faz parte do nome da `Ana`; quem o sabe é o modelo, que deve devolver o nome
completo como um só item. Com o item só `Ana`, fica `Nome: * Silva`.

**Os números são diferentes:** `1234` não se propaga para dentro de
`1234-05-06` nem de um código `ID-1234`, porque um número dentro de uma data
ou de um código é, quase sempre, outra coisa.

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
- **Só se tiram acentos às letras latinas.** Um valor com outro tipo de
  diferença (uma letra trocada) não é encontrado e gera aviso.
- **A lista de palavras de instituição é curta** (`ORGANISATION_WORDS` em
  `masking.py`, português e inglês). Uma instituição sem uma dessas palavras
  (`Lusíadas Lisboa`) ainda propaga o valor.
- **Só os meses conhecidos tornam uma data numa palavra.** `12/mar/1978` dá um
  só `*`, mas uma abreviatura que não esteja na lista (`12/sep./1978` está,
  `12/mrç/1978` não) continua a dar três.
- **O hífen nunca separa.** `Ana-Maria` é uma palavra, mas um intervalo como
  `Lisboa-Porto` também. Se o item é `Lisboa`, mascara-se `Lisboa-Porto`
  inteiro, e `Porto` fica mascarada mesmo que não seja sensível.
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
