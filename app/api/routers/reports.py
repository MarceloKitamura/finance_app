"""
Endpoints de relatórios.

Rotas (prefixo /reports):
- GET /reports/monthly?year=&month=  → resumo do mês

Toda a matemática (somar receitas, despesas, saldo, agrupar por
categoria/pessoa) já vive no ReportService. Aqui só repassamos.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_report_service
from app.api.schemas import MonthlySummaryOut, TransactionOut
from app.services.report_service import ReportService

router = APIRouter()


@router.get("/monthly", response_model=MonthlySummaryOut)
def monthly_summary(
    year: int = Query(default=date.today().year, description="Ano do resumo."),
    month: int = Query(default=date.today().month, ge=1, le=12, description="Mês (1-12)."),
    service: ReportService = Depends(get_report_service),
):
    """Resumo financeiro de um mês: totais, saldo e agrupamentos."""
    summary = service.monthly_summary(year, month)

    # O service devolve as transações como objetos Transaction; convertemos
    # para o schema de saída antes de serializar em JSON.
    return MonthlySummaryOut(
        year=summary["year"],
        month=summary["month"],
        count=summary["count"],
        total_incomes=summary["total_incomes"],
        total_expenses=summary["total_expenses"],
        balance=summary["balance"],
        expenses_by_category=summary["expenses_by_category"],
        expenses_by_person=summary["expenses_by_person"],
        transactions=[
            TransactionOut.from_entity(t) for t in summary["transactions"]
        ],
    )
