"""
Repository da agenda de vencimentos. Única camada com SQL da tabela
`vencimentos`. Espelha o GoalRepository.
"""

from typing import List, Optional

from app.database import get_connection
from app.models.vencimento import Vencimento


class VencimentoRepository:
    """Acesso a dados da tabela vencimentos."""

    def create(self, item: Vencimento) -> Vencimento:
        sql = """
        INSERT INTO vencimentos
            (name, due_date, amount, kind, status, notify_days, recurrence,
             category, notes, paid_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            item.name, item.due_date, item.amount, item.kind, item.status,
            item.notify_days, item.recurrence, item.category, item.notes,
            item.paid_at, item.created_at,
        )
        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            item.id = cursor.lastrowid
        return item

    def list_all(self) -> List[Vencimento]:
        """Lista vencimentos ordenados pela data de vencimento (mais próximos primeiro)."""
        sql = "SELECT * FROM vencimentos ORDER BY due_date ASC, id ASC"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def get_by_id(self, item_id: int) -> Optional[Vencimento]:
        sql = "SELECT * FROM vencimentos WHERE id = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (item_id,)).fetchone()
        return self._row_to_entity(row) if row else None

    def update(self, item: Vencimento) -> Vencimento:
        sql = """
        UPDATE vencimentos
        SET name = ?, due_date = ?, amount = ?, kind = ?, status = ?,
            notify_days = ?, recurrence = ?, category = ?, notes = ?, paid_at = ?
        WHERE id = ?
        """
        params = (
            item.name, item.due_date, item.amount, item.kind, item.status,
            item.notify_days, item.recurrence, item.category, item.notes,
            item.paid_at, item.id,
        )
        with get_connection() as conn:
            conn.execute(sql, params)
        return item

    def delete(self, item_id: int) -> bool:
        sql = "DELETE FROM vencimentos WHERE id = ?"
        with get_connection() as conn:
            cursor = conn.execute(sql, (item_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_entity(row) -> Vencimento:
        return Vencimento(
            id=row["id"],
            name=row["name"],
            due_date=row["due_date"],
            amount=row["amount"],
            kind=row["kind"],
            status=row["status"],
            notify_days=row["notify_days"],
            recurrence=row["recurrence"],
            category=row["category"],
            notes=row["notes"],
            paid_at=row["paid_at"],
            created_at=row["created_at"],
        )
