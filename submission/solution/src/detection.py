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
import re
import unicodedata
from pathlib import Path

from categories import CATEGORY_NAMES, CONFIDENCE_LEVELS

SOURCE = "gemini"
DEFAULT_ATTEMPTS = 2
MARKER = re.compile(r"\s*\[(\d+)\]\s*")
TAG = re.compile(r"<(/?)(document|user_instructions)>", re.IGNORECASE)
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


def _defuse(text):
    """Impede que o texto feche ou abra os blocos do pedido.

    ``</document>`` dentro do documento ou ``</user_instructions>`` nas
    instruções ficam com um espaço (``< /document>``): lê-se na mesma, mas já
    não é uma etiqueta.
    """
    return TAG.sub(r"< \1\2>", text)


def number_lines(lines):
    """Numera as linhas a partir de 1: ``[7] Nome: ...``."""
    return "\n".join(
        "[%d] %s" % (number, _defuse(line))
        for number, line in enumerate(lines, 1)
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
            _defuse(user_instructions.strip()),
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

    Diferenças só de forma não deitam um valor fora nem o deixam por
    mascarar: o ``text`` perde os espaços das pontas, ``category`` e
    ``confidence`` ignoram maiúsculas e acentos, ``line`` e ``occurrence``
    aceitam inteiros escritos como ``1.0``, e o ``text`` passa a ser o que
    está na linha (ver ``_reconcile``).
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
        pieces, problem = _split_lines(item, len(lines))
        if problem:
            warnings.append(_warning(index, raw, problem))
            continue
        for piece in pieces:
            piece["text"] = _reconcile(piece["text"], lines[piece["line"] - 1])
            key = (piece["line"], piece["text"], piece.get("occurrence"))
            if key not in seen:
                seen.add(key)
                items.append(piece)
    return items, warnings


def _split_lines(item, line_count):
    """Divide um valor que atravessa linhas num item por linha.

    O modelo pode devolver um valor que continua na linha seguinte, às vezes
    com o marcador da linha copiado (``dores<quebra>[16] abdominais``). Cada
    pedaço passa a ser um item na sua linha, sem o marcador, com a mesma
    categoria, razão e confiança. A ``occurrence`` só vale para o primeiro.
    Devolve ``([itens], None)`` ou ``(None, problema)`` se um pedaço cair fora
    do documento.
    """
    parts = re.split(r"\r?\n", item["text"])
    if len(parts) == 1:
        return [item], None
    pieces, line = [], item["line"]
    for position, part in enumerate(parts):
        marker = MARKER.match(part)
        if marker:
            part = part[marker.end():]
            if position:
                line = int(marker.group(1))
        elif position:
            line += 1
        part = part.strip()
        if not part:
            continue
        if not 1 <= line <= line_count:
            return None, "valor em várias linhas fora do documento"
        piece = dict(item, line=line, text=part)
        if pieces:
            piece.pop("occurrence", None)
        pieces.append(piece)
    if not pieces:
        return None, "texto vazio"
    return pieces, None


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


def _as_int(value):
    """Devolve o inteiro, ou ``None``.

    Aceita um inteiro e um decimal sem parte fracionária (``1.0``). Um
    booleano ou um texto não contam.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _fold(value):
    """Texto sem acentos, em minúsculas e sem espaços nas pontas."""
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return plain.strip().lower()


def _validate(raw, line_count):
    """Valida um elemento. Devolve ``(item, None)`` ou ``(None, problema)``."""
    if not isinstance(raw, dict):
        return None, "o elemento não é um objeto"
    line = _as_int(raw.get("line"))
    if line is None or not 1 <= line <= line_count:
        return None, "número de linha inválido"
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, "texto em falta ou vazio"
    category = raw.get("category")
    category = _fold(category) if isinstance(category, str) else None
    if category not in CATEGORY_NAMES:
        return None, "categoria desconhecida"
    confidence = raw.get("confidence")
    confidence = _fold(confidence) if isinstance(confidence, str) else None
    if confidence not in CONFIDENCE_LEVELS:
        return None, "confiança desconhecida"
    reason = raw.get("reason")
    if reason is not None and not isinstance(reason, str):
        return None, "razão inválida"
    occurrence = raw.get("occurrence")
    if occurrence is not None:
        occurrence = _as_int(occurrence)
        if occurrence is None or occurrence < 1:
            return None, "ocorrência inválida"

    item = {
        "line": line,
        "text": unicodedata.normalize("NFC", text.strip()),
        "category": category,
        "reason": (reason or "").strip(),
        "confidence": confidence,
        "source": SOURCE,
    }
    if occurrence is not None:
        item["occurrence"] = occurrence
    return item, None


def _reconcile(text, line):
    """Devolve o texto tal como está na linha, se só difere na forma.

    O modelo pode trocar as maiúsculas ou os espaços (``rui pinto`` por
    ``Rui Pinto``) e o mascaramento procura o texto letra a letra, por isso o
    valor ficaria por mascarar. Se o texto não está na linha, procura-o sem
    distinguir maiúsculas e com os espaços normalizados, e devolve o que lá
    está. Se não o encontra, devolve-o sem alteração: o mascaramento tenta as
    linhas vizinhas e avisa se falhar. Os acentos têm de coincidir.
    """
    if text in line:
        return text
    pattern = r"\s+".join(re.escape(word) for word in text.split())
    match = re.search(pattern, line, re.IGNORECASE)
    return match.group(0) if match else text


def empty_answer_warnings(items, rule_items):
    """Avisa se o modelo não devolveu nada mas as regras de segurança sim.

    Uma lista vazia é uma resposta válida, mas, num documento em que as regras
    apanham identificadores, quase de certeza que o modelo falhou (recusou,
    perdeu o fio, foi cortado). Devolve uma lista com zero ou um aviso, no
    formato dos outros; o texto do aviso nunca inclui valores.
    """
    if items or not rule_items:
        return []
    return [{
        "index": None,
        "line": None,
        "text": None,
        "problem": (
            "o modelo não devolveu nenhum item, mas as regras de segurança "
            "apanharam %d" % len(rule_items)
        ),
    }]


def _warning(index, raw, problem):
    """Aviso sobre um elemento rejeitado, no formato dos avisos do resto."""
    fields = raw if isinstance(raw, dict) else {}
    line = _as_int(fields.get("line"))
    text = fields.get("text")
    return {
        "index": index,
        "line": line,
        "text": text if isinstance(text, str) else None,
        "problem": problem,
    }
