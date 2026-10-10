"""Etiquetas: deixa visível o que está antes de ``:`` e mascara só o valor.

Num campo como ``Impressão digital registada no sistema: ID-BIO-12345`` o
sensível é o valor. O modelo (sobretudo o ``gemini-3.5-flash-lite``) às vezes
devolve também a etiqueta: ``Telefone: +351 912 345 678`` inteiro, ou
``Impressão digital`` à parte. O resultado seria ``*: * * *`` em vez de
``Telefone: *``. Esta passagem corrige os itens do modelo antes do
mascaramento.

Uma linha tem etiqueta quando começa por texto curto (até ``MAX_LABEL_WORDS``
palavras, sem dígitos) seguido de ``:`` e de um valor. Então:

- um item que **atravessa** os ``:`` perde a parte da etiqueta e fica só com o
  valor;
- um item **só dentro da etiqueta** é descartado se outro item da mesma linha
  cobre o valor (o campo fica protegido pelo valor). Se ninguém marcou o
  valor, o item mantém-se: não se sabe se a etiqueta era o dado sensível;
- os itens de identificação (``identificacao``) dentro da etiqueta nunca se
  descartam: ``Ana Silva: diagnosticada com...`` tem um nome antes dos ``:``.

Só usa a biblioteca padrão.
"""

import re

MAX_LABEL_WORDS = 6
KEEP_CATEGORIES = ("identificacao",)
LABEL = re.compile(r"^(\s*[^:\d]+?):(?=\s|$)")


def keep_labels(lines, items):
    """Corrige os itens para as etiquetas ficarem visíveis.

    Devolve ``(itens, alterações)``: a lista nova (os itens alterados são
    cópias; os dados não mudam) e o número de itens alterados ou descartados.
    """
    by_line = {}
    for position, item in enumerate(items):
        by_line.setdefault(item.get("line"), []).append(position)

    result, changes = list(items), 0
    drop = set()
    for number, positions in by_line.items():
        if not isinstance(number, int) or not 1 <= number <= len(lines):
            continue
        line = lines[number - 1]
        colon = _label_end(line)
        if colon is None:
            continue
        spans = {p: _span(line, items[p]) for p in positions}
        for position in positions:
            span = spans[position]
            if span is None:
                continue
            start, end = span
            item = items[position]
            if start < colon < end:
                value = item["text"][colon + 1 - start:].strip()
                changes += 1
                if value:
                    result[position] = _without_label(item, value)
                else:
                    drop.add(position)
            elif end <= colon and _label_only_is_safe(
                    item, position, positions, spans, colon):
                drop.add(position)
                changes += 1
    return [item for p, item in enumerate(result) if p not in drop], changes


def _label_end(line):
    """Posição do ``:`` da etiqueta, ou None se a linha não a tem."""
    match = LABEL.match(line)
    if not match:
        return None
    label = match.group(1)
    if not label.strip() or len(label.split()) > MAX_LABEL_WORDS:
        return None
    if not line[match.end():].strip():
        return None
    return match.end() - 1


def _span(line, item):
    """Intervalo ``(início, fim)`` do item na linha, ou None."""
    text = item.get("text")
    if not isinstance(text, str) or not text:
        return None
    start = line.find(text)
    return None if start < 0 else (start, start + len(text))


def _label_only_is_safe(item, position, positions, spans, colon):
    """O item está só na etiqueta e outro item cobre o valor da linha?"""
    if item.get("category") in KEEP_CATEGORIES:
        return False
    for other in positions:
        span = spans[other]
        if other != position and span is not None and span[0] > colon:
            return True
    return False


def _without_label(item, value):
    changed = dict(item, text=value)
    changed.pop("occurrence", None)
    return changed
