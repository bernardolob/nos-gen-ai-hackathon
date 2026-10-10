"""Regras de segurança: padrões fixos (regex) para dados óbvios.

Apanha emails, telefones, cartões, identificadores e outros valores com
formato conhecido que o modelo possa deixar passar. Também garante um mínimo
de proteção se a chamada à API falhar.

Os itens devolvidos têm os mesmos campos que os da deteção com o Gemini
(``line``, ``text``, ``category``, ``reason``, ``confidence``), mais
``source`` para indicar a origem. Os números de linha começam em 1, tal como
as linhas numeradas enviadas ao modelo.
"""

import re

CERTO = "certo"
SOURCE = "regex"

# Cada regra: (categoria, razão, padrão). Se o padrão tiver um grupo de
# captura, o item é apenas o grupo (o valor, sem a etiqueta que o precede).
RULES = [
    (
        "identificacao",
        "Endereço de email.",
        re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    ),
    (
        "identificacao",
        "Número de telefone.",
        re.compile(r"\+351[ -]?\d{3}[ -]?\d{3}[ -]?\d{3}"),
    ),
    (
        "identificacao",
        "Número de identificação fiscal (NIF).",
        re.compile(r"\bNIF\W{0,3}(\d{9})\b", re.IGNORECASE),
    ),
    (
        "identificacao",
        "Número do Cartão de Cidadão.",
        re.compile(
            r"Cart[ãa]o de Cidad[ãa]o\W{0,3}(\d{8}-?\d?[A-Z]{2}\d)",
            re.IGNORECASE,
        ),
    ),
    (
        "identificacao",
        "Número da Segurança Social.",
        re.compile(r"Seguran[çc]a Social\W{0,3}(\d{11})\b", re.IGNORECASE),
    ),
    (
        "identificacao",
        "Número de cédula profissional (CRM).",
        re.compile(r"\bCRM\W{0,3}(\d+-[A-Z]{2})\b"),
    ),
    (
        "identificacao",
        "Data de nascimento.",
        re.compile(
            r"Data de Nascimento\W{0,3}(\d{2}/\d{2}/\d{4})",
            re.IGNORECASE,
        ),
    ),
    (
        "financeiro",
        "Número de cartão de crédito.",
        re.compile(r"\b\d{4}(?:[ -]\d{4}){3}\b"),
    ),
    (
        "financeiro",
        "Data de validade do cartão.",
        re.compile(r"validade\W{0,3}(\d{2}/\d{2,4})", re.IGNORECASE),
    ),
    (
        "financeiro",
        "Código de segurança do cartão (CVV).",
        re.compile(r"\bCVV\W{0,3}(\d{3,4})\b", re.IGNORECASE),
    ),
    (
        "financeiro",
        "Número de apólice de seguro.",
        re.compile(r"ap[óo]lice\s*n[ºo.]?\s*(\d+)", re.IGNORECASE),
    ),
    (
        "financeiro",
        "IBAN.",
        re.compile(r"\bPT\d{2}(?:[ ]?\d{4}){4,5}[ ]?\d{0,3}\b"),
    ),
    (
        "biometrico",
        "Identificador biométrico.",
        re.compile(r"\b(?:ID-BIO|FACE-ID)-\d+\b"),
    ),
]


def find_sensitive(lines):
    """Devolve os itens sensíveis encontrados pelas regras.

    ``lines`` é a lista de linhas do documento. Os itens vêm ordenados por
    linha e por posição, sem repetições.
    """
    found = []
    for number, line in enumerate(lines, start=1):
        line_items = []
        for category, reason, pattern in RULES:
            for match in pattern.finditer(line):
                group = 1 if pattern.groups else 0
                line_items.append((match.start(group), {
                    "line": number,
                    "text": match.group(group),
                    "category": category,
                    "reason": reason,
                    "confidence": CERTO,
                    "source": SOURCE,
                }))
        line_items.sort(key=lambda entry: entry[0])
        found.extend(item for _, item in _drop_duplicates(line_items))
    return found


def _drop_duplicates(line_items):
    """Remove itens com o mesmo texto e a mesma posição na linha."""
    seen = set()
    for start, item in line_items:
        key = (start, item["text"])
        if key not in seen:
            seen.add(key)
            yield start, item
