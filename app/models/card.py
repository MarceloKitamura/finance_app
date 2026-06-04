"""
Modelo (entidade) Card — um cartão de crédito.

Diferente de Account (saldo/conta): um cartão tem LIMITE e datas de
fechamento/vencimento da fatura. O "saldo devedor" não é gravado — é
calculado a partir das despesas lançadas no cartão (ver CardService).

Decisão de design (igual a account): a transação guarda o NOME do cartão
no campo `card` (texto). A tabela `cards` é a fonte da verdade dos
metadados (limite, bandeira, datas, status).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Bandeiras conhecidas (apenas ilustram; o campo aceita texto livre na UI).
CARD_BRANDS = ("Visa", "Mastercard", "Elo", "American Express", "Hipercard", "Outra")

# Status possíveis do cartão.
CARD_STATUSES = ("ativo", "bloqueado")


@dataclass
class Card:
    """Representa um cartão de crédito.

    Campos:
        name: nome único e exibido (ex: "Nubank").
        brand: bandeira (ver CARD_BRANDS).
        limit_total: limite total do cartão (R$).
        closing_day: dia do mês em que a fatura fecha (1-31).
        due_day: dia do mês de vencimento da fatura (1-31).
        color: cor de destaque do card (hex).
        status: "ativo" ou "bloqueado".
        id: identificador no banco (None enquanto não salvo).
        created_at: data/hora de criação.
    """

    name: str
    brand: str = "Outra"
    limit_total: float = 0.0
    closing_day: int = 1
    due_day: int = 10
    color: str = "#8B5CF6"
    status: str = "ativo"
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def validate(self) -> None:
        """Validações de domínio. Lança ValueError em caso de erro."""
        if not self.name or not self.name.strip():
            raise ValueError("O nome do cartão não pode ser vazio.")
        if self.limit_total < 0:
            raise ValueError("O limite do cartão não pode ser negativo.")
        if not (1 <= int(self.closing_day) <= 31):
            raise ValueError("Dia de fechamento deve estar entre 1 e 31.")
        if not (1 <= int(self.due_day) <= 31):
            raise ValueError("Dia de vencimento deve estar entre 1 e 31.")
        if self.status not in CARD_STATUSES:
            raise ValueError(
                f"Status inválido: {self.status!r}. Use {CARD_STATUSES}."
            )
