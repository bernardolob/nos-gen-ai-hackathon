"""Verificação: compara o documento original com a versão mascarada.

Confere se a versão mascarada:

- tem o mesmo número de linhas e de palavras por linha que o original;
- não tem linhas vazias;
- só altera uma palavra quando a mascara por completo, com a mesma regra
  de ``masking.py`` (pontuação nas pontas mantida; vírgula, ponto e
  vírgula e barra separam palavras coladas, exceto entre dois dígitos;
  endereços web são uma só palavra; um símbolo isolado nunca é mascarado),
  ou a mantém idêntica ao original.

Esta regra está duplicada de propósito a partir de ``masking.py`` (em vez
de partilhada por um módulo comum): extrair esse módulo implicava editar
``masking.py``, que já está integrado por outra pessoa da equipa, e isso
foi deixado fora deste branch. Enquanto a duplicação existir, uma mudança
futura na regra de ``masking.py`` tem de ser repetida aqui à mão — ver a
decisão em aberto nº 1 em ``DECISIONS.md``.

Não confere se os itens da deteção foram todos encontrados no texto; essa
verificação precisa da lista de itens e fica para quando o mascaramento e a
deteção estiverem integrados.
"""

import re

MASK = "*"
EDGE_PUNCTUATION = ",;:.!?()[]{}\"'"
# Vírgula, ponto e vírgula ou barra que não está entre dois dígitos.
LIST_SEPARATOR = re.compile(r"((?<!\d)[,;/]|[,;/](?!\d))")
# Endereços web são sempre uma só palavra, apesar das barras.
WEB_ADDRESS = re.compile(r"^\W*(?:https?://|www\.)", re.IGNORECASE)


def compare_files(original_path, masked_path):
    """Lê dois ficheiros de texto e compara-os.

    Devolve a lista de problemas encontrados por ``compare_lines``.
    """
    return compare_lines(
        _read_lines(original_path), _read_lines(masked_path)
    )


def _read_lines(path):
    """Lê um ficheiro e devolve as suas linhas, sem a quebra de linha."""
    with open(path, encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle]


def compare_lines(original_lines, masked_lines):
    """Compara as linhas originais com as linhas mascaradas.

    Devolve uma lista de problemas; vazia significa que não foi encontrado
    nenhum problema.
    """
    issues = []

    if len(original_lines) != len(masked_lines):
        issues.append({
            "type": "line_count_mismatch",
            "original_lines": len(original_lines),
            "masked_lines": len(masked_lines),
        })

    for number, masked_line in enumerate(masked_lines, start=1):
        if masked_line.strip() == "":
            issues.append({"type": "blank_line", "line": number})

    for number, (original_line, masked_line) in enumerate(
        zip(original_lines, masked_lines), start=1
    ):
        issues.extend(_compare_words(number, original_line, masked_line))

    return issues


def _compare_words(number, original_line, masked_line):
    """Compara palavra a palavra; devolve os problemas encontrados."""
    original_words = original_line.split()
    masked_words = masked_line.split()

    if len(original_words) != len(masked_words):
        return [{
            "type": "word_count_mismatch",
            "line": number,
            "original_words": len(original_words),
            "masked_words": len(masked_words),
        }]

    issues = []
    for position, (original_word, masked_word) in enumerate(
        zip(original_words, masked_words)
    ):
        if not _is_valid(original_word, masked_word):
            issues.append({
                "type": "unexpected_word_change",
                "line": number,
                "position": position,
                "original_word": original_word,
                "masked_word": masked_word,
            })
    return issues


def _is_valid(original_word, masked_word):
    """Diz se ``masked_word`` é uma versão válida de ``original_word``.

    É válida se ficou idêntica (palavra não mascarada) ou se corresponde
    ao que ``masking.py`` produziria a partir do original.
    """
    return masked_word in (original_word, _mask_token(original_word))


def _mask_token(token):
    """Mascara uma sequência sem espaços, separando as palavras coladas.

    Espelha ``masking._mask_token``: a vírgula, o ponto e vírgula e a
    barra separam palavras mesmo sem espaço (``João,Ana`` passa a
    ``*,*``), exceto entre dois dígitos. Os endereços web contam como uma
    só palavra.
    """
    if WEB_ADDRESS.match(token):
        return _mask_word(token)
    parts = LIST_SEPARATOR.split(token)
    return "".join(
        part if index % 2 else _mask_word(part)
        for index, part in enumerate(parts)
    )


def _mask_word(word):
    """Troca a palavra por ``*``, mantendo a pontuação nas pontas.

    Espelha ``masking._mask_word``: um símbolo isolado, sem letras nem
    números, nunca é mascarado.
    """
    if not any(char.isalnum() for char in word):
        return word
    lead = len(word) - len(word.lstrip(EDGE_PUNCTUATION))
    trail = len(word) - len(word.rstrip(EDGE_PUNCTUATION))
    core_end = len(word) - trail
    return word[:lead] + MASK + word[core_end:]
