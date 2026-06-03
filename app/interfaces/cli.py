"""
Interface de linha de comando (CLI).

REGRA: este arquivo NÃO contém regra de negócio nem SQL.
Ele só:
- mostra o menu;
- captura input do usuário (usando prompts);
- chama os services;
- formata e mostra os resultados.

Mudança em relação à versão anterior:
- Os inputs agora usam helpers de prompts.py (seleção por número,
  validação automática, repetição em caso de erro).
- O cadastro de transação usa listas centralizadas de categorias
  e formas de pagamento.
"""

from datetime import date

from app.constants.categories import OTHER_LABEL, categories_for_type
from app.constants.payment_methods import PAYMENT_METHODS
from app.constants.people import OTHER_PERSON_LABEL, PEOPLE
from app.constants.transaction_types import TYPE_EXPENSE, TYPE_INCOME
from app.interfaces.prompts import (
    ask_amount,
    ask_date,
    ask_int,
    ask_non_empty,
    select_from_list,
)
from app.services.chart_service import ChartService
from app.services.export_service import ExportService
from app.services.report_service import ReportService
from app.services.transaction_service import TransactionService
from app.utils.date_utils import format_user, parse_iso_date
from app.utils.logger import get_logger
from app.utils.money_utils import format_brl

logger = get_logger(__name__)


