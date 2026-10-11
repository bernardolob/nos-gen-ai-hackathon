# Desenvolvimento

Como instalar, testar e contribuir. O resumo do projeto está no
[SOLUTION.md](SOLUTION.md).

## Preparar o ambiente

Python 3.10 ou superior (é a versão do lint no GitHub).

```bash
pip install -r submission/solution/requirements-dev.txt
```

Para só o núcleo (regras de segurança, mascaramento, relatório) basta o
PyMuPDF (extração do PDF) e o `flake8`: o resto usa a biblioteca padrão. O
backend da revisão precisa do `fastapi`, do `uvicorn` e do `httpx`; a saída em
PDF, de imagem e de vídeo precisam do PyMuPDF, do Pillow e do OpenCV (tudo em
`requirements.txt`), e o vídeo e o áudio do `ffmpeg` (ver abaixo). A UI precisa
do Node.js (`npm install` na pasta da UI).

### Chave do Gemini

Só vai ser precisa para a deteção. Cria uma em
[Google AI Studio](https://aistudio.google.com/) e exporta-a no terminal:

```bash
export GEMINI_API_KEY="a-tua-chave"
```

PowerShell:

```powershell
$env:GEMINI_API_KEY = "a-tua-chave"
```

**Nunca** a coloques em ficheiros, em argumentos de linha de comandos, em
notebooks nem em *commits*. Uma chave que tenha ido para um *commit* ou para o
chat tem de ser revogada. O ficheiro `.env` está no `.gitignore`.

### Extra: censura de áudio

Só é preciso para `audio_pipeline.py` e para a rota de áudio do backend de
revisão (`/api/audio`, ver [AUDIO.md](AUDIO.md) e [REVIEW.md](REVIEW.md)); o
resto do projeto não depende disto. Sem o gateway (nem uma chave) ou sem o
`ffmpeg`, o backend arranca na mesma, com a rota de áudio desligada
(`audio_enabled` falso no estado).

- **`ffmpeg`** (e o `ffprobe`) instalado no sistema (binário, não um pacote
  Python) — o `audio/redactor.py` chama-o diretamente por `subprocess`. No
  Windows: `winget install Gyan.FFmpeg`; o PATH só se atualiza num terminal
  novo. Sem ele, os testes de áudio que o usam saltam-se.
- **A transcrição.** O normal é o **gateway da Cloudflare**: com
  `GEMINI_GATEWAY_URL` e `GEMINI_GATEWAY_ORIGIN` (os mesmos do Gemini, acima)
  não precisa de mais nada, porque a chave do ElevenLabs é um segredo do
  Worker (ver [DECISIONS.md](DECISIONS.md), 16). Só para desenvolvimento
  local pode usar a sua, que tem prioridade, e nunca a ponha no repositório:

```bash
export ELEVENLABS_API_KEY="a-tua-chave"   # opcional
```

## Lint

O workflow `lint.yml` corre `flake8 .` em cada push e em cada pull request,
com as regras por defeito (79 colunas). Antes de fazer push:

```bash
python -m flake8 .
```

Sem mensagens, está conforme. Erros comuns: linhas com mais de 79 caracteres,
imports não usados, espaços no fim da linha e falta de duas linhas em branco
entre funções.

## Testes

A partir da raiz do repositório:

```bash
python -m unittest discover -s submission/solution/tests -v
```

Cobrem as regras de segurança, o mascaramento e o relatório, e só precisam da
biblioteca padrão. O `pytest` também os corre
(`python -m pytest submission/solution/tests`) e passa a ser preciso quando
entrarem os testes do cliente do Gemini.

Os testes da UI correm na pasta `Lovable_UI_JunctionX` com `npx vitest run`
(e `npx tsc --noEmit`). Os de imagem e vídeo (`tests/test_media.py`) usam o
OpenCV e o Pillow; o que grava um vídeo precisa do `ffmpeg`.

Os testes de `audio/redactor.py`, de `audio_pipeline.py` e da rota de áudio
(`tests/test_audio_route.py`) que escrevem áudio a sério precisam do `ffmpeg`
instalado; sem ele, saltam-se sozinhos, não falham. Os restantes testes da
rota de áudio usam a transcrição, o modelo e o `ffmpeg` falsos, por isso
correm em qualquer máquina (precisam do `pytest`, do `fastapi` e do
`httpx`).

### Publicar o Worker da Cloudflare

O Worker (`cloudflare/worker.ts`) tem de ser publicado de cada vez que muda: o
esquema da resposta, a rota do áudio e as de imagem e vídeo só existem depois
disso. A partir da raiz do repositório, com `npm install` feito:

```bash
npx wrangler login            # uma vez; no PowerShell use npx.cmd
npx wrangler deploy
```

Quem publica tem de ter permissão de **escrita** na conta da Cloudflare onde
está o Worker (não chega ser membro com leitura: o `wrangler` falha com 403).
Com várias contas, indique-a em `CLOUDFLARE_ACCOUNT_ID`. Para confirmar:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/octet-stream" --data-binary "" \
  https://nos-gemini-gateway.jnhorta05.workers.dev/api/v1/audio/transcribe
```

Dá 413 (corpo vazio) se a rota do áudio existe, e 404 se o Worker é antigo.

## Correr o código à mão

Os módulos importam-se pelo nome (`import masking`), por isso é preciso pôr
`src/` no caminho. Num script:

```python
import sys

sys.path[:0] = ["submission/solution/src"]
```

Em linha de comandos, o `PYTHONPATH` separa-se com `:` em Linux e macOS e com
`;` no Windows. Há um exemplo completo no [SOLUTION.md](SOLUTION.md).

## Fluxo de trabalho com Git

- **Todo o código fica em `submission/solution/`** (código em `src/`, testes em
  `tests/`). Não crees `submission/src/` nem pastas de código fora desta.
- **Um branch por componente**, criado a partir da `main`:
  `feature/<componente>` (por exemplo `feature/masking`).
- **Nada vai direto para a `main`.** Cada branch entra por pull request, com
  revisão de outra pessoa da equipa.
- **Pela ordem do pipeline.** Os pull requests abrem-se na ordem dos
  componentes (1 extração, 2 prompt e taxonomia, 3 deteção, 4 regras, 5
  mascaramento, 6 verificação, 7 relatório). Depois de cada merge, atualiza o
  branch seguinte com `git merge origin/main`, resolve os conflitos nele e só
  então abre o seu pull request. Os conflitos mais prováveis estão na
  documentação (`SOLUTION.md` e `ARCHITECTURE.md`).
- **Merge commit, não *squash*.** Assim a `main` guarda os commits de cada
  pessoa, que contam para a colaboração.
- **Commits pequenos e com mensagem clara**, no imperativo
  (`Add masking module`).
- **Testes e documentação com cada alteração.** Se mudas o comportamento de
  um módulo, atualiza o seu documento (por exemplo [MASKING.md](MASKING.md)).
- **Pull requests apontam à `main` do repositório da equipa**, não ao
  repositório oficial. A descrição diz o que muda, o que foi testado e o que
  falta rever.

### Verificações do GitHub

Em cada pull request para a `main` correm três workflows: `Lint Python Code`,
`Hackathon Evaluation` e `Prompt Evaluation`. Os dois últimos são da
organização e usam segredos que não vemos (a avaliação do
`submission/submission.txt` e da `submission/prompt.txt`). Só o lint é
nosso para corrigir.

### Identidade do Git

Define-a só neste repositório, sem tocar na configuração global:

```bash
git config user.name "O Teu Nome"
git config user.email "o-teu-email@exemplo.com"
```

Usa um email que esteja associado à tua conta do GitHub (Settings → Emails). Se
não estiver, os commits não aparecem como teus nem contam nas tuas
contribuições. Quem os faz com ferramentas automáticas (como um assistente de
código) deve confirmar que a mensagem não tem uma linha `Co-Authored-By` de
terceiros, para a autoria ficar só de quem os pediu.

## Como acrescentar um componente

1. Cria o branch `feature/<componente>` a partir da `main`.
2. Escreve o módulo em `submission/solution/src/`, com um docstring que diz o
   que recebe e devolve. Usa o mesmo [contrato de dados](ARCHITECTURE.md)
   (números de linha a começar em 1, os campos do item).
3. Escreve os testes em `submission/solution/tests/`.
4. Corre `python -m flake8 .` e os testes.
5. Atualiza o [ARCHITECTURE.md](ARCHITECTURE.md) (tabela de componentes e
   pastas) e o [SOLUTION.md](SOLUTION.md) (estado).
6. Abre o pull request.

## Problemas frequentes

| Sintoma | Causa e solução |
|---|---|
| `flake8` não é reconhecido | Acontece no Windows quando a pasta dos scripts do Python não está no `PATH`. Usa `python -m flake8 .` |
| `ModuleNotFoundError: No module named 'masking'` | `src/` não está no caminho de importação. Ver "Correr o código à mão" |
| `ModuleNotFoundError: No module named 'fitz'` | Falta o PyMuPDF: `pip install PyMuPDF`. Com `python -I` os pacotes instalados com `--user` não são vistos |
| Aviso `The fitz API is deprecated` | É só um aviso do PyMuPDF; a alternativa é `import pymupdf` |
| O `git` não é reconhecido num terminal já aberto | Abre um terminal novo depois de instalar o Git |
| O `git push` falha com `could not read Username` | Falta iniciar sessão no GitHub: `gh auth login` |
| A UI diz "Audio censoring is not available on this server." | O backend não tem como transcrever: falta `GEMINI_GATEWAY_URL` e `GEMINI_GATEWAY_ORIGIN` (ou `ELEVENLABS_API_KEY`), ou falta o `ffmpeg`. Reinicia o backend com essas variáveis; o arranque diz `áudio: ligado` ou `desligado`. Confirma também que a porta 8000 é mesmo este backend |
| Ao enviar áudio, "Não foi possível transcrever o áudio" | O backend não conseguiu falar com o Worker. O backend não mostra o código, por isso testa a rota à mão (abaixo). 404: o Worker publicado não tem a rota de áudio (falta `npm run deploy` a partir de uma branch que a tenha). 403: o `GEMINI_GATEWAY_ORIGIN` não consta de `PUBLIC_APP_ORIGINS`. 429: mais de 5 pedidos por minuto. 502 ou 503: problema com o segredo `ELEVENLABS_API_KEY` ou com o ElevenLabs |

Para testar a rota de áudio do Worker sem a UI (o esperado é 413, porque o corpo vai vazio):

```bash
curl -s -w "\n%{http_code}\n" -X POST -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/octet-stream" --data-binary "" \
  https://nos-gemini-gateway.jnhorta05.workers.dev/api/v1/audio/transcribe
```
