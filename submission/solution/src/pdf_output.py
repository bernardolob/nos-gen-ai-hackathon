"""Saída em PDF: o PDF original com os dados sensíveis substituídos por ``*``.

Para cada palavra mascarada procura-se a caixa da palavra no PDF original e
aplica-se uma *redaction*, que **apaga** o texto debaixo (não é só uma tarja
por cima) e escreve lá o ``*``. O resto da página (tipos de letra, imagens,
linhas) fica como estava.

As palavras do PDF e as linhas do documento vêm da mesma extração
(``pdf_extractor``), por isso a linha ``i`` do documento é a linha ``i`` do
PDF. Se uma linha não bater certo (outro número de palavras), cobre-se a linha
inteira e escreve-se lá a linha mascarada: nunca se deixa um dado à vista por
não se ter achado a palavra.

No fim lê-se o PDF gerado e confirma-se que as palavras que lá estão são
exatamente as do texto mascarado; se não forem, não se devolve o PDF.
"""

import unicodedata
from collections import Counter

import fitz  # PyMuPDF

FONT = "helv"
WHITE = (1, 1, 1)
BLACK = (0, 0, 0)
# O asterisco da Helvetica é pequeno: usa-se o corpo da altura da caixa.
LINE_TO_FONT = 1.0
MIN_FONT = 5.0
# A linha de base fica acima do fundo da caixa, onde ficam os descendentes.
BASELINE = 0.22


class PdfOutputError(Exception):
    """Não foi possível gerar um PDF seguro. A mensagem nunca tem dados."""


def _nfc(text):
    return unicodedata.normalize("NFC", text)


def pdf_lines(doc):
    """As linhas do PDF, pela ordem do texto.

    Cada linha é ``(página, [(caixa, palavra), ...])``.
    É a mesma ordem e agrupamento de ``page.get_text()``, que o extrator usa.
    """
    lines = []
    for number, page in enumerate(doc):
        groups = {}
        for x0, y0, x1, y1, word, block, line, _ in page.get_text("words"):
            groups.setdefault((block, line), []).append(
                (fitz.Rect(x0, y0, x1, y1), word))
        for words in groups.values():
            lines.append((number, words))
    return lines


def _redact(page, rect, text, pending):
    """Marca a caixa para apagar; o texto novo escreve-se depois de apagar."""
    page.add_redact_annot(rect, fill=WHITE, cross_out=False)
    pending.append((page.number, rect, text))


def _write(page, rect, text):
    size = max(MIN_FONT, rect.height / LINE_TO_FONT)
    width = fitz.get_text_length(text, fontname=FONT, fontsize=size)
    if width > rect.width and width > 0:
        size = max(MIN_FONT, size * rect.width / width)
    page.insert_text(
        (rect.x0, rect.y1 - rect.height * BASELINE), text,
        fontname=FONT, fontsize=size, color=BLACK)


def anonymize_pdf(source_path, original_lines, masked_lines, out_path):
    """Escreve em ``out_path`` o PDF anonimizado e devolve um resumo.

    ``original_lines`` e ``masked_lines`` são as linhas do documento antes e
    depois do mascaramento (as de ``pipeline.read_lines`` e de
    ``pipeline.run``). Levanta ``PdfOutputError`` se não conseguir um PDF que
    se confirme sem os dados.
    """
    if len(original_lines) != len(masked_lines):
        raise PdfOutputError("O texto mascarado não corresponde ao documento.")
    try:
        doc = fitz.open(str(source_path))
    except Exception:
        raise PdfOutputError("Não foi possível abrir o PDF.") from None
    with doc:
        if doc.is_encrypted or doc.needs_pass:
            raise PdfOutputError("O PDF está protegido.")
        lines = pdf_lines(doc)
        if len(lines) != len(original_lines):
            raise PdfOutputError(
                "O PDF não tem a estrutura de linhas esperada.")
        pending = []
        words_done = 0
        lines_done = 0
        pages_touched = set()
        for (number, words), original, masked in zip(
                lines, original_lines, masked_lines):
            if original == masked:
                continue
            page = doc[number]
            pages_touched.add(number)
            orig_tokens = original.split()
            mask_tokens = masked.split()
            pdf_tokens = [_nfc(word) for _, word in words]
            if (len(orig_tokens) == len(mask_tokens) == len(pdf_tokens)
                    and [_nfc(t) for t in orig_tokens] == pdf_tokens):
                for (rect, _), before, after in zip(
                        words, orig_tokens, mask_tokens):
                    if before != after:
                        _redact(page, rect, after, pending)
                        words_done += 1
            else:
                whole = fitz.Rect(words[0][0])
                for rect, _ in words:
                    whole |= rect
                _redact(page, whole, masked, pending)
                lines_done += 1
        for number in pages_touched:
            doc[number].apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE)
        for number, rect, text in pending:
            _write(doc[number], rect, text)
        doc.save(str(out_path), garbage=4, deflate=True, clean=True)
    check_pdf(out_path, masked_lines)
    return {"words": words_done, "whole_lines": lines_done,
            "pages": len(pages_touched)}


def check_pdf(path, masked_lines):
    """Confirma que as palavras do PDF são as do texto mascarado.

    Compara os conjuntos de palavras (e não a ordem: o ``*`` novo vai para o
    fim do conteúdo da página). Uma palavra sensível que sobrasse seria uma
    palavra a mais.
    """
    try:
        with fitz.open(str(path)) as doc:
            found = Counter(
                _nfc(word) for page in doc
                for *_, word, _b, _l, _n in page.get_text("words"))
    except Exception:
        raise PdfOutputError("Não foi possível verificar o PDF.") from None
    expected = Counter(
        _nfc(token) for line in masked_lines for token in line.split())
    if found != expected:
        raise PdfOutputError(
            "A verificação do PDF falhou: o PDF não foi devolvido.")
