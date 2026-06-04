"""
Modelo (entidade) RecurringExpense — um "gasto recorrente" salvo como template.

Diferença entre as duas ideias que esta feature manipula:

- TEMPLATE (esta entidade): um gasto fixo que o usuário SALVA de propósito
  para reutilizar (ex: "Netflix R$ 40, todo dia 15, no Crédito"). Fica na
  tabela `recurring_expenses`.

- DETECÇÃO: padrões que o sistema DESCOBRE sozinho olhando o histórico de
  transações (mesma descrição se repetindo mês a mês). Isso NÃO é uma
  entidade persistida — é calculado on-the-fly pelo RecurringService a
  partir da tabela `transactions`.

O template carrega os mesmos campos de uma transação (categoria, forma de
pagamento, etc.) para que, ao usá-lo, o formulário de lançamento seja
preenchido de uma vez. O `day_of_month` guarda o dia esperado da cobrança
(1-31, ou 0 quando não se sabe) e serve para projetar a próxima ocorrência.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.constants.payment_methods import PAYMENT_METHODS
from app.constants.people import DEFAULT_PERSON
from app.constants.transaction_types import TYPE_EXPENSE, VALID_TYPES


@dataclass
class RecurringExpense:
    """Representa um template de gasto/receita recorrente.

    Campos:
        description: descrição canônica (ex: "Netflix").
        amount: valor esperado (positivo).
        type: "despesa" (padrão) ou "receita".
        category: categoria já normalizada.
        payment_method: forma de pagamento já normalizada.
        spent_by: quem costuma realizar o gasto.
        account: conta/saldo afetado.
        card: cartão usado (vazio = nenhum).
        day_of_month: dia esperado da cobrança (1-31; 0 = desconhecido).
        active: 1 = ativo (gera próximas ocorrências), 0 = pausado.
        id: identificador no banco (None enquanto não salvo).
        created_at: data/hora de criação.
    """

    description: str
    amount: float
    type: str = TYPE_EXPENSE
    category: str = ""
    payment_method: str = "Outros"
    spent_by: str = DEFAULT_PERSON
    account: str = "Carteira"
    card: str = ""
    day_of_month: int = 0
    active: int = 1
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def validate(self) -> None:
        """Validações de domínio. Lança ValueError se algo estiver errado.

        Assume dados JÁ normalizados pelo service (igual à Transaction).
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

        # day_of_month aceita 0 (desconhecido) ou um dia válido do mês.
        if not (0 <= int(self.day_of_month) <= 31):
            raise ValueError(
                f"Dia do mês inválido: {self.day_of_month!r}. Use 0 (desconhecido) ou 1-31."
            )
