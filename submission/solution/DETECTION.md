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

## Limitações

- **Um só pedido por documento.** Documentos longos que não caibam no pedido
  não são divididos. O limite da API opcional (10 000 caracteres por prompt)
  já fica apertado: a prompt interna (cerca de 6 200) e o documento do
  desafio (cerca de 3 000) somam cerca de 9 200.
- **Itens mal formados perdem proteção.** Um elemento rejeitado deixa o valor
  por mascarar; o aviso é a única pista. Convém mostrá-los a quem executa.
- **Não confirma que o texto está na linha.** Se o modelo devolver um valor
  que não está lá, o mascaramento procura-o nas linhas vizinhas e no
  documento todo, e gera um aviso se não o encontrar.
- **Ainda não foi testada com o Gemini.** Os testes usam um cliente falso. O
  cliente real, e o adaptador para ele, estão por fazer.

## Testes

`tests/test_detection.py`, só com a biblioteca padrão:

```bash
python -m unittest discover -s submission/solution/tests -p "test_detection.py" -v
```

Inclui um teste que liga a deteção ao mascaramento e ao relatório com o mesmo
contrato.
