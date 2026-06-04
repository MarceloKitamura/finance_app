"""
Service da agenda de vencimentos / fluxo de caixa.

Duas responsabilidades:

1. CRUD dos vencimentos (contas a pagar), incluindo "marcar como pago" —
   que, em vencimentos mensais, já cria automaticamente a ocorrência do
   mês seguinte.

2. FLUXO DE CAIXA: projeta, dia a dia, como o saldo evolui no mês ao
   subtrair os vencimentos pendentes. O saldo inicial vem das contas
   (AccountService), então o fluxo nunca fica dessincronizado do real.

O status "atrasado" é DERIVADO (due_date < hoje e ainda pendente): não é
gravado no banco, é calculado na leitura. Isso evita ter que rodar um job
diário para "envelhecer" os vencimentos.
"""

from datetime import date, datetime, timedelta
from typing import List, Optional

from app.models.vencimento import (
    STATUS_ATRASADO,
    STATUS_PAGO,
    STATUS_PENDENTE,
    Vencimento,
)
from app.repositories.vencimento_repository import VencimentoRepository
from app.services.account_service import AccountService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VencimentoService:
    """Regras de negócio para vencimentos e fluxo de caixa."""

    def __init__(
        self,
        repository: VencimentoRepository | None = None,
        account_service: AccountService | None = None,
    ):
        self.repository = repository or VencimentoRepository()
        # Reusa o AccountService para saber o saldo inicial do fluxo (mesmo
        # padrão de injeção que o AlertService usa).
        self.account_service = account_service or AccountService()

    # ═══════════════════════════════════════════════════════
    # LEITURA
    # ═══════════════════════════════════════════════════════

    def list_vencimentos(self) -> List[dict]:
        """Lista todos os vencimentos com status/nível/dias derivados."""
        today = date.today()
        return [self._decorate(v, today) for v in self.repository.list_all()]

    def upcoming(self, days: int = 30) -> List[dict]:
        """Vencimentos PENDENTES (incluindo atrasados) até `days` dias à frente.

        Atrasados entram sempre (já passaram). Pendentes futuros entram se
        caírem na janela. Ordenados por data.
        """
        today = date.today()
        limite = today + timedelta(days=days)
        out = []
        for v in self.repository.list_all():
            if v.status == STATUS_PAGO:
                continue
            due = self._parse(v.due_date)
            if due is None:
                continue
            # Atrasado (due < hoje) OU dentro da janela futura.
            if due <= limite:
                out.append(self._decorate(v, today))
        out.sort(key=lambda d: d["due_date"])
        return out

    # ═══════════════════════════════════════════════════════
    # ESCRITA
    # ═══════════════════════════════════════════════════════

    def create(
        self,
        name: str,
        due_date: str,
        amount: float = 0.0,
        kind: str = "conta",
        notify_days: int = 3,
        recurrence: str = "unica",
        category: str = "",
        notes: str = "",
    ) -> Vencimento:
        item = Vencimento(
            name=(name or "").strip(),
            due_date=(due_date or "").strip(),
            amount=float(amount or 0),
            kind=(kind or "conta").strip(),
            notify_days=int(notify_days or 0),
            recurrence=(recurrence or "unica").strip(),
            category=(category or "").strip(),
            notes=(notes or "").strip(),
        )
        item.validate()
        saved = self.repository.create(item)
        logger.info("Vencimento criado: id=%s, nome=%s", saved.id, saved.name)
        return saved

    def update(
        self,
        item_id: int,
        name: str,
        due_date: str,
        amount: float,
        kind: str,
        notify_days: int,
        recurrence: str,
        category: str,
        notes: str,
        status: str = STATUS_PENDENTE,
    ) -> Vencimento:
        existing = self.repository.get_by_id(item_id)
        if existing is None:
            raise ValueError(f"Vencimento {item_id} não encontrado.")
        item = Vencimento(
            id=item_id,
            name=(name or "").strip(),
            due_date=(due_date or "").strip(),
            amount=float(amount or 0),
            kind=(kind or "conta").strip(),
            status=status if status in (STATUS_PENDENTE, STATUS_PAGO) else existing.status,
            notify_days=int(notify_days or 0),
            recurrence=(recurrence or "unica").strip(),
            category=(category or "").strip(),
            notes=(notes or "").strip(),
            paid_at=existing.paid_at,
            created_at=existing.created_at,
        )
        item.validate()
        self.repository.update(item)
        logger.info("Vencimento atualizado: id=%s", item_id)
        return item

    def delete(self, item_id: int) -> bool:
        deleted = self.repository.delete(item_id)
        if deleted:
            logger.info("Vencimento removido: id=%s", item_id)
        return deleted

    def mark_paid(self, item_id: int) -> Optional[Vencimento]:
        """Marca um vencimento como pago.

        Se for mensal, cria automaticamente a próxima ocorrência (mesmo dia
        do mês seguinte), para o usuário não precisar recadastrar.
        """
        item = self.repository.get_by_id(item_id)
        if item is None:
            return None

        item.status = STATUS_PAGO
        item.paid_at = date.today().strftime("%Y-%m-%d")
        self.repository.update(item)
        logger.info("Vencimento pago: id=%s, nome=%s", item_id, item.name)

        if item.recurrence == "mensal":
            proxima = self._next_month_date(item.due_date)
            nova = Vencimento(
                name=item.name,
                due_date=proxima,
                amount=item.amount,
                kind=item.kind,
                status=STATUS_PENDENTE,
                notify_days=item.notify_days,
                recurrence="mensal",
                category=item.category,
                notes=item.notes,
            )
            try:
                nova.validate()
                self.repository.create(nova)
                logger.info("Próxima ocorrência mensal criada: %s em %s", nova.name, proxima)
            except ValueError:
                logger.exception("Falha ao criar próxima ocorrência (ignorada)")

        return item

    # ═══════════════════════════════════════════════════════
    # FLUXO DE CAIXA
    # ═══════════════════════════════════════════════════════

    def cash_flow(self, year: int, month: int) -> dict:
        """Projeta o saldo dia a dia no mês, descontando os vencimentos pendentes.

        Saldo inicial = soma dos saldos atuais de todas as contas. A cada dia
        do mês, subtrai os vencimentos PENDENTES daquele dia. Devolve a série
        diária e em que dia (se algum) o saldo fica negativo.
        """
        starting = sum(
            acc["current_balance"] for acc in self.account_service.list_with_balances()
        )

        # Agrupa vencimentos pendentes do mês por dia.
        first = date(year, month, 1)
        last = self._last_day_of_month(year, month)
        por_dia: dict[str, List[Vencimento]] = {}
        for v in self.repository.list_all():
            if v.status == STATUS_PAGO:
                continue
            due = self._parse(v.due_date)
            if due is None or not (first <= due <= last):
                continue
            por_dia.setdefault(v.due_date, []).append(v)

        days = []
        running = starting
        goes_negative_on: Optional[str] = None
        cursor = first
        while cursor <= last:
            iso = cursor.strftime("%Y-%m-%d")
            itens = por_dia.get(iso, [])
            delta = -sum(v.amount for v in itens)
            running += delta
            if running < 0 and goes_negative_on is None:
                goes_negative_on = iso
            days.append({
                "date": iso,
                "delta": round(delta, 2),
                "running_balance": round(running, 2),
                "items": [
                    {"id": v.id, "name": v.name, "amount": v.amount, "kind": v.kind}
                    for v in itens
                ],
            })
            cursor += timedelta(days=1)

        return {
            "year": year,
            "month": month,
            "starting_balance": round(starting, 2),
            "ending_balance": round(running, 2),
            "goes_negative_on": goes_negative_on,
            "days": days,
        }

    # ═══════════════════════════════════════════════════════
    # AUXILIARES
    # ═══════════════════════════════════════════════════════

    def _decorate(self, v: Vencimento, today: date) -> dict:
        """Acrescenta status/dias/nível derivados a um vencimento."""
        due = self._parse(v.due_date)
        days_until = (due - today).days if due else None

        if v.status == STATUS_PAGO:
            status = STATUS_PAGO
            level = "pago"
        elif days_until is not None and days_until < 0:
            status = STATUS_ATRASADO
            level = "atrasado"
        elif days_until is not None and days_until <= max(v.notify_days, 0):
            status = STATUS_PENDENTE
            level = "urgente"
        elif days_until is not None and days_until <= 7:
            status = STATUS_PENDENTE
            level = "proximo"
        else:
            status = STATUS_PENDENTE
            level = "ok"

        return {
            "id": v.id,
            "name": v.name,
            "due_date": v.due_date,
            "amount": v.amount,
            "kind": v.kind,
            "status": status,
            "level": level,
            "notify_days": v.notify_days,
            "recurrence": v.recurrence,
            "category": v.category,
            "notes": v.notes,
            "paid_at": v.paid_at,
            "days_until": days_until,
            "created_at": v.created_at,
        }

    @staticmethod
    def _parse(iso: str) -> Optional[date]:
        try:
            return datetime.strptime((iso or "")[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _last_day_of_month(year: int, month: int) -> date:
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - timedelta(days=1)

    @classmethod
    def _next_month_date(cls, iso: str) -> str:
        """Mesma data no mês seguinte (ajustando dia para meses curtos)."""
        d = cls._parse(iso) or date.today()
        m = d.month + 1
        y = d.year
        if m > 12:
            m, y = 1, y + 1
        last = cls._last_day_of_month(y, m).day
        return date(y, m, min(d.day, last)).strftime("%Y-%m-%d")
