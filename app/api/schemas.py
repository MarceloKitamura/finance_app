"""
Schemas da API (Pydantic v2).

O que é um "schema"?
É o CONTRATO de entrada e saída da API. Ele descreve, de forma
declarativa, quais campos uma requisição precisa ter e quais campos
uma resposta vai devolver. O FastAPI usa esses schemas para:

- validar automaticamente o corpo das requisições (e devolver erro 422
  com mensagem clara se algo estiver errado);
- gerar a documentação interativa em /docs;
- serializar a resposta em JSON.

Diferença para o `models/transaction.py`:
- `Transaction` (model/dataclass) = entidade do DOMÍNIO, usada internamente.
- Schemas (Pydantic) = formato que TRAFEGA pela rede (HTTP/JSON).
Mantê-los separados evita acoplar a API à estrutura interna do banco.
"""

from datetime import date as date_type
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.constants.people import DEFAULT_PERSON
from app.models.transaction import Transaction


# ---------- Entrada ----------

class TransactionCreate(BaseModel):
    """Dados que o cliente envia para criar uma transação.

    Repare que NÃO validamos aqui se a categoria/forma de pagamento são
    válidas. Essa validação de domínio fica no service/model (que já
    normaliza "pix"/"PIX" -> "Pix"). A API só garante o formato básico
    (tipos certos, valor > 0, descrição não vazia).
    """

    date: date_type = Field(..., description="Data da transação (YYYY-MM-DD).")
    description: str = Field(..., min_length=1, description="Descrição livre.")
    amount: float = Field(..., gt=0, description="Valor positivo.")
    type: str = Field(..., description="'receita' ou 'despesa'.")
    category: str = Field(..., min_length=1)
    payment_method: str = Field(...)
    spent_by: str = Field(default=DEFAULT_PERSON, description="Quem realizou o gasto.")
    account: str = Field(default="Carteira", description="Conta/saldo afetado.")
    card: str = Field(default="", description="Cartão de crédito usado (vazio = nenhum).")

    # Exemplo que aparece na documentação /docs.
    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2026-06-02",
                "description": "Mercado Extra",
                "amount": 150.90,
                "type": "despesa",
                "category": "Mercado",
                "payment_method": "Crédito",
                "spent_by": "Eu",
                "account": "Nubank",
                "card": "Nubank",
            }
        }
    }


# ---------- Saída ----------

class TransactionOut(BaseModel):
    """Formato de uma transação devolvida pela API."""

    id: int
    date: str
    description: str
    amount: float
    type: str
    category: str
    payment_method: str
    spent_by: str
    account: str
    card: str
    created_at: str

    @classmethod
    def from_entity(cls, t: Transaction) -> "TransactionOut":
        """Converte a entidade interna (Transaction) no schema de saída.

        Centralizar a conversão aqui evita repetir o mesmo mapeamento em
        cada endpoint.
        """
        return cls(
            id=t.id,
            date=t.date,
            description=t.description,
            amount=t.amount,
            type=t.type,
            category=t.category,
            payment_method=t.payment_method,
            spent_by=t.spent_by,
            account=t.account,
            card=t.card,
            created_at=t.created_at,
        )


class MonthlySummaryOut(BaseModel):
    """Resumo financeiro de um mês (espelha report_service.monthly_summary)."""

    year: int
    month: int
    count: int
    total_incomes: float
    total_expenses: float
    balance: float
    expenses_by_category: Dict[str, float]
    expenses_by_person: Dict[str, float]
    transactions: List[TransactionOut]


class MetaOut(BaseModel):
    """Listas fixas que o frontend usa para montar dropdowns."""

    transaction_types: List[str]
    payment_methods: List[str]
    people: List[str]
    expense_categories: List[str]
    income_categories: List[str]
    accounts: List[str]
    cards: List[str]


# ---------- Contas / saldos ----------

class AccountCreate(BaseModel):
    """Dados para criar/atualizar uma conta (saldo)."""

    name: str = Field(..., min_length=1, description="Nome único da conta.")
    kind: str = Field(default="outro", description="dinheiro|banco|beneficio|investimento|outro.")
    initial_balance: float = Field(default=0.0, description="Saldo no momento do cadastro.")
    color: str = Field(default="#3B82F6", description="Cor de destaque do card (hex).")
    icon: str = Field(default="💰", description="Emoji exibido no card.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Nubank",
                "kind": "banco",
                "initial_balance": 1200.50,
                "color": "#8B5CF6",
                "icon": "💜",
            }
        }
    }


