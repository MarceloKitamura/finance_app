"""
Helpers de prompt para a CLI.

Estes helpers encapsulam padrões repetitivos:
- mostrar uma lista numerada;
- pedir uma escolha;
- repetir até a escolha ser válida.

Eles NÃO conhecem o domínio (não sabem o que é "categoria" ou "pagamento").
Recebem listas genéricas e devolvem strings. Isso os torna reutilizáveis.

Por que arquivo separado da cli.py?
A cli.py orquestra o fluxo (qual pergunta vem depois de qual).
Os prompts implementam a mecânica de cada pergunta.
Separar deixa cada arquivo com uma responsabilidade só.
"""

from typing import Sequence

from app.utils.date_utils import parse_user_date
from app.utils.money_utils import parse_amount


def select_from_list(title: str, options: Sequence[str]) -> str:
    """
    Mostra uma lista numerada e devolve a opção escolhida.

    Repete a pergunta até o usuário digitar um número válido.
    """
    print(f"\n{title}")
    for i, option in enumerate(options, start=1):
        print(f"  {i} - {option}")

    while True:
        raw = input("Opção: ").strip()
        # Valida que é número.
        if not raw.isdigit():
            print(f"  ⚠ Digite o número da opção (1 a {len(options)}).")
            continue

        index = int(raw)
        if 1 <= index <= len(options):
            # index humano (1-based) → índice Python (0-based).
            return options[index - 1]

        print(f"  ⚠ Opção fora do intervalo. Use 1 a {len(options)}.")


def ask_non_empty(prompt: str) -> str:
    """Pede um texto e exige que não seja vazio."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("  ⚠ Este campo não pode ficar vazio.")


def ask_amount(prompt: str = "Valor: ") -> float:
    """
    Pede um valor monetário, repetindo até receber um número positivo válido.

    Reaproveita a função parse_amount (que lança ValueError para entradas
    inválidas) e captura o erro para mostrar a mensagem no terminal.
    """
    while True:
        raw = input(prompt)
        try:
            return parse_amount(raw)
        except ValueError as e:
            print(f"  ⚠ {e}")


def ask_date(prompt: str = "Data [Enter para hoje]: ") -> str:
    """
    Pede uma data, repetindo até receber uma data válida.

    Devolve no formato interno (YYYY-MM-DD), pronto para ir ao banco.
    Aceita formato dd/mm/aaaa do usuário ou vazio (=hoje).
    """
    while True:
        raw = input(prompt)
        try:
            return parse_user_date(raw)
        except ValueError as e:
            print(f"  ⚠ {e}")


def ask_int(prompt: str, default: int | None = None) -> int:
    """Pede um inteiro. Se default for passado e o usuário pular, usa o default."""
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        if raw.isdigit():
            return int(raw)
        print("  ⚠ Digite um número inteiro.")
