"""Mascaramento: troca cada palavra sensível por um asterisco.

Recebe as linhas do documento (com a pontuação original) e a lista de itens
da deteção e das regras de segurança. Cada item tem ``line`` (a contar de 1),
``text`` e, opcionalmente, ``occurrence``.

Regras:

- Cada palavra (separada por espaços) de um valor sensível passa a ``*``.
- A pontuação nas pontas de cada palavra mantém-se: ``Santos,`` passa a
  ``*,`` e ``(João,`` passa a ``(*,``.
- A vírgula, o ponto e vírgula e a barra separam palavras mesmo sem espaço:
  ``João,Ana`` passa a ``*,*`` e ``Rui/Ana`` a ``*/*``. Entre dois dígitos
  não separam (``1,68m``, ``2.350,50`` e ``12/03/1978`` passam a um único
  ``*``). O hífen não separa, e os endereços web e as datas com o mês
  escrito (``12/mar/1978``) são uma só palavra. A definição está em
  ``words.py``, partilhada com a verificação.
- Os espaços e a estrutura das linhas não mudam.
- Cada item é procurado primeiro como palavra inteira, na sua linha, nas
  linhas vizinhas e depois no documento todo; só sem nenhuma palavra inteira
  se aceita um pedaço de palavra. Se não for encontrado, gera um aviso.
- Os valores são também mascarados nas outras ocorrências, quando aparecem
  como palavra inteira (``Ana`` não se mascara dentro de ``Ana-Maria``): os
  que têm letras com pelo menos ``MIN_PROPAGATION_LETTERS`` caracteres e os
  só com números com pelo menos ``MIN_PROPAGATION_LENGTH``.
- Um símbolo isolado, sem letras nem números (como ``-``), não é uma palavra
  e mantém-se.
"""

import re

from words import mask_token, whole_word_pattern

MIN_PROPAGATION_LENGTH = 4
MIN_PROPAGATION_LETTERS = 3


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
        if _should_propagate(text):
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
    """Procura o item e devolve ``(índice_da_linha, posição)`` ou None.

    Uma palavra inteira ganha sempre a um pedaço de outra palavra (``Ana`` é
    a palavra em ``Anabela e Ana``, não o início de ``Anabela``) e uma linha
    mais perto da indicada ganha a uma mais longe. Só se o valor não existir
    como palavra inteira em lado nenhum é que se aceita um pedaço de palavra,
    para o valor ficar protegido (``12345`` em ``ID12345``).
    """
    text = item["text"]
    order = _search_order(len(lines), item.get("line"))
    has_line = _is_line_number(item.get("line"), len(lines))
    stated = order[0] if has_line else None
    for whole_word in (True, False):
        for index in order:
            occurrence = item.get("occurrence") if index == stated else 1
            start = _find(lines[index], text, occurrence, whole_word)
            if start is not None:
                return index, start
    return None


def _is_line_number(number, line_count):
    """Diz se ``number`` é um número de linha válido (a contar de 1)."""
    return isinstance(number, int) and 1 <= number <= line_count


def _search_order(line_count, number):
    """Índices das linhas pela ordem de procura.

    A linha indicada, as vizinhas e depois as restantes, por ordem. Sem uma
    linha válida, o documento todo por ordem.
    """
    if not _is_line_number(number, line_count):
        return list(range(line_count))
    stated = number - 1
    near = [i for i in (stated - 1, stated + 1) if 0 <= i < line_count]
    rest = [i for i in range(line_count) if i != stated and i not in near]
    return [stated] + near + rest


def _find(line, text, occurrence, whole_word):
    """Posição da n-ésima ocorrência de ``text`` na linha, ou None.

    Com ``whole_word`` só contam as ocorrências que são palavras inteiras.
    Se pedirem uma ocorrência que não existe, usa-se a primeira.
    """
    starts = _starts(line, text, whole_word)
    if not starts:
        return None
    if not isinstance(occurrence, int) or not 1 <= occurrence <= len(starts):
        occurrence = 1
    return starts[occurrence - 1]


def _starts(line, text, whole_word):
    """Posições onde ``text`` aparece na linha."""
    if whole_word:
        pattern = whole_word_pattern(text)
        return [match.start() for match in pattern.finditer(line)]
    starts = []
    start = line.find(text)
    while start != -1:
        starts.append(start)
        start = line.find(text, start + 1)
    return starts


def _should_propagate(text):
    """Diz se o valor também deve ser mascarado nas outras ocorrências.

    Valores só com números precisam de ``MIN_PROPAGATION_LENGTH`` caracteres;
    os que têm letras (nomes, por exemplo) precisam de
    ``MIN_PROPAGATION_LETTERS``.
    """
    if any(char.isalpha() for char in text):
        return len(text) >= MIN_PROPAGATION_LETTERS
    return len(text) >= MIN_PROPAGATION_LENGTH


def _add_other_occurrences(lines, text, spans):
    """Acrescenta as ocorrências de ``text`` como palavra inteira."""
    pattern = whole_word_pattern(text)
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
        part if part.isspace() else mask_token(part) for part in parts
    )
