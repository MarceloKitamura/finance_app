"""
Endpoints da agenda de vencimentos (Fase 3).

Rotas (prefixo /vencimentos):
- GET    /vencimentos                  → lista (ou próximos, com ?upcoming_days=)
- POST   /vencimentos                  → cria
- PUT    /vencimentos/{id}             → atualiza
- DELETE /vencimentos/{id}             → remove
- POST   /vencimentos/{id}/pay         → marca como pago (mensal gera próxima)
- GET    /vencimentos/cash-flow        → projeção de fluxo de caixa do mês

Padrão igual aos demais routers: só chama o service e converte para o
schema de saída. A regra (status derivado, fluxo de caixa, recorrência) fica
no VencimentoService. Rotas literais (/cash-flow) antes das com parâmetro.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_vencimento_service
from app.api.schemas import (
    CashFlowOut,
    MessageOut,
    VencimentoCreate,
    VencimentoOut,
)
from app.services.vencimento_service import VencimentoService

router = APIRouter()


@router.get("", response_model=List[VencimentoOut])
def list_vencimentos(
    upcoming_days: Optional[int] = Query(
        None, ge=1, le=365, description="Se informado, só os próximos N dias (pendentes)."
    ),
    service: VencimentoService = Depends(get_vencimento_service),
):
    """Lista vencimentos. Com ?upcoming_days=, devolve só os pendentes/atrasados
    dentro da janela informada (para a seção 'próximos vencimentos')."""
    if upcoming_days is not None:
        items = service.upcoming(upcoming_days)
    else:
        items = service.list_vencimentos()
    return [VencimentoOut(**v) for v in items]


@router.get("/cash-flow", response_model=CashFlowOut)
def cash_flow(
    year: int = Query(..., description="Ano (ex: 2026)."),
    month: int = Query(..., ge=1, le=12, description="Mês (1-12)."),
    service: VencimentoService = Depends(get_vencimento_service),
):
    """Projeção de saldo dia a dia no mês, descontando vencimentos pendentes."""
    return CashFlowOut(**service.cash_flow(year, month))


@router.post("", response_model=VencimentoOut, status_code=status.HTTP_201_CREATED)
def create_vencimento(
    payload: VencimentoCreate,
    service: VencimentoService = Depends(get_vencimento_service),
):
    """Cria um vencimento."""
    saved = service.create(
        name=payload.name, due_date=payload.due_date, amount=payload.amount,
        kind=payload.kind, notify_days=payload.notify_days,
        recurrence=payload.recurrence, category=payload.category, notes=payload.notes,
    )
    return _find_out(service, saved.id)


@router.put("/{item_id}", response_model=VencimentoOut)
def update_vencimento(
    item_id: int,
    payload: VencimentoCreate,
    service: VencimentoService = Depends(get_vencimento_service),
):
    """Atualiza um vencimento existente."""
    service.update(
        item_id=item_id, name=payload.name, due_date=payload.due_date,
        amount=payload.amount, kind=payload.kind, notify_days=payload.notify_days,
        recurrence=payload.recurrence, category=payload.category, notes=payload.notes,
        status=payload.status,
    )
    return _find_out(service, item_id)


@router.delete("/{item_id}", response_model=MessageOut)
def delete_vencimento(
    item_id: int,
    service: VencimentoService = Depends(get_vencimento_service),
):
    """Remove um vencimento. 404 se não existir."""
    if not service.delete(item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vencimento {item_id} não encontrado.",
        )
    return MessageOut(detail=f"Vencimento {item_id} removido.")


@router.post("/{item_id}/pay", response_model=VencimentoOut)
def pay_vencimento(
    item_id: int,
    service: VencimentoService = Depends(get_vencimento_service),
):
    """Marca um vencimento como pago (recorrência mensal gera a próxima)."""
    paid = service.mark_paid(item_id)
    if paid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vencimento {item_id} não encontrado.",
        )
    return _find_out(service, item_id)


def _find_out(service: VencimentoService, item_id: int) -> VencimentoOut:
    """Relê o vencimento (já decorado) e devolve como schema de saída."""
    for v in service.list_vencimentos():
        if v["id"] == item_id:
            return VencimentoOut(**v)
    raise HTTPException(status_code=500, detail="Vencimento não encontrado após salvar.")
