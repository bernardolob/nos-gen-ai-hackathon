"""Mascaramento: troca cada palavra sensível por um asterisco.

Recebe as linhas do documento (com a pontuação original) e a lista de itens
da deteção e das regras de segurança. Cada item tem ``line`` (a contar de 1),
``text`` e, opcionalmente, ``occurrence``.

Regras:

- Cada palavra (separada por espaços) de um valor sensível passa a ``*``.
- A pontuação nas pontas de cada palavra mantém-se: ``Santos,`` passa a
  ``*,`` e ``(João,`` passa a ``(*,``.
- Os espaços e a estrutura das linhas não mudam.
- Cada item é procurado na sua linha; se não estiver lá, nas linhas vizinhas
  e depois no documento todo. Se não for encontrado, gera um aviso.
- Os valores com pelo menos ``MIN_PROPAGATION_LENGTH`` caracteres são também
  mascarados nas outras ocorrências, quando aparecem como palavra inteira.
"""

import re

MASK = "*"
EDGE_PUNCTUATION = ",;:.!?()[]{}\"'"
MIN_PROPAGATION_LENGTH = 4


def mask_lines(lines, items):
    """Mascara os itens nas linhas.

    Devolve ``(linhas_mascaradas, avisos)``. Cada aviso é um dicionário com
    ``line``, ``text`` e ``problem``.
    """
    spans = [[] for _ in lines]
    warnings = []
    for item in items:
        text = item.get("text", "")
        if not text.strip():
            warnings.append(_warning(item, "texto vazio"))
            continue
        found = _locate(lines, item)
        if found is None:
            warnings.append(_warning(item, "não encontrado no documento"))
            continue
        index, start = found
        spans[index].append((start, start + len(text)))
        if len(text) >= MIN_PROPAGATION_LENGTH:
            _add_other_occurrences(lines, text, spans)
    masked = [_apply(line, spans[i]) for i, line in enumerate(lines)]
    return masked, warnings


def _warning(item, problem):
    """Cria um aviso sobre um item."""
    return {
        "line": item.get("line"),
        "text": item.get("text", ""),
        "problem": problem,
    }


def _locate(lines, item):
    """Procura o item e devolve ``(índice_da_linha, posição)`` ou None."""
    text = item["text"]
    number = item.get("line")
    near = []
    if isinstance(number, int) and 1 <= number <= len(lines):
        index = number - 1
        start = _find(lines[index], text, item.get("occurrence"))
        if start is not None:
            return index, start
        near = [index - 1, index + 1]
    for index in near + list(range(len(lines))):
        if 0 <= index < len(lines):
            start = _find(lines[index], text, 1)
            if start is not None:
                return index, start
    return None


def _find(line, text, occurrence):
    """Posição da n-ésima ocorrência de ``text`` na linha, ou None."""
    if not isinstance(occurrence, int) or occurrence < 1:
        occurrence = 1
    start = -1
    for _ in range(occurrence):
        start = line.find(text, start + 1)
        if start == -1:
            return None
    return start


def _add_other_occurrences(lines, text, spans):
    """Acrescenta as ocorrências de ``text`` como palavra inteira."""
    pattern = re.compile(r"(?<!\w)" + re.escape(text) + r"(?!\w)")
    for index, line in enumerate(lines):
        for match in pattern.finditer(line):
            spans[index].append(match.span())


def _merge(spans):
    """Junta os intervalos que se sobrepõem."""
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _apply(line, spans):
    """Mascara os intervalos de uma linha."""
    for start, end in reversed(_merge(spans)):
        line = line[:start] + _mask_span(line[start:end]) + line[end:]
    return line


def _mask_span(segment):
    """Troca cada palavra do segmento por um asterisco."""
    parts = re.split(r"(\s+)", segment)
    return "".join(
        part if part.isspace() else _mask_word(part) for part in parts
    )


def _mask_word(word):
    """Troca a palavra por ``*``, mantendo a pontuação nas pontas."""
    core = word.strip(EDGE_PUNCTUATION)
    if not core:
        return word
    lead = len(word) - len(word.lstrip(EDGE_PUNCTUATION))
    trail = len(word) - len(word.rstrip(EDGE_PUNCTUATION))
    return word[:lead] + MASK + word[len(word) - trail:]
