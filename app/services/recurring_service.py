"""
Service de gastos recorrentes.

Duas responsabilidades:

1. TEMPLATES (CRUD) — gastos fixos que o usuário salva de propósito
   (Netflix, aluguel...). Normaliza igual ao TransactionService e persiste
   na tabela `recurring_expenses`.

2. INTELIGÊNCIA sobre o histórico:
   - detect_recurring(): descobre sozinho padrões que se repetem mês a mês
     olhando a tabela `transactions` (mesma descrição, intervalo regular).
   - find_similar(): enquanto o usuário digita a descrição no formulário,
     devolve sugestões de autopreenchimento (templates + último gasto igual).

Por que detecção é calculada e não gravada? Porque o histórico muda a cada
lançamento; recalcular na hora mantém sempre atualizado e evita
dessincronização (mesma filosofia do saldo das contas).
"""

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

from app.constants.people import DEFAULT_PERSON
from app.constants.transaction_types import TYPE_EXPENSE
from app.models.recurring_expense import RecurringExpense
from app.models.transaction import Transaction
from app.repositories.recurring_expense_repository import RecurringExpenseRepository
from app.repositories.transaction_repository import TransactionRepository
from app.utils.logger import get_logger
from app.utils.normalizers import (
    normalize_category,
    normalize_payment_method,
    normalize_transaction_type,
)

logger = get_logger(__name__)


def _norm(text: str) -> str:
    """Minúsculas, sem acento e com espaços colapsados — para comparar
    descrições ("NETFLIX.COM" e "Netflix com" caem perto)."""
    text = (text or "").strip().lower()
    nfd = unicodedata.normalize("NFD", text)
    sem_acento = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return " ".join(sem_acento.split())


@dataclass
class RecurringMatch:
    """Uma sugestão de autopreenchimento (vinda de template ou do histórico)."""
    description: str
    amount: float
    type: str
    category: str
    payment_method: str
    spent_by: str
    account: str
    card: str
    source: str          # "template" | "historico"
    last_date: str        # data da última ocorrência (histórico) ou ""
    occurrences: int      # quantas vezes apareceu (histórico) ou 1
    template_id: Optional[int] = None


@dataclass
class DetectedRecurring:
    """Um padrão recorrente DESCOBERTO no histórico (não é template salvo)."""
    description: str
    avg_amount: float
    type: str
    category: str
    payment_method: str
    spent_by: str
    account: str
    card: str
    occurrences: int        # total de lançamentos no período
    months_present: int     # em quantos meses distintos apareceu
    day_of_month: int       # dia típico da cobrança (mediana)
    last_date: str          # data da última ocorrência
    next_expected: str      # próxima ocorrência projetada (YYYY-MM-DD)
    already_template: bool  # já existe um template salvo p/ esta descrição


