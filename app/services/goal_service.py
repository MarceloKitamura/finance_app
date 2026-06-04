"""
Service de metas financeiras.

Calcula o PROGRESSO de cada meta de acordo com o tipo (kind):

- limite_gasto: progresso = despesas da categoria no mês informado
  (vem do ReportService). Aqui, ultrapassar o alvo é ruim.
- poupanca / divida: progresso = current_amount (informado pelo usuário).
  Aqui, chegar ao alvo é bom.

Também devolve o status (em_andamento | atingida | estourou) e quantos
dias faltam para o término — úteis na barra de progresso e nos alertas.
"""

from datetime import date, datetime
from typing import List

from app.models.goal import Goal
from app.repositories.goal_repository import GoalRepository
from app.services.report_service import ReportService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GoalService:
    """Regras de negócio para metas financeiras."""

    def __init__(
        self,
        repository: GoalRepository | None = None,
        report_service: ReportService | None = None,
    ):
        self.repository = repository or GoalRepository()
        self.report_service = report_service or ReportService()

    # ---------- Leitura (com progresso) ----------

    def list_with_progress(self, year: int, month: int) -> List[dict]:
        """Lista as metas com progresso calculado para o mês informado."""
        # Calcula os gastos por categoria do mês uma única vez (para os
        # limites de gasto não recalcularem por meta).
        summary = self.report_service.monthly_summary(year, month)
        by_category = summary["expenses_by_category"]

        return [self._with_progress(g, by_category) for g in self.repository.list_all()]

    def _with_progress(self, g: Goal, by_category: dict) -> dict:
        if g.kind == "limite_gasto":
            current = by_category.get(g.category, 0.0)
            exceeded = current > g.target_amount
            atingida = current >= g.target_amount  # aqui "atingir" = estourar
            status = "estourou" if exceeded else "em_andamento"
        else:  # poupanca | divida
            current = g.current_amount
            atingida = current >= g.target_amount
            exceeded = False
            status = "atingida" if atingida else "em_andamento"

        pct = (current / g.target_amount * 100) if g.target_amount > 0 else 0.0

        return {
            "id": g.id,
            "name": g.name,
            "kind": g.kind,
            "target_amount": g.target_amount,
            "category": g.category,
            "start_date": g.start_date,
            "end_date": g.end_date,
            "current_amount": g.current_amount,
            "color": g.color,
            "current_value": current,
            "pct": round(pct, 1),
            "status": status,
            "exceeded": exceeded,
            "days_left": self._days_left(g.end_date),
        }

    @staticmethod
    def _days_left(end_date: str):
        """Dias até o término (None se sem data; negativo se já passou)."""
        if not end_date:
            return None
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return None
        return (end - date.today()).days

    # ---------- Escrita ----------

    def create_goal(self, **kwargs) -> Goal:
        goal = self._build_goal(**kwargs)
        goal.validate()
        saved = self.repository.create(goal)
        logger.info("Meta criada: id=%s, nome=%s, tipo=%s", saved.id, saved.name, saved.kind)
        return saved

    def update_goal(self, goal_id: int, **kwargs) -> Goal:
        existing = self.repository.get_by_id(goal_id)
        if existing is None:
            raise ValueError(f"Meta {goal_id} não encontrada.")
        goal = self._build_goal(**kwargs)
        goal.id = goal_id
        goal.created_at = existing.created_at
        goal.validate()
        self.repository.update(goal)
        logger.info("Meta atualizada: id=%s, nome=%s", goal_id, goal.name)
        return goal

    def delete_goal(self, goal_id: int) -> bool:
        deleted = self.repository.delete(goal_id)
        if deleted:
            logger.info("Meta removida: id=%s", goal_id)
        return deleted

    # ---------- Auxiliar ----------

    @staticmethod
    def _build_goal(
        name: str,
        kind: str = "poupanca",
        target_amount: float = 0.0,
        category: str = "",
        start_date: str = "",
        end_date: str = "",
        current_amount: float = 0.0,
        color: str = "#10B981",
    ) -> Goal:
        return Goal(
            name=(name or "").strip(),
            kind=(kind or "poupanca").strip(),
            target_amount=float(target_amount or 0),
            category=(category or "").strip(),
            start_date=(start_date or "").strip(),
            end_date=(end_date or "").strip(),
            current_amount=float(current_amount or 0),
            color=(color or "#10B981").strip(),
        )
