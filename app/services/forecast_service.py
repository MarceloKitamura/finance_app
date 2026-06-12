"""
Service de PREVISÃO FINANCEIRA do mês.

═══════════════════════════════════════════════════════════════════
⭐ O QUE ESTE SERVICE FAZ
═══════════════════════════════════════════════════════════════════
Projeta quanto dinheiro o usuário deve ter ao FINAL do mês, combinando
tudo o que já sabemos do mês:

    saldo_previsto = saldo_atual
                   + entradas_futuras_lancadas   (receitas já cadastradas, data > hoje)
                   + salario_futuro              (parcelas do salário ainda não recebidas)
                   - despesas_futuras_lancadas   (despesas já cadastradas, data > hoje)
                   - gastos_recorrentes_restantes (templates ainda não lançados no mês)
                   - contas_a_pagar_restantes     (vencimentos pendentes até o fim do mês)

Diferença para o forecast_balance() do FinancialAdvisorService:
- aquele é ESTATÍSTICO (extrapola o ritmo de gastos e a média histórica);
- este é DETERMINÍSTICO (soma itens concretos já conhecidos: salário
  configurado, recorrentes, contas a pagar). É o que o usuário pediu para
  ver no dashboard.

⚠️ EVITANDO CONTAGEM DUPLICADA
- O "saldo_atual" considera só transações com data ATÉ hoje. Transações
  com data FUTURA entram separadamente como "entradas/despesas futuras".
- Recorrentes que JÁ foram lançados como transação no mês são ignorados
  (comparando a descrição), para não somar duas vezes.
- O salário configurado é tratado como a previsão de entrada do salário.
  Se o usuário também lançar o salário como transação futura, recomenda-se
  desligar um dos dois para não contar em dobro (documentado na interface).
═══════════════════════════════════════════════════════════════════
"""

import unicodedata
from datetime import date
from typing import Optional

from app.constants.payment_origins import PAYMENT_ORIGIN_CARD
from app.constants.transaction_types import TYPE_EXPENSE, TYPE_INCOME
from app.repositories.account_repository import AccountRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.salary_service import SalaryService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Faixas de status da previsão (cor no dashboard).
STATUS_POSITIVE = "positivo"   # sobra confortável (verde/azul)
STATUS_WARNING = "atencao"     # vai fechar apertado (amarelo)
STATUS_RISK = "risco"          # risco de fechar negativo (vermelho)


def _norm(text: str) -> str:
    """Minúsculas, sem acento, espaços colapsados — para comparar descrições."""
    text = (text or "").strip().lower()
    nfd = unicodedata.normalize("NFD", text)
    sem_acento = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return " ".join(sem_acento.split())


