"""
Service de transações.

A camada de service contém a REGRA DE NEGÓCIO:
- normaliza os dados de entrada (pix/PIX/Pix -> "Pix");
- valida (via Transaction.validate);
- persiste (via repository);
- registra logs.

A interface (CLI ou Streamlit) deve sempre conversar com o service,
nunca diretamente com o repository.

Mudança em relação à versão anterior:
- Agora normalizamos categoria, pagamento e tipo aqui dentro,
  antes de construir o objeto Transaction. Isso garante que o banco
  só receba dados padronizados.
"""

import calendar
import hashlib
import uuid
from datetime import date
from typing import List

from app.constants.payment_origins import (
    PAYMENT_ORIGIN_ACCOUNT,
    PAYMENT_ORIGIN_CARD,
)
from app.constants.people import DEFAULT_PERSON
from app.constants.transaction_types import TYPE_INCOME
from app.models.transaction import Transaction
from app.repositories.transaction_repository import TransactionRepository
from app.utils.logger import get_logger
from app.utils.money_utils import split_installments
from app.utils.normalizers import (
    normalize_category,
    normalize_payment_method,
    normalize_transaction_type,
)

logger = get_logger(__name__)


class TransactionService:
    """Regras de negócio para transações."""

    def __init__(self, repository: TransactionRepository | None = None):
        # Permite injetar um repository diferente (útil em testes).
        self.repository = repository or TransactionRepository()

    def add_transaction(
        self,
        date: str,
        description: str,
        amount: float,
        type_: str,
        category: str,
        payment_method: str,
        spent_by: str = DEFAULT_PERSON,
        account: str = "Carteira",
        card: str = "",
        payment_origin: str | None = None,
        installments: int = 1,
    ) -> Transaction:
        """
        Cria uma transação respeitando a origem do pagamento (conta x cartão).

        Resolução da origem (garante que NUNCA seja conta e cartão ao mesmo
        tempo — o resultado é sempre uma origem só):
        - Receita: sempre conta (não existe receita "no cartão"); cartão é
          ignorado.
        - `payment_origin` informado ("account"/"card"): vence. Origem conta
          ignora qualquer cartão enviado; origem cartão exige um cartão.
        - `payment_origin` ausente (None): deduz pela presença de cartão
          (compatibilidade com importação/recorrentes antigos).

        Despesa no cartão delega para `add_card_expense` (gera a(s) parcela(s)
        e devolve a 1ª). Para receber TODAS as parcelas, chame-o diretamente.

        Lança ValueError se algum campo for inválido.
        """
        normalized_type = normalize_transaction_type(type_)
        has_card = bool((card or "").strip())

        if payment_origin:
            origin = payment_origin.strip()
        else:
            # Não informado: deduz do cartão (gasto com cartão = origem cartão).
            origin = PAYMENT_ORIGIN_CARD if has_card else PAYMENT_ORIGIN_ACCOUNT

        # Receita nunca é cartão.
        if normalized_type == TYPE_INCOME:
            origin = PAYMENT_ORIGIN_ACCOUNT

        # Despesa no cartão → fluxo de parcelamento (gera 1+ transações).
        if origin == PAYMENT_ORIGIN_CARD:
            parcelas = self.add_card_expense(
                date=date,
                description=description,
                total_amount=amount,
                category=category,
                payment_method=payment_method,
                spent_by=spent_by,
                card=card,
                installments=installments,
                account=account,
            )
            return parcelas[0]

        # Receita ou despesa direta da conta: uma única transação.
        return self._create_account_transaction(
            date=date,
            description=description,
            amount=amount,
            type_=normalized_type,
            category=category,
            payment_method=payment_method,
            spent_by=spent_by,
            account=account,
        )

    def _create_account_transaction(
        self,
        date: str,
        description: str,
        amount: float,
        type_: str,
        category: str,
        payment_method: str,
        spent_by: str,
        account: str,
    ) -> Transaction:
        """Cria uma transação de conta (receita ou despesa direta). Sem cartão."""
        normalized_category = normalize_category(category, type_)
        normalized_payment = normalize_payment_method(payment_method)
        normalized_spent_by = (spent_by or "").strip() or DEFAULT_PERSON
        normalized_account = (account or "").strip() or "Carteira"

        transaction = Transaction(
            date=date,
            description=description.strip(),
            amount=amount,
            type=type_,
            category=normalized_category,
            payment_method=normalized_payment,
            spent_by=normalized_spent_by,
            account=normalized_account,
            card="",  # origem conta nunca tem cartão
            payment_origin=PAYMENT_ORIGIN_ACCOUNT,
        )
        transaction.validate()

        try:
            saved = self.repository.create(transaction)
            logger.info(
                "Transação (conta) criada: id=%s, tipo=%s, valor=%.2f, categoria=%s",
                saved.id, saved.type, saved.amount, saved.category,
            )
            return saved
        except Exception:
            logger.exception("Erro ao salvar transação")
            raise

    def add_card_expense(
        self,
        date: str,
        description: str,
        total_amount: float,
        category: str,
        payment_method: str = "Crédito",
        spent_by: str = DEFAULT_PERSON,
        card: str = "",
        installments: int = 1,
        account: str = "Carteira",
    ) -> List[Transaction]:
        """
        Cria um gasto no cartão de crédito, gerando as PARCELAS nas faturas.

        Regras (ver AGENTS.md):
        - `installments` = 1 → compra à vista no cartão (uma transação só).
        - `installments` > 1 → divide o total em parcelas (centavos da
          diferença vão na última) e lança CADA parcela no mês da fatura
          correspondente, com descrição "<desc> N/total".
        - Cada parcela é uma transação com origem "card", então entra na
          fatura do mês (e NÃO desconta do saldo da conta imediatamente).

        Devolve a lista de transações criadas (uma por parcela), em ordem.
        """
        installments = int(installments or 1)
        if installments < 1:
            raise ValueError("A quantidade de parcelas deve ser pelo menos 1.")

        normalized_category = normalize_category(category, "despesa")
        normalized_payment = normalize_payment_method(payment_method)
        normalized_spent_by = (spent_by or "").strip() or DEFAULT_PERSON
        normalized_account = (account or "").strip() or "Carteira"
        normalized_card = (card or "").strip()
        base_description = description.strip()

        if not normalized_card:
            raise ValueError("Para um gasto no cartão, escolha qual cartão foi usado.")

        # Divide o valor total nas parcelas (ajuste de centavos na última).
        amounts = split_installments(total_amount, installments)

        # Base das faturas = MÊS DA COMPRA (modelo simples e previsível): a 1ª
        # parcela já entra na fatura do mês em que a compra foi feita, e as
        # seguintes caem nos meses seguintes. A data de cada parcela é ancorada
        # no DIA da compra (dentro daquele mês), garantindo que a fatura do mês
        # a contabilize corretamente. (Regras de fechamento/vencimento por
        # ciclo ficam para evolução futura — closing_day/due_day já existem no
        # cartão para isso.)
        purchase_date = self._parse_date(date)
        first_year, first_month = purchase_date.year, purchase_date.month
        anchor_day = purchase_date.day

        # Agrupa as parcelas da mesma compra (vazio quando é à vista).
        group = uuid.uuid4().hex if installments > 1 else ""

        created: List[Transaction] = []
        for index in range(installments):
            year, month = self._add_months(first_year, first_month, index)
            charge_date = self._clamp_day(year, month, anchor_day)

            if installments > 1:
                parcela_desc = f"{base_description} {index + 1}/{installments}"
            else:
                parcela_desc = base_description  # à vista: sem "1/1"

            transaction = Transaction(
                date=charge_date.strftime("%Y-%m-%d"),
                description=parcela_desc,
                amount=amounts[index],
                type="despesa",
                category=normalized_category,
                payment_method=normalized_payment,
                spent_by=normalized_spent_by,
                account=normalized_account,
                card=normalized_card,
                payment_origin=PAYMENT_ORIGIN_CARD,
                installment_no=index + 1,
                installments_total=installments,
                purchase_group=group,
            )
            transaction.validate()
            created.append(self.repository.create(transaction))

        logger.info(
            "Gasto no cartão %r criado: %s parcela(s), total=%.2f, 1ª fatura=%02d/%d",
            normalized_card, installments, total_amount, first_month, first_year,
        )
        return created

    def update_transaction(
        self,
        transaction_id: int,
        *,
        date: str | None = None,
        description: str | None = None,
        amount: float | None = None,
        type_: str | None = None,
        category: str | None = None,
        payment_method: str | None = None,
        spent_by: str | None = None,
        account: str | None = None,
        card: str | None = None,
        payment_origin: str | None = None,
        apply_to_group: bool = False,
    ) -> Transaction:
        """Atualiza UMA transação no lugar (sem reparcelar nem trocar o id).

        Campos não informados (None) mantêm o valor atual. Pensado para ajustes
        pontuais — em especial o VALOR de uma parcela (ex.: a última parcela de
        uma compra costuma ter alguns centavos a mais). A metadata de parcela
        (installment_no/installments_total/purchase_group) é PRESERVADA quando a
        origem continua no cartão; se a transação passar a ser da conta, ela é
        zerada (conta não tem parcelamento).

        `apply_to_group=True`: depois de salvar esta parcela, propaga os campos
        COMPARTILHADOS da compra (quem gastou, categoria, forma de pagamento,
        conta e cartão) às DEMAIS parcelas do mesmo `purchase_group`. Valor,
        data e descrição (o "N/M") de cada parcela são mantidos — só muda o que
        é, por natureza, igual em toda a compra. Útil para corrigir "quem gastou"
        de uma compra parcelada inteira de uma vez.

        Lança ValueError se o id não existir ou se algum campo ficar inválido.
        """
        current = self.repository.get_by_id(transaction_id)
        if current is None:
            raise ValueError(f"Transação {transaction_id} não encontrada.")

        new_type = normalize_transaction_type(type_) if type_ is not None else current.type
        new_card = (card if card is not None else current.card or "").strip()

        # Resolve a origem (mesma regra do add_transaction): explícita vence;
        # senão mantém a atual; receita é sempre conta.
        if payment_origin:
            origin = payment_origin.strip()
        else:
            origin = current.payment_origin or (
                PAYMENT_ORIGIN_CARD if new_card else PAYMENT_ORIGIN_ACCOUNT
            )
        if new_type == TYPE_INCOME:
            origin = PAYMENT_ORIGIN_ACCOUNT

        # Preserva a metadata de parcela só se continuar sendo gasto no cartão
        # que JÁ era do cartão; caso contrário, vira 1/1 sem grupo.
        if origin == PAYMENT_ORIGIN_CARD and current.payment_origin == PAYMENT_ORIGIN_CARD:
            installment_no = current.installment_no
            installments_total = current.installments_total
            purchase_group = current.purchase_group
        else:
            installment_no = 1
            installments_total = 1
            purchase_group = ""
        if origin == PAYMENT_ORIGIN_ACCOUNT:
            new_card = ""

        new_category = category if category is not None else current.category
        updated = Transaction(
            id=current.id,
            date=date if date is not None else current.date,
            description=(description if description is not None else current.description).strip(),
            amount=float(amount) if amount is not None else current.amount,
            type=new_type,
            category=normalize_category(new_category, new_type),
            payment_method=(
                normalize_payment_method(payment_method)
                if payment_method is not None else current.payment_method
            ),
            spent_by=(spent_by if spent_by is not None else current.spent_by).strip() or DEFAULT_PERSON,
            account=(account if account is not None else current.account).strip() or "Carteira",
            card=new_card,
            payment_origin=origin,
            installment_no=installment_no,
            installments_total=installments_total,
            purchase_group=purchase_group,
            created_at=current.created_at,
        )
        updated.validate()
        saved = self.repository.update(updated)
        logger.info(
            "Transação %s atualizada: valor=%.2f, origem=%s, parcela=%d/%d",
            saved.id, saved.amount, saved.payment_origin,
            saved.installment_no, saved.installments_total,
        )

        if apply_to_group and saved.purchase_group:
            n = self._propagate_group_fields(saved)
            if n:
                logger.info(
                    "Campos compartilhados propagados para %d outra(s) parcela(s) do grupo %s",
                    n, saved.purchase_group,
                )
        return saved

    def _propagate_group_fields(self, ref: Transaction) -> int:
        """Copia os campos compartilhados de `ref` para as outras parcelas da compra.

        Compartilhados = quem gastou, categoria, forma de pagamento, conta e
        cartão (iguais em toda a compra). Mantém valor/data/descrição/metadata de
        cada parcela. Devolve quantas parcelas foram efetivamente alteradas.
        """
        changed = 0
        for t in self.repository.find_by_purchase_group(ref.purchase_group):
            if t.id == ref.id:
                continue
            if (
                t.spent_by == ref.spent_by
                and t.category == ref.category
                and t.payment_method == ref.payment_method
                and t.account == ref.account
                and t.card == ref.card
            ):
                continue  # já está igual: nada a fazer.
            t.spent_by = ref.spent_by
            t.category = ref.category
            t.payment_method = ref.payment_method
            t.account = ref.account
            t.card = ref.card
            t.validate()
            self.repository.update(t)
            changed += 1
        return changed

    def installment_already_imported(
        self,
        *,
        date: str,
        base_description: str,
        installment_no: int,
        installments_total: int,
        card: str,
    ) -> bool:
        """True se a parcela `installment_no` desta compra JÁ está gravada.

        Usado pela prévia de importação para AVISAR (marcar como duplicata) uma
        parcela que já foi lançada — inclusive a que foi projetada a partir da
        importação de outra fatura. Usa o mesmo purchase_group determinístico de
        `register_card_installment_line`, então reconhece a compra mesmo que a
        descrição da linha varie ("3/12" vs "03/12").
        """
        installments_total = int(installments_total or 1)
        installment_no = int(installment_no or 1)
        normalized_card = (card or "").strip()
        if not normalized_card or installments_total < 2:
            return False
        base = (base_description or "").strip() or "Compra"
        line_date = self._parse_date(date)
        first_year, first_month = self._add_months(
            line_date.year, line_date.month, -(installment_no - 1)
        )
        group = self._installment_group(
            normalized_card, base, installments_total, first_year, first_month
        )
        existing = {
            t.installment_no
            for t in self.repository.find_by_purchase_group(group)
        }
        return installment_no in existing

    def register_card_installment_line(
        self,
        *,
        date: str,
        base_description: str,
        parcela_amount: float,
        installment_no: int,
        installments_total: int,
        category: str,
        payment_method: str = "Crédito",
        spent_by: str = DEFAULT_PERSON,
        card: str = "",
        account: str = "Carteira",
        project_future: bool = True,
    ) -> dict:
        """Registra uma compra parcelada a partir de UMA linha de fatura importada.

        A linha importada é a parcela `installment_no` de `installments_total`
        (ex.: "NETFLIX 03/12"). Diferente de `add_card_expense` (que parte do
        valor TOTAL e gera tudo do zero), aqui partimos de uma parcela já
        cobrada e completamos o que falta, sem duplicar:

        - A compra é identificada por um `purchase_group` DETERMINÍSTICO
          (cartão + descrição-base + total de parcelas + mês da 1ª parcela).
          Assim, reimportar a mesma fatura — ou a fatura de outro mês da mesma
          compra — NÃO duplica parcelas.
        - Grava a parcela importada (se ainda não existir no grupo).
        - Se `project_future`, projeta as parcelas seguintes
          (installment_no+1 .. total) nas faturas dos próximos meses (as que
          ainda não existirem).

        As parcelas ANTERIORES (1 .. installment_no-1) não são criadas aqui:
        pertencem a faturas passadas, que o usuário importa em separado (e o
        mesmo purchase_group evita duplicá-las quando isso acontecer).

        Devolve {"created": [Transaction, ...], "skipped_existing": int}.
        """
        installments_total = int(installments_total or 1)
        installment_no = int(installment_no or 1)
        if installments_total < 1 or not (1 <= installment_no <= installments_total):
            raise ValueError("Número de parcela inválido para a compra importada.")

        normalized_card = (card or "").strip()
        if not normalized_card:
            raise ValueError("Para um gasto no cartão, escolha qual cartão foi usado.")

        normalized_category = normalize_category(category, "despesa")
        normalized_payment = normalize_payment_method(payment_method)
        normalized_spent_by = (spent_by or "").strip() or DEFAULT_PERSON
        normalized_account = (account or "").strip() or "Carteira"
        base = (base_description or "").strip() or "Compra"
        amount = round(float(parcela_amount), 2)

        line_date = self._parse_date(date)
        anchor_day = line_date.day
        # Mês da 1ª parcela = mês da linha menos (installment_no - 1) meses.
        first_year, first_month = self._add_months(
            line_date.year, line_date.month, -(installment_no - 1)
        )

        group = self._installment_group(
            normalized_card, base, installments_total, first_year, first_month
        )
        existing = {
            t.installment_no
            for t in self.repository.find_by_purchase_group(group)
        }

        # Parcelas a criar: a importada + (opcional) as futuras ainda não gravadas.
        to_create = [installment_no]
        if project_future:
            to_create += list(range(installment_no + 1, installments_total + 1))

        created: List[Transaction] = []
        skipped = 0
        for n in to_create:
            if n in existing:
                skipped += 1
                continue
            year, month = self._add_months(first_year, first_month, n - 1)
            charge_date = self._clamp_day(year, month, anchor_day)
            transaction = Transaction(
                date=charge_date.strftime("%Y-%m-%d"),
                description=f"{base} {n}/{installments_total}",
                amount=amount,
                type="despesa",
                category=normalized_category,
                payment_method=normalized_payment,
                spent_by=normalized_spent_by,
                account=normalized_account,
                card=normalized_card,
                payment_origin=PAYMENT_ORIGIN_CARD,
                installment_no=n,
                installments_total=installments_total,
                purchase_group=group,
            )
            transaction.validate()
            created.append(self.repository.create(transaction))

        logger.info(
            "Import parcelado %r (%d/%d): %d criada(s), %d já existia(m), grupo=%s",
            base, installment_no, installments_total, len(created), skipped, group,
        )
        return {"created": created, "skipped_existing": skipped}

    # ---------- Auxiliares de fatura/parcelamento ----------

    @staticmethod
    def _installment_group(
        card: str, base: str, total: int, year: int, month: int
    ) -> str:
        """purchase_group estável para uma compra parcelada importada.

        Determinístico: a mesma compra (mesmo cartão, descrição-base, total de
        parcelas e mês da 1ª parcela) gera SEMPRE o mesmo grupo — é isso que
        torna a reimportação segura contra duplicatas.
        """
        norm = " ".join((base or "").lower().split())
        raw = f"{card.lower()}|{norm}|{total}|{year:04d}-{month:02d}"
        return "imp-" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _parse_date(value: str) -> date:
        return date.fromisoformat(value[:10])

    @staticmethod
    def _add_months(year: int, month: int, count: int) -> tuple[int, int]:
        """Avança `count` meses a partir de (year, month). Ex: (2026,11)+2=(2027,1)."""
        index = (year * 12 + (month - 1)) + count
        return index // 12, (index % 12) + 1

    @staticmethod
    def _clamp_day(year: int, month: int, day: int) -> date:
        """Data válida no mês, limitando o dia ao último dia (ex: 31/02 → 28/29)."""
        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(max(day, 1), last))

    def list_all(self) -> List[Transaction]:
        return self.repository.list_all()

    def list_by_month(self, year: int, month: int) -> List[Transaction]:
        return self.repository.find_by_month(year, month)

    def list_by_category(self, category: str) -> List[Transaction]:
        # Também normalizamos a busca, para "pix" achar resultados de "Pix".
        # Para categorias, usamos um tipo "fictício" porque a busca não tem tipo.
        # Estratégia: passamos a string como veio e o repo busca case-insensitive.
        return self.repository.find_by_category(category)

    def list_by_person(self, spent_by: str) -> List[Transaction]:
        """Lista transações de uma pessoa (busca case-insensitive no repo)."""
        return self.repository.find_by_person(spent_by)

    def get_transaction(self, transaction_id: int) -> Transaction | None:
        """Busca uma transação pelo id (None se não existir)."""
        return self.repository.get_by_id(transaction_id)

    def delete_transaction(self, transaction_id: int) -> bool:
        """Remove uma transação. Retorna True se removeu, False se não achou."""
        deleted = self.repository.delete(transaction_id)
        if deleted:
            logger.info("Transação removida: id=%s", transaction_id)
        return deleted
