"""
Endpoints de contas/saldos (CRUD).

Rotas (prefixo /accounts):
- GET    /accounts        → lista contas COM saldo atual calculado
- POST   /accounts        → cria conta
- PUT    /accounts/{id}   → atualiza conta (renomear propaga p/ transações)
- DELETE /accounts/{id}   → remove conta (bloqueia se houver transações)

Padrão igual aos demais routers: só chama o service e converte para o
schema de saída. Regra de negócio (saldo, renomear, bloqueio) fica no
AccountService.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_account_service
from app.api.schemas import AccountCreate, AccountOut, MessageOut
from app.services.account_service import AccountService

router = APIRouter()


@router.get("", response_model=List[AccountOut])
def list_accounts(service: AccountService = Depends(get_account_service)):
    """Lista todas as contas com o saldo atual já calculado."""
    return [AccountOut(**acc) for acc in service.list_with_balances()]


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    service: AccountService = Depends(get_account_service),
):
    """Cria uma conta. Nome duplicado vira erro 422 (via ValueError)."""
    service.create_account(
        name=payload.name,
        kind=payload.kind,
        initial_balance=payload.initial_balance,
        color=payload.color,
        icon=payload.icon,
    )
    # Relê com o saldo calculado para devolver o objeto completo.
    return _find_out(service, payload.name)


@router.put("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    payload: AccountCreate,
    service: AccountService = Depends(get_account_service),
):
    """Atualiza uma conta existente."""
    updated = service.update_account(
        account_id=account_id,
        name=payload.name,
        kind=payload.kind,
        initial_balance=payload.initial_balance,
        color=payload.color,
        icon=payload.icon,
    )
    return _find_out(service, updated.name)


@router.delete("/{account_id}", response_model=MessageOut)
def delete_account(
    account_id: int,
    service: AccountService = Depends(get_account_service),
):
    """Remove uma conta. 404 se não existir; 422 se tiver transações."""
    deleted = service.delete_account(account_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta {account_id} não encontrada.",
        )
    return MessageOut(detail=f"Conta {account_id} removida.")


def _find_out(service: AccountService, name: str) -> AccountOut:
    """Acha a conta (pelo nome) já com saldo e devolve como AccountOut."""
    for acc in service.list_with_balances():
        if acc["name"] == name:
            return AccountOut(**acc)
    # Não deveria acontecer logo após criar/atualizar.
    raise HTTPException(status_code=500, detail="Conta não encontrada após salvar.")
