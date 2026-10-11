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
- uma data com o mês escrito (`12/mar/1978`) e um endereço web são uma só
  palavra;
- um hífen entre duas palavras liga-as: `Ana-Maria` é uma só, e um valor
  (`Ana`) dentro dela mascara o nome composto inteiro;
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

O guia de submissão pede o código em `submission/`, e todo o nosso fica em
`submission/solution/` (código em `src/`, testes em `tests/`). **Não há código
fora desta pasta**: dois sítios (`submission/src/` e `submission/solution/src/`)
obrigavam a pôr dois caminhos no `sys.path` e deixavam o repositório com duas
convenções.

O núcleo (regras de segurança, mascaramento, relatório) só usa a biblioteca
padrão; a extração é a única parte que precisa de uma biblioteca externa (o
PyMuPDF), e fica na mesma pasta.

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

### 11. A deteção recebe o cliente como parâmetro

`detection.detect(lines, generate)` não importa nenhum cliente: recebe uma
função `generate(instrução_de_sistema, conteúdo) -> texto`.

- **Porquê:** testa-se sem chave nem rede (`tests/test_detection.py`), e o
  cliente real liga-se com um adaptador pequeno. Se o cliente mudar, só o
  adaptador muda.
- **Um elemento mal formado não deita fora os outros.** Fica de fora e gera um
  aviso; só uma resposta que não seja uma lista JSON é repetida. Deitar fora
  tudo por causa de um elemento perderia proteção; aceitar o elemento
  estragado quebraria o mascaramento.
- **Tolerante na forma, exigente no conteúdo.** Maiúsculas, espaços nas
  pontas, acentos nos ids e `1.0` por `1` não deitam um valor fora: um
  anonimizador que falha em silêncio por uma diferença cosmética é pior do
  que um que a absorve. O `text` passa a ser o que está na linha, para o
  mascaramento o encontrar. O que muda o sentido (categoria desconhecida,
  linha fora do documento, acentos diferentes no valor) continua a ser
  rejeitado, com aviso.
- **Uma lista vazia levanta suspeita.** É válida, mas se as regras de
  segurança apanharam algo, `empty_answer_warnings` avisa.
- **As mensagens nunca repetem a resposta do modelo**, porque pode conter os
  dados sensíveis.
- **Categorias e níveis de confiança numa só definição** (`src/categories.py`),
  usada pela deteção e pelo relatório, em vez de duas cópias.

### 12. A etiqueta do campo não é um valor sensível

`Nome: Rui Pinto` passa a `Nome: * *`: a etiqueta fica visível, como no
exemplo do enunciado. Se o modelo devolver o valor **com** a etiqueta, o
mascaramento oculta-a também (`*: * *`), o que conta como mascarar a mais.

- **Decisão:** tratar o problema na prompt, com um exemplo errado e um certo
  lado a lado na regra 1, e **medir com o Gemini antes de mexer no código**.
  A prompt não dá garantias, mas é a causa; uma correção no código seria uma
  heurística (o que é uma etiqueta?) que pode enganar-se com horas
  (`10:30`) ou endereços (`https:`).
- **Fica pronta, se a medição o justificar:** uma salvaguarda determinística
  que só tira a etiqueta quando o texto começa no início da linha e tem a
  forma `<etiqueta>: <valor>`.

### 13. Uma só definição de "palavra", em `src/words.py`

O mascaramento e a verificação tinham cada um a sua cópia da regra de o que é
uma palavra. Estavam de acordo, mas qualquer mudança numa tinha de ser
repetida à mão na outra, e ao mudar a regra das datas a verificação passava a
marcar como erro o que o mascaramento fez bem.

- **Decisão:** a regra vive num só módulo (`mask_word`, `mask_token`,
  `whole_word_pattern`), que os dois usam. Há um teste que garante que o que o
  mascaramento produz passa sempre na verificação.
- **Porquê agora:** a correção das datas com o mês escrito e dos nomes
  compostos tocava na regra, e fazê-lo em duas cópias seria repetir o erro.

### 14. Um nome composto com hífen mascara-se por inteiro

Se o valor sensível é `Ana` e aparece dentro de `Ana-Maria`, mascara-se
`Ana-Maria` (um só `*`), e não só `Ana` (`*-Maria`).

