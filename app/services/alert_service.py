"""
Service de alertas.

Não tem tabela própria: ele AGREGA condições já calculadas por outros
services (contas, cartões, metas) e pelo resumo do mês, transformando-as
em uma lista de alertas acionáveis. Assim, o "estado" dos alertas é sempre
derivado dos dados reais — nunca fica desatualizado.

Cada alerta tem uma `key` estável (ex: "card-limit-Nubank"). O frontend
usa essa key para o usuário marcar como lido (guardado no localStorage),
sem precisar persistir nada no backend.

Severidades: "danger" (urgente/vermelho), "warning" (atenção/amarelo),
"info" (informativo/azul).
"""

from datetime import date
from typing import List

from app.services.account_service import AccountService
from app.services.card_service import CardService
from app.services.goal_service import GoalService
from app.services.report_service import ReportService
from app.utils.money_utils import format_brl

# Limiares (ajuste fino do que dispara cada alerta).
CARD_LIMIT_WARN_PCT = 80     # uso do limite a partir do qual avisamos
CARD_DUE_SOON_DAYS = 5       # dias para o vencimento considerados "próximos"


class AlertService:
    """Gera alertas a partir do estado atual das finanças."""

    def __init__(
        self,
        account_service: AccountService | None = None,
        card_service: CardService | None = None,
        goal_service: GoalService | None = None,
        report_service: ReportService | None = None,
    ):
        self.account_service = account_service or AccountService()
        self.card_service = card_service or CardService()
        self.goal_service = goal_service or GoalService()
        self.report_service = report_service or ReportService()

    def build_alerts(self, year: int, month: int) -> List[dict]:
        """Monta a lista de alertas do mês informado (mais sérios primeiro)."""
        alerts: List[dict] = []

        self._account_alerts(alerts)
        self._card_alerts(alerts, year, month)
        self._goal_alerts(alerts, year, month)
        self._month_alerts(alerts, year, month)

        # Ordena por severidade (danger > warning > info).
        order = {"danger": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: order.get(a["severity"], 9))
        return alerts

    # ---------- Regras ----------

    def _account_alerts(self, alerts: List[dict]) -> None:
        for acc in self.account_service.list_with_balances():
            if acc["current_balance"] < 0:
                alerts.append({
                    "key": f"acc-neg-{acc['name']}",
                    "severity": "danger",
                    "icon": "🔴",
                    "title": f"Saldo negativo: {acc['name']}",
                    "message": (
                        f"A conta {acc['name']} está em "
                        f"{format_brl(acc['current_balance'])}. Considere transferir "
                        f"ou reduzir gastos nela."
                    ),
                })

    def _card_alerts(self, alerts: List[dict], year: int, month: int) -> None:
        for c in self.card_service.list_with_usage(year, month):
            if c["status"] == "bloqueado":
                continue
            if c["limit_total"] > 0 and c["usage_pct"] >= CARD_LIMIT_WARN_PCT:
                sev = "danger" if c["usage_pct"] >= 100 else "warning"
                alerts.append({
                    "key": f"card-limit-{c['name']}",
                    "severity": sev,
                    "icon": "💳",
                    "title": f"Cartão {c['name']} perto do limite",
                    "message": (
                        f"A fatura é {format_brl(c['invoice'])} "
                        f"({c['usage_pct']:.0f}% de {format_brl(c['limit_total'])}). "
                        f"Restam {format_brl(c['available'])} de limite."
                    ),
                })
            if c["invoice"] > 0 and 0 <= c["days_until_due"] <= CARD_DUE_SOON_DAYS:
                alerts.append({
                    "key": f"card-due-{c['name']}",
                    "severity": "warning",
                    "icon": "📅",
                    "title": f"Fatura do {c['name']} vence em breve",
                    "message": (
                        f"Vence em {c['days_until_due']} dia(s): "
                        f"{format_brl(c['invoice'])}."
                    ),
                })

    def _goal_alerts(self, alerts: List[dict], year: int, month: int) -> None:
        for g in self.goal_service.list_with_progress(year, month):
            if g["kind"] == "limite_gasto" and g["exceeded"]:
                alerts.append({
                    "key": f"goal-over-{g['id']}",
                    "severity": "danger",
                    "icon": "🎯",
                    "title": f"Meta estourada: {g['name']}",
                    "message": (
                        f"Você gastou {format_brl(g['current_value'])} em "
                        f"{g['category']}, acima do teto de {format_brl(g['target_amount'])}."
                    ),
                })
            elif g["kind"] == "limite_gasto" and g["pct"] >= 80 and not g["exceeded"]:
                alerts.append({
                    "key": f"goal-near-{g['id']}",
                    "severity": "warning",
                    "icon": "🎯",
                    "title": f"Perto do teto: {g['name']}",
                    "message": (
                        f"Já usou {g['pct']:.0f}% do limite de "
                        f"{format_brl(g['target_amount'])} em {g['category']}."
                    ),
                })
            # Meta com prazo vencido e ainda não atingida (poupanca/divida).
            if g["kind"] != "limite_gasto" and g["days_left"] is not None \
                    and g["days_left"] < 0 and g["status"] != "atingida":
                alerts.append({
                    "key": f"goal-late-{g['id']}",
                    "severity": "warning",
                    "icon": "⏰",
                    "title": f"Prazo vencido: {g['name']}",
                    "message": (
                        f"O prazo passou e você está em {g['pct']:.0f}% "
                        f"({format_brl(g['current_value'])} de {format_brl(g['target_amount'])})."
                    ),
                })

    def _month_alerts(self, alerts: List[dict], year: int, month: int) -> None:
        summary = self.report_service.monthly_summary(year, month)
        if summary["balance"] < 0:
            alerts.append({
                "key": f"month-neg-{year}-{month:02d}",
                "severity": "danger",
                "icon": "📉",
                "title": "Mês no vermelho",
                "message": (
                    f"As despesas ({format_brl(summary['total_expenses'])}) superaram "
                    f"as receitas ({format_brl(summary['total_incomes'])}) em "
                    f"{format_brl(abs(summary['balance']))} neste mês."
                ),
            })