class ForecastService:
    """Previsão determinística do saldo de fim de mês."""

    def __init__(
        self,
        transaction_repository: TransactionRepository | None = None,
        account_repository: AccountRepository | None = None,
        salary_service: SalaryService | None = None,
        recurring_service=None,
        vencimento_service=None,
    ):
        self.transaction_repository = transaction_repository or TransactionRepository()
        self.account_repository = account_repository or AccountRepository()
        self.salary_service = salary_service or SalaryService()
        # Imports tardios para evitar ciclos de import e deixar a injeção fácil.
        if recurring_service is None:
            from app.services.recurring_service import RecurringService
            recurring_service = RecurringService()
        if vencimento_service is None:
            from app.services.vencimento_service import VencimentoService
            vencimento_service = VencimentoService()
        self.recurring_service = recurring_service
        self.vencimento_service = vencimento_service

    # ═══════════════════════════════════════════════════════
    # PREVISÃO PRINCIPAL
    # ═══════════════════════════════════════════════════════

    def monthly_forecast(
        self, year: int, month: int, include_salary: bool = True
    ) -> dict:
        """Monta a previsão completa do mês informado.

        Para o mês CORRENTE, projeta o fim do mês a partir de hoje. Para
        meses passados, devolve o resultado real (sem projeção).

        include_salary=False é o "modo sem salário": ignora o salário a receber
        na projeção (útil para ver o saldo só com o que já está em conta, sem
        contar com o pagamento ainda não recebido). Não altera nada salvo — é só
        uma visão; o salário detalhado vem marcado como não incluído.
        """
        today = date.today()
        is_current = (year == today.year and month == today.month)
        is_future = (year, month) > (today.year, today.month)

        # Saldo atual: soma dos saldos iniciais + transações JÁ ocorridas.
        # Para mês futuro, "hoje" para efeito da projeção é o fim do mês atual.
        current_balance = self._current_balance(today)

        first_day, last_day = self._month_bounds(year, month)

        # Para o mês corrente, "futuro" = depois de hoje. Para mês futuro,
        # tudo no mês é futuro. Para mês passado, nada é futuro.
        if is_current:
            cutoff = today
        elif is_future:
            cutoff = first_day - _one_day()  # tudo do mês conta como futuro
        else:
            cutoff = last_day  # mês fechado: nada futuro

        # 1) Receitas/despesas JÁ LANÇADAS no mês com data > cutoff.
        future_incomes, future_expenses = self._registered_future(
            year, month, cutoff, last_day
        )

        # 2) Salário ainda a receber (parcelas com dia > cutoff).
        future_salary, salary_detail = self._future_salary(year, month, cutoff, last_day)
        # Modo "sem salário": zera o salário a receber na projeção. O detalhe
        # segue visível, mas marcado como fora da previsão (para a UI explicar).
        salary_detail["included"] = include_salary
        if not include_salary:
            future_salary = 0.0

        # 3) Gastos recorrentes previstos ainda não lançados.
        future_recurring, recurring_detail = self._future_recurring(
            year, month, cutoff, last_day
        )

        # 4) Contas a pagar (vencimentos pendentes) até o fim do mês.
        future_vencimentos, venc_detail = self._future_vencimentos(cutoff, last_day)

        # 5) Fatura do cartão do mês (gastos no cartão competentes a este mês).
        #    Gasto no cartão não saiu do saldo ainda, mas a fatura será paga,
        #    então entra na previsão como dinheiro a pagar.
        future_card, card_detail = self._future_card(year, month)

        projected_balance = (
            current_balance
            + future_incomes
            + future_salary
            - future_expenses
            - future_recurring
            - future_vencimentos
            - future_card
        )

        # Quanto ainda falta entrar e sair no mês (útil para a IA).
        remaining_to_receive = future_incomes + future_salary
        remaining_to_pay = (
            future_expenses + future_recurring + future_vencimentos + future_card
        )

        # Renda total esperada no mês (para calibrar o status).
        incomes_so_far = self._month_total(year, month, TYPE_INCOME, until=cutoff)
        expected_income_month = incomes_so_far + remaining_to_receive

        status = self._status(projected_balance, expected_income_month)

        return {
            "year": year,
            "month": month,
            "is_projection": is_current or is_future,
            "current_balance": round(current_balance, 2),
            "future_incomes": round(future_incomes, 2),
            "future_salary": round(future_salary, 2),
            "future_expenses": round(future_expenses, 2),
            "future_recurring": round(future_recurring, 2),
            "future_vencimentos": round(future_vencimentos, 2),
            "future_card": round(future_card, 2),
            "card_detail": card_detail,
            "remaining_to_receive": round(remaining_to_receive, 2),
            "remaining_to_pay": round(remaining_to_pay, 2),
            "projected_balance": round(projected_balance, 2),
            "expected_income_month": round(expected_income_month, 2),
            "status": status,
            "salary": salary_detail,        # líquido + próximas parcelas
            "recurring_detail": recurring_detail,
            "vencimentos_detail": venc_detail,
        }

    # ═══════════════════════════════════════════════════════
    # CONTEXTO PARA A IA
    # ═══════════════════════════════════════════════════════

    def ai_context(self, year: int, month: int) -> dict:
        """Resumo enxuto da previsão para alimentar o prompt da IA de conselhos.

        Devolve só os números que importam para o conselho: saldo previsto,
        quanto falta receber/pagar, salário líquido e o status do mês.
        """
        f = self.monthly_forecast(year, month)
        return {
            "current_balance": f["current_balance"],
            "projected_balance": f["projected_balance"],
            "remaining_to_receive": f["remaining_to_receive"],
            "remaining_to_pay": f["remaining_to_pay"],
            "future_recurring": f["future_recurring"],
            "future_vencimentos": f["future_vencimentos"],
            # Fatura(s) do cartão competentes ao mês (inclui parcelas que caem
            # neste mês). Dá à IA visão dos gastos no cartão, não só da conta.
            "future_card": f["future_card"],
            "net_salary": f["salary"].get("net", 0.0),
            "status": f["status"],
        }

    def signature(self, year: int, month: int) -> str:
        """Assinatura curta que muda quando a previsão muda.

        O FinancialAdvisorService usa isto para invalidar o cache do conselho
        quando o salário/previsão muda, mesmo que a contagem de transações
        permaneça a mesma.
        """
        f = self.monthly_forecast(year, month)
        return f"{date.today().isoformat()}|{f['projected_balance']}|{f['remaining_to_pay']}"

    # ═══════════════════════════════════════════════════════
    # AUXILIARES DE CÁLCULO
    # ═══════════════════════════════════════════════════════

    def _current_balance(self, today: date) -> float:
        """Saldo real de HOJE: saldos iniciais + transações com data <= hoje.

        Diferente do AccountService (que soma TODAS as transações), aqui
        ignoramos transações com data futura — elas entram separadamente na
        previsão, para não contar duas vezes.
        """
        initial = sum(acc.initial_balance for acc in self.account_repository.list_all())
        today_iso = today.strftime("%Y-%m-%d")
        balance = initial
        for t in self.transaction_repository.list_all():
            if t.date[:10] > today_iso:
                continue  # transação futura: não entra no saldo de hoje
            if t.payment_origin == PAYMENT_ORIGIN_CARD:
                continue  # gasto no cartão: vai p/ a fatura, não p/ o saldo
            if t.type == TYPE_INCOME:
                balance += t.amount
            elif t.type == TYPE_EXPENSE:
                balance -= t.amount
        return balance

    def _registered_future(
        self, year: int, month: int, cutoff: date, last_day: date
    ) -> tuple[float, float]:
        """Receitas e despesas JÁ cadastradas com data entre cutoff e fim do mês."""
        incomes = 0.0
        expenses = 0.0
        cutoff_iso = cutoff.strftime("%Y-%m-%d")
        last_iso = last_day.strftime("%Y-%m-%d")
        for t in self.transaction_repository.find_by_month(year, month):
            d = t.date[:10]
            if d <= cutoff_iso or d > last_iso:
                continue
            if t.payment_origin == PAYMENT_ORIGIN_CARD:
                continue  # parcelas de cartão entram na fatura, não no saldo
            if t.type == TYPE_INCOME:
                incomes += t.amount
            elif t.type == TYPE_EXPENSE:
                expenses += t.amount
        return incomes, expenses

    def _month_total(self, year: int, month: int, type_: str, until: date) -> float:
        """Total de um tipo (receita/despesa) no mês até a data `until` (inclusive)."""
        until_iso = until.strftime("%Y-%m-%d")
        total = 0.0
        for t in self.transaction_repository.find_by_month(year, month):
            if t.type == type_ and t.date[:10] <= until_iso:
                total += t.amount
        return total

    def _future_salary(
        self, year: int, month: int, cutoff: date, last_day: date
    ) -> tuple[float, dict]:
        """Parcelas do salário que ainda vão cair (dia > cutoff) neste mês.

        Devolve (total_a_receber, detalhe). O detalhe traz o líquido e as
        duas parcelas com data e se já "passou" (para a interface).
        """
        config = self.salary_service.get_config()
        split = self.salary_service.split_payment(config)
        detail = {
            "enabled": config.enabled and config.gross > 0,
            "net": split["net"],
            "installments": [],
        }
        if not detail["enabled"]:
            return 0.0, detail

        total_future = 0.0
        for day, amount in (
            (split["pay_day_1"], split["amount_day_1"]),
            (split["pay_day_2"], split["amount_day_2"]),
        ):
            pay_date = self._clamp_day(year, month, day)
            is_future = cutoff < pay_date <= last_day
            if is_future:
                total_future += amount
            detail["installments"].append({
                "day": day,
                "date": pay_date.strftime("%Y-%m-%d"),
                "amount": round(amount, 2),
                "received": pay_date <= cutoff,  # já caiu?
            })
        return total_future, detail

    def _future_recurring(
        self, year: int, month: int, cutoff: date, last_day: date
    ) -> tuple[float, list]:
        """Gastos recorrentes (templates) previstos que ainda não foram lançados.

        Considera só templates ATIVOS de DESPESA com dia da cobrança após o
        cutoff. Ignora os que já aparecem como transação no mês (mesma
        descrição), para não contar duas vezes.
        """
        # Descrições de despesas já lançadas no mês (para dedup).
        already = {
            _norm(t.description)
            for t in self.transaction_repository.find_by_month(year, month)
            if t.type == TYPE_EXPENSE
        }

        total = 0.0
        detail = []
        for tpl in self.recurring_service.list_templates():
            if not tpl.active or tpl.type != TYPE_EXPENSE:
                continue
            if not (1 <= tpl.day_of_month <= 31):
                continue  # sem dia definido: não dá para projetar
            if _norm(tpl.description) in already:
                continue  # já foi lançado este mês
            charge_date = self._clamp_day(year, month, tpl.day_of_month)
            if cutoff < charge_date <= last_day:
                total += tpl.amount
                detail.append({
                    "description": tpl.description,
                    "amount": round(tpl.amount, 2),
                    "date": charge_date.strftime("%Y-%m-%d"),
                })
        return total, detail

    def _future_vencimentos(self, cutoff: date, last_day: date) -> tuple[float, list]:
        """Contas a pagar (vencimentos pendentes) com vencimento até o fim do mês.

        Inclui atrasados (vencimento <= cutoff e ainda pendentes), pois
        continuam sendo dinheiro que vai sair. Usa a lista decorada do
        VencimentoService (status derivado).
        """
        total = 0.0
        detail = []
        last_iso = last_day.strftime("%Y-%m-%d")
        for v in self.vencimento_service.list_vencimentos():
            if v["status"] == "pago":
                continue
            due = (v.get("due_date") or "")[:10]
            if not due or due > last_iso:
                continue
            total += v["amount"]
            detail.append({
                "name": v["name"],
                "amount": round(v["amount"], 2),
                "date": due,
            })
        return total, detail

    def _future_card(self, year: int, month: int) -> tuple[float, list]:
        """Fatura(s) do cartão competentes ao mês (gastos com origem 'card').

        Cada cartão vira uma linha {name, amount}. O total é tratado como
        dinheiro a pagar na previsão (a fatura ainda será paga). É um modelo
        simplificado: considera a fatura do mês-calendário inteira, sem
        distinguir a data exata de vencimento.
        """
        invoices = self.transaction_repository.expenses_by_card_in_month(year, month)
        detail = [
            {"name": name, "amount": round(total, 2)}
            for name, total in invoices.items()
            if total
        ]
        detail.sort(key=lambda x: x["amount"], reverse=True)
        total = sum(item["amount"] for item in detail)
        return total, detail

    # ---------- Status / datas ----------

    @staticmethod
    def _status(projected_balance: float, expected_income: float) -> str:
        """Classifica a previsão em positivo / atenção / risco.

        - Negativo  → risco (vermelho).
        - Positivo mas apertado (< 10% da renda esperada) → atenção (amarelo).
        - Folga confortável → positivo (verde/azul).
        Sem renda esperada conhecida, usa um colchão fixo de R$ 200.
        """
        if projected_balance < 0:
            return STATUS_RISK
        buffer = expected_income * 0.10 if expected_income > 0 else 200.0
        if projected_balance < buffer:
            return STATUS_WARNING
        return STATUS_POSITIVE

    @staticmethod
    def _month_bounds(year: int, month: int) -> tuple[date, date]:
        first = date(year, month, 1)
        if month == 12:
            last = date(year, 12, 31)
        else:
            last = date(year, month + 1, 1) - _one_day()
        return first, last

    @classmethod
    def _clamp_day(cls, year: int, month: int, day: int) -> date:
        """Devolve uma data válida no mês, limitando o dia ao último dia do mês.

        Ex: dia 30 em fevereiro vira o dia 28/29. Dia 31 em abril vira 30.
        """
        _, last = cls._month_bounds(year, month)
        safe_day = min(max(day, 1), last.day)
        return date(year, month, safe_day)


def _one_day():
    """timedelta de 1 dia (import local para manter o topo enxuto)."""
    from datetime import timedelta
    return timedelta(days=1)