- **Porquê:** um hífen liga duas palavras numa só, e uma palavra mascara-se
  por inteiro (a regra do enunciado conta palavras). Mascarar só o pedaço
  deixaria `Maria` visível e a palavra incompleta.
- **Custo:** `Maria` fica mascarada sem ter sido apontada. É a parte do mesmo
  nome, por isso é o lado seguro.
- **Só para valores com letras.** Um número não se propaga para dentro de uma
  data (`1234-05-06`) nem de um código (`ID-1234`).
- **O apelido só se mascara se for apontado** (ou se o item for o nome
  completo). O código não sabe o que é o apelido de quem.

### 15. Áudio: transcrever uma só vez por sessão

**O problema.** Na revisão manual, cada rejeição gera uma versão nova. Se
cada uma voltasse a transcrever, o áudio, com os dados sensíveis, seria
enviado outra vez ao ElevenLabs, com custo em créditos e mais exposição.

**A decisão.** A rota de áudio transcreve uma só vez, quando se envia o
áudio, e guarda a transcrição e os tempos das palavras. Cada rejeição repete
só a deteção e a censura (`audio_pipeline.run_transcript`), sempre a partir do
áudio original guardado numa pasta temporária privada, que se apaga ao
substituir o documento, ao fechar a sessão e ao sair do servidor.

**O que se perde.** O histórico guarda só o texto das versões rejeitadas, não
o seu áudio. E se a transcrição estiver errada, rejeitar não a corrige: é
preciso enviar o áudio outra vez.

### 16. A chave do ElevenLabs é do servidor, não do utilizador

**O problema.** A censura de áudio precisa de transcrever o áudio, e o
ElevenLabs Scribe exige uma chave de API. Quem usa a UI não deve ter de a
ter, nem de a ver.

**Os caminhos considerados**

| Caminho | Prós | Contras |
|---|---|---|
| **1. A chave no servidor** (`ELEVENLABS_API_KEY`) | o mais simples; o utilizador não vê nem precisa de nada | quem corre o backend precisa de uma chave |
| 2. Um Worker da Cloudflare para o ElevenLabs, como o do Gemini | a chave fica na Cloudflare; o backend só conhece um endereço | o áudio passa também pela Cloudflare; limites de tamanho; mais uma peça |
| 3. Transcrição local (Whisper) | sem chave; o **áudio nunca sai da máquina** | descarregar um modelo (centenas de MB); mais lento sem placa gráfica |
| 4. O utilizador cola a sua chave na UI | nenhuma infraestrutura | a chave fica no navegador: mais um dado sensível a proteger |

**A decisão.** O caminho 1. Serve a demonstração e o pitch: nós ligamos o
backend com a nossa chave e quem experimenta a UI não precisa de nada. O
caminho 4 rejeita-se. Os caminhos 2 e 3 ficam como evolução; o 3 é o que
resolve também o problema de privacidade, porque hoje o áudio original,
ainda com os dados sensíveis, vai para o ElevenLabs (ver [AUDIO.md](AUDIO.md)).

**O que se perde.** Sem a chave, o backend arranca na mesma mas o áudio fica
desligado (`audio_enabled` falso) e a UI bloqueia o envio com "Audio censoring
is not available on this server."; o texto e o PDF não são afetados. E cada
pessoa que corra o backend por conta própria precisa da sua chave.

## Decisões em aberto

1. **Normalização Unicode.** Se o Gemini devolver `ç` decomposto (NFD), o
   item não é encontrado. Normalizar para NFC na extração e na deteção.
2. **Revisão manual.** Está prevista (os itens `incerto` iriam a um humano
   antes do mascaramento) mas não implementada. É um requisito opcional do
   enunciado.
3. **Etiquetas incluídas no valor.** Medir com o Gemini quantas vezes
   acontece, mesmo com o exemplo na prompt (decisão 12). Só então decidir se
   a salvaguarda no código vale a pena.
4. **Taxonomia.** Exames e sintomas, sexo ou género, e o nome da organização.
   Ver o fim de [taxonomy.md](taxonomy.md).
5. **Cliente do Gemini e API.** As decisões sobre o modelo fixo, os erros
   sanitizados e a API opcional serão acrescentadas quando o branch
   `feature/api` entrar na `main`.
