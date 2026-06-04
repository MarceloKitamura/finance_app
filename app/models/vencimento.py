"""
Modelo (entidade) Vencimento — uma conta/compromisso a vencer.

Exemplos: "Aluguel" (todo dia 5), "Fatura Nubank" (dia 10), "IPVA" (data
única). A agenda de vencimentos usa essas datas para montar o fluxo de
caixa do mês e alertar antes do vencimento.

Decisão de design (igual ao resto do projeto): o saldo/fluxo NÃO é gravado
aqui — é calculado pelo VencimentoService a partir das contas e dos
vencimentos pendentes. Esta entidade só guarda o compromisso em si.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Tipos de vencimento (só organizam/ilustram, não travam).
VENCIMENTO_KINDS = ("conta", "cartao", "meta", "outro")

# Status possíveis. "atrasado" é DERIVADO (due_date < hoje e ainda pendente)
# e calculado pelo service; no banco guardamos só "pendente"/"pago".
STATUS_PENDENTE = "pendente"
STATUS_PAGO = "pago"
STATUS_ATRASADO = "atrasado"

# Recorrência: "unica" (só uma vez) ou "mensal" (gera a próxima ao pagar).
RECURRENCES = ("unica", "mensal")


@dataclass
class Vencimento:
    """Representa um vencimento (conta a pagar).

    Campos:
        name: descrição do compromisso (ex: "Aluguel").
        due_date: data de vencimento (YYYY-MM-DD).
        amount: valor a pagar (>= 0).
        kind: categoria do vencimento (ver VENCIMENTO_KINDS).
        status: "pendente" ou "pago" (atrasado é derivado no service).
        notify_days: avisar N dias antes (padrão 3).
        recurrence: "unica" ou "mensal".
        category: categoria financeira opcional (espelha as de despesa).
        notes: observação livre.
        paid_at: data em que foi pago (YYYY-MM-DD) ou "" se pendente.
        id: identificador no banco (None enquanto não salvo).
        created_at: data/hora de criação.
    """

    name: str
    due_date: str
    amount: float = 0.0
    kind: str = "conta"
    status: str = STATUS_PENDENTE
    notify_days: int = 3
    recurrence: str = "unica"
    category: str = ""
    notes: str = ""
    paid_at: str = ""
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def validate(self) -> None:
        """Validações de domínio. Lança ValueError em caso de erro."""
        if not self.name or not self.name.strip():
            raise ValueError("O nome do vencimento não pode ser vazio.")
        if self.amount < 0:
            raise ValueError("O valor não pode ser negativo.")
        if self.kind not in VENCIMENTO_KINDS:
            raise ValueError(
                f"Tipo de vencimento inválido: {self.kind!r}. Use {VENCIMENTO_KINDS}."
            )
        if self.recurrence not in RECURRENCES:
            raise ValueError(
                f"Recorrência inválida: {self.recurrence!r}. Use {RECURRENCES}."
            )
        if self.status not in (STATUS_PENDENTE, STATUS_PAGO):
            raise ValueError(
                f"Status inválido: {self.status!r}. Use 'pendente' ou 'pago'."
            )
        # Valida formato ISO da data.
        try:
            datetime.strptime(self.due_date, "%Y-%m-%d")
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Data inválida: {self.due_date!r}. Use o formato YYYY-MM-DD."
            ) from exc
