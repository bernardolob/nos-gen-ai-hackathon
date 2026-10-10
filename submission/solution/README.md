# Solução

Sistema que deteta e oculta dados pessoais e sensíveis num documento
(RGPD), trocando cada palavra sensível por `*`.

Este README é incremental: vai crescendo com a arquitetura.

## Ficheiros

| Ficheiro | Descrição |
|---|---|
| `taxonomy.md` | Taxonomia de dados sensíveis: categorias, exemplos do documento, o que não ocultar e decisões em aberto. |
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

### Localização dos itens no código

1. Procurar o `text` na linha indicada (usando `occurrence` quando existir).
2. Se não for encontrado, procurar nas linhas vizinhas e depois no documento
   todo.
3. Se mesmo assim falhar, registar um aviso e passar o item à revisão manual.
4. Mascarar também as outras ocorrências do mesmo valor (por exemplo,
   "Maria Santos" no texto corrido).
- As instruções opcionais do utilizador vão entre `<user_instructions>` e só
  podem acrescentar regras de ocultação.
- As categorias seguem o `taxonomy.md`.

## Estado

- [x] Taxonomia (rascunho)
- [x] Prompt interna (versão 1)
- [ ] Testar a prompt no documento real
- [ ] Extração, mascaramento, verificação, relatório
- [ ] Avaliação própria

## Pontos em aberto

- Confirmar com a NOS que `submission/prompt.txt` pode conter esta prompt,
  uma vez que o documento final é produzido pelo código a partir do JSON.
- Decisões da secção 12 do `taxonomy.md` (datas, referência, sexo,
  especialidade).
