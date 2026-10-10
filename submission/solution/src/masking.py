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
- O valor escrito sem acentos (``Conceicao``) encontra ``Conceição``.
- Os espaços e a estrutura das linhas não mudam.
- Cada item é procurado primeiro como palavra inteira, na sua linha, nas
  linhas vizinhas e depois no documento todo; só sem nenhuma palavra inteira
  se aceita um pedaço de palavra. Se não for encontrado, gera um aviso.
- Os valores são também mascarados nas outras ocorrências, quando aparecem
  como palavra inteira (``Ana`` dentro de ``Ana-Maria`` mascara o nome
  composto todo): os que têm letras com pelo menos
  ``MIN_PROPAGATION_LETTERS`` caracteres e os só com números com pelo menos
  ``MIN_PROPAGATION_LENGTH``. Uma palavra isolada não se propaga depois de
  ``Centro``, ``Hospital``... (``Centro Médico Lisboa``): fica um aviso.
- Um símbolo isolado, sem letras nem números (como ``-``), não é uma palavra
  e mantém-se.
"""

import re
import unicodedata

from words import (
    expand_compound,
    has_letters,
    mask_token,
    whole_word_pattern,
)

MIN_PROPAGATION_LENGTH = 4
MIN_PROPAGATION_LETTERS = 2
# Palavras que, antes de um valor isolado, indicam o nome de uma instituição
# (``Centro Médico Lisboa``): aí o valor não se propaga.
ORGANISATION_WORDS = frozenset({
    "centro", "hospital", "clínica", "clinica", "instituto", "universidade",
    "faculdade", "escola", "farmácia", "farmacia", "laboratório",
    "laboratorio", "câmara", "camara", "junta", "ministério", "ministerio",
    "fundação", "fundacao", "associação", "associacao", "misericórdia",
    "misericordia", "centre", "clinic", "university", "institute", "school",
    "pharmacy", "laboratory", "foundation", "association",
})
CONTEXT_WORDS = 3


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
            across = _locate_across_lines(lines, item)
            if across is not None:
                for index, start, end in across:
                    spans[index].append((start, end))
                continue
            warnings.append(_warning(item, "não encontrado no documento"))
            continue
        index, start = found
        text = lines[index][start:start + len(text)]
        spans[index].append(_cover(lines[index], start, text))
        if _should_propagate(text):
            for skipped in _add_other_occurrences(lines, text, spans):
                warnings.append(_warning(
                    {"line": skipped + 1, "text": text},
                    "não propagado: parece fazer parte do nome de uma "
                    "instituição"))
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
    found = _locate_exact(lines, item)
    if found is not None:
        return found
    # O modelo escreveu o valor sem acentos (ou com outros): o texto
    # sem acentos tem o mesmo comprimento, por isso as posições servem.
    folded = [_fold(line) for line in lines]
    return _locate_exact(folded, dict(item, text=_fold(item["text"])))


def _fold(text):
    """Tira os acentos letra a letra, mantendo o comprimento do texto."""
    out = []
    for char in unicodedata.normalize("NFC", text):
        plain = unicodedata.normalize("NFKD", char)[:1]
        out.append(plain if len(unicodedata.normalize("NFKD", char)) > 1
                   and plain.isalpha() else char)
    return "".join(out)


def _locate_exact(lines, item):
    """Procura o texto tal como está, sem alterar acentos."""
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


def _locate_across_lines(lines, item):
    """Procura um valor partido por uma mudança de linha.

    ``Rua das Flores`` com ``Rua das`` no fim de uma linha e ``Flores`` no
    início da seguinte. Devolve ``[(linha, início, fim), ...]`` com o pedaço
    de cada linha, ou None.
    """
    words = item["text"].split()
    for first in _search_order(len(lines) - 1, item.get("line")):
        for cut in range(1, len(words)):
            head = " ".join(words[:cut])
            tail = " ".join(words[cut:])
            line, following = lines[first], lines[first + 1]
            if (line.endswith(head) and following.startswith(tail)
                    and whole_word_pattern(head).search(line[-len(head) - 1:])
                    and not following[len(tail):][:1].isalnum()):
                return [(first, len(line) - len(head), len(line)),
                        (first + 1, 0, len(tail))]
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


def _cover(line, start, text):
    """Intervalo a mascarar para ``text`` encontrado em ``start``.

    Um nome dentro de um nome composto cobre o nome todo (``Ana`` em
    ``Ana-Maria`` cobre ``Ana-Maria``), porque as palavras ligadas por hífen
    são uma só e mascaram-se por inteiro. Um número cobre só o que é.
    """
    end = start + len(text)
    if has_letters(text):
        return expand_compound(line, start, end)
    return start, end


def _add_other_occurrences(lines, text, spans):
    """Acrescenta as ocorrências de ``text`` como palavra inteira.

    Devolve os índices das linhas onde uma ocorrência ficou de fora por fazer
    parte do nome de uma instituição.
    """
    pattern = whole_word_pattern(text)
    skipped = []
    for index, line in enumerate(lines):
        for match in pattern.finditer(line):
            if _in_organisation_name(line, match.start(), text):
                skipped.append(index)
                continue
            spans[index].append(_cover(line, match.start(), text))
    return skipped


def _in_organisation_name(line, start, text):
    """Diz se uma palavra isolada vem depois de ``Centro``, ``Hospital``...

    Só vale para uma palavra com letras: ``Lisboa`` em ``Centro Médico
    Lisboa`` não é a morada de ninguém. Os valores com várias palavras ou
    números propagam-se sempre.
    """
    if not has_letters(text) or len(text.split()) > 1:
        return False
    before = re.findall(r"\w+", line[:start])[-CONTEXT_WORDS:]
    return any(word.lower() in ORGANISATION_WORDS for word in before)


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
