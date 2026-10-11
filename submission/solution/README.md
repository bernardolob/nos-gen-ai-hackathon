# MiniNovers: anonimização de documentos (RGPD)

Ferramenta que deteta dados pessoais e sensíveis num documento e os oculta,
trocando **cada palavra sensível por um `*`** sem mudar mais nada, e explica
num relatório o que ocultou e porquê. Feita no NOS Gen-AI Hackathon.

Funciona com qualquer tipo de documento, não só o do desafio (um relatório de
admissão hospitalar fictício). O utilizador revê o resultado e **aprova ou
rejeita**, e pode escrever instruções do tipo "mascara também o nome da
clínica" ou "não mascares a informação médica".

## O que faz

| Entrada | O que sai |
|---|---|
| Texto e PDF | o texto com `*`, o PDF anonimizado e um relatório |
| Áudio | o áudio com cada palavra sensível trocada por um som |
| Fotografia | a imagem com as zonas sensíveis desfocadas |
| Vídeo | o vídeo com as zonas sensíveis desfocadas (só a imagem, não o som) |

Tudo se revê numa interface web, que também deixa escolher entre seis temas de
cor e o modo claro ou escuro.

## Como funciona

```
Documento -> Gemini deteta + regras de segurança -> o código mascara
          -> verificação -> resultado + relatório -> revisão na UI
```

- **O modelo deteta, o código mascara.** O Gemini só devolve a lista do que é
  sensível; quem escreve os `*` é o código, por isso a formatação nunca
  depende do modelo.
- **Regras de segurança** (NIF, email, telefone, cartão...) apanham o que o
  modelo falhar e correm sem ele.
- **As chaves não vão para o browser.** Um Worker da Cloudflare guarda as
  chaves do Gemini e do ElevenLabs e deixa qualquer pessoa usar a ferramenta
  sem ter uma.
- O critério do prompt é a **reidentificação**: é sensível o que, sozinho ou
  com o resto do documento, pode identificar uma pessoa ou revelar
  informação sensível sobre ela.

## O projeto em retrospetiva

### Desafios

- **As chaves de API:** conservar a segurança mas permitir o uso. A solução
  foi um Worker da Cloudflare que guarda as chaves e limita os pedidos.
- **Perda de código** nas partes relacionadas com os vídeos.
- **Eficiência de tokens** no Gemini: cache do contexto e respostas mais
  curtas.
- **O prompt interno:** preservar bem o RGPD e saber que informação mascarar.
  Chegámos a um critério de reidentificação, em vez de uma lista fixa.

### O que correu bem

- **O quadro branco partilhado** como meio de organização.
- **O trabalho em equipa:** a delegação de trabalho e o empenho do grupo.
- **O brainstorming** e a preparação, os primeiros passos.
- **Documentação logo desde o início.**

<!-- Fotografias do quadro branco: pôr os ficheiros em docs/whiteboard/ e
     ligá-los aqui com ![descrição](docs/whiteboard/ficheiro.jpg) -->

### O que correu menos bem

- **Alguns merges:** a falta de atenção deu problemas que só apareceram mais
  à frente.
- **Faltaram testes periódicos** de algumas funcionalidades específicas.

### O que ficou por fazer

- Um design da interface mais cuidado.
- **Censurar o áudio dos vídeos.** Hoje só se censura a parte visual.
- **Censurar as imagens dentro dos PDFs.**
- Uma deteção automática melhor em vídeos e imagens.

## Como correr

Precisa de Python 3.10+, Node.js e, para áudio e vídeo, do `ffmpeg`. O
backend usa o Worker da Cloudflare (ver [GATEWAY.md](GATEWAY.md)), por isso
não precisa de nenhuma chave nas mãos.

```bash
# backend, a partir de submission/solution
pip install -r requirements.txt
export GEMINI_GATEWAY_URL=<endereço do Worker>
export GEMINI_GATEWAY_ORIGIN=http://localhost:5173
PYTHONPATH=src python src/user_validation.py      # http://127.0.0.1:8000

# interface, a partir de submission/solution/Lovable_UI_JunctionX
npm install && npm run dev                         # http://localhost:5173
```

Pela linha de comandos também dá para anonimizar um ficheiro sem a interface;
ver [SOLUTION.md](SOLUTION.md), "Experimentar".

## Documentação

[SOLUTION.md](SOLUTION.md) é o ponto de entrada. Daí chegam-se aos outros:

| Para saber | Ler |
|---|---|
| Como está organizado | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Como se deteta e se decide o que mascarar | [DETECTION.md](DETECTION.md), [taxonomy.md](taxonomy.md) |
| A revisão e a interface | [REVIEW.md](REVIEW.md) |
| Áudio, imagem e vídeo | [AUDIO.md](AUDIO.md), [MEDIA.md](MEDIA.md) |
| As chaves e o Worker | [GATEWAY.md](GATEWAY.md), [CLOUDFLARE.md](CLOUDFLARE.md) |
| Porque decidimos assim | [DECISIONS.md](DECISIONS.md) |
| Preparar o ambiente e testar | [DEVELOPMENT.md](DEVELOPMENT.md) |
