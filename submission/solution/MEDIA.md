# Anonimização de imagens e vídeos

A revisão manual aceita fotografias e vídeos, além de PDF e texto. A análise
visual só arranca quando existe um modelo explicitamente autorizado para
**imagem, vídeo e saída JSON estruturada**. Não há fallback para um modelo de
texto nem para deteção apenas de rostos.

## Formatos e limites

| Tipo | Formatos | Limite |
|---|---|---|
| Imagem | JPEG, PNG, WebP | 20 MB e 25 megapíxeis |
| Vídeo | MP4, MOV, WebM | 100 MB, 60 segundos e 1920 × 1080 |

O modelo recebe fotografias ou amostras JPEG do vídeo como partes de imagem
reais. O vídeo é amostrado uniformemente até 3 fotogramas por segundo e nas
mudanças de cena, sem esgotar o orçamento antes do fim do ficheiro. Um detetor
OpenCV procura rostos até 10 vezes por segundo. Se
`OPENCV_FACE_DETECTOR_MODEL` apontar para um modelo ONNX YuNet, usa-o; sem esse
ficheiro mantém o Haar cascade offline como fallback. Uma segunda
passagem procura dados residuais depois de aplicar as primeiras ocultações.
Uma falha de qualquer lote interrompe a análise: nunca gera silenciosamente
uma versão parcial.

As regiões cobrem rostos, texto identificável, documentos de identificação,
matrículas, assinaturas, biometria, códigos e outros objetos que possam ligar
o conteúdo a uma pessoa. Os rostos usam caixas justas do detetor facial quando
este encontra uma face dentro da caixa sugerida pelo modelo. Em fotografias,
o modelo visual decide quais os objetos sensíveis presentes. O detetor local
apenas refina rostos indicados pelo modelo, com sobreposição suficiente; não
acrescenta máscaras por si só nem substitui a confiança do modelo por certeza.
As instruções do revisor são enviadas em ambas as passagens. A segunda passagem
usa as mesmas regras visuais e procura apenas dados ainda expostos. Esta regra
de confirmação aplica-se às fotografias; o vídeo mantém a deteção local densa
para acompanhar rostos entre as amostras do modelo. As observações
são associadas uma a uma por posição, dimensão e movimento, nunca através de
mudanças de cena. Deteções repetidas no mesmo fotograma são combinadas, e as
duas passagens são associadas a partir das observações originais completas.
Os objetos começam no primeiro fotograma observado, sem antecipação fixa.
O fluxo ótico acrescenta posições até 10 vezes por segundo entre observações,
mantendo as caixas do modelo nos seus instantes exatos. Quando o rastreio perde
confiança, fotogramas adicionais são verificados pelo modelo dentro do
orçamento de 180 amostras. Entre observações confirmadas, uma falha usa uma
caixa conservadora que cobre ambas; após a última observação, a máscara termina
quando deixam de existir características rastreáveis. Só as máscaras de rosto
são suavizadas e recebem uma margem adaptada à velocidade. O utilizador pode
acrescentar, mover, redimensionar, limitar no
tempo ou remover regiões antes de aprovar. Uma caixa manual pode ser rastreada
para a frente e para trás por fluxo ótico; a linha temporal mostra todos os
fotogramas-chave gerados e permite corrigi-los.

### Máscaras ajustadas ao conteúdo

Se `OPENCV_FACE_PARSER_MODEL` apontar para o modelo ResNet18 BiSeNet ONNX, cada
caixa de rosto detetada é refinada localmente para um polígono de 32 pontos. A máscara
inclui pele, características faciais, orelhas, óculos e brincos, mas exclui
cabelo, chapéus, pescoço, roupa e fundo. O código fecha pequenos buracos e
acrescenta uma margem de segurança igual ao maior de 4 píxeis ou 3% da largura
do rosto. No vídeo, os mesmos 32 vértices são suavizados e interpolados entre
fotogramas-chave, sem atravessar cortes de cena.

