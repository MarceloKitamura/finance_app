"""
Repository de contas/saldos.

Mesma filosofia do TransactionRepository: é a ÚNICA camada que escreve
SQL para a tabela `accounts`. Services e routers conversam com objetos
Account, nunca com linhas do banco.
"""

from typing import List, Optional

from app.database import get_connection
from app.models.account import Account


class AccountRepository:
    """Acesso a dados da tabela accounts."""

    def create(self, account: Account) -> Account:
        """Insere uma conta nova e devolve com o id preenchido.

        Pode levantar sqlite3.IntegrityError se o nome já existir (UNIQUE);
        o service traduz isso numa mensagem amigável.
        """
        sql = """
        INSERT INTO accounts (name, kind, initial_balance, color, icon, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            account.name,
            account.kind,
            account.initial_balance,
            account.color,
            account.icon,
            account.created_at,
        )
        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            account.id = cursor.lastrowid
        return account

    def list_all(self) -> List[Account]:
        """Lista contas em ordem alfabética."""
        sql = "SELECT * FROM accounts ORDER BY name COLLATE NOCASE"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_account(row) for row in rows]

    def get_by_id(self, account_id: int) -> Optional[Account]:
        sql = "SELECT * FROM accounts WHERE id = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (account_id,)).fetchone()
        return self._row_to_account(row) if row else None

    def get_by_name(self, name: str) -> Optional[Account]:
        sql = "SELECT * FROM accounts WHERE name = ? COLLATE NOCASE"
        with get_connection() as conn:
            row = conn.execute(sql, (name,)).fetchone()
        return self._row_to_account(row) if row else None

    def update(self, account: Account) -> Account:
        """Atualiza uma conta existente (pelo id)."""
        sql = """
        UPDATE accounts
        SET name = ?, kind = ?, initial_balance = ?, color = ?, icon = ?
        WHERE id = ?
        """
        params = (
            account.name,
            account.kind,
            account.initial_balance,
            account.color,
            account.icon,
            account.id,
        )
        with get_connection() as conn:
            conn.execute(sql, params)
        return account

    def delete(self, account_id: int) -> bool:
        """Remove uma conta pelo id. True se removeu, False se não existia."""
        sql = "DELETE FROM accounts WHERE id = ?"
        with get_connection() as conn:
            cursor = conn.execute(sql, (account_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_account(row) -> Account:
        return Account(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            initial_balance=row["initial_balance"],
            color=row["color"],
            icon=row["icon"],
            created_at=row["created_at"],
        )
