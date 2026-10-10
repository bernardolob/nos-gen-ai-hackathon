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

Tudo o resto (ponto, hífen, `@`, `+`, `€`, `:`) **não** separa palavras.

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
| Data com mês escrito | `Data: 12/mar/1978` | `Data: */*/*` |
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

O módulo procura o `text` do item por esta ordem:

1. Na linha indicada em `line` (a n-ésima ocorrência, se houver
   `occurrence`).
2. Nas linhas vizinhas (anterior e seguinte).
3. No documento todo.

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

## Itens sobrepostos

Se dois itens se sobrepõem na mesma linha (por exemplo `Maria Conceição` e
`Conceição Santos`), os intervalos juntam-se e a palavra em comum só é
mascarada uma vez.

## Limitações conhecidas

- **O texto do item tem de coincidir letra a letra com o do documento.** Se o
  Gemini devolver o mesmo texto com os acentos decompostos (Unicode NFD), o
  item não é encontrado e gera um aviso. Convém normalizar para NFC na
  extração e na deteção.
- **A barra entre letras e dígitos separa.** Datas com o mês escrito
  (`12/mar/1978`) dão `*/*/*`, e não um só `*`.
- **O hífen nunca separa.** `Ana-Maria` é uma palavra, mas um intervalo como
  `Lisboa-Porto` também.
- **Os caracteres de pontuação ficam na saída.** Um item como
  `Rua das Flores, 123, Apt 45` mantém as vírgulas: `* * *, *, * *`.
  A pontuação em si não é dado sensível.
- **A verificação tem de usar a mesma definição de palavra.** A versão da
  verificação em desenvolvimento (`feature/verification`) só aceita uma
  palavra mascarada como um `*` com a pontuação nas pontas. Para palavras
  coladas por vírgula, ponto e vírgula ou barra (`João,Ana` dá `*,*`,
  `Rui/Ana` dá `*/*`) marcaria `unexpected_word_change`, apesar de o
  mascaramento estar certo. Com espaço (`João, Ana`) ou entre dígitos
  (`12/03/1978`) não há problema. A correção é as duas partes partilharem uma
  só definição; ver [DECISIONS.md](DECISIONS.md).

## Relação com os outros componentes

- **Recebe** as linhas da extração e os itens da deteção e das regras de
  segurança, todos com o mesmo [contrato de dados](ARCHITECTURE.md).
- **Devolve** as linhas mascaradas e os avisos. O relatório usa os itens e os
  avisos; a verificação confere as linhas.
- Usa só a biblioteca padrão do Python.

## Como testar

Os casos desta tabela estão em `tests/test_masking.py`. Não precisam de
bibliotecas externas:

```bash
python -m unittest discover -s submission/solution/tests -v
```

O guia completo está em [DEVELOPMENT.md](DEVELOPMENT.md).
