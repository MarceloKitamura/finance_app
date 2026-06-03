# Finance App

Sistema de gestão financeira pessoal em Python com múltiplas interfaces, IA de categorização e análise inteligente. Suporta CLI, web (Streamlit e HTML/CSS/JS puro), e API REST (FastAPI) com um núcleo compartilhado de lógica de negócio.

## Visão Geral

**Finance App** oferece:

- **CLI** (linha de comando) — para uso rápido e scripting
- **Streamlit** — dashboard interativo com gráficos Plotly
- **API REST** (FastAPI) — para integração com frontends customizados
- **Frontend web** — HTML/CSS/JS puro consumindo a API
- **IA de categorização** — sugestão automática de categoria com padrões offline + LLM opcional
- **Análise financeira** — consultor inteligente com alertas, conselhos e insights
- **Multi-contas** — suporte a múltiplas carteiras/contas
- **Cartões de crédito** — rastreamento de fatura, limite e vencimento
- **Metas financeiras** — limites de gasto, objetivos de poupança, controle de dívidas

Todas as interfaces compartilham o mesmo **core de serviços, repositórios e banco de dados** SQLite.

---

## Quick Start

### Setup

```bash
# 1. Crie o ambiente virtual
python -m venv .venv

# 2. Ative (Windows)
.\.venv\Scripts\activate
# Ou (Linux/Mac)
source .venv/bin/activate

# 3. Instale dependências
pip install -r requirements.txt

# 4. Defina encoding para suportar UTF-8 (Windows)
set PYTHONIOENCODING=utf-8
```

### Rode a aplicação

```bash
# Opção 1: CLI (terminal)
python -m app.main

# Opção 2: Streamlit (web interativo)
streamlit run run_streamlit.py

# Opção 3: API REST
python run_api.py
# Acesse http://127.0.0.1:8000/docs (Swagger)

# Opção 4: Frontend web (consumindo a API)
# Abra em navegador: file:///caminho/para/frontend/index.html
# Ou sirva com Python: python -m http.server --directory frontend 8080
```

---

## Estrutura do Projeto

```
finance_app/
├── app/
│   ├── main.py                           # CLI entrypoint
│   ├── database.py                       # SQLite setup
│   ├── config.py                         # Paths e configuração
│   │
│   ├── models/
│   │   ├── transaction.py
│   │   ├── account.py
│   │   ├── card.py
│   │   └── goal.py
│   │
│   ├── repositories/                     # Data access (único lugar com SQL)
│   │   ├── transaction_repository.py
│   │   ├── account_repository.py
│   │   ├── card_repository.py
│   │   └── goal_repository.py
│   │
│   ├── services/                         # Business logic (compartilhado)
│   │   ├── transaction_service.py
│   │   ├── report_service.py
│   │   ├── account_service.py
│   │   ├── card_service.py
│   │   ├── goal_service.py
│   │   ├── ai_service.py                 # IA de categorização
│   │   ├── financial_advisor_service.py  # Análise e alertas
│   │   ├── alert_service.py              # Agregador de alertas
│   │   └── export_service.py
│   │
│   ├── constants/
│   │   ├── categories.py
│   │   ├── payment_methods.py
│   │   ├── transaction_types.py
│   │   └── category_patterns.py          # Padrões para IA
│   │
│   ├── interfaces/
│   │   ├── cli.py                        # Menu terminal
│   │   ├── prompts.py                    # Input helpers
│   │   └── streamlit_app.py              # Dashboard Streamlit
│   │
│   ├── api/                              # FastAPI
│   │   ├── main.py                       # App FastAPI
│   │   ├── schemas.py                    # Pydantic models
│   │   └── routers/
│   │       ├── transactions.py
│   │       ├── accounts.py
│   │       ├── cards.py
│   │       ├── goals.py
│   │       ├── alerts.py
│   │       ├── reports.py
│   │       └── ai.py
│   │
│   └── utils/
│       ├── date_utils.py
│       ├── money_utils.py
│       ├── normalizers.py
│       └── logger.py
│
├── frontend/
│   ├── index.html                        # Home/Dashboard
│   ├── pages/
│   │   ├── transacoes.html
│   │   ├── cartoes.html
│   │   ├── metas.html
│   │   ├── alertas.html
│   │   ├── relatorios.html
│   │   └── configuracoes.html
│   │
│   ├── js/
│   │   ├── api.js                        # Chamadas HTTP
│   │   ├── ui.js                         # Componentes UI
│   │   ├── app.js                        # Lógica principal
│   │   ├── theme.js                      # Tema claro/escuro
│   │   └── utils.js                      # Helpers
│   │
│   └── css/
│       ├── style.css                     # Base
│       └── light-theme.css               # Tema claro
│
├── .streamlit/
│   └── config.toml                       # Tema Streamlit
│
├── data/
│   ├── database.db                       # SQLite (criado em runtime)
│   └── exports/                          # Arquivos exportados
│
├── logs/
│   └── app.log
│
├── run_streamlit.py
├── run_api.py
├── requirements.txt
├── STUDY_GUIDE.md
├── CHALLENGES.md
└── README.md
```

