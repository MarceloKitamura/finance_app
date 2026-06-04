"""
Constantes dos tipos de transação.

Centraliza o vocabulário do domínio: o que chamamos
internamente de "receita" e "despesa".

Por que constantes em vez de strings soltas pelo código?
- Erro de digitação vira erro de Python (NameError), não bug silencioso.
- Refatorar fica trivial (renomeia em um lugar só).
- IDEs conseguem autocompletar.
"""

TYPE_INCOME = "receita"
TYPE_EXPENSE = "despesa"

VALID_TYPES = (TYPE_INCOME, TYPE_EXPENSE)
