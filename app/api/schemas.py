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
    payment_origin: Optional[str] = Field(
        default=None,
        description=(
            "Origem do gasto: 'account' (sai do saldo) ou 'card' (entra na "
            "fatura). Se omitido, é deduzida pela presença do cartão."
        ),
    )
    installments: int = Field(
        default=1, ge=1, le=72,
        description="Nº de parcelas (só para gasto no cartão; 1 = à vista).",
    )

    # Exemplo que aparece na documentação /docs.
    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2026-06-10",
                "description": "Celular",
                "amount": 1200.00,
                "type": "despesa",
                "category": "Compras",
                "payment_method": "Crédito",
                "spent_by": "Eu",
                "account": "Nubank",
                "card": "Nubank",
                "payment_origin": "card",
                "installments": 12,
            }
        }
    }


class TransactionUpdate(BaseModel):
    """Dados para editar uma transação existente (PUT /transactions/{id}).

    Edita UMA transação no lugar, sem reparcelar nem trocar o id. Útil sobretudo
    para corrigir o VALOR de uma parcela (ex.: centavos da última). Campos
    omitidos mantêm o valor atual; a metadata de parcela é preservada no service.
    Não há `installments` aqui de propósito: editar não recria as parcelas.
    """

    date: Optional[date_type] = Field(None, description="Data (YYYY-MM-DD).")
    description: Optional[str] = Field(None, min_length=1)
    amount: Optional[float] = Field(None, gt=0, description="Valor positivo.")
    type: Optional[str] = Field(None, description="'receita' ou 'despesa'.")
    category: Optional[str] = Field(None, min_length=1)
    payment_method: Optional[str] = None
    spent_by: Optional[str] = None
    account: Optional[str] = None
    card: Optional[str] = None
    payment_origin: Optional[str] = Field(
        None, description="'account' ou 'card' (se omitido, mantém a atual)."
    )


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
    payment_origin: str
    installment_no: int
    installments_total: int
    purchase_group: str
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
            payment_origin=t.payment_origin,
            installment_no=t.installment_no,
            installments_total=t.installments_total,
            purchase_group=t.purchase_group,
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


class CardStatementItemOut(BaseModel):
    """Um lançamento dentro de uma fatura do cartão."""

    id: int
    date: str
    description: str
    amount: float
    category: str
    spent_by: str
    installment_no: int
    installments_total: int


class CardStatementOut(BaseModel):
    """Uma fatura (mês) do cartão, com seus lançamentos."""

    year: int
    month: int
    label: str            # "Junho/2026"
    total: float
    count: int
    is_current: bool      # é a fatura do mês atual?
    items: List[CardStatementItemOut]


class CardStatementsOut(BaseModel):
    """Fatura atual + próximas faturas de um cartão."""

    card_id: int
    card_name: str
    limit_total: float
    statements: List[CardStatementOut]


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


class AIStatusOut(BaseModel):
    """Estado das integrações de IA (para o frontend avisar se falta chave).

    O app funciona SEM chave (regras offline + categorização por palavras-chave);
    estas flags só dizem se os recursos de LLM estão disponíveis.
    """

    groq_configured: bool      # conselhos personalizados (GROQ_API_KEY)
    openai_configured: bool    # categorização via LLM (OPENAI_API_KEY)
    advice_provider: str       # "groq" | "offline"
    category_provider: str     # "openai" | "offline"


# ---------- Gastos recorrentes (Fase 3) ----------

class RecurringCreate(BaseModel):
    """Dados para criar/atualizar um template de gasto recorrente."""

    description: str = Field(..., min_length=1, description="Descrição (ex: Netflix).")
    amount: float = Field(..., gt=0, description="Valor esperado.")
    type: str = Field(default="despesa", description="'receita' ou 'despesa'.")
    category: str = Field(default="", description="Categoria.")
    payment_method: str = Field(default="Outros")
    spent_by: str = Field(default=DEFAULT_PERSON)
    account: str = Field(default="Carteira")
    card: str = Field(default="")
    day_of_month: int = Field(default=0, ge=0, le=31, description="Dia esperado (0=desconhecido).")
    active: int = Field(default=1, description="1=ativo, 0=pausado.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "description": "Netflix", "amount": 39.90, "type": "despesa",
                "category": "Assinaturas", "payment_method": "Crédito",
                "spent_by": "Eu", "account": "Nubank", "card": "Nubank",
                "day_of_month": 15, "active": 1,
            }
        }
    }


class RecurringOut(BaseModel):
    """Template de gasto recorrente devolvido pela API."""

    id: int
    description: str
    amount: float
    type: str
    category: str
    payment_method: str
    spent_by: str
    account: str
    card: str
    day_of_month: int
    active: int
    created_at: str
    next_date: Optional[str] = None    # próxima cobrança projetada (se day_of_month)
    days_until: Optional[int] = None   # dias até a próxima cobrança


