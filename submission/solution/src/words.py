"""Palavras: o que conta como uma palavra e como se mascara.

Definição única, usada pelo mascaramento (``masking.py``) e pela verificação
(``verification.py``). Se a regra mudasse só num deles, a verificação passava
a marcar como erro o que o mascaramento fez bem. Só usa a biblioteca padrão.

Regras (detalhes e exemplos em ``MASKING.md``):

- as palavras separam-se por espaços;
- a vírgula, o ponto e vírgula e a barra também separam palavras coladas
  (``João,Ana`` dá ``*,*``), exceto entre dois dígitos (``1,68m``);
- uma data com o mês escrito (``12/mar/1978``) é uma só palavra;
- os endereços web são uma só palavra;
- a pontuação nas pontas de uma palavra mantém-se (``Santos,`` dá ``*,``);
- um símbolo isolado, sem letras nem números (``-``), não é uma palavra;
- um hífen entre duas palavras liga-as: ``Ana-Maria`` é uma só, e um valor
  dentro dela mascara-a por inteiro.
"""

import re

MASK = "*"
EDGE_PUNCTUATION = ",;:.!?()[]{}\"'"
# Hífen normal, hífen Unicode e hífen sem quebra de linha.
HYPHENS = "-‐‑"

# Vírgula, ponto e vírgula ou barra que não está entre dois dígitos.
LIST_SEPARATOR = re.compile(r"((?<!\d)[,;/]|[,;/](?!\d))")
# Endereços web são sempre uma só palavra, apesar das barras.
WEB_ADDRESS = re.compile(r"^\W*(?:https?://|www\.)", re.IGNORECASE)

# Só meses verdadeiros: uma palavra qualquer entre barras continua a separar.
MONTH = (
    r"(?:janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro"
    r"|outubro|novembro|dezembro"
    r"|january|february|march|april|may|june|july|august|september|october"
    r"|november|december"
    r"|jan|fev|feb|mar|abr|apr|mai|jun|jul|ago|aug|set|sept|sep|out|oct|nov"
    r"|dez|dec)\.?"
)
# ``12/mar/1978``, ``12/mar`` e ``mar/1978``.
WRITTEN_DATE = re.compile(
    r"^\W*(?:\d{1,2}/" + MONTH + r"(?:/\d{2,4})?|" + MONTH + r"/\d{2,4})\W*$",
    re.IGNORECASE,
)


def mask_word(word):
    """Troca a palavra por ``*``, mantendo a pontuação nas pontas.

    Um símbolo isolado, sem letras nem números, não é uma palavra e mantém-se.
    """
    if not any(char.isalnum() for char in word):
        return word
    lead = len(word) - len(word.lstrip(EDGE_PUNCTUATION))
    trail = len(word) - len(word.rstrip(EDGE_PUNCTUATION))
    return word[:lead] + MASK + word[len(word) - trail:]


def mask_token(token):
    """Mascara uma sequência sem espaços, separando as palavras coladas.

    A vírgula, o ponto e vírgula e a barra separam palavras mesmo sem espaço
    (``João,Ana`` passa a ``*,*`` e ``Rui/Ana`` a ``*/*``), exceto entre dois
    dígitos (``1,68m``, ``12/03/1978``). Os endereços web e as datas com o mês
    escrito (``12/mar/1978``) contam como uma só palavra.
    """
    if WEB_ADDRESS.match(token) or WRITTEN_DATE.match(token):
        return mask_word(token)
    parts = LIST_SEPARATOR.split(token)
    return "".join(
        part if index % 2 else mask_word(part)
        for index, part in enumerate(parts)
    )


def has_letters(text):
    """Diz se o texto tem pelo menos uma letra (um nome, não um número)."""
    return any(char.isalpha() for char in text)


def whole_word_pattern(text):
    """Expressão que encontra ``text`` só como palavra inteira.

    Não há letras, dígitos ou ``_`` colados de nenhum dos lados:
    ``Ana`` não está em ``Anabela``, mas está em ``(Ana)``, ``Ana - Maria`` e
    ``- Ana``.

    Um hífen entre duas palavras liga-as. Para um **nome** (``text`` com
    letras), ``Ana`` está também em ``Ana-Maria``: é a palavra ``Ana-Maria``
    que se mascara (ver ``expand_compound``). Para um **número**, um hífen
    não deixa encontrá-lo (``1234`` não está em ``1234-05-06``): um número
    não se propaga para dentro de uma data ou de um código.
    """
    before = r"(?<!\w)"
    after = r"(?!\w)"
    if not has_letters(text):
        before += r"(?<!\w[" + HYPHENS + r"])"
        after += r"(?![" + HYPHENS + r"]\w)"
    return re.compile(before + re.escape(text) + after)


def _is_word_char(char):
    """Letra, dígito ou sublinhado: o que conta como parte de uma palavra."""
    return char.isalnum() or char == "_"


def _hyphen_joins(line, hyphen_at, word_at):
    """Diz se o hífen em ``hyphen_at`` liga à palavra em ``word_at``."""
    return (
        0 <= hyphen_at < len(line)
        and 0 <= word_at < len(line)
        and line[hyphen_at] in HYPHENS
        and _is_word_char(line[word_at])
    )


def expand_compound(line, start, end):
    """Alarga ``[start, end)`` ao nome ligado por hífens que o contém.

    ``Ana`` em ``Nome: Ana-Maria Silva`` cobre ``Ana-Maria``. Um hífen só
    liga se tem uma palavra de cada lado, por isso ``Ana - Maria``, ``- Ana``
    e ``Ana-`` não alargam nada. Uma pontuação à volta não faz parte do nome:
    em ``(Ana-Maria),`` cobre ``Ana-Maria``.
    """
    while True:
        moved = False
        if _hyphen_joins(line, start - 1, start - 2):
            start -= 2
            while start > 0 and _is_word_char(line[start - 1]):
                start -= 1
            moved = True
        if _hyphen_joins(line, end, end + 1):
            end += 2
            while end < len(line) and _is_word_char(line[end]):
                end += 1
            moved = True
        if not moved:
            return start, end
