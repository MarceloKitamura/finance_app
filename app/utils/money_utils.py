"""
Funções utilitárias para lidar com valores monetários.

Separar a formatação BRL aqui faz com que ela apareça uma única vez
no projeto. Se um dia precisarmos suportar outra moeda, mudamos aqui.
"""


def parse_amount(text: str) -> float:
    """
    Converte uma string digitada pelo usuário em float.

    Aceita tanto "1234.56" quanto "1234,56" (padrão brasileiro).
    Mensagens de erro claras para feedback no terminal.
    """
    text = (text or "").strip().replace(",", ".")

    if not text:
        raise ValueError("Valor não pode ser vazio.")

    try:
        value = float(text)
    except ValueError:
        # Substituímos a mensagem padrão do Python por uma mais amigável.
        raise ValueError(
            f"Valor inválido: {text!r}. Use números como 10 ou 10,50."
        )

    if value <= 0:
        raise ValueError("O valor deve ser positivo (maior que zero).")

    return value


def format_brl(value: float) -> str:
    """
    Formata um número como moeda brasileira: R$ 1.234,56.

    Truque: o f-string padrão usa . para milhar e , para decimal.
    Em pt-BR é o contrário, então fazemos um swap controlado.
    """
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
    return f"R$ {formatted}"
