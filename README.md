# 💸 Finance App

Sistema de **gestão financeira pessoal** em Python, com IA que age como um gestor financeiro. Um único núcleo de regras de negócio servindo **quatro interfaces**: API REST (FastAPI), frontend web (HTML/CSS/JS puro), CLI e Streamlit.

> Diferencia gasto na conta × cartão, entende compras parceladas (inclusive importadas da fatura), projeta o saldo do fim do mês e gera conselhos personalizados com IA.

---

## ✨ Principais recursos

- **Conta × cartão** — toda despesa tem origem clara (`account` ou `card`). Gasto no cartão não desconta do saldo na hora: entra na **fatura**.
- **Parcelamento** — compras parceladas viram N lançamentos nas faturas dos meses certos. O valor total é dividido e a diferença de centavos vai na última parcela.
- **Importação de extrato/fatura (CSV e OFX)** — pré-visualização com sugestão de categoria, detecção de **duplicatas** e de **parcelas** (“NETFLIX 03/12”), lançando as parcelas futuras automaticamente sem duplicar ao reimportar.
- **Faturas detalhadas** — fatura atual + **próximas faturas** do cartão, com os lançamentos de cada mês (incluindo parcelas futuras).
- **Previsão do mês** — saldo previsto = saldo atual + salário a receber − contas/faturas a pagar. Com modo “sem salário”.
- **IA gestora (Groq)** — score de saúde financeira (0–100) + conselhos **específicos e quantificados** (categorias que pesaram, variação vs média, carga de parcelas, onde cortar e quanto). Funciona offline com regras determinísticas quando não há chave.
- **IA de categorização** — sugere a categoria pela descrição (palavras-chave offline + LLM opcional via OpenAI).
- **Multi-contas, cartões, metas, alertas, salário (INSS/IRRF), recorrentes e vencimentos.**

---

## 🏗️ Arquitetura

Regra de ouro: **interfaces não contêm regra de negócio**. Tudo passa pelo núcleo compartilhado.

```
app/
├── api/            # FastAPI: routers + schemas (camada fina sobre os services)
├── services/       # REGRA DE NEGÓCIO (transações, cartões, IA, previsão, importação…)
├── repositories/   # ÚNICO lugar com SQL (SQLite)
├── models/         # Entidades do domínio (Transaction, Card, Goal…)
├── constants/      # Valores fixos (categorias, formas de pagamento, origens…)
├── utils/          # Auxiliares (datas, dinheiro, normalização, .env, logger)
└── interfaces/     # CLI e Streamlit
frontend/           # HTML/CSS/JS puro consumindo a API
```

Detalhes e convenções obrigatórias estão em [`AGENTS.md`](AGENTS.md).

**Stack:** Python 3.11+ · FastAPI · SQLite · HTML/CSS/JS puro · Groq (LLM, opcional) · sem dependências pesadas no core.

---

## 🚀 Como rodar

```bash
# 1. Ambiente virtual
python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # Linux/Mac

# 2. Dependências
pip install -r requirements.txt

# 3. (Opcional, Windows) UTF-8 no terminal
set PYTHONIOENCODING=utf-8
```

### API REST + frontend web (recomendado)

```bash
python run_api.py
# API em http://127.0.0.1:8000  (docs interativas em /docs)
```

Em outro terminal, sirva o frontend:

```bash
python -m http.server --directory frontend 8080
# Abra http://127.0.0.1:8080
```

### Outras interfaces

```bash
python -m app.main            # CLI
streamlit run run_streamlit.py  # Streamlit
```

---

## 🔑 Configuração da IA (`.env`)

A IA é **opcional** — sem chave, o app usa regras offline. Para ligar os conselhos personalizados:

1. Crie uma chave gratuita em **[console.groq.com](https://console.groq.com)** (começa com `gsk_`, ~56 caracteres).
2. Copie o `.env.example` para `.env` e preencha:

   ```env
   GROQ_API_KEY=gsk_sua_chave_completa_aqui
   ```
3. **Reinicie a API** (a chave é lida na inicialização).

Confira em `http://127.0.0.1:8000/ai/status` se `groq_configured` está `true`.

> A categorização por LLM (opcional) usa `OPENAI_API_KEY` — também no `.env`.
> O `.env` está no `.gitignore` e **nunca** é versionado.

---

## 🧪 Testes

```bash
python -m tests.test_installment_import
```

Cobre a detecção/importação de parcelas, edição de parcela (preservando o grupo), aviso de duplicata e o modo “sem salário”.

---

## 📂 Dados

O banco SQLite fica em `data/database.db` (criado automaticamente na primeira execução). **Não é versionado** — contém dados pessoais.

---

## 📄 Licença

Projeto pessoal/educacional. Sinta-se livre para estudar e adaptar.
