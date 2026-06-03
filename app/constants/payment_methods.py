"""
Formas de pagamento aceitas no sistema.

Tupla imutável, fonte única da verdade.
"""

PAYMENT_METHODS: tuple[str, ...] = (
    "Dinheiro",
    "Pix",
    "Débito",
    "Crédito",
    "Transferência",
    "Boleto",
    "Vale Refeição",
    "Vale Alimentação",
    "Outros",
)
