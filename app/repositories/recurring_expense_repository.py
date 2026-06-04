"""
Repository de gastos recorrentes (templates). Única camada com SQL da
tabela `recurring_expenses`.

Mesma filosofia dos outros repositories: services e routers conversam com
objetos RecurringExpense, nunca com linhas do banco.
"""

from typing import List, Optional

from app.database import get_connection
from app.models.recurring_expense import RecurringExpense


class RecurringExpenseRepository:
    """Acesso a dados da tabela recurring_expenses."""

    def create(self, item: RecurringExpense) -> RecurringExpense:
        sql = """
        INSERT INTO recurring_expenses
            (description, amount, type, category, payment_method, spent_by,
             account, card, day_of_month, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            item.description, item.amount, item.type, item.category,
            item.payment_method, item.spent_by, item.account, item.card,
            item.day_of_month, item.active, item.created_at,
        )
        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            item.id = cursor.lastrowid
        return item

    def list_all(self) -> List[RecurringExpense]:
        """Lista templates, mais recentes primeiro."""
        sql = "SELECT * FROM recurring_expenses ORDER BY id DESC"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def get_by_id(self, item_id: int) -> Optional[RecurringExpense]:
        sql = "SELECT * FROM recurring_expenses WHERE id = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (item_id,)).fetchone()
        return self._row_to_entity(row) if row else None

    def update(self, item: RecurringExpense) -> RecurringExpense:
        sql = """
        UPDATE recurring_expenses
        SET description = ?, amount = ?, type = ?, category = ?,
            payment_method = ?, spent_by = ?, account = ?, card = ?,
            day_of_month = ?, active = ?
        WHERE id = ?
        """
        params = (
            item.description, item.amount, item.type, item.category,
            item.payment_method, item.spent_by, item.account, item.card,
            item.day_of_month, item.active, item.id,
        )
        with get_connection() as conn:
            conn.execute(sql, params)
        return item

    def delete(self, item_id: int) -> bool:
        sql = "DELETE FROM recurring_expenses WHERE id = ?"
        with get_connection() as conn:
            cursor = conn.execute(sql, (item_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_entity(row) -> RecurringExpense:
        return RecurringExpense(
            id=row["id"],
            description=row["description"],
            amount=row["amount"],
            type=row["type"],
            category=row["category"],
            payment_method=row["payment_method"],
            spent_by=row["spent_by"],
            account=row["account"],
            card=row["card"],
            day_of_month=row["day_of_month"],
            active=row["active"],
            created_at=row["created_at"],
        )
