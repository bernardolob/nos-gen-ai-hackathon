"""Redação do áudio: substitui cada intervalo de tempo por um som.

Usa o ``ffmpeg`` diretamente por ``subprocess``, sem o ``pydub``: essa
biblioteca depende do módulo ``audioop``, removido da biblioteca padrão a
partir do Python 3.13, e exigiria mais uma dependência só para operações
simples de corte e concatenação que o próprio ``ffmpeg`` já faz. Mantém o
princípio do resto do núcleo: o mínimo de dependências possível.

A duração total do áudio não muda: cada som de substituição é cortado ou
repetido (``-stream_loop -1`` seguido de ``-t``, que funciona nos dois
casos) até à duração exata do intervalo que substitui.
"""

import itertools
import subprocess
import tempfile
from pathlib import Path

SAMPLE_RATE = "48000"
CHANNELS = "1"


class RedactionError(Exception):
    """O ``ffmpeg`` falhou a produzir o áudio censurado."""


def redact(audio_path, ranges, sound_paths, out_path):
    """Substitui ``ranges`` no áudio por sons de ``sound_paths``, em
    rotação, e grava o resultado em ``out_path``.

    ``ranges`` é uma lista de ``(início, fim)`` em segundos, ordenada e
    sem sobreposição (a forma que ``alignment.find_masked_ranges``
    devolve). Sem som nenhum em ``sound_paths``, levanta ``ValueError``.
    """
    if not sound_paths:
        raise ValueError("sound_paths está vazia")
    duration = _probe_duration(audio_path)
    sounds = itertools.cycle(str(path) for path in sound_paths)
    with tempfile.TemporaryDirectory() as tmp:
        chunk_paths = _build_chunks(
            str(audio_path), ranges, sounds, duration, Path(tmp))
        _concat(chunk_paths, str(out_path))


def _build_chunks(audio_path, ranges, sounds, duration, tmp_dir):
    """Lista, pela ordem do tempo, os troços a concatenar no resultado."""
    chunks = []
    cursor = 0.0
    for index, (start, end) in enumerate(ranges):
        if start > cursor:
            chunks.append(_extract(
                audio_path, cursor, start,
                tmp_dir / ("keep_%d.wav" % index)))
        chunks.append(_fit_sound(
            next(sounds), end - start, tmp_dir / ("fit_%d.wav" % index)))
        cursor = end
    if cursor < duration:
        chunks.append(_extract(
            audio_path, cursor, duration, tmp_dir / "keep_last.wav"))
    return chunks


def _probe_duration(path):
    """Duração do áudio em segundos, pelo ``ffprobe``."""
    result = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(result.stdout.strip())


def _extract(audio_path, start, end, out_path):
    """Copia ``[start, end]`` do áudio original para ``out_path`` (wav)."""
    _run([
        "ffmpeg", "-y", "-i", audio_path,
        "-ss", str(start), "-to", str(end),
        "-ar", SAMPLE_RATE, "-ac", CHANNELS, str(out_path),
    ])
    return out_path


def _fit_sound(sound_path, target_duration, out_path):
    """Corta ou repete ``sound_path`` até durar exatamente ``target_duration``.

    ``-stream_loop -1`` repete o som indefinidamente antes de o decodificar;
    ``-t`` corta o resultado à duração pedida, quer isso o encurte (som mais
    longo do que o intervalo) quer o alongue (som mais curto).
    """
    _run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", sound_path,
        "-t", str(target_duration),
        "-ar", SAMPLE_RATE, "-ac", CHANNELS, str(out_path),
    ])
    return out_path


def _concat(chunk_paths, out_path):
    """Concatena os troços, pela ordem dada, no ficheiro final."""
    if not chunk_paths:
        raise RedactionError("áudio original vazio: nada para gravar")
    list_file = Path(chunk_paths[0]).parent / "list.txt"
    list_file.write_text(
        "\n".join("file '%s'" % path for path in chunk_paths),
        encoding="utf-8",
    )
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), out_path,
    ])


def _run(command):
    """Corre ``command``; levanta ``RedactionError`` com o erro do ffmpeg."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RedactionError(
            "%s falhou: %s" % (command[0], result.stderr[-500:]))
    return result
