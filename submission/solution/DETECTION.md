# Deteção (`src/detection.py`)

Ponto 3 do pipeline: pede ao modelo a lista dos valores sensíveis do
documento e valida a resposta. Só usa a biblioteca padrão.

O módulo **não fala com o Gemini**. `detect` recebe o cliente como
parâmetro, uma função `generate(instrução_de_sistema, conteúdo) -> texto`.
Assim a deteção testa-se sem chave nem rede, e o cliente real liga-se com um
adaptador de poucas linhas quando estiver pronto.

## Como se usa

```python
import detection

lines = detection.normalize_lines(lines)          # Unicode NFC, uma vez
items, warnings = detection.detect(lines, generate)
```

| Parâmetro | Descrição |
|---|---|
| `lines` | Linhas do documento, em NFC |
| `generate` | `generate(instrução_de_sistema, conteúdo) -> texto` |
| `user_instructions` | Instruções opcionais do utilizador (só acrescentam regras) |
| `system_prompt` | Prompt a usar; por defeito a `internal_prompt.txt` |
| `attempts` | Tentativas se a resposta não for utilizável (por defeito 2) |

Devolve `(itens, avisos)`. Os itens seguem o
[contrato de dados](ARCHITECTURE.md) e trazem `source: "gemini"`.

## O que envia

- **Instrução de sistema:** o texto de [internal_prompt.txt](internal_prompt.txt).
- **Conteúdo:** o documento com as linhas numeradas a partir de 1, entre
  `<document>` e `</document>`, e, se houver, as instruções do utilizador
  entre `<user_instructions>` e `</user_instructions>`:

```
<document>
[1] Nome: Rui Pinto
[2] NIF: 123456789
</document>

<user_instructions>
Mascara também as datas.
</user_instructions>
```

## O que valida na resposta

A resposta tem de ser uma lista JSON. Tolera um bloco de código à volta e
texto antes ou depois da lista, apesar de a prompt o proibir.

Cada elemento tem de ter:

| Campo | Regra |
|---|---|
| `line` | inteiro entre 1 e o número de linhas (um booleano não conta) |
| `text` | texto não vazio; é normalizado para NFC |
| `category` | um dos 9 ids de [categories.py](src/categories.py) |
| `confidence` | `certo`, `provavel` ou `incerto` |
| `reason` | texto, ou em falta (fica vazio) |
| `occurrence` | opcional; inteiro maior ou igual a 1 |

Os itens repetidos (mesma linha, texto e ocorrência) contam uma só vez.

### Tolerância a diferenças de forma

Um valor não pode ficar por mascarar (nem ser rejeitado) por uma diferença que
não muda o sentido. Por isso:

| O modelo devolve | A deteção faz |
|---|---|
| `"Rui Pinto "` ou `" Rui Pinto"` | tira os espaços das pontas do `text` |
| `"rui pinto"` ou `"RUI PINTO"` | usa o texto que está **na linha** (`Rui Pinto`) |
| `"Rui Pinto"` quando o documento tem `Rui   Pinto` | idem: usa `Rui   Pinto` |
| `category: "IDENTIFICACAO"`, `confidence: "provável"` | ignora maiúsculas, acentos e espaços; guarda o id canónico |
| `line: 1.0`, `occurrence: 2.0` | aceita decimais sem parte fracionária; guarda inteiros |

**Os acentos do `text` têm de coincidir** com os do documento (`Joao` não
reconcilia com `João`), e `line` ou `occurrence` em texto (`"1"`) continuam a
ser rejeitados. Se o valor não está na linha indicada, fica como veio: o
mascaramento procura nas linhas vizinhas e no documento todo.

## Erros e avisos

| Situação | O que acontece |
|---|---|
| A resposta não é JSON, não é uma lista ou está vazia | Tenta de novo, até `attempts` vezes; depois levanta `DetectionError` |
| Um elemento está mal formado | **Fica de fora e gera um aviso**; os outros mantêm-se, e não há nova tentativa |
| O documento está vazio | Devolve `([], [])` sem chamar o modelo |
| O `generate` falha (rede, chave...) | O erro propaga-se sem alteração |