Texto, documentos, matrículas, assinaturas e códigos mantêm a caixa completa
do modelo. A segmentação genérica pode selecionar a mão ou apenas uma zona
colorida de um cartão e deixar dados expostos. As restantes regiões sugeridas
pelo modelo passam por segmentação local conservadora no OpenCV. O primeiro
plano dentro da caixa é limpo, dilatado com uma margem de segurança e convertido
num polígono convexo de 32 pontos. Regiões manuais continuam retangulares porque
não têm uma classe ou uma segmentação confirmada a partir da análise original.

O contrato mantém a caixa envolvente em todos os fotogramas-chave. Se o
refinamento falhar, não cobrir o centro da deteção, produzir uma área
implausível ou ficar demasiado pequeno face à caixa original, o sistema usa
essa caixa inteira. Assim, uma falha no refinamento nunca reduz a proteção. Os
exportadores Pillow/OpenCV pixelizam a caixa e compõem o resultado através da
máscara poligonal, exceto nos rostos, que levam o desfoque em elipse descrito
em "Privacidade e saída".

O protótipo usa o modelo ResNet18 do projeto `yakhyo/face-parsing`. Embora o
código desse projeto tenha licença MIT, os pesos derivam do CelebAMask-HQ,
cujos dados são limitados a investigação não comercial. Esta configuração é
adequada para a demonstração do hackathon; antes de uso comercial, os direitos
dos pesos têm de ser revistos ou os pesos substituídos por um modelo autorizado.

## Configuração

```powershell
$env:GEMINI_MEDIA_MODEL = "gemini-3.5-flash-lite"
$env:GEMINI_GATEWAY_URL = "https://nos-gemini-gateway.jnhorta05.workers.dev"
$env:GEMINI_GATEWAY_ORIGIN = "http://localhost:5173"
```

`GEMINI_MEDIA_MODEL` é validado contra a lista explícita em
`src/media/capabilities.py`; o backend pede ao Worker que confirme a identidade
do modelo junto do fornecedor. A chave `GEMINI_API_KEY` existe apenas como
segredo cifrado do Worker Cloudflare e nunca é lida pelo processo Python.
Uma configuração desconhecida, um gateway indisponível ou um modelo sem as
três capacidades necessárias devolve HTTP 503 nos uploads multimédia.

São necessários Pillow, OpenCV e os executáveis `ffmpeg`/`ffprobe`. As
dependências Python constam de `requirements.txt`.

Para ativar YuNet, descarregue um modelo `face_detection_yunet_*.onnx` do
repositório oficial OpenCV Zoo e defina o seu caminho absoluto em
`OPENCV_FACE_DETECTOR_MODEL`. O ficheiro e a deteção ficam locais.

Para ativar a máscara ajustada, descarregue `resnet18.onnx` da versão usada
pelo projeto `yakhyo/face-parsing` e defina o seu caminho absoluto em
`OPENCV_FACE_PARSER_MODEL`. O ficheiro, a inferência e as máscaras permanecem
locais. Sem esta variável, a aplicação continua a funcionar com caixas.

## Privacidade e saída

- Os originais e resultados ficam numa pasta temporária da sessão local e são
  eliminados ao começar outra revisão ou ao fechar o servidor.
- As respostas e ficheiros usam `Cache-Control: no-store`.
- O contrato de regiões nunca contém o texto reconhecido; guarda apenas
  categoria, razão genérica, confiança, origem, tempo e coordenadas.
- **Rostos:** desfocados de forma suave, numa **elipse colada à cara** (um
  pouco maior do que a caixa, com a borda esbatida), em vez de uma grelha de
  píxeis. A região é reduzida a cerca de 6 células de cor, ampliada com
  interpolação e desfocada: o detalhe fino (olhos, boca, pele) perde-se por
  completo e não se recupera do ficheiro. Uma caixa com menos de 8 píxeis cai
  na grelha. O contorno da elipse vem da caixa, não do polígono (o polígono da
  segmentação genérica pode ser mais pequeno do que a cara e deixá-la à vista).
