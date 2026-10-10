"""Transcrição: liga o ElevenLabs Scribe ao resto do pipeline.

``transcribe(audio_path, call_scribe)`` devolve as linhas de texto e, por
linha, a lista de ``(início, fim)`` de cada palavra — a forma que
``pipeline.run`` espera para as linhas, e o que ``audio.alignment``
precisa para voltar a encontrar o tempo de cada palavra ocultada.

``call_scribe(audio_bytes)`` é o cliente real, injetado (o mesmo desenho
de ``detection.detect(lines, generate)``): aqui testa-se com um cliente
falso, sem rede nem chave.

**Por confirmar com a chave real:** o esquema de resposta abaixo (uma
lista ``words``, cada palavra com ``text``, ``start``, ``end`` e ``type``,
em que ``type`` pode ser ``"word"``, ``"spacing"`` ou ``"audio_event"``)
vem de exemplos de terceiros, não foi possível consultar a referência
oficial da API desde este ambiente (rede bloqueada para
``elevenlabs.io``/``api.elevenlabs.io``). Confirmar antes de depender
disto com áudio real.
"""

import unicodedata
from pathlib import Path

SENTENCE_END = ".!?"
MAX_WORDS_PER_LINE = 20
WORD_TYPE = "word"


class TranscriptionError(Exception):
    """A resposta do Scribe não se pode usar com segurança."""


def transcribe(audio_path, call_scribe):
    """Lê ``audio_path``, chama ``call_scribe`` e devolve ``(lines,
    word_times)``.

    ``lines`` são as linhas de texto, prontas para ``pipeline.run``.
    ``word_times`` é paralela a ``lines``: para cada linha, a lista de
    ``(início, fim)`` de cada palavra, na mesma ordem que
    ``lines[i].split()``.
    """
    audio_bytes = Path(audio_path).read_bytes()
    raw = call_scribe(audio_bytes)
    words = _extract_words(raw)
    return _group_into_lines(words)


def _extract_words(raw):
    """Palavras válidas (``type == "word"``) da resposta do Scribe."""
    try:
        entries = raw["words"]
    except (KeyError, TypeError) as error:
        raise TranscriptionError(
            "resposta sem a lista 'words'") from error
    return [
        _normalize_word(entry) for entry in entries
        if entry.get("type") == WORD_TYPE
    ]


def _normalize_word(entry):
    """Devolve ``(texto, início, fim)``; levanta ``TranscriptionError``."""
    try:
        text = unicodedata.normalize("NFC", entry["text"])
        start = float(entry["start"])
        end = float(entry["end"])
    except (KeyError, TypeError, ValueError) as error:
        raise TranscriptionError(
            "palavra mal formada na resposta: %r" % (entry,)) from error
    if not text.strip():
        raise TranscriptionError(
            "palavra sem texto na resposta: %r" % (entry,))
    if end <= start:
        raise TranscriptionError(
            "palavra com duração inválida: %r" % (entry,))
    return text, start, end


def _group_into_lines(words):
    """Agrupa as palavras em linhas, por frase ou por um máximo cada."""
    lines, word_times = [], []
    current_words, current_times = [], []
    for text, start, end in words:
        current_words.append(text)
        current_times.append((start, end))
        ends_sentence = text[-1:] in SENTENCE_END
        if ends_sentence or len(current_words) >= MAX_WORDS_PER_LINE:
            lines.append(" ".join(current_words))
            word_times.append(current_times)
            current_words, current_times = [], []
    if current_words:
        lines.append(" ".join(current_words))
        word_times.append(current_times)
    return lines, word_times
