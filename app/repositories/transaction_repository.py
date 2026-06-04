"""
Repository de transações.

A camada repository é a ÚNICA que escreve SQL. As demais camadas
(service, CLI) pedem dados em forma de objetos Transaction.

Vantagens dessa separação:
- Se trocarmos SQLite por outro banco, só este arquivo muda.
- A regra de negócio (services) não precisa entender SQL.
- Fica fácil de testar (podemos simular um repository em memória).
"""

from typing import List, Optional

from app.database import get_connection
from app.models.transaction import Transaction
from app.utils.date_utils import month_range


class TransactionRepository:
    """Acesso a dados da tabela transactions."""

    def create(self, transaction: Transaction) -> Transaction:
        """
        Insere uma nova transação no banco e retorna a transação
        com o id preenchido pelo SQLite.
        """
        sql = """
        INSERT INTO transactions
            (date, description, amount, type, category, payment_method,
             spent_by, account, card, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            transaction.date,
            transaction.description,
            transaction.amount,
            transaction.type,
            transaction.category,
            transaction.payment_method,
            transaction.spent_by,
            transaction.account,
            transaction.card,
            transaction.created_at,
        )

        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            transaction.id = cursor.lastrowid
        return transaction

    def list_all(self) -> List[Transaction]:
        """Retorna todas as transações ordenadas da mais recente para a mais antiga."""
        sql = "SELECT * FROM transactions ORDER BY date DESC, id DESC"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def find_by_month(self, year: int, month: int) -> List[Transaction]:
        """Retorna transações de um mês específico."""
        first_day, last_day = month_range(year, month)
        sql = """
        SELECT * FROM transactions
        WHERE date BETWEEN ? AND ?
        ORDER BY date DESC, id DESC
        """
        with get_connection() as conn:
            rows = conn.execute(sql, (first_day, last_day)).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def find_by_category(self, category: str) -> List[Transaction]:
        """Retorna transações de uma categoria (case-insensitive)."""
        sql = """
        SELECT * FROM transactions
        WHERE LOWER(category) = LOWER(?)
        ORDER BY date DESC, id DESC
        """
        with get_connection() as conn:
            rows = conn.execute(sql, (category,)).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def find_by_type(self, type_: str) -> List[Transaction]:
        """Retorna transações de um tipo ('receita' ou 'despesa')."""
        sql = "SELECT * FROM transactions WHERE type = ? ORDER BY date DESC, id DESC"
        with get_connection() as conn:
            rows = conn.execute(sql, (type_,)).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def find_by_person(self, spent_by: str) -> List[Transaction]:
        """Retorna transações de uma pessoa (case-insensitive)."""
        sql = """
        SELECT * FROM transactions
        WHERE LOWER(spent_by) = LOWER(?)
        ORDER BY date DESC, id DESC
        """
        with get_connection() as conn:
            rows = conn.execute(sql, (spent_by,)).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def get_by_id(self, transaction_id: int) -> Optional[Transaction]:
        """Busca uma transação pelo id. Retorna None se não existir."""
        sql = "SELECT * FROM transactions WHERE id = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (transaction_id,)).fetchone()
        return self._row_to_transaction(row) if row else None

    def delete(self, transaction_id: int) -> bool:
        """
        Remove uma transação pelo id.

        Retorna True se algo foi removido, False se o id não existia.
        cursor.rowcount diz quantas linhas o DELETE afetou.
        """
        sql = "DELETE FROM transactions WHERE id = ?"
        with get_connection() as conn:
            cursor = conn.execute(sql, (transaction_id,))
        return cursor.rowcount > 0

    def find_incomes_by_month(self, year: int, month: int) -> List[Transaction]:
        """Receitas de um mês."""
        return self._find_by_type_and_month("receita", year, month)

    def find_expenses_by_month(self, year: int, month: int) -> List[Transaction]:
        """Despesas de um mês."""
        return self._find_by_type_and_month("despesa", year, month)

    # ---------- Métodos auxiliares (privados) ----------

    def _find_by_type_and_month(
        self, type_: str, year: int, month: int
    ) -> List[Transaction]:
        first_day, last_day = month_range(year, month)
        sql = """
        SELECT * FROM transactions
        WHERE type = ? AND date BETWEEN ? AND ?
        ORDER BY date DESC, id DESC
        """
        with get_connection() as conn:
            rows = conn.execute(sql, (type_, first_day, last_day)).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def totals_by_account(self) -> dict:
        """Soma receitas e despesas agrupadas por conta (todo o histórico).

        Retorna {nome_conta: {"income": x, "expense": y}}. O AccountService
        usa isso para calcular o saldo atual de cada conta:
            saldo_atual = saldo_inicial + income - expense
        """
        sql = """
        SELECT account,
               COALESCE(SUM(CASE WHEN type = 'receita' THEN amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN type = 'despesa' THEN amount END), 0) AS expense
        FROM transactions
        GROUP BY account
        """
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return {
            row["account"]: {"income": row["income"], "expense": row["expense"]}
            for row in rows
        }

    def expenses_by_card_in_month(self, year: int, month: int) -> dict:
        """Soma das despesas lançadas em cada cartão num mês (a "fatura").

        Retorna {nome_cartao: total}. Ignora transações sem cartão (card='')
        e considera apenas despesas. O CardService usa isso para o uso do
        limite e o valor da fatura do mês.
        """
        first_day, last_day = month_range(year, month)
        sql = """
        SELECT card, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE type = 'despesa' AND card <> '' AND date BETWEEN ? AND ?
        GROUP BY card
        """
        with get_connection() as conn:
            rows = conn.execute(sql, (first_day, last_day)).fetchall()
        return {row["card"]: row["total"] for row in rows}

    @staticmethod
    def _row_to_transaction(row) -> Transaction:
        """
        Converte uma linha do banco (sqlite3.Row) em um objeto Transaction.

        Manter essa conversão num único lugar evita repetição.
        """
        # row.keys() permite tratar bancos antigos que ainda não têm as
        # colunas spent_by/account/card (fallback para os padrões).
        keys = row.keys()
        spent_by = row["spent_by"] if "spent_by" in keys else "Eu"
        account = row["account"] if "account" in keys else "Carteira"
        card = row["card"] if "card" in keys else ""
        return Transaction(
            id=row["id"],
            date=row["date"],
            description=row["description"],
            amount=row["amount"],
            type=row["type"],
            category=row["category"],
            payment_method=row["payment_method"],
            spent_by=spent_by,
            account=account,
            card=card,
            created_at=row["created_at"],
        )
