"""
Service de relatórios.

Responsável por calcular totais, saldos e agrupamentos.
Não conhece SQL nem interface — só recebe dados (via repository)
e devolve números/estruturas prontas para exibição.
"""

from typing import Dict, List

from app.models.transaction import TYPE_EXPENSE, TYPE_INCOME, Transaction
from app.repositories.transaction_repository import TransactionRepository


class ReportService:
    """Cálculos financeiros e agregações."""

    def __init__(self, repository: TransactionRepository | None = None):
        self.repository = repository or TransactionRepository()

    def total_incomes(self, transactions: List[Transaction]) -> float:
        """Soma das receitas em uma lista de transações."""
        return sum(t.amount for t in transactions if t.type == TYPE_INCOME)

    def total_expenses(self, transactions: List[Transaction]) -> float:
        """Soma das despesas em uma lista de transações."""
        return sum(t.amount for t in transactions if t.type == TYPE_EXPENSE)

    def balance(self, transactions: List[Transaction]) -> float:
        """Saldo = receitas - despesas."""
        return self.total_incomes(transactions) - self.total_expenses(transactions)

    def expenses_by_category(
        self, transactions: List[Transaction]
    ) -> Dict[str, float]:
        """
        Agrupa despesas por categoria.

        Retorna um dicionário {categoria: total_gasto}, ordenado do
        maior para o menor.
        """
        totals: Dict[str, float] = {}
        for t in transactions:
            if t.type != TYPE_EXPENSE:
                continue
            totals[t.category] = totals.get(t.category, 0.0) + t.amount

        # Ordena do maior para o menor.
        return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))

    def expenses_by_person(
        self, transactions: List[Transaction]
    ) -> Dict[str, float]:
        """
        Agrupa despesas por pessoa (quem gastou).

        Útil para responder "quanto eu gastei?" e "quanto a namorada
        gastou usando meu cartão?". Retorna {pessoa: total}, do maior
        para o menor.
        """
        totals: Dict[str, float] = {}
        for t in transactions:
            if t.type != TYPE_EXPENSE:
                continue
            totals[t.spent_by] = totals.get(t.spent_by, 0.0) + t.amount

        return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))

    def monthly_summary(self, year: int, month: int) -> dict:
        """
        Gera um resumo completo de um mês.

        Retorna um dicionário com:
        - total de transações;
        - total de receitas;
        - total de despesas;
        - saldo;
        - gastos por categoria.
        """
        transactions = self.repository.find_by_month(year, month)

        return {
            "year": year,
            "month": month,
            "count": len(transactions),
            "total_incomes": self.total_incomes(transactions),
            "total_expenses": self.total_expenses(transactions),
            "balance": self.balance(transactions),
            "expenses_by_category": self.expenses_by_category(transactions),
            "expenses_by_person": self.expenses_by_person(transactions),
            "transactions": transactions,
        }
