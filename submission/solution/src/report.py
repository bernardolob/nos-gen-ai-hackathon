"""Relatório: gera o relatório explicativo em Markdown.

Recebe os itens da deteção e das regras de segurança (``line``, ``text``,
``category``, ``reason``, ``confidence`` e, opcionalmente, ``source``) e os
avisos do mascaramento (``line``, ``text``, ``problem``).

O relatório não deve revelar os dados que foram ocultados. Por defeito mostra
só a linha, a categoria, a razão e o número de palavras de cada item. Com
``include_values=True`` mostra também o valor original, para uso interno
(por exemplo, na revisão manual).

Os itens com o mesmo texto na mesma linha são juntados num só, com as
origens somadas e a maior confiança.
"""

CATEGORY_NAMES = {
    "identificacao": "Identificação pessoal",
    "saude": "Saúde",
    "genetico": "Dados genéticos",
    "biometrico": "Dados biométricos",
    "origem_religiao_politica": "Origem, religião, política ou orientação",
    "financeiro": "Dados financeiros",
    "familia": "Vida familiar",
    "comportamento": "Comportamentos pessoais",
    "quasi_identificador": "Quasi-identificadores",
}

SOURCE_NAMES = {
    "gemini": "Gemini",
    "regex": "Regras de segurança",
}

DEFAULT_SOURCE = "gemini"
CONFIDENCE_ORDER = {"certo": 0, "provavel": 1, "incerto": 2}
CONFIDENCE_NAMES = {
    "certo": "certo",
    "provavel": "provável",
    "incerto": "incerto",
}


def build_report(items, warnings=None, include_values=False):
    """Devolve o relatório em Markdown.

    ``items`` são os itens mascarados, ``warnings`` os avisos do
    mascaramento e ``include_values`` indica se o valor original aparece.
    """
    merged = merge_items(items)
    lines = ["# Relatório de anonimização", ""]
    lines += _summary(merged)
    lines += _items_table(merged, include_values)
    lines += _warnings_section(warnings or [], include_values)
    return "\n".join(lines).rstrip() + "\n"


def merge_items(items):
    """Junta os itens com o mesmo texto na mesma linha.

    Mantém a primeira categoria e razão, soma as origens e fica com a maior
    confiança. A ordem é a da linha e depois a da primeira aparição.
    """
    merged = {}
    for item in items:
        key = (item.get("line"), item.get("text", ""))
        source = item.get("source") or DEFAULT_SOURCE
        if key not in merged:
            entry = dict(item)
            entry["sources"] = [source]
            merged[key] = entry
            continue
        entry = merged[key]
        if source not in entry["sources"]:
            entry["sources"].append(source)
        if _rank(item.get("confidence")) < _rank(entry.get("confidence")):
            entry["confidence"] = item.get("confidence")
    return sorted(merged.values(), key=lambda entry: _line(entry))


def _rank(confidence):
    """Ordem da confiança: quanto menor, mais certa."""
    return CONFIDENCE_ORDER.get(confidence, len(CONFIDENCE_ORDER))


def _line(entry):
    """Número de linha para ordenar (itens sem linha ficam no fim)."""
    line = entry.get("line")
    return line if isinstance(line, int) else float("inf")


def _summary(merged):
    """Secção com os totais por categoria, origem e confiança."""
    words = sum(len(entry.get("text", "").split()) for entry in merged)
    out = [
        "## Resumo",
        "",
        "- Itens ocultados: %d" % len(merged),
        "- Palavras nesses itens: %d" % words,
        "",
    ]
    out += _count_table(
        "Categoria",
        [_category_name(entry.get("category")) for entry in merged],
    )
    out += _count_table(
        "Origem",
        [_source_name(source)
         for entry in merged for source in entry["sources"]],
    )
    out += _count_table(
        "Confiança",
        [CONFIDENCE_NAMES.get(entry.get("confidence"), "desconhecida")
         for entry in merged],
    )
    return out


def _count_table(title, values):
    """Tabela com a contagem de cada valor, do mais ao menos frequente."""
    if not values:
        return []
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    rows = sorted(counts.items(), key=lambda row: (-row[1], row[0]))
    out = ["| %s | Itens |" % title, "|---|---|"]
    out += ["| %s | %d |" % (_cell(name), count) for name, count in rows]
    out.append("")
    return out


def _items_table(merged, include_values):
    """Secção com um item por linha."""
    out = ["## Itens ocultados", ""]
    if not merged:
        return out + ["Nenhum item foi ocultado.", ""]
    header = ["#", "Linha", "Categoria", "Razão", "Confiança", "Origem",
              "Palavras"]
    if include_values:
        header.append("Valor original")
    out.append("| " + " | ".join(header) + " |")
    out.append("|" + "---|" * len(header))
    for number, entry in enumerate(merged, start=1):
        text = entry.get("text", "")
        row = [
            str(number),
            _line_label(entry),
            _category_name(entry.get("category")),
            entry.get("reason") or "",
            CONFIDENCE_NAMES.get(entry.get("confidence"), "desconhecida"),
            ", ".join(_source_name(s) for s in entry["sources"]),
            str(len(text.split())),
        ]
        if include_values:
            row.append(text)
        out.append("| " + " | ".join(_cell(value) for value in row) + " |")
    out.append("")
    return out


def _warnings_section(warnings, include_values):
    """Secção com os itens que o mascaramento não conseguiu aplicar."""
    if not warnings:
        return []
    out = [
        "## Avisos",
        "",
        "Itens que não foram aplicados e precisam de revisão:",
        "",
    ]
    for warning in warnings:
        line = warning.get("line")
        where = "linha %s" % line if line is not None else "sem linha"
        text = ""
        if include_values and warning.get("text"):
            text = " (`%s`)" % warning["text"]
        out.append("- %s%s: %s" % (where, text, warning.get("problem", "")))
    out.append("")
    return out


def _line_label(entry):
    """Número da linha como texto."""
    line = entry.get("line")
    return str(line) if line is not None else "-"


def _category_name(category):
    """Nome legível da categoria."""
    return CATEGORY_NAMES.get(category, category or "sem categoria")


def _source_name(source):
    """Nome legível da origem."""
    return SOURCE_NAMES.get(source, source)


def _cell(value):
    """Prepara um valor para uma célula de tabela Markdown."""
    return str(value).replace("|", "\\|").replace("\n", " ")
