"""Categorias de dados sensíveis e níveis de confiança.

Definição única, partilhada pela deteção (valida a resposta do modelo) e pelo
relatório (mostra os nomes). Os ids são os da taxonomia (``taxonomy.md``) e os
da prompt interna (``internal_prompt.txt``): mudar um obriga a mudar os três.
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

# Do mais certo para o menos certo.
CONFIDENCE_LEVELS = ("certo", "provavel", "incerto")
