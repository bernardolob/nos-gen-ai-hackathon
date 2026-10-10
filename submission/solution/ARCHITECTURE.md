# Arquitetura (componentes núcleo)

Este documento descreve apenas os componentes núcleo. Os extras (revisão
manual, prompt do utilizador, API e interface) ficam para mais tarde.

## Fluxo

```
PDF -> Extração -> Deteção (Gemini) + Regras de segurança (regex)
    -> Mascaramento -> Verificação -> submission.txt + report.md

Avaliação própria: compara a saída com eval/ground_truth.txt
```

## Componentes

| # | Componente | Ficheiro previsto | Entrada | Saída |
|---|---|---|---|---|
| 1 | Extração | `src/extraction.py` | caminho do PDF | linhas de texto, sem linhas vazias e sem limpar a pontuação |
| 2 | Prompt interna | `internal_prompt.txt` | | instruções enviadas ao Gemini |
| 3 | Deteção | `src/detection.py` | linhas numeradas | lista de itens (`line`, `text`, `category`, `reason`, `confidence`) |
| 4 | Regras de segurança | `src/safety_rules.py` | linhas | itens extra (emails, telefones, cartões, NIF, CVV) |
| 5 | Mascaramento | `src/masking.py` | linhas e itens | texto com `*` no lugar de cada palavra sensível |
| 6 | Verificação | `src/verification.py` | linhas originais e texto mascarado | lista de problemas encontrados |
| 7 | Relatório | `src/report.py` | itens | `report.md` |
| 8 | Avaliação própria | `eval/evaluate.py` | saída e `ground_truth.txt` | precisão e recall por palavra |

## Responsabilidades

1. **Extração.** Lê o PDF com o PyMuPDF e devolve as linhas do texto. Não
   remove acentos nem pontuação (ao contrário do notebook do tutorial).
2. **Prompt interna.** Ver `internal_prompt.txt`. O documento é enviado com as
   linhas numeradas.
3. **Deteção.** Faz a chamada ao Gemini (`temperature=0`) e valida o JSON
   devolvido. A chave vem de uma variável de ambiente e nunca é guardada no
   repositório.
4. **Regras de segurança.** Padrões fixos que apanham o que o modelo deixe
   passar. Também asseguram um mínimo se a API falhar.
5. **Mascaramento.** Localiza cada item na sua linha (ver `SOLUTION.md`), troca
   cada palavra por `*` e mascara as outras ocorrências do mesmo valor. Os
   números de linha nunca chegam ao documento final.
6. **Verificação.** Confirma que:
   - cada linha tem o mesmo número de palavras que o original;
   - as palavras não mascaradas são idênticas às originais;
   - não há linhas vazias;
   - todos os itens foram encontrados no texto.
7. **Relatório.** Para cada item mascarado, indica o texto, a categoria e a
   razão.
8. **Avaliação própria.** Compara com um documento anonimizado à mão, para
   medir o efeito de cada alteração à prompt.

## Estrutura de pastas prevista

```
submission/solution/
  SOLUTION.md
  ARCHITECTURE.md
  taxonomy.md
  internal_prompt.txt
  src/
    extraction.py
    detection.py
    safety_rules.py
    masking.py
    verification.py
    report.py
  eval/
    evaluate.py
```

## Estado

Por agora existe apenas esta documentação. Os ficheiros de código ainda não
foram criados e serão adicionados componente a componente.

Todo o código Python tem de passar o `flake8` (o workflow `lint.yml` corre-o
em cada push).