---

## Arquitetura

```
┌─────────────────────────────────────────┐
│  CLI  │ Streamlit │ API REST │ Frontend  │
└──────────────┬──────────────────────────┘
               │
       ┌───────▼──────────┐
       │    Services      │
       │ (lógica negócio) │
       └───────┬──────────┘
               │
       ┌───────▼──────────────┐
       │   Repositories       │
       │  (acesso a dados)    │
       └───────┬──────────────┘
               │
        ┌──────▼─────────┐
        │   SQLite DB    │
        └────────────────┘
```

**Princípio:** Services e Repositories são agnósticos de interface. Qualquer novo client (CLI, web, mobile) reutiliza o core sem mudanças.

---

## Recursos

### IA de Categorização

Ao adicionar uma transação, a IA sugere automaticamente a categoria:

1. **Offline (padrão)** — reconhece palavras-chave ("mercado", "uber", "netflix") via `category_patterns.py`. Rápido, privado, sem custo.

2. **LLM (opcional)** — para descrições que não casam com padrões, consulta uma IA remota (OpenAI, Groq, etc).

Ativar LLM:
```bash
pip install openai
set OPENAI_API_KEY=sk-...
streamlit run run_streamlit.py
```

Ou com Groq:
```bash
set GROQ_API_KEY=gsk-...
python run_api.py
```

### Análise Financeira (Financial Advisor)

Consultor inteligente que analisa seu histórico e gera:

- **Alertas** — saldo negativo, cartão acima de 80%, meta estourada, mês no vermelho
- **Conselhos** — onde economizar, gastos concentrados, padrões de consumo
- **Resumo** — taxa de poupança, evolução, principais despesas

Roda 100% offline, com regras + estatística. Dados nunca deixam seu computador.

### Multi-Contas

Gerencie múltiplas carteiras/contas:
- Cada transação está ligada a uma conta
- Saldo calculado automaticamente (inicial + receitas - despesas)
- Relatórios por conta
- Dashboard com cards de cada conta

### Cartões de Crédito

Rastreie fatura, limite de crédito e vencimento:
- Visualize transações por cartão
- Veja fatura do mês e uso do limite
- Alertas para cartões vencidos ou acima de 80%

### Metas Financeiras

Três tipos de meta:

1. **Limite de gasto** — defina máximo para uma categoria/mês
2. **Poupança** — objetivo de valor a poupar
3. **Dívida** — controle de empréstimos/cartão rotativo

Barra de progresso e alertas automáticos.

---

## Guia de Uso

### CLI

```bash
python -m app.main

# Menu:
# 1 - Adicionar transação
# 2 - Gerar relatório
# 3 - Listar transações
# 4 - Exportar Excel
# ... etc
```

