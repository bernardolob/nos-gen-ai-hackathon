# Solução

Sistema que deteta e oculta dados pessoais e sensíveis num documento
(RGPD), trocando cada palavra sensível por `*`.

Este README é incremental: vai crescendo com a arquitetura.

## Ficheiros

| Ficheiro | Descrição |
|---|---|
| `taxonomy.md` | Taxonomia de dados sensíveis: categorias, exemplos do documento, o que não ocultar e decisões em aberto. |
| `ARCHITECTURE.md` | Componentes núcleo, fluxo e estrutura de pastas. |
| `internal_prompt.txt` | Prompt interna enviada ao Gemini (versão 2, com linhas numeradas; ainda por testar). |

## Prompt interna

- Pede ao modelo apenas a **lista de itens sensíveis** em JSON
  (`line`, `text`, `category`, `reason`, `confidence` e, opcionalmente,
  `occurrence`). O mascaramento com `*` é feito em código, não pelo modelo.
- O documento vai entre `<document>` e é tratado como dados, nunca como
  instruções.
- Cada linha do documento é enviada numerada (`[7] Nome: ...`). O modelo
  devolve o número da linha de cada item e o código procura o `text` só
  dentro dessa linha. Os números são retirados antes do mascaramento, por
  isso não aparecem no documento final.
- As instruções opcionais do utilizador vão entre `<user_instructions>` e só
  podem acrescentar regras de ocultação.
- As categorias seguem o `taxonomy.md`.

## Regras de segurança (`src/safety_rules.py`)

Padrões fixos (regex) para dados com formato conhecido: emails, telefones com
`+351`, NIF, Cartão de Cidadão, Segurança Social, CRM, data de nascimento,
cartão de crédito, validade, CVV, apólice, IBAN e identificadores
biométricos. `find_sensitive(lines)` devolve itens com os mesmos campos da
deteção (`line`, `text`, `category`, `reason`, `confidence`) mais
`source: "regex"`.

Pressupõe texto com a pontuação original. Os números só são apanhados quando
têm a etiqueta ao lado (por exemplo `NIF:`), porque um número de 9 dígitos
sozinho pode ser um telefone, um NIF ou uma apólice.

## Mascaramento (`src/masking.py`)

`mask_lines(lines, items)` devolve `(linhas_mascaradas, avisos)`.

- Cada palavra (separada por espaços) de um valor sensível passa a `*`:
  `Maria Conceição Oliveira Santos` passa a `* * * *`.
- A pontuação nas pontas de cada palavra mantém-se: `Santos,` passa a `*,` e
  `(João,` passa a `(*,`. Símbolos como `+` e `€` contam como parte da
  palavra.
- Os espaços e a estrutura das linhas não mudam.

### Localização dos itens no código

1. Procurar o `text` na linha indicada (usando `occurrence` quando existir).
2. Se não for encontrado, procurar nas linhas vizinhas e depois no documento
   todo.
3. Se mesmo assim falhar, devolver um aviso (`line`, `text`, `problem`) para
   a verificação e a revisão manual tratarem.
4. Mascarar também as outras ocorrências do mesmo valor (por exemplo,
   "Maria Santos" no texto corrido). Só se aplica a valores com 4 ou mais
   caracteres e quando aparecem como palavra inteira, para não mascarar
   números curtos sem relação.

## Como correr o projeto

Esta secção cresce à medida que os componentes ficam prontos.

### Requisitos

- Python 3.10 ou superior (o workflow de lint usa 3.10).
- Uma chave da API do Gemini, guardada numa variável de ambiente e nunca
  num ficheiro do repositório.

### Verificar o estilo do código (flake8)

O workflow `.github/workflows/lint.yml` corre o `flake8` em cada push e em
cada pull request, por isso todo o código Python tem de o passar. Antes de
fazer push, corre localmente a partir da raiz do repositório:

```bash
pip install flake8
flake8 .
```

Se o comando `flake8` não for reconhecido (acontece no Windows quando a pasta
dos scripts do Python não está no PATH), usa:

```bash
python -m flake8 .
```

Sem nenhuma mensagem de erro, o código está conforme. Os erros mais comuns
são linhas com mais de 79 caracteres, imports não usados, espaços no fim da
linha e a falta de duas linhas em branco entre funções.

### Executar a solução

A fazer: instruções de execução, depois de existir o ponto de entrada.

## Estado

- [x] Taxonomia (rascunho)
- [x] Prompt interna (versão 2, por testar)
- [x] Regras de segurança (regex)
- [x] Mascaramento
- [ ] Testar a prompt no documento real
- [ ] Extração, deteção, verificação, relatório
- [ ] Avaliação própria

## Pontos em aberto

- Confirmar com a NOS que `submission/prompt.txt` pode conter esta prompt,
  uma vez que o documento final é produzido pelo código a partir do JSON.
- Decisões da secção 12 do `taxonomy.md` (datas, referência, sexo,
  especialidade).
