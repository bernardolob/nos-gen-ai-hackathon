# Saída em PDF

Quando o documento enviado é um PDF, além do texto anonimizado pode obter-se o
**PDF anonimizado**: o PDF original, com o layout, os tipos de letra e as
imagens como estavam, mas com cada palavra sensível **apagada** e um `*` no
lugar. Não é uma tarja por cima: o texto debaixo é removido do ficheiro.

## Como funciona (`src/pdf_output.py`)

1. O extrator (`pdf_extractor`) e o `pdf_output` leem o PDF da mesma forma
   (`page.get_text()` e `page.get_text("words")`), por isso a linha `i` do
   documento é a linha `i` do PDF.
2. Para cada linha mascarada, compara-se palavra a palavra o original com o
   texto mascarado. Cada palavra que mudou recebe uma *redaction* na sua
   caixa (`apply_redactions` remove o texto; as imagens e as linhas
   desenhadas ficam). Depois escreve-se o texto mascarado dessa palavra
   (`*`, ou `*,` se havia pontuação colada) na mesma posição.
3. Se uma linha não bate certo (outro número de palavras, ou o texto não é o
   do PDF), cobre-se a **linha inteira** e escreve-se lá a linha mascarada.
   Nunca se deixa um dado à vista por não se achar a palavra.
4. **Verificação.** Lê-se o PDF gerado e confirma-se que as palavras que lá
   estão são exatamente as do texto mascarado (como conjunto: o `*` novo vai
   para o fim do conteúdo da página, por isso a ordem não conta). Uma palavra
   sensível que sobrasse seria uma palavra a mais. Se falhar, o PDF não é
   devolvido.

## Onde se usa

| Onde | Como |
|---|---|
| Linha de comandos | `python pipeline.py documento.pdf --out saida --pdf` escreve também `saida/anonymized.pdf` (só para PDF, e precisa de `--out`) |
| Backend da revisão | `GET /api/pdf/current` gera o PDF da versão em revisão (cada rejeição dá um PDF novo); 404 se o documento não veio de um PDF; 502 com uma mensagem fixa se a verificação falhar. O estado traz `pdf_url` (ou `null`) |
| UI | O botão "Download PDF", ao lado de "Download .txt", em documentos que vieram de um PDF |

O PDF original fica na pasta temporária da sessão (apagada ao substituir a
revisão ou fechar o servidor) e o gerado nunca fica em cache no navegador
(`Cache-Control: no-store`).

## Limites

- **PDF só de imagem** (digitalizado): não tem texto para extrair, por isso o
  documento é recusado como já era ("O documento não tem texto").
- **PDF protegido com palavra-passe**: recusado.
- **Fundo que não é branco:** a caixa apagada fica branca. Num fundo
  colorido vê-se um retângulo branco.
- **Texto em imagens** dentro do PDF não é apagado (só o texto do PDF).
- **Páginas rodadas e colunas** não foram testadas; a verificação apanha o
  que falhar (o PDF não é devolvido), mas não garante que o PDF saia.

## Verificação

- No PDF do desafio, com o Gemini real: 2 páginas, 193 `*`, 0 avisos e 0
  problemas; nomes, diagnósticos e números já não estão no texto do PDF
  e a página mantém o layout. Num PDF de teste confirmou-se também que o
  texto apagado não aparece nos bytes do ficheiro. Demora cerca de 0,4 s.
- 18 testes novos (módulo, linha de comandos, rota) e 4 da UI.