class RecurringSuggestionOut(BaseModel):
    """Sugestão de autopreenchimento ao digitar a descrição."""

    description: str
    amount: float
    type: str
    category: str
    payment_method: str
    spent_by: str
    account: str
    card: str
    source: str          # "template" | "historico"
    last_date: str
    occurrences: int
    template_id: Optional[int] = None


class DetectedRecurringOut(BaseModel):
    """Padrão recorrente detectado automaticamente no histórico."""

    description: str
    avg_amount: float
    type: str
    category: str
    payment_method: str
    spent_by: str
    account: str
    card: str
    occurrences: int
    months_present: int
    day_of_month: int
    last_date: str
    next_expected: str
    already_template: bool


# ---------- Agenda de vencimentos / fluxo de caixa (Fase 3) ----------

class VencimentoCreate(BaseModel):
    """Dados para criar/atualizar um vencimento."""

    name: str = Field(..., min_length=1, description="Nome do compromisso.")
    due_date: str = Field(..., description="Data de vencimento (YYYY-MM-DD).")
    amount: float = Field(default=0.0, ge=0, description="Valor a pagar.")
    kind: str = Field(default="conta", description="conta|cartao|meta|outro.")
    notify_days: int = Field(default=3, ge=0, le=60, description="Avisar N dias antes.")
    recurrence: str = Field(default="unica", description="unica|mensal.")
    category: str = Field(default="", description="Categoria financeira (opcional).")
    notes: str = Field(default="", description="Observação livre.")
    status: str = Field(default="pendente", description="pendente|pago.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Aluguel", "due_date": "2026-06-05", "amount": 1500.0,
                "kind": "conta", "notify_days": 3, "recurrence": "mensal",
                "category": "Moradia", "notes": "", "status": "pendente",
            }
        }
    }


class VencimentoOut(BaseModel):
    """Vencimento devolvido pela API, com status/dias/nível derivados."""

    id: int
    name: str
    due_date: str
    amount: float
    kind: str
    status: str           # pendente | pago | atrasado (derivado)
    level: str            # ok | proximo | urgente | atrasado | pago
    notify_days: int
    recurrence: str
    category: str
    notes: str
    paid_at: str
    days_until: Optional[int]
    created_at: str


class CashFlowItemOut(BaseModel):
    """Um vencimento que cai num dia do fluxo de caixa."""

    id: int
    name: str
    amount: float
    kind: str


class CashFlowDayOut(BaseModel):
    """Um dia da projeção de fluxo de caixa."""

    date: str
    delta: float                 # variação do dia (negativa = saídas)
    running_balance: float       # saldo acumulado após o dia
    items: List[CashFlowItemOut]


class CashFlowOut(BaseModel):
    """Projeção de fluxo de caixa de um mês."""

    year: int
    month: int
    starting_balance: float
    ending_balance: float
    goes_negative_on: Optional[str]   # 1ª data em que o saldo fica negativo
    days: List[CashFlowDayOut]


# ---------- Importação de extrato (CSV / OFX) (Fase 3) ----------

class ImportPreviewIn(BaseModel):
    """Pedido de preview de importação."""

    format: str = Field(..., description="'csv' ou 'ofx'.")
    content: str = Field(..., description="Conteúdo bruto do arquivo (texto).")
    mapping: Optional[Dict] = Field(
        default=None,
        description=(
            "Só para CSV: índices das colunas {date, amount, description} "
            "e padrões {default_type, default_account, default_payment}."
        ),
    )


class ImportPreviewItemOut(BaseModel):
    """Uma transação candidata na pré-visualização."""

    date: str
    description: str
    amount: float
    type: str
    category_suggested: Optional[str]
    confidence: float
    payment_method: str
    spent_by: str
    account: str
    card: str
    # Parcelamento detectado na fatura (1/1 = à vista). base_description é a
    # descrição sem o "N/M"; project_future liga a projeção das próximas parcelas.
    base_description: str = ""
    installment_no: int = 1
    installments_total: int = 1
    project_future: bool = False
    duplicate: bool
    include: bool


class ImportPreviewOut(BaseModel):
    """Resposta do preview: cabeçalhos (CSV) + transações candidatas."""

    headers: List[str]
    delimiter: str
    sample: List[List[str]] = []
    items: List[ImportPreviewItemOut]


class ImportConfirmItemIn(BaseModel):
    """Item revisado a importar (vindo da tela de preview)."""

    date: str
    description: str
    amount: float
    type: str
    category: Optional[str] = None
    payment_method: str = "Outros"
    spent_by: str = DEFAULT_PERSON
    account: str = "Carteira"
    card: str = ""
    # Parcelamento (só para linha de fatura de cartão). installments_total > 1
    # faz o service gravar a parcela e projetar as próximas faturas.
    base_description: str = ""
    installment_no: int = 1
    installments_total: int = 1
    project_future: bool = True
    include: bool = True


