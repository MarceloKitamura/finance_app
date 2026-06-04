"""
Repository de cartões de crédito.

Única camada que escreve SQL para a tabela `cards`. Espelha o
AccountRepository.
"""

from typing import List, Optional

from app.database import get_connection
from app.models.card import Card


class CardRepository:
    """Acesso a dados da tabela cards."""

    def create(self, card: Card) -> Card:
        sql = """
        INSERT INTO cards
            (name, brand, limit_total, closing_day, due_day, color, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            card.name, card.brand, card.limit_total, card.closing_day,
            card.due_day, card.color, card.status, card.created_at,
        )
        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            card.id = cursor.lastrowid
        return card

    def list_all(self) -> List[Card]:
        sql = "SELECT * FROM cards ORDER BY name COLLATE NOCASE"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_card(row) for row in rows]

    def get_by_id(self, card_id: int) -> Optional[Card]:
        sql = "SELECT * FROM cards WHERE id = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (card_id,)).fetchone()
        return self._row_to_card(row) if row else None

    def update(self, card: Card) -> Card:
        sql = """
        UPDATE cards
        SET name = ?, brand = ?, limit_total = ?, closing_day = ?,
            due_day = ?, color = ?, status = ?
        WHERE id = ?
        """
        params = (
            card.name, card.brand, card.limit_total, card.closing_day,
            card.due_day, card.color, card.status, card.id,
        )
        with get_connection() as conn:
            conn.execute(sql, params)
        return card

    def delete(self, card_id: int) -> bool:
        sql = "DELETE FROM cards WHERE id = ?"
        with get_connection() as conn:
            cursor = conn.execute(sql, (card_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_card(row) -> Card:
        return Card(
            id=row["id"],
            name=row["name"],
            brand=row["brand"],
            limit_total=row["limit_total"],
            closing_day=row["closing_day"],
            due_day=row["due_day"],
            color=row["color"],
            status=row["status"],
            created_at=row["created_at"],
        )
