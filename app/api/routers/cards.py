"""
Endpoints de cartões de crédito (CRUD + uso/fatura).

Rotas (prefixo /cards):
- GET    /cards?year=&month=  → lista cartões COM fatura/uso do mês
- POST   /cards               → cria cartão
- PUT    /cards/{id}          → atualiza (renomear propaga p/ transações)
- DELETE /cards/{id}          → remove

Regra de negócio (fatura, uso do limite, dias p/ vencer) fica no
CardService.
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_card_service
from app.api.schemas import CardCreate, CardOut, MessageOut
from app.services.card_service import CardService

router = APIRouter()


@router.get("", response_model=List[CardOut])
def list_cards(
    year: int = Query(default=date.today().year, description="Ano da fatura."),
    month: int = Query(default=date.today().month, ge=1, le=12, description="Mês (1-12)."),
    service: CardService = Depends(get_card_service),
):
    """Lista os cartões com a fatura/uso do mês informado."""
    return [CardOut(**c) for c in service.list_with_usage(year, month)]


@router.post("", response_model=CardOut, status_code=status.HTTP_201_CREATED)
def create_card(
    payload: CardCreate,
    service: CardService = Depends(get_card_service),
):
    """Cria um cartão. Nome duplicado vira erro 422."""
    service.create_card(**payload.model_dump())
    return _find_out(service, payload.name)


@router.put("/{card_id}", response_model=CardOut)
def update_card(
    card_id: int,
    payload: CardCreate,
    service: CardService = Depends(get_card_service),
):
    """Atualiza um cartão existente."""
    updated = service.update_card(card_id, **payload.model_dump())
    return _find_out(service, updated.name)


@router.delete("/{card_id}", response_model=MessageOut)
def delete_card(
    card_id: int,
    service: CardService = Depends(get_card_service),
):
    """Remove um cartão. 404 se não existir."""
    deleted = service.delete_card(card_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão {card_id} não encontrado.",
        )
    return MessageOut(detail=f"Cartão {card_id} removido.")


def _find_out(service: CardService, name: str) -> CardOut:
    """Acha o cartão (pelo nome) já com fatura/uso e devolve como CardOut."""
    today = date.today()
    for c in service.list_with_usage(today.year, today.month):
        if c["name"] == name:
            return CardOut(**c)
    raise HTTPException(status_code=500, detail="Cartão não encontrado após salvar.")
