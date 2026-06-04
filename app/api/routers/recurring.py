"""
Endpoints de gastos recorrentes (Fase 3).

Rotas (prefixo /recurring-expenses):
- GET    /recurring-expenses            → lista templates (com próxima cobrança)
- POST   /recurring-expenses            → cria template
- PUT    /recurring-expenses/{id}       → atualiza template
- DELETE /recurring-expenses/{id}       → remove template
- GET    /recurring-expenses/suggest    → autopreenchimento ao digitar descrição
- GET    /recurring-expenses/detected   → padrões detectados no histórico

Padrão igual aos demais routers: só chama o service e converte para o
schema de saída. A inteligência (detecção/sugestão) fica no RecurringService.

ATENÇÃO À ORDEM: as rotas literais (/suggest, /detected) vêm ANTES da rota
com parâmetro (/{id}) para o FastAPI não tentar interpretar "suggest" como id.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_recurring_service
from app.api.schemas import (
    DetectedRecurringOut,
    MessageOut,
    RecurringCreate,
    RecurringOut,
    RecurringSuggestionOut,
)
from app.services.recurring_service import RecurringService

router = APIRouter()


def _to_out(item, next_date=None, days_until=None) -> RecurringOut:
    return RecurringOut(
        id=item.id, description=item.description, amount=item.amount,
        type=item.type, category=item.category, payment_method=item.payment_method,
        spent_by=item.spent_by, account=item.account, card=item.card,
        day_of_month=item.day_of_month, active=item.active,
        created_at=item.created_at, next_date=next_date, days_until=days_until,
    )


@router.get("", response_model=List[RecurringOut])
def list_recurring(service: RecurringService = Depends(get_recurring_service)):
    """Lista templates, já com a próxima cobrança projetada (quando há dia)."""
    # Mapa id -> próxima ocorrência, calculado uma vez.
    next_map = {
        o["template"].id: (o["next_date"], o["days_until"])
        for o in service.next_occurrences()
    }
    out = []
    for tpl in service.list_templates():
        nd, du = next_map.get(tpl.id, (None, None))
        out.append(_to_out(tpl, nd, du))
    return out


@router.get("/suggest", response_model=List[RecurringSuggestionOut])
def suggest_recurring(
    description: str = Query(..., min_length=2, description="Texto digitado na descrição."),
    service: RecurringService = Depends(get_recurring_service),
):
    """Sugere autopreenchimentos (templates + último gasto similar)."""
    matches = service.find_similar(description)
    return [RecurringSuggestionOut(**m.__dict__) for m in matches]


@router.get("/detected", response_model=List[DetectedRecurringOut])
def detected_recurring(
    months_back: int = Query(6, ge=1, le=24, description="Janela em meses."),
    service: RecurringService = Depends(get_recurring_service),
):
    """Lista padrões recorrentes descobertos automaticamente no histórico."""
    return [DetectedRecurringOut(**d.__dict__) for d in service.detect_recurring(months_back)]


@router.post("", response_model=RecurringOut, status_code=status.HTTP_201_CREATED)
def create_recurring(
    payload: RecurringCreate,
    service: RecurringService = Depends(get_recurring_service),
):
    """Cria um template de gasto recorrente."""
    saved = service.create_template(
        description=payload.description, amount=payload.amount, type_=payload.type,
        category=payload.category, payment_method=payload.payment_method,
        spent_by=payload.spent_by, account=payload.account, card=payload.card,
        day_of_month=payload.day_of_month, active=payload.active,
    )
    return _to_out(saved)


@router.put("/{item_id}", response_model=RecurringOut)
def update_recurring(
    item_id: int,
    payload: RecurringCreate,
    service: RecurringService = Depends(get_recurring_service),
):
    """Atualiza um template existente."""
    updated = service.update_template(
        item_id=item_id,
        description=payload.description, amount=payload.amount, type_=payload.type,
        category=payload.category, payment_method=payload.payment_method,
        spent_by=payload.spent_by, account=payload.account, card=payload.card,
        day_of_month=payload.day_of_month, active=payload.active,
    )
    return _to_out(updated)


@router.delete("/{item_id}", response_model=MessageOut)
def delete_recurring(
    item_id: int,
    service: RecurringService = Depends(get_recurring_service),
):
    """Remove um template. 404 se não existir."""
    if not service.delete_template(item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gasto recorrente {item_id} não encontrado.",
        )
    return MessageOut(detail=f"Gasto recorrente {item_id} removido.")
