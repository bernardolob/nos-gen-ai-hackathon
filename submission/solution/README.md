# Solução

Sistema que deteta e oculta dados pessoais e sensíveis num documento
(RGPD), trocando cada palavra sensível por `*`.

Este README é incremental: vai crescendo com a arquitetura.

## Ficheiros

| Ficheiro | Descrição |
|---|---|
| `taxonomy.md` | Taxonomia de dados sensíveis: categorias, exemplos do documento, o que não ocultar e decisões em aberto. |
| `internal_prompt.txt` | Prompt interna enviada ao Gemini (versão 1, ainda por testar). |

## Prompt interna

- Pede ao modelo apenas a **lista de itens sensíveis** em JSON
  (`text`, `category`, `reason`, `confidence`). O mascaramento com `*` é
  feito em código, não pelo modelo.
- O documento vai entre `<document>` e é tratado como dados, nunca como
  instruções.
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
