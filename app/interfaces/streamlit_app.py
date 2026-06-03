"""
Interface Streamlit do Finance App — Fase 2.5 (visual melhorado + IA).

═══════════════════════════════════════════════════════════════════
⭐ MAPA DO ARQUIVO (para você se localizar ao estudar)
═══════════════════════════════════════════════════════════════════
Este arquivo é dividido em seções marcadas com "====". Na ordem:

  1. IMPORTS + CONFIG       → bibliotecas e configuração da página
  2. CSS CUSTOMIZADO        → estilos visuais extras (cards bonitos)
  3. INIT                   → inicializa services no session_state
  4. HELPERS VISUAIS        → funções que montam cards e gráficos Plotly
  5. PÁGINA: Dashboard      → visão geral com KPIs e gráficos
  6. PÁGINA: Adicionar      → formulário COM sugestão de IA
  7. PÁGINA: Transações     → listagem com filtros
  8. PÁGINA: Relatórios     → análises e evolução mensal
  9. PÁGINA: Exportar       → download de Excel e gráficos
  10. NAVEGAÇÃO             → o menu que liga tudo

PRINCÍPIO QUE NÃO MUDA: este arquivo só MOSTRA coisas e CHAMA services.
Nenhum cálculo de saldo, nenhum SQL. A regra de negócio fica nos services.
═══════════════════════════════════════════════════════════════════
"""

# ============================================================
# 1. IMPORTS + CONFIG
# ============================================================

import io
from collections import Counter
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.constants.categories import OTHER_LABEL, categories_for_type
from app.constants.payment_methods import PAYMENT_METHODS
from app.constants.transaction_types import TYPE_EXPENSE, TYPE_INCOME
from app.database import initialize_database
from app.services.ai_service import AIService
from app.services.chart_service import ChartService
from app.services.financial_advisor_service import (
    SEVERITY_DANGER,
    SEVERITY_INFO,
    SEVERITY_SUCCESS,
    SEVERITY_WARNING,
    SOURCE_LLM,
    FinancialAdvisorService,
)
from app.services.export_service import ExportService
from app.services.report_service import ReportService
from app.services.transaction_service import TransactionService
from app.utils.date_utils import format_iso, format_user, parse_iso_date
from app.utils.logger import get_logger
from app.utils.money_utils import format_brl

logger = get_logger(__name__)

# Paleta de cores (centralizada para reuso nos gráficos).
# Mudou aqui, mudou em todos os gráficos.
COLOR_INCOME = "#10B981"   # verde (receita)
COLOR_EXPENSE = "#EF4444"  # vermelho (despesa)
COLOR_BALANCE = "#3B82F6"  # azul (saldo)
COLOR_PALETTE = px.colors.qualitative.Set2  # paleta para categorias

