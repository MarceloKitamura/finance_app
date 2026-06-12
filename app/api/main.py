"""
Aplicação FastAPI — ponto de entrada da API REST.

Responsabilidades deste arquivo:
- criar a instância do FastAPI;
- inicializar o banco na subida (lifespan);
- liberar CORS (para o frontend, que rodará em outra porta, poder chamar);
- traduzir erros de regra de negócio (ValueError) em respostas HTTP claras;
- registrar os routers (transactions, reports, meta).

Como rodar (na raiz do projeto):
    uvicorn app.api.main:app --reload
ou:
    python run_api.py

Depois abra a documentação interativa em:
    http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import (
    accounts,
    advice,
    ai,
    alerts,
    cards,
    forecast,
    goals,
    imports,
    meta,
    recurring,
    reports,
    salary,
    transactions,
    vencimentos,
)
from app.database import initialize_database
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Roda na SUBIDA e na DESCIDA do app.

    Antes do `yield`: preparamos o que o app precisa (criar tabelas/migrar).
    Depois do `yield`: limpamos recursos (nada a fazer aqui por enquanto).

    É o substituto moderno do antigo @app.on_event("startup").
    """
    logger.info("Iniciando API e banco de dados")
    initialize_database()
    yield
    logger.info("Encerrando API")


app = FastAPI(
    title="Finance App API",
    version="1.0.0",
    description=(
        "API REST do Finance App. Mesma lógica da CLI e do Streamlit, "
        "agora acessível via HTTP. Use /docs para explorar."
    ),
    lifespan=lifespan,
)

# CORS: permite que o frontend (em outra origem/domínio) chame esta API pelo
# navegador. A lista de origens permitidas vem da variável de ambiente
# CORS_ORIGINS (separada por vírgula). Em desenvolvimento o padrão "*" libera
# tudo; em produção, defina CORS_ORIGINS com a URL do seu frontend Vercel, ex:
#   CORS_ORIGINS=https://meu-finance.vercel.app
import os

_cors_env = os.getenv("CORS_ORIGINS", "*").strip()
_allow_origins = (
    ["*"] if _cors_env == "*" else [o.strip() for o in _cors_env.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    # Não usamos cookies/sessão (a API é sem login); manter False permite usar
    # "*" com segurança e evita o conflito credentials+wildcard do navegador.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Converte erros de validação de domínio em HTTP 422.

    Os services e o model lançam ValueError com mensagens amigáveis
    (ex: "Forma de pagamento inválida"). Sem este handler, viraria um
    erro 500 genérico. Com ele, o cliente recebe 422 + a mensagem.
    """
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# Registro dos routers. O `prefix` define o início da URL de cada grupo;
# `tags` agrupa os endpoints na documentação /docs.
app.include_router(transactions.router, prefix="/transactions", tags=["Transações"])
app.include_router(reports.router, prefix="/reports", tags=["Relatórios"])
app.include_router(accounts.router, prefix="/accounts", tags=["Contas / Saldos"])
app.include_router(cards.router, prefix="/cards", tags=["Cartões de Crédito"])
app.include_router(goals.router, prefix="/goals", tags=["Metas"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alertas"])
app.include_router(advice.router, prefix="/advice", tags=["Conselhos / IA"])
app.include_router(ai.router, prefix="/ai", tags=["IA"])
app.include_router(salary.router, prefix="/salary", tags=["Salário"])
app.include_router(forecast.router, prefix="/forecast", tags=["Previsão do mês"])
app.include_router(
    recurring.router, prefix="/recurring-expenses", tags=["Gastos Recorrentes"]
)
app.include_router(vencimentos.router, prefix="/vencimentos", tags=["Agenda / Vencimentos"])
app.include_router(imports.router, prefix="/import", tags=["Importar Extrato"])
app.include_router(meta.router, prefix="/meta", tags=["Metadados"])


@app.get("/", tags=["Status"])
def root():
    """Endpoint de saúde: confirma que a API está no ar."""
    return {"status": "ok", "docs": "/docs", "app": "Finance App API"}
