"""
Categorias de transação (receita e despesa).

Listas centralizadas: a CLI, o futuro Streamlit e qualquer outra
interface devem importar daqui. Evita listas duplicadas pelo projeto.

Usamos TUPLA (e não lista) porque queremos imutabilidade:
ninguém deve conseguir alterar essas listas em runtime.
"""

# Rótulo especial para categoria personalizada.
# Centralizado para não ficar comparando a string "Outros" no código.
OTHER_LABEL = "Outros"


EXPENSE_CATEGORIES: tuple[str, ...] = (
    "Alimentação",
    "Mercado",
    "Transporte",
    "Moradia",
    "Contas",
    "Saúde",
    "Educação",
    "Lazer",
    "Assinaturas",
    "Compras",
    "Cartão de crédito",
    "Investimentos",
    "Família",
    "Pets",
    OTHER_LABEL,
)

INCOME_CATEGORIES: tuple[str, ...] = (
    "Salário",
    "Freelance",
    "Reembolso",
    "Investimentos",
    "Presente",
    OTHER_LABEL,
)


def categories_for_type(transaction_type: str) -> tuple[str, ...]:
    """
    Retorna a tupla de categorias apropriada para o tipo da transação.

    Função simples, mas evita que a CLI tenha um if/elif decidindo
    qual lista usar. Toda a lógica de "qual lista pertence a qual tipo"
    fica neste arquivo.
    """
    # Import local para evitar import circular.
    from app.constants.transaction_types import TYPE_INCOME, TYPE_EXPENSE

    if transaction_type == TYPE_INCOME:
        return INCOME_CATEGORIES
    if transaction_type == TYPE_EXPENSE:
        return EXPENSE_CATEGORIES
    raise ValueError(f"Tipo de transação inválido: {transaction_type!r}")
