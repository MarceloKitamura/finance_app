"""
Service de cartões de crédito.

Regra de negócio central: a FATURA de um cartão num mês é a soma das
despesas lançadas nele naquele mês (transações com card == nome). A
partir disso calculamos o uso do limite e quanto ainda resta.

Também calculamos quantos dias faltam para o vencimento (due_day),
usado nos alertas de "vencimento próximo".

NOTA: este é um modelo simplificado de fatura (gastos do mês-calendário),
suficiente para o controle de uso de limite e alertas. Um controle de
ciclos de fatura/pagamentos por fechamento fica para uma evolução futura.
"""

import calendar
import sqlite3
from datetime import date
from typing import List

from app.models.card import Card
from app.repositories.card_repository import CardRepository
from app.repositories.transaction_repository import TransactionRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CardService:
    """Regras de negócio para cartões de crédito."""

    def __init__(
        self,
        repository: CardRepository | None = None,
        transaction_repository: TransactionRepository | None = None,
    ):
        self.repository = repository or CardRepository()
        self.transaction_repository = transaction_repository or TransactionRepository()

    # ---------- Leitura (com uso calculado) ----------

    def list_with_usage(self, year: int, month: int) -> List[dict]:
        """Lista os cartões com fatura do mês, uso do limite e dias p/ vencer.

        Cada item tem: id, name, brand, limit_total, closing_day, due_day,
        color, status, invoice (fatura do mês), available (limite - fatura),
        usage_pct (0-100), days_until_due.
        """
        invoices = self.transaction_repository.expenses_by_card_in_month(year, month)
        result = []
        for card in self.repository.list_all():
            invoice = invoices.get(card.name, 0.0)
            available = card.limit_total - invoice
            usage_pct = (invoice / card.limit_total * 100) if card.limit_total > 0 else 0.0
            result.append({
                "id": card.id,
                "name": card.name,
                "brand": card.brand,
                "limit_total": card.limit_total,
                "closing_day": card.closing_day,
                "due_day": card.due_day,
                "color": card.color,
                "status": card.status,
                "invoice": invoice,
                "available": available,
                "usage_pct": round(usage_pct, 1),
                "days_until_due": self._days_until_due(card.due_day),
            })
        return result

    def statements(
        self, card_id: int, year: int, month: int, months_ahead: int = 6
    ) -> dict:
        """Fatura detalhada do mês + as PRÓXIMAS faturas do cartão.

        Devolve, do mês informado até `months_ahead` meses à frente, uma lista
        de faturas. Cada fatura traz o total e os lançamentos (itens), com a
        informação de parcela. As parcelas futuras já estão gravadas como
        transações nos meses das respectivas faturas, então basta agrupá-las
        por mês — é a mesma regra de fatura (soma dos gastos do cartão no mês).

        Estrutura:
            {card_id, card_name, limit_total, statements: [
                {year, month, label, total, count, is_current, items: [...]}
            ]}
        """
        card = self.repository.get_by_id(card_id)
        if card is None:
            raise ValueError(f"Cartão {card_id} não encontrado.")

        today = date.today()
        statements = []
        for i in range(max(0, months_ahead) + 1):
            y, m = self._add_months(year, month, i)
            txs = self.transaction_repository.find_by_card_in_month(card.name, y, m)
            items = [
                {
                    "id": t.id,
                    "date": t.date,
                    "description": t.description,
                    "amount": round(t.amount, 2),
                    "category": t.category,
                    "spent_by": t.spent_by,
                    "installment_no": t.installment_no,
                    "installments_total": t.installments_total,
                }
                for t in txs
            ]
            statements.append({
                "year": y,
                "month": m,
                "label": self._month_label(y, m),
                "total": round(sum(t.amount for t in txs), 2),
                "count": len(items),
                "is_current": (y == today.year and m == today.month),
                "items": items,
            })

        return {
            "card_id": card.id,
            "card_name": card.name,
            "limit_total": card.limit_total,
            "statements": statements,
        }

    @staticmethod
    def _add_months(year: int, month: int, count: int) -> tuple[int, int]:
        """Avança `count` meses a partir de (year, month)."""
        index = (year * 12 + (month - 1)) + count
        return index // 12, (index % 12) + 1

    @staticmethod
    def _month_label(year: int, month: int) -> str:
        nomes = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
        ]
        return f"{nomes[month - 1]}/{year}"

    @staticmethod
    def _days_until_due(due_day: int) -> int:
        """Quantos dias faltam até a próxima ocorrência do dia de vencimento.

        Se o dia de vencimento já passou neste mês, conta para o mês seguinte.
        O dia é "clampado" ao tamanho do mês (ex: dia 31 em fevereiro vira 28/29).
        """
        today = date.today()

        def clamp(y: int, m: int, d: int) -> date:
            last = calendar.monthrange(y, m)[1]
            return date(y, m, min(d, last))

        due_this_month = clamp(today.year, today.month, due_day)
        if due_this_month >= today:
            return (due_this_month - today).days
        # Já passou: próximo mês.
        ny, nm = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return (clamp(ny, nm, due_day) - today).days

    # ---------- Escrita ----------

    def create_card(self, **kwargs) -> Card:
        """Cria um cartão novo (nome único). kwargs = campos do Card."""
        card = self._build_card(**kwargs)
        card.validate()
        try:
            saved = self.repository.create(card)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Já existe um cartão chamado {kwargs.get('name')!r}.") from exc
        logger.info("Cartão criado: id=%s, nome=%s", saved.id, saved.name)
        return saved

    def update_card(self, card_id: int, **kwargs) -> Card:
        """Atualiza um cartão. Renomear propaga para as transações."""
        existing = self.repository.get_by_id(card_id)
        if existing is None:
            raise ValueError(f"Cartão {card_id} não encontrado.")

        old_name = existing.name
        card = self._build_card(**kwargs)
        card.id = card_id
        card.created_at = existing.created_at
        card.validate()
        try:
            self.repository.update(card)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Já existe um cartão chamado {kwargs.get('name')!r}.") from exc

        if old_name != card.name:
            self._rename_card_in_transactions(old_name, card.name)

        logger.info("Cartão atualizado: id=%s, nome=%s", card_id, card.name)
        return card

    def delete_card(self, card_id: int) -> bool:
        """Remove um cartão. As transações históricas mantêm o nome antigo."""
        card = self.repository.get_by_id(card_id)
        if card is None:
            return False
        deleted = self.repository.delete(card_id)
        if deleted:
            logger.info("Cartão removido: id=%s, nome=%s", card_id, card.name)
        return deleted

    # ---------- Auxiliares ----------

    @staticmethod
    def _build_card(
        name: str,
        brand: str = "Outra",
        limit_total: float = 0.0,
        closing_day: int = 1,
        due_day: int = 10,
        color: str = "#8B5CF6",
        status: str = "ativo",
    ) -> Card:
        return Card(
            name=(name or "").strip(),
            brand=(brand or "Outra").strip(),
            limit_total=float(limit_total or 0),
            closing_day=int(closing_day or 1),
            due_day=int(due_day or 10),
            color=(color or "#8B5CF6").strip(),
            status=(status or "ativo").strip(),
        )

    def _rename_card_in_transactions(self, old_name: str, new_name: str) -> None:
        from app.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE transactions SET card = ? WHERE card = ?",
                (new_name, old_name),
            )
        logger.info("Transações migradas do cartão %r para %r", old_name, new_name)
