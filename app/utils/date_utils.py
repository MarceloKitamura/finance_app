"""
Funções utilitárias para trabalhar com datas.

Formatos:
- INTERNO (banco / lógica): YYYY-MM-DD (formato ISO).
  SQLite ordena strings nesse formato como se fossem datas reais.
- USUÁRIO (entrada na CLI): dd/mm/aaaa (formato brasileiro).

A função parse_user_date traduz do formato do usuário para o interno.
"""

from datetime import date, datetime, timedelta


ISO_FORMAT = "%Y-%m-%d"
USER_FORMAT = "%d/%m/%Y"


def parse_iso_date(text: str) -> date:
    """Converte uma string YYYY-MM-DD em objeto date."""
    return datetime.strptime(text, ISO_FORMAT).date()


def format_iso(value: date) -> str:
    """Converte um date em string YYYY-MM-DD."""
    return value.strftime(ISO_FORMAT)


def format_user(value: date) -> str:
    """Converte um date em string dd/mm/aaaa (para exibição)."""
    return value.strftime(USER_FORMAT)


def today_iso() -> str:
    """Retorna a data de hoje no formato YYYY-MM-DD."""
    return format_iso(date.today())


def parse_user_date(user_input: str) -> str:
    """
    Recebe a data como o usuário digitou e devolve no formato interno.

    Aceita:
    - "dd/mm/aaaa" (preferido)
    - "yyyy-mm-dd" (formato interno, também aceito)
    - vazio → data de hoje

    Lança ValueError com mensagem clara se a data for inválida
    (ex: 31/02/2026, que o strptime rejeita).
    """
    user_input = (user_input or "").strip()
    if not user_input:
        return today_iso()

    # Tenta primeiro o formato brasileiro, depois o ISO.
    for fmt in (USER_FORMAT, ISO_FORMAT):
        try:
            parsed = datetime.strptime(user_input, fmt).date()
            return format_iso(parsed)
        except ValueError:
            continue

    raise ValueError(
        f"Data inválida: {user_input!r}. Use o formato dd/mm/aaaa."
    )


def month_range(year: int, month: int) -> tuple[str, str]:
    """
    Retorna (primeiro_dia, último_dia) do mês no formato YYYY-MM-DD.
    Útil para filtrar transações de um mês no SQL com BETWEEN.
    """
    first_day = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return format_iso(first_day), format_iso(last_day)
