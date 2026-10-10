# Decisões de desenho

O que decidimos, porquê, e o que ficou em aberto. Serve a quem entra no
projeto e a quem avalia a solução (explicabilidade e qualidade técnica).

## Decisões tomadas

### 1. O modelo deteta; o código mascara

O Gemini devolve só a lista dos valores sensíveis (em JSON). Os `*` são
escritos pelo código (`src/masking.py`).

- **Porquê:** a formatação e o número de asteriscos ficam exatos e testáveis,
  e não dependem de o modelo contar bem palavras. Cada passo falha de forma
  isolada e visível.
- **Alternativa rejeitada:** pedir ao modelo o documento já anonimizado. É mais
  simples, mas o modelo reescreve, troca palavras e conta mal.
- **Consequência:** a prompt devolve itens e não o documento final. Falta
  confirmar com a NOS que `submission/prompt.txt` pode conter esta prompt.

### 2. Linhas numeradas e procura na linha

O documento vai ao modelo com cada linha numerada (`[7] Nome: ...`). O
modelo devolve o número da linha de cada item e o código procura o texto só
nessa linha. Se não o encontra, tenta as linhas vizinhas e depois o documento
todo.

- **Porquê:** os modelos contam mal caracteres, por isso não pedimos posições
  (`início`/`fim`). Um número de linha chega para desambiguar.
- **Alternativa rejeitada:** posições em caracteres.

### 3. Um `*` por palavra, e o que é uma palavra

Regra do enunciado: um `*` por cada palavra anonimizada. Concretizamos assim
(detalhes em [MASKING.md](MASKING.md)):

- as palavras separam-se por espaços;
- a vírgula, o ponto e vírgula e a barra também separam, mesmo sem espaço
  (`João,Ana` dá `*,*`), exceto entre dois dígitos (`1,68m`, `12/03/1978`);
- a pontuação nas pontas mantém-se (`Santos,` dá `*,`);
- o hífen e os endereços web não separam;
- um símbolo isolado (`-`) não é uma palavra.

- **Porquê:** `João,Ana` e `João, Ana` são o mesmo conteúdo e devem dar o
  mesmo número de asteriscos. A exceção dos dígitos evita partir números e
  datas.
- **Limite:** o ficheiro-alvo da NOS é secreto. Não sabemos se conta a
  pontuação; é a leitura mais natural da regra.

### 4. Genérico, não só médico

Nada no desafio limita o sistema a dados médicos. A prompt, a taxonomia e as
regras de segurança não têm nada específico do documento do desafio. O que é
específico de um documento ou de uma organização (por exemplo, mascarar
todas as datas) vai nas **instruções do utilizador**, que só podem
acrescentar regras, nunca relaxá-las.

- **Consequência:** as datas de eventos e os números de referência não se
  mascaram por defeito, o que coincide com o exemplo do enunciado.

### 5. Nove categorias com ids fixos

`identificacao`, `saude`, `genetico`, `biometrico`,
`origem_religiao_politica`, `financeiro`, `familia`, `comportamento`,
`quasi_identificador`. Seguem as categorias da análise da própria NOS no
notebook do tutorial, e os artigos 4 e 9 do RGPD.

- **Porquê ids fixos:** a prompt, o código e o relatório partilham-nos. Mudar
  um obriga a mudar os três.

### 6. O relatório não revela o que foi ocultado

Por defeito o relatório mostra linha, categoria, razão e número de palavras,
mas não o valor. Um relatório que lista "Maria Conceição Oliveira Santos"
deixava de ser anónimo.

- **Para uso interno:** `build_report(..., include_values=True)`.

### 7. Regras de segurança como rede de segurança

As regras (regex) correm sempre, mesmo com o Gemini.

- **Porquê:** apanham o que o modelo deixe passar, são determinísticas e
  garantem um mínimo se a API falhar.
- **Números só com etiqueta:** um número de 9 dígitos sozinho pode ser
  telefone, NIF ou apólice. Por isso `NIF:`, `CVV` e semelhantes são
  exigidos. Os padrões ambíguos (telefone sem indicativo, matrícula, código
  postal, URL, IP) têm confiança `provavel`.
- **Sobreposições:** se dois padrões apanham o mesmo valor, fica o mais
  comprido (um IBAN não gera também um falso cartão).
- **Identificadores biométricos:** só com etiqueta, porque o formato muda de
  sistema para sistema.

### 8. Tudo em `submission/solution/`

O guia de submissão pede o código em `submission/`. O núcleo (regras de
segurança, mascaramento, relatório) só usa a biblioteca padrão. A extração
está à parte, em `submission/src/`, por ser a única parte que precisa de uma
biblioteca externa (o PyMuPDF).

### 9. 79 colunas

O `lint.yml` da organização corre `flake8 .` com as regras por defeito.
Mantemos o código dentro das 79 colunas em vez de acrescentar um `.flake8` que
mudava a regra para todos.

### 10. Integração incremental

Cada componente vive num branch próprio e entra na `main` por pull request,
pela ordem do pipeline, com **merge commit** (e não *squash*) para o histórico
guardar os commits de cada pessoa. Antes de cada merge atualiza-se o branch
com a `main` e confirma-se o lint e os testes. Ver
[DEVELOPMENT.md](DEVELOPMENT.md).

## Decisões em aberto

1. **Uma só definição de "palavra" para o mascaramento e a verificação.** A
   verificação (em desenvolvimento) tem a sua cópia da regra e discorda do
   mascaramento em palavras coladas (`João,Ana`). Proposta: um módulo
   partilhado (por exemplo `src/words.py`) com a lista de separadores e a
   função que mascara uma palavra, usado pelos dois. Tem de estar resolvido
   antes de juntar a verificação.
2. **Onde fica a extração.** Está em `submission/src/pdf_extractor.py` e o
   resto em `submission/solution/src/`. Mover para o mesmo sítio simplifica
   as importações.
3. **Normalização Unicode.** Se o Gemini devolver `ç` decomposto (NFD), o
   item não é encontrado. Normalizar para NFC na extração e na deteção.
4. **Revisão manual.** Está prevista (os itens `incerto` iriam a um humano
   antes do mascaramento) mas não implementada. É um requisito opcional do
   enunciado.
5. **Taxonomia.** Exames e sintomas, sexo ou género, e o nome da organização.
   Ver o fim de [taxonomy.md](taxonomy.md).
6. **Cliente do Gemini e API.** As decisões sobre o modelo fixo, os erros
   sanitizados e a API opcional serão acrescentadas quando o branch
   `feature/api` entrar na `main`.
