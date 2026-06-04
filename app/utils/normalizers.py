"""
Normalizadores de entradas de texto.

Objetivo: receber variações que o usuário pode digitar
("pix", "PIX", "Pix", "credito", "cartão crédito") e devolver
sempre a forma canônica ("Pix", "Crédito").

Estratégia em duas camadas:
1. _strip_accents_lower: remove acentos e baixa a caixa.
   Resolve a maioria dos casos triviais (PIX → pix).
2. Mapa de sinônimos: trata os casos onde a versão canônica
   tem várias grafias razoáveis (cartao credito → Crédito).
"""

import unicodedata
from typing import Iterable, Optional

from app.constants.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from app.constants.payment_methods import PAYMENT_METHODS


# Mapa de sinônimos → forma canônica (já sem acento, lowercase).
# Quando o usuário digita algo "esquisito", procuramos aqui primeiro.
_PAYMENT_SYNONYMS = {
    "cartao": "Crédito",
    "cartao credito": "Crédito",
    "cartao de credito": "Crédito",
    "credito": "Crédito",
    "cred": "Crédito",
    "debito": "Débito",
    "cartao debito": "Débito",
    "cartao de debito": "Débito",
    "deb": "Débito",
    "pix": "Pix",
    "dinheiro": "Dinheiro",
    "especie": "Dinheiro",
    "cash": "Dinheiro",
    "transferencia": "Transferência",
    "ted": "Transferência",
    "doc": "Transferência",
    "boleto": "Boleto",
    "vale refeicao": "Vale Refeição",
    "vale-refeicao": "Vale Refeição",
    "vr": "Vale Refeição",
    "vale alimentacao": "Vale Alimentação",
    "vale-alimentacao": "Vale Alimentação",
    "va": "Vale Alimentação",
    "outros": "Outros",
    "outro": "Outros",
}


def _strip_accents_lower(text: str) -> str:
    """
    Remove acentos e converte para minúsculas.

    Ex: "Alimentação" -> "alimentacao"
    Ex: "  PIX  "     -> "pix"

    Usado tanto na normalização quanto na busca em listas.
    """
    text = text.strip().lower()
    # NFD separa a letra do acento (ex: "ç" vira "c" + caractere combinante).
    nfd = unicodedata.normalize("NFD", text)
    # Remove os caracteres combinantes (categoria "Mn" = Mark, Nonspacing).
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def _match_in_canonical_list(
    user_input: str, canonical_list: Iterable[str]
) -> Optional[str]:
    """
    Tenta achar a forma canônica olhando se o texto digitado,
    sem acento e em minúsculas, bate com alguma da lista oficial.

    Retorna a string canônica original se encontrar, None caso contrário.
    """
    normalized_input = _strip_accents_lower(user_input)
    for canonical in canonical_list:
        if _strip_accents_lower(canonical) == normalized_input:
            return canonical
    return None


def normalize_payment_method(user_input: str) -> str:
    """
    Padroniza uma forma de pagamento digitada pelo usuário.

    Ordem de tentativas:
    1. O texto bate com alguma forma canônica (ignorando acento/caixa)?
    2. O texto bate com algum sinônimo conhecido?
    3. Se nada bater, lança ValueError.

    Exemplos:
      "pix"            -> "Pix"
      "PIX"            -> "Pix"
      "credito"        -> "Crédito"
      "cartao credito" -> "Crédito"
    """
    if not user_input or not user_input.strip():
        raise ValueError("Forma de pagamento não pode ser vazia.")

    # 1) Match direto contra a lista canônica.
    match = _match_in_canonical_list(user_input, PAYMENT_METHODS)
    if match is not None:
        return match

    # 2) Match contra o dicionário de sinônimos.
    normalized = _strip_accents_lower(user_input)
    if normalized in _PAYMENT_SYNONYMS:
        return _PAYMENT_SYNONYMS[normalized]

    raise ValueError(
        f"Forma de pagamento inválida: {user_input!r}. "
        f"Aceitas: {', '.join(PAYMENT_METHODS)}."
    )


def normalize_category(user_input: str, transaction_type: str) -> str:
    """
    Padroniza uma categoria.

    Se bater com alguma categoria pré-definida (ignorando acento/caixa),
    devolve a versão canônica. Caso contrário, devolve o texto digitado
    em "Title Case" (Primeira Letra De Cada Palavra Maiúscula).

    Por que aceitar categorias personalizadas aqui em vez de recusar?
    Porque o usuário pode escolher a opção "Outros" no menu e digitar
    o próprio rótulo. Esse rótulo personalizado também precisa entrar
    padronizado no banco.
    """
    if not user_input or not user_input.strip():
        raise ValueError("Categoria não pode ser vazia.")

    # Tenta achar nas duas listas (receita ou despesa, dependendo do tipo).
    from app.constants.transaction_types import TYPE_INCOME, TYPE_EXPENSE
    if transaction_type == TYPE_INCOME:
        canonical_list = INCOME_CATEGORIES
    elif transaction_type == TYPE_EXPENSE:
        canonical_list = EXPENSE_CATEGORIES
    else:
        # Fallback: procura em ambas (não deveria acontecer).
        canonical_list = EXPENSE_CATEGORIES + INCOME_CATEGORIES

    match = _match_in_canonical_list(user_input, canonical_list)
    if match is not None:
        return match

    # Categoria personalizada: padroniza em Title Case.
    # str.title() é simples e suficiente para nosso caso.
    return user_input.strip().title()


def normalize_transaction_type(user_input: str) -> str:
    """
    Padroniza o tipo: aceita "receita", "RECEITA", "Receita", etc.
    """
    from app.constants.transaction_types import VALID_TYPES

    match = _match_in_canonical_list(user_input, VALID_TYPES)
    if match is not None:
        return match
    raise ValueError(
        f"Tipo inválido: {user_input!r}. Use {VALID_TYPES}."
    )
