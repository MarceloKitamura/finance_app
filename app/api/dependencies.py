"""
Dependências da API (injeção de dependência do FastAPI).

O FastAPI tem um mecanismo chamado "Depends": em vez de cada endpoint
criar seu próprio service, ele declara que PRECISA de um service e o
FastAPI o entrega. Vantagens:

- um único ponto cria os services (fácil de trocar em testes);
- os endpoints ficam enxutos (só pedem o que precisam).

Usamos lru_cache para reaproveitar a mesma instância entre requisições
(os services não guardam estado por requisição — só seguram um
repository, que abre/fecha conexão a cada chamada).
"""

from functools import lru_cache

from app.services.account_service import AccountService
from app.services.ai_service import AIService
from app.services.alert_service import AlertService
from app.services.card_service import CardService
from app.services.financial_advisor_service import FinancialAdvisorService
from app.services.goal_service import GoalService
from app.services.report_service import ReportService
from app.services.transaction_service import TransactionService


@lru_cache
def get_transaction_service() -> TransactionService:
    return TransactionService()


@lru_cache
def get_report_service() -> ReportService:
    return ReportService()


@lru_cache
def get_account_service() -> AccountService:
    return AccountService()


@lru_cache
def get_card_service() -> CardService:
    return CardService()


@lru_cache
def get_goal_service() -> GoalService:
    return GoalService()


@lru_cache
def get_alert_service() -> AlertService:
    return AlertService()


@lru_cache
def get_advisor_service() -> FinancialAdvisorService:
    # use_llm=True liga o conselho personalizado via Groq. Sem GROQ_API_KEY,
    # o service ignora a IA e segue só com as regras determinísticas.
    return FinancialAdvisorService(use_llm=True)


@lru_cache
def get_ai_service() -> AIService:
    # use_llm=True permite a camada LLM (OpenAI) quando há OPENAI_API_KEY;
    # sem chave, usa só palavras-chave (offline). Ver AIService.
    return AIService(use_llm=True)
