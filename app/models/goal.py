"""
Modelo (entidade) Goal — uma meta financeira.

Três tipos (kind), cada um com uma forma de medir progresso:

- "limite_gasto": teto de gasto mensal numa categoria (ex: "no máximo
  R$ 500 em Alimentação/mês"). O progresso é CALCULADO: soma das despesas
  da categoria no mês. Estourar o teto é o "alerta".

- "poupanca": juntar um valor até uma data (ex: "R$ 5.000 até dez/2026").
  O progresso é o `current_amount`, atualizado manualmente pelo usuário
  conforme ele guarda dinheiro.

- "divida": quitar um valor (ex: "pagar R$ 1.000 de dívida"). Igual à
  poupança no cálculo: progresso = `current_amount` informado.

A data de início/fim serve para mostrar prazo e calcular se está "no
ritmo". A categoria só é obrigatória no tipo "limite_gasto".
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

GOAL_KINDS = ("limite_gasto", "poupanca", "divida")


@dataclass
class Goal:
    """Representa uma meta financeira.

    Campos:
        name: título da meta (ex: "Reserva de emergência").
        kind: "limite_gasto" | "poupanca" | "divida".
        target_amount: valor-alvo (teto, ou quanto juntar/quitar).
        category: categoria relacionada (obrigatória em limite_gasto).
        start_date / end_date: período da meta (YYYY-MM-DD; podem ser '').
        current_amount: progresso manual (poupanca/divida).
        color: cor de destaque.
        id, created_at: controle.
    """

    name: str
    kind: str = "poupanca"
    target_amount: float = 0.0
    category: str = ""
    start_date: str = ""
    end_date: str = ""
    current_amount: float = 0.0
    color: str = "#10B981"
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def validate(self) -> None:
        """Validações de domínio. Lança ValueError em caso de erro."""
        if not self.name or not self.name.strip():
            raise ValueError("O nome da meta não pode ser vazio.")
        if self.kind not in GOAL_KINDS:
            raise ValueError(f"Tipo de meta inválido: {self.kind!r}. Use {GOAL_KINDS}.")
        if self.target_amount <= 0:
            raise ValueError("O valor-alvo da meta deve ser maior que zero.")
        if self.kind == "limite_gasto" and not self.category.strip():
            raise ValueError("Metas de limite de gasto exigem uma categoria.")
        # Datas, quando informadas, devem ser ISO válidas.
        for label, value in (("início", self.start_date), ("término", self.end_date)):
            if value:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError as exc:
                    raise ValueError(
                        f"Data de {label} inválida: {value!r}. Use YYYY-MM-DD."
                    ) from exc
