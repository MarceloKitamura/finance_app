"""
Endpoint de alertas.

Rotas (prefixo /alerts):
- GET /alerts?year=&month=  → lista de alertas do mês

Os alertas são DERIVADOS do estado atual (contas, cartões, metas, mês),
calculados pelo AlertService. Não há POST/DELETE: "resolver" um alerta é
mudar o dado que o originou (pagar a fatura, cobrir o saldo, etc.). O
"marcar como lido" é feito no frontend (localStorage), usando a `key`.
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_alert_service
from app.api.schemas import AlertOut
from app.services.alert_service import AlertService

router = APIRouter()


@router.get("", response_model=List[AlertOut])
def list_alerts(
    year: int = Query(default=date.today().year),
    month: int = Query(default=date.today().month, ge=1, le=12),
    service: AlertService = Depends(get_alert_service),
):
    """Lista os alertas do mês informado (mais sérios primeiro)."""
    return [AlertOut(**a) for a in service.build_alerts(year, month)]
