"""Testes de ``submission/prompt.txt``: tem de ser o pedido exato.

O ficheiro da submissão guarda o prompt interno, o documento do desafio e as
instruções iniciais do utilizador, como o gateway os recebe (``gateway.py``
junta a instrução de sistema e o conteúdo com uma linha em branco). Se
alguma destas partes mudar, o teste falha e o ficheiro tem de ser refeito.
"""

from pathlib import Path

import pytest

import detection
import pipeline

ROOT = Path(__file__).resolve().parents[3]
PROMPT_FILE = ROOT / "submission" / "prompt.txt"
INSTRUCTIONS_FILE = ROOT / "submission" / "solution" / "user_instructions.txt"
CHALLENGE_PDF = ROOT / "raw_data" / "document_to_anonymize.pdf"


def test_initial_instructions_fit_the_limit():
    instructions = pipeline.read_instructions(path=INSTRUCTIONS_FILE)
    assert instructions
    assert len(instructions) <= pipeline.MAX_INSTRUCTIONS


@pytest.mark.skipif(
    not CHALLENGE_PDF.exists(), reason="falta o PDF do desafio")
def test_prompt_file_is_the_exact_request():
    lines = pipeline.read_lines(str(CHALLENGE_PDF))
    instructions = pipeline.read_instructions(path=INSTRUCTIONS_FILE)
    expected = "%s\n\n%s" % (
        detection.load_internal_prompt(),
        detection.build_request(lines, instructions))
    assert PROMPT_FILE.read_text(encoding="utf-8") == expected
