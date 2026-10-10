"""Valores que o utilizador pediu para deixar visíveis.

O utilizador tem a palavra final sobre o que se mascara. As instruções
``Não mascares os emails`` chegam ao modelo, que o cumpre não devolvendo
esses valores; mas as regras de segurança (``safety_rules.py``) correm sem o
modelo e continuariam a mascará-los. Para as regras também obedecerem, o
modelo devolve esses valores com ``"visible": true``: não se mascaram e
cancelam qualquer item (do modelo ou das regras) que se sobreponha na mesma
linha.

Só vale quando há instruções do utilizador: sem elas, um ``visible`` do
modelo seria uma fuga de dados por engano, por isso é ignorado.

Só usa a biblioteca padrão.
"""


def split_visible(items):
    """Separa os itens a mascarar dos marcados ``visible``."""
    masks = [item for item in items if not item.get("visible")]
    visible = [item for item in items if item.get("visible")]
    return masks, visible


def drop_overlapping(lines, items, visible):
    """Tira os itens que se sobrepõem a um valor visível.

    Devolve ``(itens_que_ficam, quantos_saíram)``. A sobreposição conta na
    mesma linha, por posição no texto; o item que sai pode ser maior ou
    menor que o valor visível.
    """
    spans = _visible_spans(lines, visible)
    kept, dropped = [], 0
    for item in items:
        if _overlaps(lines, item, spans):
            dropped += 1
        else:
            kept.append(item)
    return kept, dropped


def _visible_spans(lines, visible):
    """``{linha: [(início, fim), ...]}`` de todas as ocorrências visíveis."""
    spans = {}
    for item in visible:
        number, text = item.get("line"), item.get("text")
        if not _valid(lines, number) or not isinstance(text, str) or not text:
            continue
        line = lines[number - 1]
        start = line.find(text)
        while start >= 0:
            spans.setdefault(number, []).append((start, start + len(text)))
            start = line.find(text, start + 1)
    return spans


def _overlaps(lines, item, spans):
    number, text = item.get("line"), item.get("text")
    if number not in spans or not _valid(lines, number):
        return False
    if not isinstance(text, str) or not text:
        return False
    start = lines[number - 1].find(text)
    if start < 0:
        return False
    end = start + len(text)
    return any(start < b and a < end for a, b in spans[number])


def _valid(lines, number):
    return isinstance(number, int) and 1 <= number <= len(lines)
