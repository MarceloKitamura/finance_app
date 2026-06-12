"""
Endpoints de transações (CRUD).

Rotas (prefixo /transactions, definido no main.py):
- GET    /transactions          → lista (com filtros opcionais)
- GET    /transactions/{id}     → busca uma
- POST   /transactions          → cria
- DELETE /transactions/{id}     → remove

Repare no padrão: cada endpoint só chama o service e converte o
resultado para o schema de saída. Nada de SQL ou regra de negócio aqui.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_transaction_service
from app.api.schemas import (
    MessageOut,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services.transaction_service import TransactionService
from app.utils.date_utils import format_iso

router = APIRouter()


@router.get("", response_model=List[TransactionOut])
def list_transactions(
    year: Optional[int] = Query(None, description="Filtra por ano (use junto com month)."),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filtra por mês (1-12)."),
    category: Optional[str] = Query(None, description="Filtra por categoria."),
    spent_by: Optional[str] = Query(None, description="Filtra por quem gastou."),
    type: Optional[str] = Query(None, description="'receita' ou 'despesa'."),
    service: TransactionService = Depends(get_transaction_service),
):
    """Lista transações.

    Sem nenhum filtro, devolve todas. Os filtros são opcionais e
    aplicados em ordem de especificidade (mês > categoria > pessoa);
    o filtro de tipo é aplicado por último, em memória.
    """
    if year and month:
        items = service.list_by_month(year, month)
    elif category:
        items = service.list_by_category(category)
    elif spent_by:
        items = service.list_by_person(spent_by)
    else:
        items = service.list_all()

    if type:
        items = [t for t in items if t.type == type]

    return [TransactionOut.from_entity(t) for t in items]


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service),
):
    """Busca uma transação pelo id. Devolve 404 se não existir."""
    transaction = service.get_transaction(transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação {transaction_id} não encontrada.",
        )
    return TransactionOut.from_entity(transaction)


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service),
):
    """Cria uma transação.

    O FastAPI já validou o formato (via TransactionCreate). A validação
    de DOMÍNIO (tipo/categoria/pagamento válidos) acontece no service e,
    se falhar, vira erro 422 graças ao handler de ValueError no main.py.

    Convertemos a data (objeto date) para o formato interno ISO que o
    service espera.

    Para gasto no cartão parcelado (payment_origin='card', installments>1),
    o service cria UMA transação por parcela nas faturas futuras; aqui
    devolvemos a 1ª parcela como representante (o cliente recarrega a lista).
    """
    transaction = service.add_transaction(
        date=format_iso(payload.date),
        description=payload.description,
        amount=payload.amount,
        type_=payload.type,
        category=payload.category,
        payment_method=payload.payment_method,
        spent_by=payload.spent_by,
        account=payload.account,
        card=payload.card,
        payment_origin=payload.payment_origin,
        installments=payload.installments,
    )
    return TransactionOut.from_entity(transaction)


@router.put("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    apply_to_group: bool = Query(
        default=False,
        description=(
            "True = propaga quem gastou/categoria/pagamento/conta/cartão para "
            "TODAS as parcelas da mesma compra (mantém valor/data de cada uma)."
        ),
    ),
    service: TransactionService = Depends(get_transaction_service),
):
    """Edita uma transação no lugar (sem reparcelar nem trocar o id).

    Campos omitidos mantêm o valor atual. A metadata de parcela é preservada
    pelo service — então dá para ajustar só o valor de uma parcela (ex.: os
    centavos da última) sem desfazer o vínculo da compra. Com apply_to_group=True,
    os campos compartilhados (ex.: "quem gastou") valem para a compra inteira.
    404 se o id não existe.
    """
    transaction = service.get_transaction(transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação {transaction_id} não encontrada.",
        )
    updated = service.update_transaction(
        transaction_id,
        date=format_iso(payload.date) if payload.date is not None else None,
        description=payload.description,
        amount=payload.amount,
        type_=payload.type,
        category=payload.category,
        payment_method=payload.payment_method,
        spent_by=payload.spent_by,
        account=payload.account,
        card=payload.card,
        payment_origin=payload.payment_origin,
        apply_to_group=apply_to_group,
    )
    return TransactionOut.from_entity(updated)


@router.delete("/{transaction_id}", response_model=MessageOut)
def delete_transaction(
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service),
):
    """Remove uma transação. Devolve 404 se o id não existir."""
    deleted = service.delete_transaction(transaction_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação {transaction_id} não encontrada.",
        )
    return MessageOut(detail=f"Transação {transaction_id} removida.")
