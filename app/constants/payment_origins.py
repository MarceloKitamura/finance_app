"""
Origem do pagamento de uma transação: CONTA ou CARTÃO.

Uma despesa precisa ter UMA origem clara e exclusiva:

- "account": gasto direto da conta/carteira/saldo (débito, Pix, dinheiro,
  transferência). Afeta o saldo da conta imediatamente.
- "card": gasto no cartão de crédito. NÃO desconta do saldo na hora — entra
  na fatura do cartão (e pode ser parcelado).

Centralizar esses valores aqui evita strings soltas pelo código e garante
que API, services, models e interfaces falem o mesmo vocabulário.
"""

PAYMENT_ORIGIN_ACCOUNT = "account"
PAYMENT_ORIGIN_CARD = "card"

VALID_PAYMENT_ORIGINS: tuple[str, ...] = (
    PAYMENT_ORIGIN_ACCOUNT,
    PAYMENT_ORIGIN_CARD,
)

# Rótulos amigáveis para exibir na interface (português).
PAYMENT_ORIGIN_LABELS = {
    PAYMENT_ORIGIN_ACCOUNT: "Conta / carteira / saldo",
    PAYMENT_ORIGIN_CARD: "Cartão de crédito",
}
