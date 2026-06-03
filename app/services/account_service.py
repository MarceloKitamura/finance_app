"""
Service de contas/saldos.

Regra de negócio central: o SALDO ATUAL de uma conta é

    saldo_atual = saldo_inicial + (receitas da conta) - (despesas da conta)

As receitas/despesas vêm das transações cujo campo `account` aponta para
o nome da conta. Mantemos o saldo CALCULADO (e não gravado), para nunca
ficar dessincronizado do histórico de transações.
"""

import sqlite3
from typing import List

from app.models.account import Account
from app.repositories.account_repository import AccountRepository
from app.repositories.transaction_repository import TransactionRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AccountService:
    """Regras de negócio para contas/saldos."""

    def __init__(
        self,
        repository: AccountRepository | None = None,
        transaction_repository: TransactionRepository | None = None,
    ):
        self.repository = repository or AccountRepository()
        self.transaction_repository = transaction_repository or TransactionRepository()

    # ---------- Leitura (com saldo calculado) ----------

    def list_with_balances(self) -> List[dict]:
        """Lista as contas já com o saldo atual e as movimentações.

        Devolve dicts (e não Account) porque o saldo atual é um dado
        DERIVADO, que não existe na entidade Account. Cada item tem:
        id, name, kind, initial_balance, color, icon, income, expense,
        current_balance.
        """
        totals = self.transaction_repository.totals_by_account()
        result = []
        for acc in self.repository.list_all():
            t = totals.get(acc.name, {"income": 0.0, "expense": 0.0})
            income = t["income"]
            expense = t["expense"]
            result.append({
                "id": acc.id,
                "name": acc.name,
                "kind": acc.kind,
                "initial_balance": acc.initial_balance,
                "color": acc.color,
                "icon": acc.icon,
                "income": income,
                "expense": expense,
                "current_balance": acc.initial_balance + income - expense,
            })
        return result

    # ---------- Escrita ----------

    def create_account(
        self,
        name: str,
        kind: str = "outro",
        initial_balance: float = 0.0,
        color: str = "#3B82F6",
        icon: str = "💰",
    ) -> Account:
        """Cria uma conta nova (nome único)."""
        account = Account(
            name=name.strip(),
            kind=(kind or "outro").strip(),
            initial_balance=float(initial_balance or 0),
            color=(color or "#3B82F6").strip(),
            icon=(icon or "💰").strip(),
        )
        account.validate()
        try:
            saved = self.repository.create(account)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Já existe uma conta chamada {name!r}.") from exc
        logger.info("Conta criada: id=%s, nome=%s", saved.id, saved.name)
        return saved

    def update_account(
        self,
        account_id: int,
        name: str,
        kind: str,
        initial_balance: float,
        color: str,
        icon: str,
    ) -> Account:
        """Atualiza uma conta existente.

        ATENÇÃO: as transações guardam o NOME da conta. Ao renomear, as
        transações antigas continuam apontando para o nome velho. Por isso,
        ao trocar o nome, propagamos a mudança para as transações também.
        """
        existing = self.repository.get_by_id(account_id)
        if existing is None:
            raise ValueError(f"Conta {account_id} não encontrada.")

        old_name = existing.name
        updated = Account(
            id=account_id,
            name=name.strip(),
            kind=(kind or "outro").strip(),
            initial_balance=float(initial_balance or 0),
            color=(color or "#3B82F6").strip(),
            icon=(icon or "💰").strip(),
            created_at=existing.created_at,
        )
        updated.validate()
        try:
            self.repository.update(updated)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Já existe uma conta chamada {name!r}.") from exc

        # Renomeou? Atualiza as transações que referenciam o nome antigo.
        if old_name != updated.name:
            self._rename_account_in_transactions(old_name, updated.name)

        logger.info("Conta atualizada: id=%s, nome=%s", account_id, updated.name)
        return updated

    def delete_account(self, account_id: int) -> bool:
        """Remove uma conta. Não apaga transações; só impede se houver uso.

        Para não criar transações "órfãs" (apontando para uma conta que não
        existe mais), bloqueamos a exclusão de contas que ainda têm
        movimentações. O usuário deve mover/excluir as transações antes.
        """
        account = self.repository.get_by_id(account_id)
        if account is None:
            return False

        totals = self.transaction_repository.totals_by_account()
        usage = totals.get(account.name)
        if usage and (usage["income"] or usage["expense"]):
            raise ValueError(
                f"A conta {account.name!r} tem transações vinculadas. "
                f"Mova ou exclua essas transações antes de remover a conta."
            )

        deleted = self.repository.delete(account_id)
        if deleted:
            logger.info("Conta removida: id=%s, nome=%s", account_id, account.name)
        return deleted

    # ---------- Auxiliar ----------

    def _rename_account_in_transactions(self, old_name: str, new_name: str) -> None:
        """Propaga a renomeação de uma conta para as transações."""
        from app.database import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE transactions SET account = ? WHERE account = ?",
                (new_name, old_name),
            )
        logger.info("Transações migradas da conta %r para %r", old_name, new_name)