class CLI:
    """Menu interativo no terminal."""

    def __init__(self):
        self.transaction_service = TransactionService()
        self.report_service = ReportService()
        self.export_service = ExportService()
        self.chart_service = ChartService()

    # ---------- Loop principal ----------

    def run(self) -> None:
        while True:
            self._print_menu()
            choice = input("Escolha uma opção: ").strip()
            print()

            try:
                if choice == "1":
                    self._add_transaction(TYPE_INCOME)
                elif choice == "2":
                    self._add_transaction(TYPE_EXPENSE)
                elif choice == "3":
                    self._list_transactions()
                elif choice == "4":
                    self._monthly_summary()
                elif choice == "5":
                    self._filter_by_category()
                elif choice == "6":
                    self._filter_by_person()
                elif choice == "7":
                    self._export_excel()
                elif choice == "8":
                    self._generate_chart()
                elif choice == "9":
                    print("Até logo!")
                    return
                else:
                    print("Opção inválida.\n")
            except ValueError as e:
                # Erros de validação são esperados — mostramos amigavelmente.
                print(f"Erro: {e}\n")
            except Exception as e:
                # Erros inesperados — logamos com stacktrace.
                logger.exception("Erro inesperado na CLI")
                print(f"Erro inesperado: {e}\n")

    # ---------- Menu ----------

    @staticmethod
    def _print_menu() -> None:
        print("=== Sistema Financeiro ===")
        print("1 - Adicionar receita")
        print("2 - Adicionar despesa")
        print("3 - Listar transações")
        print("4 - Ver resumo mensal")
        print("5 - Filtrar por categoria")
        print("6 - Filtrar por pessoa")
        print("7 - Exportar Excel")
        print("8 - Gerar gráfico")
        print("9 - Sair")

    # ---------- Ações ----------

    def _add_transaction(self, type_: str) -> None:
        label = "Receita" if type_ == TYPE_INCOME else "Despesa"
        print(f"=== Adicionar {label} ===\n")

        description = ask_non_empty("Descrição: ")
        amount = ask_amount("Valor: ")

        # Seleção de categoria por número, baseada no tipo.
        available_categories = categories_for_type(type_)
        chosen_category = select_from_list(
            "Escolha a categoria:", available_categories
        )

        # Se escolheu "Outros", pedir uma categoria personalizada.
        if chosen_category == OTHER_LABEL:
            chosen_category = ask_non_empty("Digite a categoria personalizada: ")

        # Seleção de forma de pagamento por número.
        payment_method = select_from_list(
            "Escolha a forma de pagamento:", PAYMENT_METHODS
        )

        # "Quem gastou?" só faz sentido em despesas. Em receitas mantemos
        # o padrão ("Eu") sem perguntar.
        if type_ == TYPE_EXPENSE:
            spent_by = select_from_list("Quem gastou?", PEOPLE)
            if spent_by == OTHER_PERSON_LABEL:
                spent_by = ask_non_empty("Digite quem gastou: ")
        else:
            spent_by = "Eu"

        date_iso = ask_date("\nData da transação [Enter para hoje]: ")

        transaction = self.transaction_service.add_transaction(
            date=date_iso,
            description=description,
            amount=amount,
            type_=type_,
            category=chosen_category,
            payment_method=payment_method,
            spent_by=spent_by,
        )
        print(
            f"\n✓ {label} cadastrada com sucesso! "
            f"(id={transaction.id} | {format_brl(transaction.amount)})\n"
        )

    def _list_transactions(self) -> None:
        transactions = self.transaction_service.list_all()
        if not transactions:
            print("Nenhuma transação cadastrada.\n")
            return

        print(f"--- {len(transactions)} transações ---")
        self._print_transaction_table(transactions)
        print()

    def _monthly_summary(self) -> None:
        today = date.today()
        year = ask_int(f"Ano [{today.year}]: ", default=today.year)
        month = ask_int(f"Mês [{today.month}]: ", default=today.month)

        summary = self.report_service.monthly_summary(year, month)

        # "Painel" do mês: cada linha é um indicador, com os valores
        # alinhados à direita para ficar fácil de ler.
        balance = summary["balance"]
        balance_label = "Saldo (sobra)" if balance >= 0 else "Saldo (déficit)"

        print(f"\n┌─ Resumo de {month:02d}/{year} " + "─" * 24)
        print(f"│ Transações   {summary['count']:>20}")
        print(f"│ Receitas     {format_brl(summary['total_incomes']):>20}")
        print(f"│ Despesas     {format_brl(summary['total_expenses']):>20}")
        print("│ " + "─" * 32)
        print(f"│ {balance_label:<13}{format_brl(balance):>20}")
        print("└" + "─" * 33)

        if summary["expenses_by_category"]:
            print("\nGastos por categoria:")
            for category, total in summary["expenses_by_category"].items():
                print(f"  - {category:<20} {format_brl(total):>14}")

        if summary["expenses_by_person"]:
            print("\nGastos por pessoa:")
            for person, total in summary["expenses_by_person"].items():
                print(f"  - {person:<20} {format_brl(total):>14}")
        print()

    def _filter_by_category(self) -> None:
        category = ask_non_empty("Categoria: ")
        transactions = self.transaction_service.list_by_category(category)
        if not transactions:
            print(f"Nenhuma transação na categoria '{category}'.\n")
            return

        print(f"--- {len(transactions)} transações em '{category}' ---")
        self._print_transaction_table(transactions)
        print()

    def _filter_by_person(self) -> None:
        person = select_from_list("Filtrar por quem gastou:", PEOPLE)
        if person == OTHER_PERSON_LABEL:
            person = ask_non_empty("Digite o nome: ")

        transactions = self.transaction_service.list_by_person(person)
        if not transactions:
            print(f"Nenhuma transação de '{person}'.\n")
            return

        # Soma só as despesas dessa pessoa — responde "quanto fulano gastou".
        total_spent = sum(
            t.amount for t in transactions if t.type == TYPE_EXPENSE
        )
        print(f"--- {len(transactions)} transações de '{person}' ---")
        self._print_transaction_table(transactions)
        print(f"\nTotal gasto por {person}: {format_brl(total_spent)}\n")

    def _export_excel(self) -> None:
        transactions = self.transaction_service.list_all()
        if not transactions:
            print("Nenhuma transação para exportar.\n")
            return

        path = self.export_service.export_to_excel(transactions)
        print(f"✓ Excel gerado em: {path}\n")

    def _generate_chart(self) -> None:
        today = date.today()
        year = ask_int(f"Ano [{today.year}]: ", default=today.year)
        month = ask_int(f"Mês [{today.month}]: ", default=today.month)

        summary = self.report_service.monthly_summary(year, month)
        expenses = summary["expenses_by_category"]

        if not expenses:
            print("Nenhuma despesa no mês para gerar gráfico.\n")
            return

        path = self.chart_service.expenses_by_category_chart(expenses)
        print(f"✓ Gráfico salvo em: {path}\n")

    # ---------- Helpers de impressão ----------

    @staticmethod
    def _print_transaction_table(transactions) -> None:
        print(
            f"{'ID':<5}{'Data':<12}{'Tipo':<10}{'Categoria':<20}"
            f"{'Quem':<12}{'Valor':>14}  Descrição"
        )
        print("-" * 92)
        for t in transactions:
            # Mostramos a data no formato brasileiro para o usuário.
            display_date = format_user(parse_iso_date(t.date))
            print(
                f"{t.id:<5}{display_date:<12}{t.type:<10}{t.category:<20}"
                f"{t.spent_by:<12}{format_brl(t.amount):>14}  {t.description}"
            )
