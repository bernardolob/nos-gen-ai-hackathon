"""Extra: ponto de entrada da censura de áudio.

Liga a transcrição (``audio.transcriber``), o pipeline de texto
(``pipeline.run``, sem alterações) e a redação do áudio
(``audio.redactor``). Ver ``AUDIO.md`` para a arquitetura.

Uso, a partir de ``submission/solution/src``::

    python audio_pipeline.py audio.m4a --no-model
    python audio_pipeline.py audio.m4a --no-model --out saida

Sem ``--out`` nada é escrito: mostra só o resumo (ensaio). Com
``--out DIR`` escreve ``DIR/audio_censurado.m4a``, ``DIR/submission.txt``
e ``DIR/report.md``, tal como ``pipeline.py``.

O modelo e as instruções do utilizador funcionam como em ``pipeline.py``.
Os sons de substituição vêm, por defeito, de ``assets/censor_sounds/``
(``--sounds`` deixa-os escolher outros, em rotação).

Códigos de saída: 0 sem problemas, 1 a verificação encontrou problemas,
2 erro (ficheiro, argumentos, transcrição, alinhamento ou redação).
"""

import argparse
import sys
from pathlib import Path

import detection
import gateway
import pipeline
from audio import (
    AlignmentError,
    ConfigurationError,
    RedactionError,
    ScribeRequestError,
    TranscriptionError,
    find_masked_ranges,
    redact,
    scribe_from_env,
    transcribe,
)

EXIT_OK = 0
EXIT_VERIFICATION = 1
EXIT_ERROR = 2

CENSORED_FILE = "audio_censurado.m4a"
DEFAULT_SOUNDS_DIR = (
    Path(__file__).resolve().parents[1] / "assets" / "censor_sounds"
)
DEFAULT_SOUNDS = sorted(DEFAULT_SOUNDS_DIR.glob("censor_*.m4a"))


def run(audio_path, call_scribe, generate=None, user_instructions=None,
        include_values=False):
    """Corre o pipeline de áudio e devolve um dicionário.

    Além das chaves de ``pipeline.run`` (``masked``, ``items``,
    ``warnings``, ``label_changes``, ``issues``, ``report``), devolve
    ``lines`` (a transcrição) e ``ranges`` (os intervalos de tempo a
    substituir no áudio).

    Levanta ``audio.TranscriptionError``, ``detection.DetectionError`` ou
    ``audio.AlignmentError`` se algum passo não se puder usar com
    segurança.
    """
    lines, word_times = transcribe(audio_path, call_scribe)
    return run_transcript(
        lines, word_times, generate, user_instructions, include_values)


def run_transcript(lines, word_times, generate=None, user_instructions=None,
                   include_values=False):
    """A parte de ``run`` que não toca no áudio, a partir da transcrição.

    Permite repetir a deteção (por exemplo, com novas instruções do
    utilizador) sem voltar a transcrever, ou seja, sem voltar a enviar o
    áudio ao ElevenLabs. Devolve o mesmo que ``run``.
    """
    lines = detection.normalize_lines(lines)
    result = pipeline.run(lines, generate, user_instructions, include_values)
    result["lines"] = lines
    result["ranges"] = find_masked_ranges(
        lines, result["masked"], word_times)
    return result


def write_outputs(result, audio_path, sound_paths, out_dir):
    """Escreve o áudio censurado, ``submission.txt`` e ``report.md``."""
    pipeline.write_outputs(result, out_dir)
    out_path = Path(out_dir) / CENSORED_FILE
    redact(audio_path, result["ranges"], sound_paths, out_path)


def summary(result):
    """Resumo de uma linha por tema, sem valores sensíveis."""
    rows = pipeline.summary(result).split("\n")
    rows.append("intervalos de áudio a substituir: %d" % len(
        result["ranges"]))
    return "\n".join(rows)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Censura um áudio: substitui cada palavra sensível "
        "por um som.")
    parser.add_argument("audio", help="ficheiro de áudio (mp3, m4a, wav)")
    parser.add_argument(
        "--no-model", action="store_true",
        help="só as regras de segurança, sem o Gemini")
    instructions = parser.add_mutually_exclusive_group()
    instructions.add_argument(
        "--instructions", help="instruções do utilizador, em texto livre")
    instructions.add_argument(
        "--instructions-file", metavar="FICHEIRO",
        help="ficheiro de texto (UTF-8) com as instruções do utilizador")
    parser.add_argument(
        "--out", metavar="DIR",
        help="escreve o áudio censurado, submission.txt e report.md "
        "aqui (sem isto, ensaio)")
    parser.add_argument(
        "--include-values", action="store_true",
        help="mostra os valores originais no relatório")
    parser.add_argument(
        "--sounds", nargs="+", metavar="FICHEIRO",
        help="sons de substituição, em rotação (por defeito, os de "
        "assets/censor_sounds/)")
    return parser


def main(argv=None, generate=None, call_scribe=None):
    """Corre o pipeline de áudio pela linha de comandos."""
    args = build_parser().parse_args(argv)
    try:
        if args.no_model:
            generate = None
        elif generate is None:
            generate = gateway.from_env()
            if generate is None:
                print("Erro: falta ligar ao Gemini. Defina "
                      "GEMINI_GATEWAY_URL e GEMINI_GATEWAY_ORIGIN, ou use "
                      "--no-model para correr só as regras de segurança.",
                      file=sys.stderr)
                return EXIT_ERROR
        if call_scribe is None:
            call_scribe = scribe_from_env()
        sound_paths = args.sounds or DEFAULT_SOUNDS
        if not sound_paths:
            print("Erro: nenhum som de substituição em %s; use --sounds."
                  % DEFAULT_SOUNDS_DIR, file=sys.stderr)
            return EXIT_ERROR
        instructions = pipeline.read_instructions(
            args.instructions, args.instructions_file)
        result = run(
            args.audio, call_scribe, generate, instructions,
            args.include_values)
    except (OSError, RuntimeError, ValueError, detection.DetectionError,
            gateway.GatewayError, TranscriptionError, AlignmentError,
            RedactionError, ScribeRequestError,
            ConfigurationError) as error:
        print("Erro: %s" % error, file=sys.stderr)
        return EXIT_ERROR
    if args.out:
        write_outputs(result, args.audio, sound_paths, args.out)
    print(summary(result))
    if not args.out:
        print("(ensaio: nada foi escrito; use --out DIR)")
    return EXIT_VERIFICATION if result["issues"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
