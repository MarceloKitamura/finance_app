"""
Modelo (entidade) Transaction.

Um "model" representa um conceito do domínio do problema:
aqui, uma transação financeira (receita ou despesa).

Mudança em relação à versão anterior:
- As listas de tipos e formas de pagamento agora vivem em app/constants/.
  Este arquivo apenas importa o que precisa.
- A validação agora aceita os valores canônicos das constantes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Reexporta para quem já importava daqui (compatibilidade).
from app.constants.transaction_types import (  # noqa: F401
    TYPE_INCOME,
    TYPE_EXPENSE,
    VALID_TYPES,
)
from app.constants.payment_methods import PAYMENT_METHODS
from app.constants.people import DEFAULT_PERSON


@dataclass
class Transaction:
    """
    Representa uma transação financeira.

    Campos:
        id: identificador único no banco (None quando ainda não foi salva).
        date: data da transação no formato YYYY-MM-DD.
        description: descrição livre.
        amount: valor positivo.
        type: "receita" ou "despesa".
        category: categoria (já normalizada antes de chegar aqui).
        payment_method: forma de pagamento (já normalizada).
        spent_by: quem realizou o gasto (ex: "Eu", "Namorada").
        created_at: data/hora em que o registro foi criado.
    """

    date: str
    description: str
    amount: float
    type: str
    category: str
    payment_method: str
    # Campos com valor padrão precisam vir depois dos sem padrão.
    spent_by: str = DEFAULT_PERSON
    # Conta/saldo afetado pela transação (ex: "Nubank"). Texto, igual a
    # payment_method. O padrão é a conta "Carteira".
    account: str = "Carteira"
    # Cartão de crédito usado (ex: "Nubank"). Vazio = não foi no cartão.
    card: str = ""
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def validate(self) -> None:
        """
        Validações de domínio. Lança ValueError se algo estiver errado.

        Esta validação assume que os dados JÁ FORAM normalizados pelo
        service (pix/PIX/Pix viraram "Pix"). Aqui só conferimos a
        validade final.
        """
        if self.amount <= 0:
            raise ValueError("O valor (amount) deve ser positivo.")

        if self.type not in VALID_TYPES:
            raise ValueError(
                f"Tipo inválido: {self.type!r}. Use {VALID_TYPES}."
            )

        if self.payment_method not in PAYMENT_METHODS:
            raise ValueError(
                f"Forma de pagamento inválida: {self.payment_method!r}. "
                f"Aceitas: {PAYMENT_METHODS}."
            )

        if not self.description.strip():
            raise ValueError("A descrição não pode ser vazia.")
        if not self.category.strip():
            raise ValueError("A categoria não pode ser vazia.")
        if not self.spent_by.strip():
            raise ValueError("O campo 'quem gastou' não pode ser vazio.")
        if not self.account.strip():
            raise ValueError("A conta (saldo) não pode ser vazia.")

        # Valida formato ISO da data.
        try:
            datetime.strptime(self.date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"Data inválida: {self.date!r}. Use o formato YYYY-MM-DD."
            ) from exc
