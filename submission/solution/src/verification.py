"""Verificação: compara o documento original com a versão mascarada.

Confere se a versão mascarada:

- tem o mesmo número de linhas e de palavras por linha que o original;
- não tem linhas vazias;
- só altera uma palavra quando a mascara por completo, ou a mantém idêntica
  ao original.

"Mascarar por completo" é o que ``words.mask_token`` produz: a mesma
definição de palavra que o mascaramento usa (``words.py``), por isso as duas
partes não podem discordar.

Não confere se os itens da deteção foram todos encontrados no texto; essa
verificação precisa da lista de itens e fica para quando o mascaramento e a
deteção estiverem integrados.
"""

from words import mask_token, mask_word, split_token


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
    ao que ``masking.py`` produziria a partir do original. Numa sequência
    com palavras coladas (``João,Ana``) cada palavra conta à parte: ``João,*``
    é válido, porque só ``Ana`` era sensível.
    """
    if masked_word in (original_word, mask_token(original_word)):
        return True
    original = split_token(original_word)
    masked = split_token(masked_word)
    if len(original) != len(masked):
        return False
    return all(
        new == old if index % 2 else new in (old, mask_word(old))
        for index, (old, new) in enumerate(zip(original, masked))
    )
