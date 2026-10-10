"""Alinhamento: liga as palavras ocultadas aos seus intervalos de tempo.

Compara a linha original com a linha mascarada, palavra a palavra, para
saber que posições foram ocultadas, e usa a lista de palavras com tempo
(devolvida por ``transcriber.transcribe``) para converter essas posições em
intervalos ``(início, fim)``, em segundos. Intervalos seguidos ou
sobrepostos juntam-se num só.

Não reutiliza ``verification.py``: o trabalho da verificação é confirmar
que o mascaramento não teve erros de formato, não listar que posições
mudaram. Qualquer desalinhamento entre a transcrição e as linhas levanta
``AlignmentError`` em vez de ignorar palavras em silêncio — ocultar menos
do que devia é o erro perigoso aqui, não o inverso.
"""


class AlignmentError(Exception):
    """A transcrição e o mascaramento não alinham."""


def find_masked_ranges(original_lines, masked_lines, word_times):
    """Devolve os intervalos de tempo a substituir, ordenados e sem
    sobreposição.

    ``word_times`` é paralela a ``original_lines``: para cada linha, a
    lista de ``(início, fim)`` de cada palavra, na mesma ordem que
    ``original_lines[i].split()``.
    """
    if len(original_lines) != len(masked_lines):
        raise AlignmentError(
            "número de linhas diferente: original tem %d, mascarado tem %d"
            % (len(original_lines), len(masked_lines)))
    if len(original_lines) != len(word_times):
        raise AlignmentError(
            "número de linhas diferente: original tem %d, timestamps têm %d"
            % (len(original_lines), len(word_times)))
    ranges = []
    for number, (original_line, masked_line, times) in enumerate(
        zip(original_lines, masked_lines, word_times), start=1
    ):
        ranges.extend(_line_ranges(number, original_line, masked_line, times))
    return _merge(ranges)


def _line_ranges(number, original_line, masked_line, times):
    """Intervalos a substituir numa linha; levanta ``AlignmentError``."""
    original_words = original_line.split()
    masked_words = masked_line.split()
    if len(original_words) != len(masked_words):
        raise AlignmentError(
            "linha %d: o mascaramento mudou o número de palavras (%d -> %d)"
            % (number, len(original_words), len(masked_words)))
    if len(times) != len(original_words):
        raise AlignmentError(
            "linha %d: %d palavras, mas %d marcas de tempo"
            % (number, len(original_words), len(times)))
    return [
        times[position]
        for position, (original_word, masked_word) in enumerate(
            zip(original_words, masked_words)
        )
        if masked_word != original_word
    ]


def _merge(ranges):
    """Junta intervalos seguidos ou sobrepostos, pela ordem do tempo."""
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
