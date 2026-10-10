"""Verificação: compara o documento original com a versão mascarada.

Confere se a versão mascarada:

- tem o mesmo número de linhas e de palavras por linha que o original;
- não tem linhas vazias;
- só altera uma palavra quando a mascara por completo (``*``, mantendo a
  pontuação nas pontas — a mesma regra do ``masking.py``) ou a mantém
  idêntica ao original. Um símbolo isolado, sem letras nem números, nunca
  é mascarado.

Esta regra está duplicada aqui (em vez de importada de ``masking.py``)
porque essa branch ainda não está integrada em ``main``; quando os dois
módulos existirem no mesmo lugar, vale a pena partilhar uma só definição.

Não confere se os itens da deteção foram todos encontrados no texto; essa
verificação precisa da lista de itens e fica para quando o mascaramento e a
deteção estiverem integrados.
"""

EDGE_PUNCTUATION = ",;:.!?()[]{}\"'"
MASK = "*"


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

    É válida se ficou idêntica (palavra não mascarada) ou se ficou
    totalmente mascarada, mantendo a pontuação nas pontas. Um símbolo
    isolado, sem letras nem números, nunca é mascarado.
    """
    if masked_word == original_word:
        return True
    if not any(char.isalnum() for char in original_word):
        return False
    lead = len(original_word) - len(original_word.lstrip(EDGE_PUNCTUATION))
    trail = len(original_word) - len(original_word.rstrip(EDGE_PUNCTUATION))
    core_end = len(original_word) - trail
    expected = original_word[:lead] + MASK + original_word[core_end:]
    return masked_word == expected