class AccountOut(BaseModel):
    """Conta devolvida pela API, com o saldo ATUAL já calculado."""

    id: int
    name: str
    kind: str
    initial_balance: float
    color: str
    icon: str
    income: float          # total de receitas que entraram na conta
    expense: float         # total de despesas que saíram da conta
    current_balance: float # initial_balance + income - expense


# ---------- Cartões de crédito ----------

class CardCreate(BaseModel):
    """Dados para criar/atualizar um cartão de crédito."""

    name: str = Field(..., min_length=1, description="Nome único do cartão.")
    brand: str = Field(default="Outra", description="Bandeira (Visa, Mastercard, Elo...).")
    limit_total: float = Field(default=0.0, ge=0, description="Limite total (R$).")
    closing_day: int = Field(default=1, ge=1, le=31, description="Dia de fechamento da fatura.")
    due_day: int = Field(default=10, ge=1, le=31, description="Dia de vencimento da fatura.")
    color: str = Field(default="#8B5CF6", description="Cor de destaque (hex).")
    status: str = Field(default="ativo", description="'ativo' ou 'bloqueado'.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Nubank", "brand": "Mastercard", "limit_total": 5000.0,
                "closing_day": 3, "due_day": 10, "color": "#8B5CF6", "status": "ativo",
            }
        }
    }


class CardOut(BaseModel):
    """Cartão devolvido pela API, com fatura/uso já calculados."""

    id: int
    name: str
    brand: str
    limit_total: float
    closing_day: int
    due_day: int
    color: str
    status: str
    invoice: float          # fatura do mês (soma das despesas no cartão)
    available: float        # limite - fatura
    usage_pct: float        # uso do limite (0-100)
    days_until_due: int     # dias até o próximo vencimento


class MessageOut(BaseModel):
    """Resposta genérica de confirmação."""

    detail: str


# ---------- Conselhos / IA gestora ----------

class InsightOut(BaseModel):
    """Um insight gerado pelo FinancialAdvisorService."""

    category: str   # "alerta" | "economia" | "resumo"
    severity: str   # "success" | "info" | "warning" | "danger"
    title: str
    message: str
    source: str     # "rules" (offline) | "llm" (Groq)


class AdviceOut(BaseModel):
    """Conjunto de insights de um mês + se a IA (Groq) foi usada."""

    year: int
    month: int
    llm_used: bool
    insights: List[InsightOut]


# ---------- Metas financeiras ----------

class GoalCreate(BaseModel):
    """Dados para criar/atualizar uma meta financeira."""

    name: str = Field(..., min_length=1, description="Título da meta.")
    kind: str = Field(default="poupanca", description="limite_gasto | poupanca | divida.")
    target_amount: float = Field(..., gt=0, description="Valor-alvo (R$).")
    category: str = Field(default="", description="Categoria (obrigatória em limite_gasto).")
    start_date: str = Field(default="", description="Início (YYYY-MM-DD), opcional.")
    end_date: str = Field(default="", description="Término (YYYY-MM-DD), opcional.")
    current_amount: float = Field(default=0.0, description="Progresso atual (poupanca/divida).")
    color: str = Field(default="#10B981", description="Cor de destaque (hex).")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Reserva de emergência", "kind": "poupanca",
                "target_amount": 5000.0, "category": "", "start_date": "2026-01-01",
                "end_date": "2026-12-31", "current_amount": 1200.0, "color": "#10B981",
            }
        }
    }


class GoalOut(BaseModel):
    """Meta devolvida pela API, com progresso já calculado."""

    id: int
    name: str
    kind: str
    target_amount: float
    category: str
    start_date: str
    end_date: str
    current_amount: float
    color: str
    current_value: float   # progresso (calculado p/ limite_gasto, manual p/ resto)
    pct: float             # percentual do alvo (pode passar de 100)
    status: str            # em_andamento | atingida | estourou
    exceeded: bool         # estourou o teto (limite_gasto)
    days_left: Optional[int]  # dias até o término (None se sem data)


# ---------- Alertas ----------

class AlertOut(BaseModel):
    """Um alerta agregado a partir do estado atual das finanças."""

    key: str        # identificador estável (p/ marcar como lido no front)
    severity: str   # danger | warning | info
    icon: str
    title: str
    message: str


# ---------- IA de categorização ----------

class CategorySuggestionOut(BaseModel):
    """Sugestão de categoria para uma descrição.

    category=None significa "não consegui sugerir" (o usuário escolhe na mão).
    confidence vai de 0 a 1 (ex: 0.95 = 95% de certeza).
    """

    category: Optional[str]
    confidence: float
