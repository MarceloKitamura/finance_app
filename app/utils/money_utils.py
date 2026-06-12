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


def split_installments(total: float, parts: int) -> list[float]:
    """
    Divide um valor total em N parcelas com 2 casas decimais.

    A divisão simples pode gerar diferença de centavos (ex: 100/3 = 33,33,
    que somado dá 99,99). Para nunca "perder" ou "criar" dinheiro, as N-1
    primeiras parcelas usam o valor arredondado e a ÚLTIMA absorve a
    diferença de arredondamento.

    Exemplo: split_installments(100, 3) -> [33.33, 33.33, 33.34].

    Lança ValueError se parts < 1 ou total <= 0.
    """
    if parts < 1:
        raise ValueError("A quantidade de parcelas deve ser pelo menos 1.")
    if total <= 0:
        raise ValueError("O valor total deve ser positivo.")

    # Trabalhamos em centavos (inteiros) para não acumular erro de float.
    total_cents = round(total * 100)
    base = total_cents // parts            # centavos de cada parcela "normal"
    rest = total_cents - base * parts      # sobra a colocar na última parcela

    amounts = [base for _ in range(parts)]
    amounts[-1] += rest                    # última parcela ajusta a diferença
    return [c / 100 for c in amounts]


def format_brl(value: float) -> str:
    """
    Formata um número como moeda brasileira: R$ 1.234,56.

    Truque: o f-string padrão usa . para milhar e , para decimal.
    Em pt-BR é o contrário, então fazemos um swap controlado.
    """
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
    return f"R$ {formatted}"