# set_page_config DEVE ser a primeira chamada Streamlit do app.
st.set_page_config(
    page_title="Finance App",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 2. CSS CUSTOMIZADO
# ============================================================
# O Streamlit permite injetar CSS para refinar o visual além do tema.
# Aqui criamos "cards" com borda, sombra e cantos arredondados.
# COMO ESTUDAR: comente este bloco inteiro e veja como o app fica "cru".

def inject_css() -> None:
    """Injeta CSS customizado para deixar o visual mais polido."""
    st.markdown(
        """
        <style>
        /* Cartoes de metrica com fundo e borda suaves */
        div[data-testid="stMetric"] {
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }
        /* Rotulo da metrica um pouco mais claro */
        div[data-testid="stMetricLabel"] {
            color: #94A3B8;
            font-weight: 600;
        }
        /* Titulo das paginas com peso maior */
        h1 {
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        /* Remove o menu hamburguer e o rodape "Made with Streamlit" */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,  # necessario para injetar HTML/CSS.
    )


# ============================================================
# 3. INIT
# ============================================================

def init_app() -> None:
    """Cria tabelas e inicializa services no session_state.

    session_state = memoria que sobrevive entre as re-execucoes do script.
    Streamlit roda o arquivo inteiro a cada clique; sem session_state,
    criariamos novos services toda vez.
    """
    initialize_database()

    if "services_initialized" not in st.session_state:
        st.session_state.transaction_service = TransactionService()
        st.session_state.report_service = ReportService()
        st.session_state.export_service = ExportService()
        st.session_state.chart_service = ChartService()
        # use_llm=True: usa IA externa SE houver API key; senao, so patterns.
        st.session_state.ai_service = AIService(use_llm=True)
        # Consultor financeiro: gera insights por regras e, com use_llm=True,
        # acrescenta um conselho personalizado via Ollama local. Se o Ollama
        # estiver fora do ar, cai no fallback e mostra só os insights por regra.
        st.session_state.advisor_service = FinancialAdvisorService(
            report_service=st.session_state.report_service,
            use_llm=True,
        )
        st.session_state.services_initialized = True


# ============================================================
# 4. HELPERS VISUAIS
# ============================================================

def month_year_picker(label_prefix: str = "") -> tuple[int, int]:
    """Seletores de ano e mes lado a lado. Devolve (ano, mes).

    Centralizado para nao repetir o mesmo codigo em cada pagina.
    O label_prefix + key evitam conflito quando ha varios na mesma tela.
    """
    today = date.today()
    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input(
            f"Ano{' ' + label_prefix if label_prefix else ''}",
            value=today.year, min_value=2000, max_value=2100, step=1,
            key=f"year_{label_prefix}",
        )
    with col2:
        month_names = [
            "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
        ]
        month = st.selectbox(
            f"Mes{' ' + label_prefix if label_prefix else ''}",
            options=range(1, 13), index=today.month - 1,
            format_func=lambda i: month_names[i - 1],
            key=f"month_{label_prefix}",
        )
    return int(year), int(month)


def transactions_to_dataframe(transactions) -> pd.DataFrame:
    """Converte lista de Transaction em DataFrame formatado para exibir."""
    if not transactions:
        return pd.DataFrame()
    return pd.DataFrame([
        {
            "ID": t.id,
            "Data": format_user(parse_iso_date(t.date)),
            "Tipo": t.type.capitalize(),
            "Categoria": t.category,
            "Valor": format_brl(t.amount),
            "Descricao": t.description,
            "Pagamento": t.payment_method,
        }
        for t in transactions
    ])


def donut_chart(data: dict, title: str, color_sequence=None) -> go.Figure:
    """Cria um grafico de rosca (donut) interativo com Plotly.

    Recebe um dicionario {rotulo: valor} e devolve uma figura Plotly.
    Donut e melhor que pizza para comparar proporcoes e fica moderno.
    """
    labels = list(data.keys())
    values = list(data.values())

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.55,  # tamanho do buraco central (0=pizza, 1=anel fino).
        marker=dict(colors=color_sequence or COLOR_PALETTE),
        textinfo="percent",
        hovertemplate="%{label}<br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
    )])
    fig.update_layout(
        title=title,
        showlegend=True,
        height=350,
        margin=dict(t=50, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",  # fundo transparente.
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F1F5F9"),
    )
    return fig


def bar_chart_horizontal(data: dict, title: str, color: str) -> go.Figure:
    """Cria um grafico de barras horizontais interativo (maior no topo)."""
    # Ordena do maior para o menor.
    sorted_items = sorted(data.items(), key=lambda x: x[1])
    labels = [item[0] for item in sorted_items]
    values = [item[1] for item in sorted_items]

    fig = go.Figure(data=[go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker=dict(color=color),
        hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>",
        text=[format_brl(v) for v in values],
        textposition="auto",
    )])
    fig.update_layout(
        title=title,
        height=max(300, len(labels) * 45),
        margin=dict(t=50, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F1F5F9"),
        xaxis=dict(gridcolor="#334155"),
    )
    return fig


def income_vs_expense_chart(incomes: float, expenses: float) -> go.Figure:
    """Grafico de barras comparando receitas e despesas."""
    fig = go.Figure(data=[go.Bar(
        x=["Receitas", "Despesas"],
        y=[incomes, expenses],
        marker=dict(color=[COLOR_INCOME, COLOR_EXPENSE]),
        text=[format_brl(incomes), format_brl(expenses)],
        textposition="auto",
        hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
    )])
    fig.update_layout(
        height=350,
        margin=dict(t=20, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F1F5F9"),
        yaxis=dict(gridcolor="#334155"),
    )
    return fig


def evolution_line_chart(df: pd.DataFrame) -> go.Figure:
    """Grafico de linha da evolucao mensal (receitas, despesas, saldo)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Receitas"], name="Receitas",
        line=dict(color=COLOR_INCOME, width=3), mode="lines+markers",
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Despesas"], name="Despesas",
        line=dict(color=COLOR_EXPENSE, width=3), mode="lines+markers",
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Saldo"], name="Saldo",
        line=dict(color=COLOR_BALANCE, width=3, dash="dot"), mode="lines+markers",
    ))
    fig.update_layout(
        height=400,
        margin=dict(t=20, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F1F5F9"),
        xaxis=dict(gridcolor="#334155"),
        yaxis=dict(gridcolor="#334155"),
        legend=dict(orientation="h", y=1.1),
        hovermode="x unified",
    )
    return fig


def build_monthly_evolution(year: int, month: int, months_back: int = 6) -> pd.DataFrame:
    """Monta DataFrame com receitas/despesas/saldo dos ultimos N meses.

    Volta no tempo a partir do mes escolhido e consulta o ReportService
    para cada mes. Zero SQL aqui — tudo via service.
    """
    rs = st.session_state.report_service
    rows = []
    for i in range(months_back - 1, -1, -1):
        m, y = month - i, year
        while m <= 0:  # corrige quando "volta" para o ano anterior.
            m += 12
            y -= 1
        s = rs.monthly_summary(y, m)
        rows.append({
            "Mes": f"{m:02d}/{y}",
            "Receitas": s["total_incomes"],
            "Despesas": s["total_expenses"],
            "Saldo": s["balance"],
        })
    return pd.DataFrame(rows).set_index("Mes")


def render_insights(insights) -> None:
    """Mostra a lista de insights do consultor financeiro.

    Cada insight vira um "alerta" colorido do Streamlit conforme a
    severidade. Agrupamos por categoria (resumo, alerta, economia) para
    organizar visualmente.

    Mapeamos a severidade para a funcao certa do Streamlit:
      success → st.success (verde)
      info    → st.info    (azul)
      warning → st.warning (amarelo)
      danger  → st.error   (vermelho)

    Conselhos vindos do LLM (Groq) ganham um badge "🤖 [LLM]" no titulo para
    o usuario distinguir o que foi gerado por IA do que veio das regras locais
    (offline). Os insights das regras NAO recebem badge.
    """
    # Funcao do Streamlit para cada severidade.
    render_by_severity = {
        SEVERITY_SUCCESS: st.success,
        SEVERITY_INFO: st.info,
        SEVERITY_WARNING: st.warning,
        SEVERITY_DANGER: st.error,
    }

    # Titulo amigavel de cada grupo.
    group_titles = {
        "alerta": "🚨 Alertas",
        "economia": "💡 Conselhos de economia",
        "resumo": "📋 Resumo e análise",
    }

    # Ordem de exibicao dos grupos (alertas primeiro, por urgencia).
    group_order = ["alerta", "economia", "resumo"]

    for group in group_order:
        group_insights = [i for i in insights if i.category == group]
        if not group_insights:
            continue

        st.markdown(f"#### {group_titles[group]}")
        for ins in group_insights:
            render_fn = render_by_severity.get(ins.severity, st.info)
            # Badge so para conselhos do LLM; regras locais ficam sem marca.
            badge = "🤖 `[LLM]` " if ins.source == SOURCE_LLM else ""
            render_fn(f"{badge}**{ins.title}**  \n{ins.message}")


# ============================================================
# 5. PÁGINA: Dashboard
# ============================================================

def page_dashboard() -> None:
    """Visao geral: KPIs + comparativo + graficos do mes."""
    st.title("📊 Dashboard")

    with st.sidebar:
        st.subheader("Periodo")
        year, month = month_year_picker()

    summary = st.session_state.report_service.monthly_summary(year, month)

    # ---- KPIs ----
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Receitas", format_brl(summary["total_incomes"]))
    col2.metric("💸 Despesas", format_brl(summary["total_expenses"]))

    balance = summary["balance"]
    col3.metric(
        "💵 Saldo", format_brl(balance),
        delta="positivo" if balance >= 0 else "negativo",
        delta_color="normal" if balance >= 0 else "inverse",
    )
    col4.metric("📝 Transacoes", summary["count"])

    # Card extra: maior despesa do mes (destaque util).
    expenses = [t for t in summary["transactions"] if t.type == TYPE_EXPENSE]
    if expenses:
        biggest = max(expenses, key=lambda t: t.amount)
        st.caption(
            f"🔺 Maior despesa do mes: **{biggest.description}** "
            f"({format_brl(biggest.amount)} em {biggest.category})"
        )

    st.divider()

    if summary["count"] == 0:
        st.info("📭 Nenhuma transacao neste mes. Adicione transacoes para ver os graficos.")
        return

    # ---- Seção do Consultor IA ----
    # Fica em um expander aberto por padrão para dar destaque sem ocupar
    # a tela inteira. O usuário pode recolher se quiser.
    with st.expander("🤖 **Consultor IA** — análise e conselhos do mês", expanded=True):
        insights = st.session_state.advisor_service.generate_insights(year, month)
        render_insights(insights)
        # Legenda das origens. Mostramos a nota sobre o LLM apenas quando algum
        # conselho realmente veio da Groq, para nao confundir quando esta offline.
        used_llm = any(i.source == SOURCE_LLM for i in insights)
        if used_llm:
            st.caption(
                "💡 Conselhos sem marca vêm das regras locais (offline, privado). "
                "Os marcados com 🤖 `[LLM]` foram gerados pela IA (Groq) a partir "
                "dos seus dados."
            )
        else:
            st.caption(
                "💡 Análise gerada automaticamente a partir dos seus dados "
                "(offline, sem enviar informações para fora)."
            )

    st.divider()

    # ---- Linha 1 de graficos: comparativo + donut de categorias ----
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Receitas vs Despesas")
        fig = income_vs_expense_chart(
            summary["total_incomes"], summary["total_expenses"]
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_b:
        st.subheader("Distribuicao de gastos")
        if summary["expenses_by_category"]:
            fig = donut_chart(summary["expenses_by_category"], "")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.info("Sem despesas neste mes.")

    # ---- Linha 2 de graficos: barras de categoria + pagamento ----
    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Gastos por categoria")
        if summary["expenses_by_category"]:
            fig = bar_chart_horizontal(
                summary["expenses_by_category"], "", COLOR_EXPENSE
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.info("Sem despesas neste mes.")

    with col_d:
        st.subheader("Formas de pagamento")
        payment_counts = Counter(
            t.payment_method for t in summary["transactions"]
            if t.type == TYPE_EXPENSE
        )
        if payment_counts:
            fig = donut_chart(
                dict(payment_counts), "", px.colors.qualitative.Pastel
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.info("Sem despesas neste mes.")

    st.divider()

    # ---- Tabela ----
    st.subheader("Transacoes do mes")
    df = transactions_to_dataframe(summary["transactions"])
    st.dataframe(df, width="stretch", hide_index=True)


# ============================================================
# 6. PÁGINA: Adicionar (com sugestão de IA)
# ============================================================

def page_add_transaction() -> None:
    """Formulario de cadastro COM sugestao automatica de categoria via IA."""
    st.title("➕ Adicionar transacao")

    # Tipo fica FORA do form para o resto reagir a escolha.
    transaction_type = st.radio(
        "Tipo",
        options=[TYPE_INCOME, TYPE_EXPENSE],
        format_func=lambda x: "💰 Receita" if x == TYPE_INCOME else "💸 Despesa",
        horizontal=True,
    )

    # ---- Descricao + sugestao de IA ----
    # Por que fora de st.form? Porque dentro de form, widgets so disparam
    # acao no submit. Queremos a sugestao ANTES de salvar, enquanto digita.
    description = st.text_input(
        "Descricao*",
        placeholder="Ex: Mercado Extra, Uber, Salario",
        key="add_description",
    )

    suggested_category = None
    if description.strip():
        suggested_category, confidence = st.session_state.ai_service.suggest_category(
            description, transaction_type
        )
        if suggested_category:
            st.success(
                f"🤖 **IA sugere:** {suggested_category}  "
                f"_(confianca: {confidence:.0%})_  — "
                f"ja deixei selecionado abaixo, mas voce pode trocar."
            )
        else:
            st.caption("🤖 IA: nao reconheci um padrao — escolha a categoria manualmente.")

    # ---- Demais campos ----
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input(
            "Valor (R$)*", min_value=0.0, step=0.01, format="%.2f",
            key="add_amount",
        )
    with col2:
        transaction_date = st.date_input(
            "Data*", value=date.today(), format="DD/MM/YYYY", key="add_date",
        )

    col3, col4 = st.columns(2)
    with col3:
        categories = categories_for_type(transaction_type)
        # Se a IA sugeriu uma categoria valida, pre-seleciona ela.
        default_index = 0
        if suggested_category and suggested_category in categories:
            default_index = categories.index(suggested_category)
        chosen_category = st.selectbox(
            "Categoria*", options=categories, index=default_index,
            key="add_category",
        )
        custom_category = ""
        if chosen_category == OTHER_LABEL:
            custom_category = st.text_input(
                "Categoria personalizada*", key="add_custom_category",
            )
    with col4:
        chosen_payment = st.selectbox(
            "Forma de pagamento*", options=PAYMENT_METHODS, key="add_payment",
        )

    st.divider()

    # ---- Botao salvar ----
    if st.button("💾 Salvar transacao", type="primary"):
        final_category = (
            custom_category if chosen_category == OTHER_LABEL else chosen_category
        )

        # Validacoes de interface (campos vazios).
        if not description.strip():
            st.error("⚠ Descricao nao pode ser vazia.")
            return
        if amount <= 0:
            st.error("⚠ Valor deve ser maior que zero.")
            return
        if not final_category.strip():
            st.error("⚠ Categoria nao pode ser vazia.")
            return

        # Validacao de dominio fica no service (try/except).
        try:
            transaction = st.session_state.transaction_service.add_transaction(
                date=format_iso(transaction_date),
                description=description,
                amount=amount,
                type_=transaction_type,
                category=final_category,
                payment_method=chosen_payment,
            )
            tipo = "Receita" if transaction_type == TYPE_INCOME else "Despesa"
            st.success(
                f"✓ {tipo} salva! ID {transaction.id} | "
                f"{format_brl(transaction.amount)} | {transaction.category}"
            )
            st.balloons()  # animacao divertida de sucesso.
        except ValueError as e:
            st.error(f"⚠ {e}")
        except Exception as e:
            st.error(f"❌ Erro inesperado: {e}")
            logger.exception("Erro ao adicionar via Streamlit")


# ============================================================
# 7. PÁGINA: Transações (listagem com filtros)
# ============================================================

def page_list_all() -> None:
    """Listagem com filtros por mes, tipo, categoria e forma de pagamento."""
    st.title("📋 Transacoes")

    transactions = st.session_state.transaction_service.list_all()
    if not transactions:
        st.info("Nenhuma transacao cadastrada. Va em '➕ Adicionar transacao'.")
        return

    # ---- Filtros na sidebar ----
    with st.sidebar:
        st.subheader("Filtros")
        use_month_filter = st.checkbox("Filtrar por mes")
        filter_year, filter_month = None, None
        if use_month_filter:
            filter_year, filter_month = month_year_picker("(filtro)")

        filter_types = st.multiselect(
            "Tipo", options=[TYPE_INCOME, TYPE_EXPENSE],
            default=[TYPE_INCOME, TYPE_EXPENSE],
            format_func=lambda x: "Receita" if x == TYPE_INCOME else "Despesa",
        )
        existing_categories = sorted({t.category for t in transactions})
        filter_categories = st.multiselect("Categoria", options=existing_categories)
        existing_payments = sorted({t.payment_method for t in transactions})
        filter_payments = st.multiselect("Forma de pagamento", options=existing_payments)

    # ---- Aplica filtros ----
    if use_month_filter:
        filtered = st.session_state.transaction_service.list_by_month(
            filter_year, filter_month
        )
    else:
        filtered = transactions

    if not filter_types:
        st.warning("⚠ Marque ao menos um tipo na sidebar.")
        return

    filtered = [t for t in filtered if t.type in filter_types]
    if filter_categories:
        filtered = [t for t in filtered if t.category in filter_categories]
    if filter_payments:
        filtered = [t for t in filtered if t.payment_method in filter_payments]

    # ---- Resumo do filtro ----
    st.subheader(f"Resultados ({len(filtered)} de {len(transactions)})")
    if not filtered:
        st.info("Nenhuma transacao corresponde aos filtros.")
        return

    rs = st.session_state.report_service
    col1, col2, col3 = st.columns(3)
    col1.metric("Receitas", format_brl(rs.total_incomes(filtered)))
    col2.metric("Despesas", format_brl(rs.total_expenses(filtered)))
    col3.metric("Saldo", format_brl(rs.balance(filtered)))

    df = transactions_to_dataframe(filtered)
    st.dataframe(df, width="stretch", hide_index=True)


# ============================================================
# 8. PÁGINA: Relatórios
# ============================================================

def page_reports() -> None:
    """Analises por periodo + evolucao dos ultimos meses."""
    st.title("📈 Relatorios")

    st.subheader("Periodo")
    year, month = month_year_picker("(periodo)")

    summary = st.session_state.report_service.monthly_summary(year, month)

    st.divider()
    st.subheader(f"Resumo de {month:02d}/{year}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Receitas", format_brl(summary["total_incomes"]))
    col2.metric("Despesas", format_brl(summary["total_expenses"]))
    col3.metric("Saldo", format_brl(summary["balance"]))
    col4.metric("Transacoes", summary["count"])

    if summary["count"] == 0:
        st.info("Sem transacoes neste periodo.")
        return

    st.divider()

    # Detalhamento por categoria com %.
    if summary["expenses_by_category"]:
        st.subheader("Despesas por categoria")
        col_a, col_b = st.columns([3, 2])
        with col_a:
            fig = bar_chart_horizontal(summary["expenses_by_category"], "", COLOR_EXPENSE)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        with col_b:
            total = summary["total_expenses"]
            rows = [
                {
                    "Categoria": cat,
                    "Total": format_brl(val),
                    "%": f"{val / total * 100:.1f}%",
                }
                for cat, val in summary["expenses_by_category"].items()
            ]
            st.dataframe(rows, width="stretch", hide_index=True)

    st.divider()

    # Evolucao mensal.
    st.subheader("Evolucao dos ultimos 6 meses")
    evolution = build_monthly_evolution(year, month)
    if not evolution.empty:
        fig = evolution_line_chart(evolution)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        st.info("Sem dados para evolucao.")


# ============================================================
# 9. PÁGINA: Exportar
# ============================================================

def page_export() -> None:
    """Download de Excel e geracao de grafico PNG."""
    st.title("📥 Exportar dados")

    transactions = st.session_state.transaction_service.list_all()
    if not transactions:
        st.warning("Nenhuma transacao cadastrada ainda.")
        return

    # ---- Excel (download direto) ----
    st.subheader("📊 Exportar para Excel")
    st.write(f"Transacoes disponiveis: **{len(transactions)}**")

    excel_bytes = _generate_excel_bytes(transactions)
    st.download_button(
        label="⬇ Baixar Excel",
        data=excel_bytes,
        file_name=f"transacoes_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    if st.button("💾 Salvar Excel em data/exports/"):
        try:
            path = st.session_state.export_service.export_to_excel(transactions)
            st.success(f"✓ Salvo em: `{path}`")
        except Exception as e:
            st.error(f"Erro: {e}")

    st.divider()

    # ---- Grafico ----
    st.subheader("📈 Gerar grafico de gastos")
    year, month = month_year_picker("(grafico)")
    summary = st.session_state.report_service.monthly_summary(year, month)

    if not summary["expenses_by_category"]:
        st.info("Sem despesas neste mes para gerar grafico.")
        return

    fig = bar_chart_horizontal(summary["expenses_by_category"], "Previa", COLOR_EXPENSE)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    if st.button("💾 Salvar grafico PNG em data/charts/"):
        try:
            path = st.session_state.chart_service.expenses_by_category_chart(
                summary["expenses_by_category"]
            )
            st.success(f"✓ Salvo em: `{path}`")
            st.image(str(path), caption="Grafico gerado")
        except Exception as e:
            st.error(f"Erro: {e}")


def _generate_excel_bytes(transactions) -> bytes:
    """Gera Excel em memoria (BytesIO) para o download_button.

    O ExportService salva em disco (para a CLI). O navegador precisa de
    bytes em memoria. Pequena duplicacao justificada pela UX do download.
    """
    df = pd.DataFrame([
        {
            "ID": t.id, "Data": t.date, "Descricao": t.description,
            "Valor": t.amount, "Tipo": t.type, "Categoria": t.category,
            "Pagamento": t.payment_method, "Criado em": t.created_at,
        }
        for t in transactions
    ])
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# 10. NAVEGAÇÃO
# ============================================================

def main() -> None:
    """Ponto de entrada: monta o menu e chama a pagina escolhida."""
    init_app()
    inject_css()

    with st.sidebar:
        st.title("💰 Finance App")
        st.divider()
        page = st.radio(
            "Navegacao",
            options=[
                "📊 Dashboard",
                "➕ Adicionar transacao",
                "📋 Transacoes",
                "📈 Relatorios",
                "📥 Exportar",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        # Indicador de status da IA.
        if st.session_state.ai_service._llm_available():
            st.caption("🤖 IA: patterns + LLM ativo")
        else:
            st.caption("🤖 IA: patterns (offline)")

    # Dispatcher: liga o nome da pagina a funcao correspondente.
    pages = {
        "📊 Dashboard": page_dashboard,
        "➕ Adicionar transacao": page_add_transaction,
        "📋 Transacoes": page_list_all,
        "📈 Relatorios": page_reports,
        "📥 Exportar": page_export,
    }
    pages[page]()


if __name__ == "__main__":
    main()
