"""Deteção: pede ao modelo a lista de itens sensíveis do documento.

Monta o pedido (a prompt interna como instrução de sistema e o documento com
as linhas numeradas), envia-o e valida a resposta em JSON contra o contrato de
dados (ver ``ARCHITECTURE.md``). Só usa a biblioteca padrão.

O cliente do modelo não está aqui: ``detect`` recebe-o como parâmetro, uma
função ``generate(instrução_de_sistema, conteúdo) -> texto``. Assim a deteção
testa-se sem o Gemini e o cliente real liga-se com um adaptador pequeno.

As mensagens de erro e de aviso nunca repetem o que o modelo respondeu, porque
a resposta pode conter os dados sensíveis.
"""

import json
import unicodedata
from pathlib import Path

from categories import CATEGORY_NAMES, CONFIDENCE_LEVELS

SOURCE = "gemini"
DEFAULT_ATTEMPTS = 2
PROMPT_PATH = Path(__file__).resolve().parents[1] / "internal_prompt.txt"


class DetectionError(Exception):
    """A resposta do modelo não se pôde usar."""


def load_internal_prompt(path=PROMPT_PATH):
    """Lê a prompt interna."""
    return Path(path).read_text(encoding="utf-8")


def normalize_lines(lines):
    """Normaliza as linhas para Unicode NFC.

    Deve fazer-se uma vez, no início, antes da deteção: assim o texto que o
    modelo devolve coincide com o do documento, mesmo que os acentos venham
    decompostos.
    """
    return [unicodedata.normalize("NFC", line) for line in lines]


def number_lines(lines):
    """Numera as linhas a partir de 1: ``[7] Nome: ...``."""
    return "\n".join(
        "[%d] %s" % (number, line) for number, line in enumerate(lines, 1)
    )


def build_request(lines, user_instructions=None):
    """Monta o conteúdo enviado ao modelo.

    O documento vai entre ``<document>`` e as instruções opcionais do
    utilizador entre ``<user_instructions>``, como a prompt interna espera.
    """
    parts = ["<document>", number_lines(lines), "</document>"]
    if user_instructions and user_instructions.strip():
        parts += [
            "",
            "<user_instructions>",
            user_instructions.strip(),
            "</user_instructions>",
        ]
    return "\n".join(parts)


def detect(
    lines,
    generate,
    user_instructions=None,
    system_prompt=None,
    attempts=DEFAULT_ATTEMPTS,
):
    """Deteta os itens sensíveis das linhas.

    ``generate(instrução_de_sistema, conteúdo)`` devolve o texto da resposta.
    As ``lines`` devem estar em NFC (ver ``normalize_lines``). Se a resposta
    não for uma lista JSON utilizável, tenta de novo até ``attempts`` vezes e
    depois levanta ``DetectionError``. Os erros do próprio ``generate``
    propagam-se sem alteração.

    Devolve ``(itens, avisos)``. Um item mal formado não deita fora os
    outros: fica de fora e gera um aviso (ver ``parse_response``).
    """
    if not any(line.strip() for line in lines):
        return [], []
    if system_prompt is None:
        system_prompt = load_internal_prompt()
    request = build_request(lines, user_instructions)

    attempts = max(1, attempts)
    last_problem = ""
    for _ in range(attempts):
        answer = generate(system_prompt, request)
        try:
            return parse_response(answer, lines)
        except DetectionError as error:
            last_problem = str(error)
    raise DetectionError(
        "A deteção falhou após %d tentativa(s): %s" % (attempts, last_problem)
    )


def parse_response(answer, lines):
    """Valida a resposta do modelo e devolve ``(itens, avisos)``.

    Levanta ``DetectionError`` se a resposta não for uma lista JSON. Cada
    elemento inválido gera um aviso ``{"index", "line", "text", "problem"}``
    e fica de fora; os repetidos (mesma linha, texto e ocorrência) contam uma
    só vez.
    """
    data = _load_json(answer)
    if not isinstance(data, list):
        raise DetectionError("A resposta do modelo não é uma lista JSON.")

    items, warnings, seen = [], [], set()
    for index, raw in enumerate(data):
        item, problem = _validate(raw, len(lines))
        if problem:
            warnings.append(_warning(index, raw, problem))
            continue
        key = (item["line"], item["text"], item.get("occurrence"))
        if key not in seen:
            seen.add(key)
            items.append(item)
    return items, warnings


def _load_json(answer):
    """Lê o JSON da resposta, tolerando blocos de código à volta."""
    if not isinstance(answer, str) or not answer.strip():
        raise DetectionError("A resposta do modelo está vazia.")
    text = _strip_code_fence(answer.strip())
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("["), text.rfind("]")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            pass
    raise DetectionError("A resposta do modelo não é JSON válido.")


def _strip_code_fence(text):
    """Tira o bloco de código (três acentos graves) à volta do texto."""
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[1] if "\n" in text else ""
    body = body.rstrip()
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()


def _is_int(value):
    """Inteiro verdadeiro (``True`` e ``False`` não contam)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate(raw, line_count):
    """Valida um elemento. Devolve ``(item, None)`` ou ``(None, problema)``."""
    if not isinstance(raw, dict):
        return None, "o elemento não é um objeto"
    line = raw.get("line")
    if not _is_int(line) or not 1 <= line <= line_count:
        return None, "número de linha inválido"
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, "texto em falta ou vazio"
    if raw.get("category") not in CATEGORY_NAMES:
        return None, "categoria desconhecida"
    if raw.get("confidence") not in CONFIDENCE_LEVELS:
        return None, "confiança desconhecida"
    reason = raw.get("reason")
    if reason is not None and not isinstance(reason, str):
        return None, "razão inválida"
    occurrence = raw.get("occurrence")
    if occurrence is not None and (not _is_int(occurrence) or occurrence < 1):
        return None, "ocorrência inválida"

    item = {
        "line": line,
        "text": unicodedata.normalize("NFC", text),
        "category": raw["category"],
        "reason": (reason or "").strip(),
        "confidence": raw["confidence"],
        "source": SOURCE,
    }
    if occurrence is not None:
        item["occurrence"] = occurrence
    return item, None


def _warning(index, raw, problem):
    """Aviso sobre um elemento rejeitado, no formato dos avisos do resto."""
    fields = raw if isinstance(raw, dict) else {}
    line = fields.get("line")
    text = fields.get("text")
    return {
        "index": index,
        "line": line if _is_int(line) else None,
        "text": text if isinstance(text, str) else None,
        "problem": problem,
    }