Um aviso tem `index` (posição na resposta), `line`, `text` (se for texto) e
`problem`, no mesmo formato dos avisos do mascaramento, por isso o relatório
mostra os dois juntos.

**As mensagens nunca repetem o que o modelo respondeu**, porque a resposta
pode conter os dados sensíveis. O texto do elemento rejeitado só aparece no
campo `text` do aviso, e o relatório só o mostra com `include_values=True`.

### Lista vazia

Uma lista vazia é uma resposta válida, mas num documento em que as regras de
segurança apanham identificadores quase de certeza que o modelo falhou
(recusou, perdeu o fio, foi cortado). A função
`empty_answer_warnings(itens_do_modelo, itens_das_regras)` devolve um aviso
nesse caso, sem repetir valores. Quem liga os componentes (o ponto de entrada)
deve chamá-la e juntar o aviso aos outros.

## Limitações

- **Um só pedido por documento.** Documentos longos que não caibam no pedido
  não são divididos. O limite da API opcional (10 000 caracteres por prompt)
  já fica apertado: a prompt interna (cerca de 6 200) e o documento do
  desafio (cerca de 3 000) somam cerca de 9 200.
- **Itens mal formados perdem proteção.** Um elemento rejeitado deixa o valor
  por mascarar; o aviso é a única pista. Convém mostrá-los a quem executa.
- **Etiqueta incluída no valor.** Se o modelo devolve `Nome: Rui Pinto` em vez
  de `Rui Pinto`, o mascaramento oculta também a etiqueta (`*: * *`). A
  deteção não a adivinha; a correção é na prompt, que já o proíbe.
- **Resposta cortada.** Um JSON truncado (limite de tokens de saída) dá
  `DetectionError` e a repetição provavelmente trunca de novo. A solução é no
  cliente: pedir resposta em JSON e um limite de saída adequado.
- **Formatos que não aceitamos:** vírgula a mais antes do `]`, aspas simples e
  a lista dentro de um objeto (`{"items": [...]}`). Falham de forma visível e
  a repetição pode resolver.
- **Custo da reconciliação:** cerca de 1,3 s para 50 000 elementos. Para as
  dezenas de itens de uma resposta real é irrelevante.
- **Não adivinha valores.** Se o texto não está na linha, nem sem distinguir
  maiúsculas, fica como veio e o mascaramento procura-o nas linhas vizinhas e
  no documento todo, e gera um aviso se não o encontrar.
- **Ainda não foi testada com o Gemini.** Os testes usam um cliente falso. O
  cliente real, e o adaptador para ele, estão por fazer. Isto quer dizer que
  **a qualidade da deteção em si (o que o modelo apanha) ainda não está
  medida**: o que se testa aqui é o que fazemos com a resposta.

## Testes

`tests/test_detection.py` (65 testes), só com a biblioteca padrão:

```bash
python -m unittest discover -s submission/solution/tests -p "test_detection.py" -v
```

| Grupo | O que verifica |
|---|---|
| Pedido | Numeração das linhas, blocos `<document>` e `<user_instructions>`, a prompt interna |
| Resposta válida | Itens, bloco de código, texto à volta, NFC, ocorrências, duplicados |
| Elementos inválidos | Linha, texto, categoria, confiança, razão e ocorrência inválidos; avisos |
| Normalização | Espaços, maiúsculas, acentos e decimais (`1.0`) |
| Reconciliação | Outras maiúsculas e espaços, valor mascarado de ponta a ponta |
| Lista vazia | Aviso quando as regras apanharam algo e o modelo não |
| Limites conhecidos | JSON truncado, lista dentro de objeto, vírgula a mais, recusa |
| `detect` | Repetição, falha após as tentativas, erros do cliente, mensagens sem a resposta |
| Ponta a ponta | Deteção, mascaramento e relatório com o mesmo contrato |