### Streamlit Web

```bash
streamlit run run_streamlit.py
```

Páginas:
- **Dashboard** — KPIs, saldos, comparativo receitas vs despesas
- **Adicionar** — Formulário com sugestão de IA
- **Transações** — Lista com filtros (mês, tipo, categoria, conta)
- **Relatórios** — Evolução e breakdown por categoria
- **Cartões** — Status de faturas e limites
- **Metas** — Progresso de objetivos
- **Alertas** — Avisos e recomendações
- **Exportar** — Download Excel, gráficos PNG

### API REST (FastAPI)

```bash
python run_api.py
```

Endpoints principais:

```
GET  /transactions              # Listar
POST /transactions              # Criar
GET  /transactions/{id}         # Detalhe
PUT  /transactions/{id}         # Atualizar
DELETE /transactions/{id}       # Deletar

GET  /accounts                  # Listar contas
POST /accounts                  # Criar conta

GET  /cards                      # Listar cartões
POST /cards                      # Criar cartão

GET  /goals                      # Listar metas
POST /goals                      # Criar meta

GET  /alerts                     # Alertas agregados

GET  /reports/summary            # Resumo financeiro
GET  /reports/by-category        # Despesas por categoria

POST /ai/suggest-category        # Sugerir categoria
GET  /advice                     # Análise financeira
```

Documentação interativa: http://127.0.0.1:8000/docs

### Frontend Web

```bash
cd frontend
python -m http.server 8080
# Abra http://localhost:8080
```

Interface moderna com:
- Tema claro/escuro
- Gráficos interativos
- Responsive (mobile-friendly)
- Consumo direto da API

---

## Configuração Avançada

### Banco de Dados

O SQLite fica em `data/database.db`. Para inspecionar:

```bash
# 1. Terminal SQLite
sqlite3 data/database.db
sqlite> SELECT * FROM transactions;

# 2. GUI: DB Browser for SQLite (sqlitebrowser.org)

# 3. Via CLI do app: python -m app.main → opção 3
```

### Temas e Cores

Streamlit: edite `.streamlit/config.toml`

Frontend: modifique `frontend/css/light-theme.css`

### Logging

Logs em `logs/app.log`. Nível configurável em `app/utils/logger.py`.

---

## Troubleshooting

| Problema | Solução |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Use `python -m app.main`, não `python app/main.py` |
| Importação falha | Ative `.venv` e rode `pip install -r requirements.txt` |
| `Port 8501 already in use` | `streamlit run run_streamlit.py --server.port 8502` |
| `Port 8000 already in use` | `python run_api.py --port 8001` |
| Caracteres estranhos (Windows) | `set PYTHONIOENCODING=utf-8` |
| API retorna 422 | Verifique schema Pydantic em `app/api/schemas.py` |

---

## Roadmap

- Fase 1: CLI + SQLite + Relatórios (COMPLETO)
- Fase 2: Streamlit com gráficos Plotly (COMPLETO)
- Fase 2.5: IA de categorização + Consultor (COMPLETO)
- Fase 3: API FastAPI + Frontend web (COMPLETO)
- Fase 4: Multi-contas, cartões, metas, alertas (COMPLETO)
- Fase 5: Importação CSV/OFX, automação, gestão de casal

---

## Desenvolvimento

### Padrões

- **Interfaces** são agnósticas — chamam apenas `services`
- **Services** contêm toda lógica de negócio
- **Repositories** são o único lugar com SQL
- **Models** definem entidades
- **Constants** centralizam categorias, tipos, padrões

### Testes

Sem suite de testes automatizados ainda. Verificação manual via TestClient ou uvicorn.

### Contribuições

Para adicionar uma feature:

1. Implemente o serviço (`app/services/`)
2. Exponha em todas as interfaces desejadas (CLI, Streamlit, API)
3. Teste em cada interface
4. Atualize este README

---

## Licença

Projeto pessoal de aprendizado e gestão financeira.
