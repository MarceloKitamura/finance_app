"""
Endpoints de metadados (listas fixas).

Rotas (prefixo /meta):
- GET /meta  → todas as listas de uma vez (tipos, pagamentos, pessoas, categorias)

Para que serve? O frontend precisa montar os <select> (dropdowns) de
"forma de pagamento", "categoria", "quem gastou", etc. Em vez de o
frontend ter essas listas duplicadas (e ficarem desatualizadas), ele
pede aqui — e a fonte da verdade continua sendo os arquivos em
app/constants/.
"""

from datetime import date

from fastapi import APIRouter, Depends

from app.api.dependencies import get_account_service, get_card_service
from app.api.schemas import MetaOut
from app.constants.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from app.constants.payment_methods import PAYMENT_METHODS
from app.constants.people import PEOPLE
from app.constants.transaction_types import VALID_TYPES
from app.services.account_service import AccountService
from app.services.card_service import CardService

router = APIRouter()


@router.get("", response_model=MetaOut)
def get_meta(
    account_service: AccountService = Depends(get_account_service),
    card_service: CardService = Depends(get_card_service),
):
    """Devolve todas as listas que o frontend usa para montar formulários.

    Inclui os nomes das contas (saldos) e cartões para os <select> do
    formulário de lançamentos.
    """
    account_names = [acc["name"] for acc in account_service.list_with_balances()]
    today = date.today()
    card_names = [c["name"] for c in card_service.list_with_usage(today.year, today.month)]
    return MetaOut(
        transaction_types=list(VALID_TYPES),
        payment_methods=list(PAYMENT_METHODS),
        people=list(PEOPLE),
        expense_categories=list(EXPENSE_CATEGORIES),
        income_categories=list(INCOME_CATEGORIES),
        accounts=account_names,
        cards=card_names,
    )
