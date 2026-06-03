"""
Endpoints de metas financeiras (CRUD + progresso).

Rotas (prefixo /goals):
- GET    /goals?year=&month=  → lista metas COM progresso do mês
- POST   /goals               → cria meta
- PUT    /goals/{id}          → atualiza meta
- DELETE /goals/{id}          → remove meta

O cálculo do progresso (incluindo limite de gasto por categoria) fica no
GoalService.
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_goal_service
from app.api.schemas import GoalCreate, GoalOut, MessageOut
from app.services.goal_service import GoalService

router = APIRouter()


@router.get("", response_model=List[GoalOut])
def list_goals(
    year: int = Query(default=date.today().year),
    month: int = Query(default=date.today().month, ge=1, le=12),
    service: GoalService = Depends(get_goal_service),
):
    """Lista as metas com progresso calculado para o mês informado."""
    return [GoalOut(**g) for g in service.list_with_progress(year, month)]


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreate,
    service: GoalService = Depends(get_goal_service),
):
    """Cria uma meta. Validações de domínio viram 422 (via ValueError)."""
    created = service.create_goal(**payload.model_dump())
    return _find_out(service, created.id)


@router.put("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: int,
    payload: GoalCreate,
    service: GoalService = Depends(get_goal_service),
):
    """Atualiza uma meta existente."""
    service.update_goal(goal_id, **payload.model_dump())
    return _find_out(service, goal_id)


@router.delete("/{goal_id}", response_model=MessageOut)
def delete_goal(
    goal_id: int,
    service: GoalService = Depends(get_goal_service),
):
    """Remove uma meta. 404 se não existir."""
    deleted = service.delete_goal(goal_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meta {goal_id} não encontrada.",
        )
    return MessageOut(detail=f"Meta {goal_id} removida.")


def _find_out(service: GoalService, goal_id: int) -> GoalOut:
    """Acha a meta (pelo id) já com progresso e devolve como GoalOut."""
    today = date.today()
    for g in service.list_with_progress(today.year, today.month):
        if g["id"] == goal_id:
            return GoalOut(**g)
    raise HTTPException(status_code=500, detail="Meta não encontrada após salvar.")
