"""Regras de segurança: padrões fixos (regex) para dados óbvios.

Apanha emails, telefones, cartões, identificadores e outros valores com
formato conhecido que o modelo possa deixar passar. Também garante um mínimo
de proteção se a chamada à API falhar.

Os itens devolvidos têm os mesmos campos que os da deteção com o Gemini
(``line``, ``text``, ``category``, ``reason``, ``confidence``), mais
``source`` para indicar a origem. Os números de linha começam em 1, tal como
as linhas numeradas enviadas ao modelo.

Quando um padrão tem um grupo de captura, o item é apenas o grupo (o valor,
sem a etiqueta que o precede). Se dois itens se sobrepõem na mesma linha,
fica o mais comprido.
"""

import re

CERTO = "certo"
PROVAVEL = "provavel"
SOURCE = "regex"

IGNORE_CASE = re.IGNORECASE

# Separador entre uma etiqueta e o valor: "nº", "n.º", ":", "-", espaços.
SEP = r"(?:\s*n\.?[º°o]\.?)?[\s:.-]{0,4}"
# Separador entre grupos de dígitos num número.
GAP = r"[ .-]?"

PHONE_PREFIX = r"(?:\(\+351\)|\+351|00351)"
PHONE_BODY = (
    r"(?:\d{3}" + GAP + r"\d{3}" + GAP + r"\d{3}"
    r"|\d{2}[ .-]\d{3}[ .-]\d{2}[ .-]\d{2})"
)
PHONE_LANDLINE = r"2\d[ .-]\d{3}[ .-]\d{2}[ .-]\d{2}"
PHONE_NINE = r"(?:9[1236]\d|2\d\d)" + GAP + r"\d{3}" + GAP + r"\d{3}"
NOT_AFTER_NUMBER = r"(?<![\d+/.-])"

DATE = (
    r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2} de [^\W\d_]+ de \d{4})"
)

OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"


def _rule(category, reason, pattern, confidence=CERTO, flags=0):
    """Cria uma regra: categoria, razão, confiança e padrão compilado."""
    return category, reason, confidence, re.compile(pattern, flags)


RULES = [
    _rule(
        "identificacao",
        "Endereço de email.",
        r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    ),
    _rule(
        "identificacao",
        "Número de telefone.",
        PHONE_PREFIX + GAP + PHONE_BODY + r"(?!\d)",
    ),
    _rule(
        "identificacao",
        "Provável número de telefone (sem indicativo).",
        NOT_AFTER_NUMBER + r"(?:" + PHONE_NINE + r"|" + PHONE_LANDLINE + r")"
        r"(?!\d)",
        PROVAVEL,
    ),
    _rule(
        "identificacao",
        "Número de identificação fiscal (NIF).",
        r"\b(?:N\.?I\.?F\.?|Contribuinte)" + SEP
        + r"(\d{3}[ ]?\d{3}[ ]?\d{3})(?!\d)",
        flags=IGNORE_CASE,
    ),
    _rule(
        "identificacao",
        "Número do Cartão de Cidadão ou Bilhete de Identidade.",
        r"(?:Cart[ãa]o de Cidad[ãa]o|Bilhete de Identidade"
        r"|\bC\.?C\.?|\bB\.?I\.?)" + SEP
        + r"(\d{8}(?:[ -]?\d(?:[ -]?[A-Z]{2}\d)?)?)(?![\w])",
        flags=IGNORE_CASE,
    ),
    _rule(
        "identificacao",
        "Número de passaporte.",
        r"Passaporte" + SEP + r"([A-Z]{1,2}\d{6,7})\b",
        flags=IGNORE_CASE,
    ),
    _rule(
        "identificacao",
        "Número da Segurança Social.",
        r"(?:Seguran[çc]a Social|\bNISS|\bNSS)" + SEP + r"(\d{11})(?!\d)",
        flags=IGNORE_CASE,
    ),
    _rule(
        "identificacao",
        "Número de cédula profissional (CRM).",
        r"\bCRM" + SEP + r"(\d+-[A-Z]{2})\b",
    ),
    _rule(
        "identificacao",
        "Data de nascimento.",
        r"(?:Data de Nascimento|Data Nasc\.|Nascid[oa] (?:a|em)"
        r"|Nasceu (?:a|em))" + SEP + DATE,
        flags=IGNORE_CASE,
    ),
    _rule(
        "identificacao",
        "Código postal.",
        r"\b\d{4}-\d{3}\b",
        PROVAVEL,
    ),
    _rule(
        "identificacao",
        "Endereço web.",
        r"(?:https?://|www\.)[^\s<>\"')\]]*[^\s<>\"')\].,;:!?]",
        PROVAVEL,
        IGNORE_CASE,
    ),
    _rule(
        "identificacao",
        "Endereço IP.",
        r"\b(?:" + OCTET + r"\.){3}" + OCTET + r"\b",
        PROVAVEL,
    ),
    _rule(
        "financeiro",
        "Número de cartão de crédito.",
        r"\b(?:\d{4}(?:[ -]?\d{4}){3}|3[47]\d{2}[ -]?\d{6}[ -]?\d{5})\b",
    ),
    _rule(
        "financeiro",
        "Data de validade do cartão.",
        r"\b(?:validade|val\.|expira|exp\.?|expiry)" + SEP
        + r"(\d{2}/\d{2,4})\b",
        flags=IGNORE_CASE,
    ),
    _rule(
        "financeiro",
        "Código de segurança do cartão (CVV).",
        r"(?:\bCVV2?|\bCVC2?|\bCSC|C[óo]digo de seguran[çc]a)" + SEP
        + r"(\d{3,4})\b",
        flags=IGNORE_CASE,
    ),
    _rule(
        "financeiro",
        "Número de apólice de seguro.",
        r"ap[óo]lice" + SEP + r"(\d[\d-]*\d)\b",
        flags=IGNORE_CASE,
    ),
    _rule(
        "financeiro",
        "IBAN.",
        r"\bPT\d{2}(?:[ ]?\d{4}){4,5}[ ]?\d{0,3}\b",
        flags=IGNORE_CASE,
    ),
    _rule(
        "biometrico",
        "Identificador biométrico.",
        r"\b(?:ID-BIO|FACE-ID)-\d+\b",
    ),
]


def find_sensitive(lines):
    """Devolve os itens sensíveis encontrados pelas regras.

    ``lines`` é a lista de linhas do documento. Os itens vêm ordenados por
    linha e por posição.
    """
    found = []
    for number, line in enumerate(lines, start=1):
        candidates = []
        for category, reason, confidence, pattern in RULES:
            group = 1 if pattern.groups else 0
            for match in pattern.finditer(line):
                candidates.append((match.start(group), match.end(group), {
                    "line": number,
                    "text": match.group(group),
                    "category": category,
                    "reason": reason,
                    "confidence": confidence,
                    "source": SOURCE,
                }))
        found.extend(item for _, item in _drop_overlaps(candidates))
    return found


def _drop_overlaps(candidates):
    """Remove os itens contidos noutro, mantendo o mais comprido.

    Com o mesmo intervalo, fica o da regra que vem primeiro em ``RULES``.
    Devolve ``(início, item)`` ordenado pela posição na linha.
    """
    ordered = sorted(
        enumerate(candidates),
        key=lambda entry: (-(entry[1][1] - entry[1][0]), entry[0]),
    )
    kept = []
    for _, (start, end, item) in ordered:
        inside = any(s <= start and end <= e for s, e, _ in kept)
        if not inside:
            kept.append((start, end, item))
    return sorted(((s, item) for s, _, item in kept), key=lambda e: e[0])
