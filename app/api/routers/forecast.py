"""
Endpoint de previsão financeira do mês.

Rotas (prefixo /forecast):
- GET /forecast?year=&month=  → previsão determinística do saldo de fim de mês

Combina saldo atual + salário a receber + entradas/saídas futuras +
recorrentes + contas a pagar (ver ForecastService). É o que alimenta o
bloco "Previsão do mês" no dashboard.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_forecast_service
from app.api.schemas import MonthlyForecastOut
from app.services.forecast_service import ForecastService

router = APIRouter()


@router.get("", response_model=MonthlyForecastOut)
def get_forecast(
    year: int = Query(default=date.today().year, description="Ano."),
    month: int = Query(default=date.today().month, ge=1, le=12, description="Mês (1-12)."),
    include_salary: bool = Query(
        default=True,
        description="False = modo sem salário: ignora o salário a receber na projeção.",
    ),
    service: ForecastService = Depends(get_forecast_service),
):
    """Projeta o saldo de fim de mês somando salário, recorrentes e contas.

    Com include_salary=False, o salário a receber é desconsiderado (visão do
    saldo sem contar com o pagamento ainda não recebido).
    """
    return MonthlyForecastOut(
        **service.monthly_forecast(year, month, include_salary=include_salary)
    )
