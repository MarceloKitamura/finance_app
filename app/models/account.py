"""
Modelo (entidade) Account — um "saldo"/conta do usuário.

Exemplos de contas: "Dinheiro", "Nubank", "Conta Corrente", "Vale
Refeição". Cada conta tem um SALDO INICIAL (quanto havia quando foi
cadastrada) e, a partir daí, as transações que apontam para ela alteram
esse saldo: receitas somam, despesas subtraem.

Decisão de design (igual ao resto do projeto): a transação guarda o
NOME da conta como texto (campo `account`), do mesmo jeito que já guarda
`payment_method`. A tabela `accounts` é a "fonte da verdade" da lista de
contas + metadados (saldo inicial, cor, ícone). O saldo ATUAL não é
gravado: é calculado somando as transações (ver AccountService).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Tipos de conta aceitos (só organizam/ilustram; não são uma trava rígida).
ACCOUNT_KINDS = ("dinheiro", "banco", "beneficio", "investimento", "outro")

# Conta padrão criada na primeira execução. As transações antigas (sem
# conta) são migradas para ela, para nada ficar "órfão".
DEFAULT_ACCOUNT_NAME = "Carteira"


@dataclass
class Account:
    """Representa uma conta/saldo.

    Campos:
        name: nome único e exibido (ex: "Nubank").
        kind: categoria da conta (ver ACCOUNT_KINDS) — só organiza.
        initial_balance: saldo no momento do cadastro (pode ser negativo).
        color: cor de destaque do card (hex, ex: "#8B5CF6").
        icon: emoji exibido no card (ex: "💳").
        id: identificador no banco (None enquanto não salvo).
        created_at: data/hora de criação.
    """

    name: str
    kind: str = "outro"
    initial_balance: float = 0.0
    color: str = "#3B82F6"
    icon: str = "💰"
    id: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def validate(self) -> None:
        """Validações de domínio. Lança ValueError em caso de erro."""
        if not self.name or not self.name.strip():
            raise ValueError("O nome da conta não pode ser vazio.")
        if self.kind not in ACCOUNT_KINDS:
            raise ValueError(
                f"Tipo de conta inválido: {self.kind!r}. Use {ACCOUNT_KINDS}."
            )
        # initial_balance pode ser qualquer número (inclusive negativo,
        # ex: limite usado), então não validamos sinal aqui.
        try:
            float(self.initial_balance)
        except (TypeError, ValueError) as exc:
            raise ValueError("Saldo inicial deve ser um número.") from exc