class ImportConfirmIn(BaseModel):
    """Lista final de transações a gravar."""

    items: List[ImportConfirmItemIn]


class ImportResultOut(BaseModel):
    """Resultado da importação."""

    imported: int
    skipped: int
    errors: List[str]


# ---------- IA Gestora: score de saúde (Fase 3) ----------

class ScoreMetricOut(BaseModel):
    """Uma sub-métrica do score (0-100) com seu peso."""

    score: int
    weight: int
    label: str


class ForecastOut(BaseModel):
    """Previsão de saldo de fim de mês."""

    projected_balance: float
    projected_income: float
    projected_expense: float
    is_projection: bool   # False = mês já fechado (valor real)


class HealthScoreOut(BaseModel):
    """Resposta da IA Gestora: score + breakdown + previsão + insights."""

    year: int
    month: int
    score: int                            # 0-100
    faixa: str                            # critica | atencao | saudavel
    breakdown: Dict[str, ScoreMetricOut]  # sub-métricas
    forecast: ForecastOut
    insights: List[InsightOut]
    llm_used: bool


# ---------- Salário (bruto / líquido / divisão) ----------

class OtherDiscountIn(BaseModel):
    """Um desconto avulso do salário (plano de saúde, pensão, etc.)."""

    label: str = Field(..., min_length=1, description="Nome do desconto.")
    amount: float = Field(..., ge=0, description="Valor mensal do desconto (R$).")


class SalaryConfigIn(BaseModel):
    """Configuração de salário enviada pelo cliente (PUT /salary)."""

    gross: float = Field(default=0.0, ge=0, description="Salário bruto mensal.")
    dependents: int = Field(default=0, ge=0, description="Nº de dependentes (IRRF).")
    inss_enabled: bool = Field(default=True, description="Descontar INSS?")
    irrf_enabled: bool = Field(default=True, description="Descontar IRRF?")
    vt_enabled: bool = Field(default=False, description="Descontar vale-transporte?")
    vt_monthly_cost: float = Field(default=0.0, ge=0, description="Custo real do VT (0 = teto de 6%).")
    other_discounts: List[OtherDiscountIn] = Field(default_factory=list)
    pay_day_1: int = Field(default=15, ge=1, le=31, description="1º dia de pagamento.")
    pay_day_2: int = Field(default=30, ge=1, le=31, description="2º dia de pagamento.")
    split_mode: str = Field(default="metade", description="'metade' (50/50) ou 'personalizado'.")
    amount_day_1: float = Field(default=0.0, ge=0, description="Valor líquido no 1º dia (modo personalizado).")
    amount_day_2: float = Field(default=0.0, ge=0, description="Valor líquido no 2º dia (modo personalizado).")
    enabled: bool = Field(default=True, description="Usar o salário na previsão?")

    model_config = {
        "json_schema_extra": {
            "example": {
                "gross": 3500.0, "dependents": 0, "vt_enabled": True,
                "vt_monthly_cost": 0.0, "other_discounts": [{"label": "Plano de saúde", "amount": 120.0}],
                "pay_day_1": 15, "pay_day_2": 30, "split_mode": "metade", "enabled": True,
            }
        }
    }


class SalaryBreakdownOut(BaseModel):
    """Detalhamento do cálculo do líquido."""

    gross: float
    inss: float
    irrf: float
    vt: float
    other_discounts: float
    other_discounts_detail: List[Dict]
    total_discounts: float
    net: float


class SalarySplitOut(BaseModel):
    """Divisão do líquido nos dias de recebimento."""

    net: float
    pay_day_1: int
    pay_day_2: int
    amount_day_1: float
    amount_day_2: float
    split_mode: str


class SalaryOut(BaseModel):
    """Resposta de GET/PUT /salary: config + descontos + divisão."""

    config: Dict
    breakdown: SalaryBreakdownOut
    split: SalarySplitOut
    enabled: bool


# ---------- Previsão financeira do mês ----------

class MonthlyForecastOut(BaseModel):
    """Previsão determinística do saldo de fim de mês (GET /forecast)."""

    year: int
    month: int
    is_projection: bool
    current_balance: float
    future_incomes: float
    future_salary: float
    future_expenses: float
    future_recurring: float
    future_vencimentos: float
    future_card: float
    card_detail: List[Dict]
    remaining_to_receive: float
    remaining_to_pay: float
    projected_balance: float
    expected_income_month: float
    status: str                  # positivo | atencao | risco
    salary: Dict                 # líquido + parcelas (dias 15/30)
    recurring_detail: List[Dict]
    vencimentos_detail: List[Dict]
