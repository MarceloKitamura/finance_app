"""
Repository de metas financeiras. Única camada com SQL da tabela `goals`.
"""

from typing import List, Optional

from app.database import get_connection
from app.models.goal import Goal


class GoalRepository:
    """Acesso a dados da tabela goals."""

    def create(self, goal: Goal) -> Goal:
        sql = """
        INSERT INTO goals
            (name, kind, target_amount, category, start_date, end_date,
             current_amount, color, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            goal.name, goal.kind, goal.target_amount, goal.category,
            goal.start_date, goal.end_date, goal.current_amount, goal.color,
            goal.created_at,
        )
        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            goal.id = cursor.lastrowid
        return goal

    def list_all(self) -> List[Goal]:
        sql = "SELECT * FROM goals ORDER BY id DESC"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_goal(row) for row in rows]

    def get_by_id(self, goal_id: int) -> Optional[Goal]:
        sql = "SELECT * FROM goals WHERE id = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (goal_id,)).fetchone()
        return self._row_to_goal(row) if row else None

    def update(self, goal: Goal) -> Goal:
        sql = """
        UPDATE goals
        SET name = ?, kind = ?, target_amount = ?, category = ?,
            start_date = ?, end_date = ?, current_amount = ?, color = ?
        WHERE id = ?
        """
        params = (
            goal.name, goal.kind, goal.target_amount, goal.category,
            goal.start_date, goal.end_date, goal.current_amount, goal.color,
            goal.id,
        )
        with get_connection() as conn:
            conn.execute(sql, params)
        return goal

    def delete(self, goal_id: int) -> bool:
        sql = "DELETE FROM goals WHERE id = ?"
        with get_connection() as conn:
            cursor = conn.execute(sql, (goal_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_goal(row) -> Goal:
        return Goal(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            target_amount=row["target_amount"],
            category=row["category"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            current_amount=row["current_amount"],
            color=row["color"],
            created_at=row["created_at"],
        )