class RecurringService:
    """Regras de negócio para gastos recorrentes."""

    def __init__(
        self,
        repository: RecurringExpenseRepository | None = None,
        transaction_repository: TransactionRepository | None = None,
    ):
        self.repository = repository or RecurringExpenseRepository()
        self.transaction_repository = transaction_repository or TransactionRepository()

    # ═══════════════════════════════════════════════════════
    # TEMPLATES (CRUD)
    # ═══════════════════════════════════════════════════════

    def list_templates(self) -> List[RecurringExpense]:
        return self.repository.list_all()

    def get_template(self, item_id: int) -> Optional[RecurringExpense]:
        return self.repository.get_by_id(item_id)

    def create_template(
        self,
        description: str,
        amount: float,
        type_: str = TYPE_EXPENSE,
        category: str = "",
        payment_method: str = "Outros",
        spent_by: str = DEFAULT_PERSON,
        account: str = "Carteira",
        card: str = "",
        day_of_month: int = 0,
        active: int = 1,
    ) -> RecurringExpense:
        """Cria um template (normaliza igual a uma transação)."""
        item = self._build(
            None, description, amount, type_, category, payment_method,
            spent_by, account, card, day_of_month, active,
        )
        saved = self.repository.create(item)
        logger.info("Template recorrente criado: id=%s, desc=%s", saved.id, saved.description)
        return saved

    def update_template(
        self,
        item_id: int,
        description: str,
        amount: float,
        type_: str,
        category: str,
        payment_method: str,
        spent_by: str,
        account: str,
        card: str,
        day_of_month: int,
        active: int,
    ) -> RecurringExpense:
        existing = self.repository.get_by_id(item_id)
        if existing is None:
            raise ValueError(f"Gasto recorrente {item_id} não encontrado.")
        item = self._build(
            item_id, description, amount, type_, category, payment_method,
            spent_by, account, card, day_of_month, active,
        )
        item.created_at = existing.created_at
        self.repository.update(item)
        logger.info("Template recorrente atualizado: id=%s", item_id)
        return item

    def delete_template(self, item_id: int) -> bool:
        deleted = self.repository.delete(item_id)
        if deleted:
            logger.info("Template recorrente removido: id=%s", item_id)
        return deleted

    def _build(
        self, item_id, description, amount, type_, category, payment_method,
        spent_by, account, card, day_of_month, active,
    ) -> RecurringExpense:
        """Normaliza os campos e monta a entidade, já validada."""
        normalized_type = normalize_transaction_type(type_)
        normalized_category = normalize_category(category, normalized_type)
        normalized_payment = normalize_payment_method(payment_method)
        item = RecurringExpense(
            id=item_id,
            description=(description or "").strip(),
            amount=float(amount),
            type=normalized_type,
            category=normalized_category,
            payment_method=normalized_payment,
            spent_by=(spent_by or "").strip() or DEFAULT_PERSON,
            account=(account or "").strip() or "Carteira",
            card=(card or "").strip(),
            day_of_month=int(day_of_month or 0),
            active=1 if active else 0,
        )
        item.validate()
        return item

    # ═══════════════════════════════════════════════════════
    # AUTOPREENCHIMENTO (busca de similares)
    # ═══════════════════════════════════════════════════════

    def find_similar(self, query: str, limit: int = 6) -> List[RecurringMatch]:
        """Sugere autopreenchimentos para a descrição que está sendo digitada.

        Combina duas fontes (templates primeiro, depois histórico), sem
        repetir a mesma descrição. Cada sugestão traz todos os campos para
        preencher o formulário de uma vez.
        """
        q = _norm(query)
        if len(q) < 2:
            return []

        results: List[RecurringMatch] = []
        seen: set[str] = set()

        # 1) Templates salvos cuja descrição contém o texto digitado.
        for tpl in self.repository.list_all():
            if not tpl.active:
                continue
            key = _norm(tpl.description)
            if q in key and key not in seen:
                seen.add(key)
                results.append(RecurringMatch(
                    description=tpl.description,
                    amount=tpl.amount,
                    type=tpl.type,
                    category=tpl.category,
                    payment_method=tpl.payment_method,
                    spent_by=tpl.spent_by,
                    account=tpl.account,
                    card=tpl.card,
                    source="template",
                    last_date="",
                    occurrences=1,
                    template_id=tpl.id,
                ))

        # 2) Histórico: agrupa transações por descrição e pega a mais recente
        #    de cada grupo que casa com o texto digitado.
        groups: dict[str, List[Transaction]] = defaultdict(list)
        for t in self.transaction_repository.list_all():
            key = _norm(t.description)
            if q in key:
                groups[key].append(t)

        historico: List[RecurringMatch] = []
        for key, txs in groups.items():
            if key in seen:
                continue
            # Mais recente do grupo = base do autopreenchimento.
            txs.sort(key=lambda t: t.date, reverse=True)
            last = txs[0]
            historico.append(RecurringMatch(
                description=last.description,
                amount=last.amount,
                type=last.type,
                category=last.category,
                payment_method=last.payment_method,
                spent_by=last.spent_by,
                account=last.account,
                card=last.card,
                source="historico",
                last_date=last.date,
                occurrences=len(txs),
            ))

        # Histórico ordenado por frequência (mais recorrente primeiro) e recência.
        historico.sort(key=lambda m: (m.occurrences, m.last_date), reverse=True)
        results.extend(historico)

        return results[:limit]

    # ═══════════════════════════════════════════════════════
    # DETECÇÃO AUTOMÁTICA (padrões no histórico)
    # ═══════════════════════════════════════════════════════

    def detect_recurring(
        self, months_back: int = 6, min_months: int = 2
    ) -> List[DetectedRecurring]:
        """Descobre gastos que se repetem regularmente no histórico.

        Critério: mesma descrição aparecendo em pelo menos `min_months` meses
        DISTINTOS dentro da janela de `months_back` meses. Isso captura
        assinaturas e contas fixas e ignora compras avulsas.
        """
        cutoff = self._months_ago(months_back)
        existing_keys = {_norm(t.description) for t in self.repository.list_all()}

        # Agrupa transações recentes por descrição normalizada.
        groups: dict[str, List[Transaction]] = defaultdict(list)
        for t in self.transaction_repository.list_all():
            if t.date >= cutoff:
                groups[_norm(t.description)].append(t)

        detected: List[DetectedRecurring] = []
        for key, txs in groups.items():
            meses = {t.date[:7] for t in txs}  # "YYYY-MM" distintos
            if len(meses) < min_months:
                continue

            txs.sort(key=lambda t: t.date)
            last = txs[-1]
            amounts = [t.amount for t in txs]
            avg = sum(amounts) / len(amounts)
            dias = sorted(int(t.date[8:10]) for t in txs)
            dia_tipico = dias[len(dias) // 2]  # mediana

            detected.append(DetectedRecurring(
                description=last.description,
                avg_amount=round(avg, 2),
                type=last.type,
                category=last.category,
                payment_method=last.payment_method,
                spent_by=last.spent_by,
                account=last.account,
                card=last.card,
                occurrences=len(txs),
                months_present=len(meses),
                day_of_month=dia_tipico,
                last_date=last.date,
                next_expected=self._next_after(last.date, dia_tipico),
                already_template=key in existing_keys,
            ))

        # Mais relevantes primeiro: mais meses, depois maior valor médio.
        detected.sort(key=lambda d: (d.months_present, d.avg_amount), reverse=True)
        return detected

    # ---------- Auxiliares de data ----------

    @staticmethod
    def _months_ago(months: int) -> str:
        """Data (YYYY-MM-DD) de `months` meses atrás a partir de hoje."""
        today = date.today()
        m = today.month - months
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        day = min(today.day, 28)  # evita 31 em meses curtos
        return date(y, m, day).strftime("%Y-%m-%d")

    @staticmethod
    def _next_after(last_iso: str, day_of_month: int) -> str:
        """Projeta a próxima ocorrência: mês seguinte ao último, no dia típico."""
        try:
            last = datetime.strptime(last_iso[:10], "%Y-%m-%d").date()
        except ValueError:
            return ""
        m = last.month + 1
        y = last.year
        if m > 12:
            m = 1
            y += 1
        # Garante um dia válido para o mês (ex: dia 31 em fevereiro).
        d = day_of_month if 1 <= day_of_month <= 28 else min(max(day_of_month, 1), 28)
        return date(y, m, d).strftime("%Y-%m-%d")

    def next_occurrences(self, reference: Optional[date] = None) -> List[dict]:
        """Para cada template ativo, projeta a próxima cobrança esperada.

        Devolve dicts {template, next_date, days_until} ordenados por
        proximidade. Usado pela página de recorrentes para mostrar "próximas
        ocorrências".
        """
        ref = reference or date.today()
        out = []
        for tpl in self.repository.list_all():
            if not tpl.active or not (1 <= tpl.day_of_month <= 31):
                continue
            nxt = self._next_occurrence_from(ref, tpl.day_of_month)
            out.append({
                "template": tpl,
                "next_date": nxt.strftime("%Y-%m-%d"),
                "days_until": (nxt - ref).days,
            })
        out.sort(key=lambda x: x["days_until"])
        return out

    @staticmethod
    def _next_occurrence_from(ref: date, day_of_month: int) -> date:
        """Próxima data >= hoje que caia no `day_of_month` informado."""
        d = min(day_of_month, 28)
        candidate = ref.replace(day=d)
        if candidate < ref:
            m = ref.month + 1
            y = ref.year
            if m > 12:
                m, y = 1, y + 1
            candidate = date(y, m, d)
        return candidate
