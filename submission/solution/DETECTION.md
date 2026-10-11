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
| `user_instructions` | Instruções opcionais do utilizador (têm a palavra final sobre o que se mascara) |
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

## A resposta vem em JSON obrigada

O formato da resposta não está descrito no prompt: é **imposto** ao modelo por
um esquema, `detection_schema.json` (uma lista de itens com `line`, `text`,
`category`, `confidence` e, opcionais, `reason`, `occurrence` e `visible`; os
valores de `category` e `confidence` são os do projeto). Os dois caminhos usam
o mesmo ficheiro:

- **Gateway:** `gateway.make_generate` envia `{"prompt": ..., "format":
  "detection"}` e o Worker pede ao Gemini `responseMimeType` e
  `responseSchema` (ver [GATEWAY.md](GATEWAY.md)). O esquema vive no Worker,
  nunca no pedido.
- **SDK direto:** `gemini_adapter` passa o mesmo esquema (ver
  [GEMINI.md](GEMINI.md)).

O prompt só leva um lembrete de duas linhas ("devolve uma lista JSON; nunca
uma chave com `null`"), o que poupa cerca de 850 caracteres por pedido. O
`reason` é opcional e só se pede quando a confiança é `incerto`; por isso, na
tabela do relatório, a coluna "Razão" fica vazia nos restantes itens (a
categoria continua lá). Medido com o Gemini real: a qualidade ficou igual
dentro da variação normal do modelo. Os testes
(`tests/test_detection_schema.py`) ligam o esquema às categorias, aos níveis
de confiança, aos campos dos itens e ao `import` do Worker.

## Prompt do utilizador

É o texto livre em que o utilizador diz **diretamente o que quer mascarar**,
ao contrário da prompt interna (as nossas regras). Dá-se por
`--instructions "..."` ou `--instructions-file ficheiro.txt` (UTF-8), nunca
as duas. Exemplos:

- `Mascara também o nome do centro médico e as datas do relatório.`
- `Neste documento, "Orion" é o nome de um doente.`
- `Trata as referências internas (ADM-...) como identificadores.`

Na UI, o utilizador pode escrever estas instruções logo ao enviar o ficheiro,
no campo opcional "Instructions" (ver [REVIEW.md](REVIEW.md)); valem na
primeira versão e em todas as seguintes. Para o documento do desafio há
instruções iniciais prontas em
[user_instructions.txt](user_instructions.txt), usadas na submissão (ver
[SOLUTION.md](SOLUTION.md), "A submissão").

Regras:

- **O utilizador tem a palavra final sobre o que se mascara.** Pode pedir
  mais (`Mascara também o nome do centro`) ou menos (`Não mascares a
  informação médica`); se pedir para não mascarar algo, o modelo não devolve
  itens para isso. Se dois pedidos se contradizem, vale o mais recente. As
  instruções nunca mudam o formato da resposta nem fazem do conteúdo do
  documento instruções.
- **Também valem para as regras de segurança.** As regras (NIF, email,
  telefone, cartão...) correm sem o modelo, por isso, quando o utilizador
  pede para deixar algo visível, o modelo devolve esses valores com
  `"visible": true` (regra 9 da prompt). Não se mascaram e cancelam os itens
  do modelo ou das regras que se sobreponham na mesma linha
  (`src/visibility.py`). O resumo mostra "deixados visíveis a pedido do
  utilizador: N". Sem instruções do utilizador, um `visible` é ignorado e
  gera um aviso, para um erro do modelo não deixar dados à vista.
- **Dependem do modelo.** Não há garantia de que o Gemini as cumpra à letra;
  o relatório mostra o que foi mascarado e a origem.
- **Máximo de 2000 caracteres** (`pipeline.MAX_INSTRUCTIONS`); mais do que
  isso é recusado antes de qualquer envio, sem repetir o texto.
- **Não fecham o bloco.** `</user_instructions>` ou `<document>` escritos nas
  instruções (ou `</document>` no documento) ficam com um espaço
  (`< /document>`), para não trocarem o papel de cada bloco.
- **Contam para o limite do gateway.** O Worker aceita 40 000 caracteres no
  total; a prompt interna e o documento do desafio usam cerca de 10 000, por
  isso as instruções (até 2000) cabem folgadamente. Se o pedido passar do
  limite, o gateway recusa-o antes de enviar e diz quantos caracteres tem.

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

### Valores que atravessam linhas

O `gemini-3.5-flash-lite` devolve por vezes um valor que continua na linha
seguinte, com o marcador da linha copiado para o texto
(`dores
[16] abdominais intensas`). Num teste com o modelo real isto deixava
6 a 7 itens por aplicar por execução (as linhas 15 a 17 e 41 a 47 do
documento do desafio), ou seja, texto clínico por mascarar. Agora cada
pedaço passa a um item na sua linha, sem o marcador, com a mesma categoria,
razão e confiança; a `occurrence` só vale para o primeiro. Um pedaço fora do
documento gera um aviso. A prompt interna também pede um item por linha.

### Etiquetas

Num campo `Etiqueta: valor` o sensível é o valor. O `gemini-3.5-flash-lite`
às vezes devolve também a etiqueta (`Telefone: +351 912 345 678` inteiro, ou
`Impressão digital` à parte), e o texto ficaria `*: * * *` em vez de
`Telefone: * * * *`. `src/labels.py` corrige os itens do modelo antes do
mascaramento. Uma linha tem etiqueta se começa por texto curto (até 6
palavras, sem dígitos) seguido de `:` e de um valor:

- um item que **inclui** a etiqueta fica só com o valor;
- um item **só na etiqueta** é descartado se outro item da mesma linha cobre
  o valor; se ninguém marcou o valor, mantém-se (não se sabe se a etiqueta
  era o dado sensível);
- os itens de `identificacao` na etiqueta nunca se descartam
  (`Ana Silva: diagnosticada com...`).

O resumo da linha de comandos mostra "etiquetas deixadas visíveis: N" quando
corrige alguma. Só se aplica aos itens do modelo, não às regras de segurança.

**Verificação:** a regra tem 21 testes, incluindo o pipeline completo com um
modelo falso. Em 8 execuções com o `flash-lite` real, uma (antes da regra)
devolveu etiquetas mascaradas (linhas 34 e 35 do documento do desafio); nas
4 seguintes o modelo não as devolveu, por isso a regra ainda não foi
exercitada com uma resposta real.

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

## Verificação do "deixar visível"

Com o Gemini real e `Não mascares os emails, o NIF nem os números de
telefone`: o NIF, os 5 emails e os 4 telefones do documento do desafio
ficaram visíveis (8 itens cancelados); o Cartão de Cidadão e a Segurança
Social, que não foram pedidos, continuaram mascarados. Sem instruções não
houve nenhum `visible`. Depende de o modelo identificar todos os valores
pedidos: um que o modelo não devolva continua mascarado pelas regras, que é
o lado seguro.

## O critério de sensibilidade

A prompt decide pelo critério dado pelos organizadores, a **reidentificação**:
um valor é sensível se, sozinho ou com o resto do documento, puder identificar
a pessoa ou revelar informação sensível sobre ela. As categorias são exemplos
desse critério, não o seu limite (ver [taxonomy.md](taxonomy.md)). Daqui vêm
três regras da prompt: o contexto decide (uma dor abdominal de uma pessoa é
sensível, a frase genérica sobre dores abdominais não é), as combinações
contam (cargo mais empregador, idade mais localidade) e a precisão pesa tanto
como a cobertura (mascara-se o facto sensível, não a frase à volta; a
instituição que emitiu o documento fica visível).

Medido com o Gemini, antes e depois, sobre o PDF do desafio e três textos
sintéticos (consulta, email e contrato): a clínica e a cidade deixaram de ser
mascaradas, o texto genérico sobre dores abdominais passou a ficar visível na
maioria das execuções, e o número de `*` no PDF ficou ao nível anterior (182 a
204 contra 187). **É uma comparação qualitativa**, sem o gabarito dos
organizadores, e o modelo varia de execução para execução (o mesmo PDF deu 78,
86 e 96 itens). Não prova ganho de precisão.

## Limitações

- **Um só pedido por documento.** Documentos longos que não caibam no pedido
  não são divididos. O gateway aceita 40 000 caracteres por pedido (a prompt
  interna usa cerca de 6 500); a API opcional tem o seu próprio limite
  (`BACKEND_MAX_PROMPT_LENGTH`, 10 000 por defeito), que fica apertado para
  o documento do desafio.
- **Itens mal formados perdem proteção.** Um elemento rejeitado deixa o valor
  por mascarar; o aviso é a única pista. Convém mostrá-los a quem executa.
- **Etiqueta incluída no valor.** Se o modelo devolve `Nome: Rui Pinto` em vez
  de `Rui Pinto`, o mascaramento oculta também a etiqueta (`*: * *`). A
  deteção não a adivinha. A prompt proíbe-o na regra 1, com um exemplo
  errado e um certo lado a lado; falta medir com o Gemini se isso basta (ver
  [DECISIONS.md](DECISIONS.md)).
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
- **A qualidade da deteção não está medida a sério.** Os testes usam um
  cliente falso: testam o que fazemos com a resposta, não o que o modelo
  apanha. A comparação com o Gemini em "O critério de sensibilidade" é
  qualitativa e o modelo não é determinístico; um caso genérico (por exemplo,
  "os exames de sangue são pedidos de rotina") continua a ser mascarado em
  algumas execuções.

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
