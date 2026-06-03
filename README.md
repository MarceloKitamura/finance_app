# 💰 Finance App

Sistema financeiro pessoal em Python com **duas interfaces** e **IA de categorização**.

- 🖥️ **CLI** (terminal) — Fase 1
- 🌐 **Streamlit** (navegador) — Fase 2 e 2.5
- 🤖 **IA** que sugere categorias automaticamente — Fase 2.5

Todas as interfaces compartilham o mesmo núcleo: services, repositories e banco SQLite.

---

## 🚀 Início rápido

```bash
# 1. Instale as dependências
pip install -r requirements.txt

# 2a. Rode a versão WEB (recomendado)
streamlit run run_streamlit.py

# 2b. OU rode a versão TERMINAL
python -m app.main
```

A versão web abre em `http://localhost:8501`.

> 📚 **Está aprendendo?** Comece pelo arquivo `STUDY_GUIDE.md` — tem um cronograma
> passo a passo. Para praticar, veja `CHALLENGES.md`.

---

## 📂 Estrutura

```
finance_app/
├── app/
│   ├── main.py                     # Entrypoint da CLI
│   ├── database.py                 # Conexão SQLite
│   ├── config.py                   # Caminhos e pastas
│   │
│   ├── models/                     # Entidades (Transaction)
│   ├── repositories/               # Acesso ao banco (único lugar com SQL)
│   ├── services/                   # Regras de negócio (compartilhadas)
│   │   ├── transaction_service.py
│   │   ├── report_service.py
│   │   ├── export_service.py
│   │   ├── chart_service.py
│   │   ├── ai_service.py           # 🤖 IA de categorização
│   │   └── financial_advisor_service.py  # 🧠 IA consultora (insights)
│   │
│   ├── constants/                  # Categorias, pagamentos, tipos, patterns
│   │   ├── categories.py
│   │   ├── payment_methods.py
│   │   ├── transaction_types.py
│   │   └── category_patterns.py    # 🤖 palavras-chave da IA
│   │
│   ├── interfaces/
│   │   ├── cli.py                  # Interface terminal
│   │   ├── prompts.py              # Helpers de input da CLI
│   │   └── streamlit_app.py        # Interface web (Plotly + IA)
│   │
│   └── utils/                      # date_utils, money_utils, normalizers, logger
│
├── .streamlit/
│   └── config.toml                 # 🎨 tema visual (cores)
│
├── data/                           # Criado em runtime
│   ├── database.db                 # Banco SQLite
│   ├── exports/                    # Excels exportados
│   └── charts/                     # Gráficos PNG
├── logs/                           # app.log
│
├── run_streamlit.py                # Launcher do Streamlit
├── requirements.txt
├── STUDY_GUIDE.md                  # 📚 cronograma de estudo
├── CHALLENGES.md                   # 🎯 desafios de prática
└── README.md
```

---

## 🤖 Como funciona a IA

Ao digitar a descrição de uma transação, a IA sugere a categoria automaticamente.

Ela trabalha em **duas camadas**:

1. **Palavras-chave (offline, grátis)** — reconhece termos como "mercado", "uber",
   "netflix" e sugere a categoria. Funciona sem internet, cobre a maioria dos casos.

2. **LLM / ChatGPT (opcional)** — se você configurar uma API key, casos que as
   palavras-chave não pegam são enviados para uma IA mais poderosa.

**Para usar só patterns (padrão):** não precisa fazer nada, já funciona.

**Para ativar o LLM:**
```bash
pip install openai
export OPENAI_API_KEY="sua-chave"     # Linux/Mac
set OPENAI_API_KEY=sua-chave           # Windows
streamlit run run_streamlit.py
```

A barra lateral mostra o status: `🤖 IA: patterns (offline)` ou `patterns + LLM ativo`.

---

## 🧠 Consultor IA (análise financeira)

Além de categorizar, o app tem um **consultor financeiro** que analisa seus dados
e gera conselhos automaticamente. Ele aparece no topo do **Dashboard**.

O consultor gera três tipos de insight:

- **🚨 Alertas** — avisa quando algo precisa de atenção (gastou mais do que ganhou,
  categoria muito acima da média dos meses anteriores)
- **💡 Conselhos de economia** — onde dá para cortar (assinaturas pesando, gastos
  concentrados numa categoria, dicas práticas)
- **📋 Resumo e análise** — visão geral do mês (taxa de poupança, maior despesa)

Como funciona (por dentro): o consultor usa **regras + estatística** sobre seu
histórico. Por exemplo, compara o gasto de cada categoria com a média dos 3 meses
anteriores e alerta se houver um estouro. **Tudo offline e privado** — seus dados
nunca saem do seu computador.

A arquitetura já está **preparada para LLM** (o método `_refine_with_llm` é um
gancho pronto), mas por padrão roda 100% offline.

---

## 🌐 Páginas do Streamlit

| Página | O que faz |
|---|---|
| **📊 Dashboard** | KPIs, comparativo receitas vs despesas, donuts de categoria e pagamento, maior despesa do mês |
| **➕ Adicionar** | Formulário com **sugestão de IA** em tempo real |
| **📋 Transações** | Lista com filtros: mês, tipo, categoria, pagamento + resumo do filtro |
| **📈 Relatórios** | Despesas por categoria com %, evolução de 6 meses (gráfico de linha) |
| **📥 Exportar** | Download direto de Excel + geração de gráfico PNG |

Todos os gráficos são **interativos** (Plotly): passe o mouse para ver valores.

---

## 🎨 Mudar as cores

Edite `.streamlit/config.toml` (cores do app) ou as constantes `COLOR_*` no topo de
`app/interfaces/streamlit_app.py` (cores dos gráficos). Salve e recarregue.

---

## 🗄️ Acessar o banco de dados

O banco fica em `data/database.db` (SQLite). Três formas de acessar:

```bash
# 1. Via terminal SQLite
sqlite3 data/database.db
sqlite> SELECT * FROM transactions;
sqlite> .quit

# 2. Visual: baixe o "DB Browser for SQLite" (gratuito) em sqlitebrowser.org

# 3. Pela própria CLI: python -m app.main → opção 3 (Listar)
```

---

## ❗ Erros comuns

| Erro | Solução |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Use `python -m app.main`, não `python app/main.py` |
| `ModuleNotFoundError: No module named 'plotly'` | `pip install -r requirements.txt` |
| `Port 8501 is already in use` | `streamlit run run_streamlit.py --server.port 8502` |
| Página em branco | Ctrl+Shift+R para recarregar |

---

## 🏛️ Princípio arquitetural

```
CLI ──┐
      ├─→ Services ──→ Repositories ──→ SQLite
Web ──┘     ↑
         IA Service
```

**Nenhum service, repository ou model muda** ao adicionar uma interface nova.
A interface só MOSTRA dados e CHAMA services. Por isso o projeto está pronto
para a Fase 3 (FastAPI + frontend HTML/CSS/React).

---

## 📈 Fases do projeto

- ✅ **Fase 1** — CLI + SQLite + relatórios + Excel + gráficos
- ✅ **Fase 2** — Streamlit (dashboard, filtros, exportação)
- ✅ **Fase 2.5** — Visual com Plotly + IA de categorização ← *você está aqui*
- 🔜 **Fase 3** — API REST (FastAPI) + frontend web
- 🔜 **Fase 4** — Importação CSV/OFX, Open Finance, mais IA