- **Texto, documentos, matrículas, assinaturas, códigos e outros:** grandes
  blocos pixelizados, com uma tonalidade azul-ardósia discreta, para que nada
  se leia.
- Em ambos os casos os detalhes originais da região não podem ser recuperados
  do ficheiro de saída. Remove EXIF/GPS e metadados de
  contentor e usa nomes de saída genéricos.
- O áudio do vídeo é preservado. Dados pessoais falados não são censurados
  nesta versão.

## Uma cara, uma região

A mesma cara costuma voltar de vários detetores (o modelo, o detetor local, uma
pista partida em pedaços), cada um com a sua caixa, e isso aparecia como duas ou
três "caras" na mesma pessoa. `_merge_face_regions` junta-as: duas regiões de
rosto são a mesma cara quando, nos instantes que partilham (ou quase,
300 ms), a caixa mais pequena está em grande parte (60%) dentro da maior, em
pelo menos um terço desses instantes (o fim de um pedaço pode já ter derivado
da cara). O resultado é uma só região cuja caixa, em cada instante, é a **união**
das caixas do grupo: a máscara só pode crescer, nunca perde parte da cara. Duas
caras diferentes, ou a mesma zona em instantes muito afastados, não se juntam.
Corre nas fotografias e nos vídeos (antes e depois do alisamento das caixas), e
só toca em rostos. Num vídeo real passou de 5 pistas de rosto para 1.

## Verificação real

Com o Worker de produção, o Gemini (`gemini-3.5-flash-lite`) e o `ffmpeg`:

| Teste | Resultado |
|---|---|
| Fotografia: um cartão de cidadão fictício com uma cara e uma matrícula | cara, cartão e matrícula detetados com o contorno certo; a exportação deixa-os ilegíveis |
| Vídeo sintético (6 s): um cartão a deslizar e uma matrícula | pronto em 27 s; 2 regiões com 60 quadros-chave cada, a seguir o movimento; exportação em cerca de 4 s |
| Vídeo real (6,7 s): uma cara que vira a cabeça e um cartão que entra e passa à frente da cara | pronto em 50 s; a cara em vários troços, o cartão duas vezes; exportação em cerca de 4 s, MP4 H.264 com o áudio; a cara fica desfocada em todos os fotogramas vistos |

**Limites verificados:** quando o cartão **entra** em cena, desfocado pelo
movimento, houve uns 0,2 s sem máscara (o modelo só o vê na primeira amostra,
cerca de 3 por segundo, e o rastreio começa aí), embora nada se lesse. O
modelo varia de uma execução para outra (7 e 9 regiões no mesmo vídeo, e uma
vez apanhou parte do logótipo de uma t-shirt, que não é um dado pessoal).
Rostos a sério em vários planos, vários rostos e filmagens longas não foram
testados.

## API da revisão

| Método | Rota | Função |
|---|---|---|
| `POST` | `/api/document` | envia documento, imagem ou vídeo |
| `GET` | `/api/current` | estado, progresso, modelo e regiões |
| `GET` | `/api/media/source` | pré-visualização temporária |
| `PUT` | `/api/media/regions` | substitui o manifesto editado |
| `POST` | `/api/media/preview` | devolve uma imagem com o desfoque e a pixelização já aplicados às regiões enviadas (a fotografia, ou um fotograma do vídeo), para o revisor ver o resultado antes de aprovar |
| `POST` | `/api/media/track` | rastreia uma caixa manual nos dois sentidos |
| `POST` | `/api/reject` | reanalisa com observações |
| `POST` | `/api/approve` | inicia a exportação final |
| `GET` | `/api/media/output` | descarrega a versão aprovada |

O frontend consulta `/api/current` durante `processing` e `exporting`.
