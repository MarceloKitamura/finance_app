"""
Service de consultoria financeira (IA que analisa e aconselha).

═══════════════════════════════════════════════════════════════════
⭐ COMO ESTE SERVICE FUNCIONA (leia antes de estudar o código)
═══════════════════════════════════════════════════════════════════
Enquanto o ai_service.py categoriza UMA transação, este service olha
o PANORAMA: todo o histórico de gastos e gera "insights" — alertas,
conselhos de economia e um resumo do mês.

A ideia central é uma LISTA DE REGRAS. Cada regra é um método que:
  1. recebe um "contexto" (dados já calculados do mês + histórico);
  2. decide se tem algo a dizer;
  3. se sim, devolve um Insight; se não, devolve None.

O método principal (generate_insights) roda todas as regras e junta
os insights que "dispararam". Isso deixa MUITO fácil adicionar uma
regra nova: basta escrever um método e adicioná-lo à lista.

Por que regras em vez de IA externa (ChatGPT)?
- Funciona offline, de graça e instantâneo.
- Não manda seus dados financeiros para fora (privacidade).
- É PREVISÍVEL: você sabe exatamente por que cada conselho apareceu.

REFINO COM LLM (opcional): se o service for criado com use_llm=True e
houver uma GROQ_API_KEY configurada (no .env), o método _refine_with_llm()
manda um resumo dos dados para a Groq e ACRESCENTA um insight com um conselho
personalizado em linguagem natural. As regras determinísticas continuam
valendo — o LLM só soma um conselho a mais. Se não houver chave ou a API
falhar, tudo segue funcionando normalmente (o conselho extra é só pulado).
═══════════════════════════════════════════════════════════════════
"""

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from app.constants.transaction_types import TYPE_EXPENSE
from app.repositories.transaction_repository import TransactionRepository
from app.services.report_service import ReportService
from app.utils.env import load_env_file
from app.utils.logger import get_logger
from app.utils.money_utils import format_brl

logger = get_logger(__name__)


# ───────────────────────────────────────────────────────────
# Carregamento do .env (sem dependências externas)
# ───────────────────────────────────────────────────────────
# A GROQ_API_KEY fica no .env na raiz. Carregamos via util central (idempotente
# e compartilhado com o ai_service), ANTES de ler as constantes abaixo, para que
# os.getenv enxergue a chave independentemente da ordem de import.
load_env_file()


# ───────────────────────────────────────────────────────────
# Configuração da Groq (LLM via API)
# ───────────────────────────────────────────────────────────
# A Groq (https://groq.com) expõe uma API compatível com a da OpenAI e
# roda modelos abertos com baixa latência. Para usar:
#   1. Crie uma chave em https://console.groq.com e coloque no .env:
#        GROQ_API_KEY=gsk_...
#   2. Crie o service com use_llm=True.
#
# Modelo e timeout podem ser trocados por variáveis de ambiente:
#   set GROQ_MODEL=llama-3.3-70b-versatile   (Windows)
#   set GROQ_TIMEOUT=30
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = os.getenv(
    "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
)
# Timeout em segundos para a chamada ao modelo (a geração pode demorar um pouco).
GROQ_TIMEOUT = float(os.getenv("GROQ_TIMEOUT", "30"))


# ───────────────────────────────────────────────────────────
# Tipos de dados
# ───────────────────────────────────────────────────────────

# Severidade do insight, controla a cor/ícone na interface.
SEVERITY_SUCCESS = "success"  # algo bom (verde)
SEVERITY_INFO = "info"        # neutro/informativo (azul)
SEVERITY_WARNING = "warning"  # atenção (amarelo)
SEVERITY_DANGER = "danger"    # alerta sério (vermelho)

# Origem do insight, para a interface deixar claro quem o gerou.
SOURCE_RULES = "rules"  # regras determinísticas locais (offline, privado)
SOURCE_LLM = "llm"      # gerado pelo LLM (Groq) a partir dos dados


@dataclass
class Insight:
    """Um conselho/alerta gerado pela análise.

    Campos:
        category: "alerta", "economia" ou "resumo" (agrupa na tela).
        severity: uma das constantes SEVERITY_* (cor/ícone).
        title: título curto (ex: "Gasto acima da média").
        message: texto explicativo para o usuário.
        source: SOURCE_RULES (regras offline) ou SOURCE_LLM (Groq). O padrão
            é SOURCE_RULES, então toda regra determinística já vem marcada como
            offline sem precisar passar nada — só o conselho do LLM sobrescreve.
    """
    category: str
    severity: str
    title: str
    message: str
    source: str = SOURCE_RULES


@dataclass
class AnalysisContext:
    """Dados pré-calculados que as regras usam.

    Calcular tudo UMA vez aqui (e passar pronto para as regras) evita
    que cada regra recalcule as mesmas coisas. As regras só leem.
    """
    year: int
    month: int
    total_incomes: float
    total_expenses: float
    balance: float
    expenses_by_category: dict        # {categoria: total} do mês atual
    transactions: list                # transações do mês atual
    category_averages: dict           # {categoria: média dos meses anteriores}
    months_of_history: int            # quantos meses anteriores foram considerados


class FinancialAdvisorService:
    """Analisa as finanças e gera insights (alertas, dicas, resumo)."""

    def __init__(
        self,
        report_service: ReportService | None = None,
        repository: TransactionRepository | None = None,
        use_llm: bool = False,
        goal_service=None,
        forecast_service=None,
    ):
        self.report_service = report_service or ReportService()
        self.repository = repository or TransactionRepository()
        # use_llm=True liga o conselho personalizado via Groq.
        # Sem GROQ_API_KEY, é ignorado sem quebrar nada.
        self.use_llm = use_llm
        # GoalService entra no score (progresso de metas). Import tardio para
        # evitar ciclo de import (goal_service -> report_service -> ...).
        if goal_service is None:
            from app.services.goal_service import GoalService
            goal_service = GoalService(report_service=self.report_service)
        self.goal_service = goal_service
        # ForecastService dá à IA a previsão DETERMINÍSTICA de fim de mês
        # (saldo previsto, quanto falta receber/pagar). Opcional: se None, a
        # análise segue sem esses números (compatível com o comportamento antigo).
        self.forecast_service = forecast_service
        # Cache do score por (ano, mês). Guarda (contagem_de_transações, resultado):
        # se a contagem do mês não mudou, devolvemos o cache e NÃO rechamamos a Groq.
        self._score_cache: dict[tuple[int, int], tuple[int, dict]] = {}

    # ═══════════════════════════════════════════════════════
    # MÉTODO PRINCIPAL (o que o Dashboard chama)
    # ═══════════════════════════════════════════════════════

    def generate_insights(self, year: int, month: int) -> list[Insight]:
        """Gera todos os insights para o mês informado.

        Passos:
          1. Monta o contexto (calcula tudo uma vez).
          2. Roda cada regra da lista.
          3. Junta os insights que dispararam.
          4. (Futuro) Refina com LLM se ativado.
        """
        context = self._build_context(year, month)

        # Se não há nenhuma transação, retorna um único insight neutro.
        if context.total_incomes == 0 and context.total_expenses == 0:
            return [Insight(
                category="resumo",
                severity=SEVERITY_INFO,
                title="Sem dados ainda",
                message=(
                    "Não há transações neste mês. Cadastre receitas e despesas "
                    "para receber análises e conselhos personalizados."
                ),
            )]

        # Lista de regras. Para adicionar uma nova análise, escreva um
        # método _rule_xxx e inclua-o aqui.
        rules: list[Callable[[AnalysisContext], Optional[Insight]]] = [
            self._rule_savings_rate,
            self._rule_balance_negative,
            self._rule_category_above_average,
            self._rule_biggest_expense,
            self._rule_subscriptions_weight,
            self._rule_expense_concentration,
            self._rule_top_category_tip,
        ]

        insights: list[Insight] = []
        for rule in rules:
            try:
                result = rule(context)
                if result is not None:
                    insights.append(result)
            except Exception:
                # Uma regra com bug não pode derrubar as outras.
                logger.exception("Erro ao executar regra %s", rule.__name__)

        # Sempre adiciona um resumo geral no topo.
        insights.insert(0, self._build_summary(context))

        # Gancho para o futuro (hoje devolve igual).
        if self.use_llm:
            insights = self._refine_with_llm(insights, context)

        return insights

    # ═══════════════════════════════════════════════════════
    # IA GESTORA: SCORE DE SAÚDE + PREVISÃO (Fase 3)
    # ═══════════════════════════════════════════════════════

    def health_score(self, year: int, month: int) -> dict:
        """Calcula o Score de Saúde Financeira (0-100) do mês + previsão.

        O score é DETERMINÍSTICO: média ponderada de 5 sub-métricas (cada uma
        0-100). Quando há GROQ_API_KEY e use_llm, acrescentamos UMA
        interpretação em linguagem natural — mas o número nunca depende da IA.

        Resultado é cacheado por (ano, mês) e só recalcula se a quantidade de
        transações do mês mudar (evita rechamar a Groq à toa).
        """
        summary = self.report_service.monthly_summary(year, month)
        count = summary["count"]

        # Contexto da previsão determinística (saldo previsto, falta receber/
        # pagar). Pode ser None se nenhum ForecastService foi injetado.
        fin_ctx = self._forecast_ai_context(year, month)
        # A assinatura entra na chave do cache: se o salário/previsão mudar
        # (mesmo sem mudar a contagem de transações), o conselho é recalculado.
        sig = (count, fin_ctx.get("signature") if fin_ctx else None)

        cached = self._score_cache.get((year, month))
        if cached and cached[0] == sig:
            return cached[1]

        breakdown = self._score_breakdown(year, month, summary)
        score = round(sum(b["score"] * b["weight"] for b in breakdown.values()) / 100)
        faixa = self._faixa(score)
        forecast = self._forecast_block(year, month, summary, fin_ctx)

        # Groq-first: quando há chave, a IA escreve a análise inteira (resumo,
        # insights e recomendações). Sem chave/erro, caímos nas regras locais.
        llm_used = False
        insights: list[Insight] = []
        if self.use_llm and self._groq_available() and count > 0:
            llm_insights = self._llm_analysis(year, month, score, faixa, breakdown, forecast, summary, fin_ctx)
            if llm_insights:
                insights = llm_insights
                llm_used = True
        if not insights:
            insights = self._score_insights(score, faixa, breakdown, forecast, summary, fin_ctx)

        result = {
            "year": year,
            "month": month,
            "score": score,
            "faixa": faixa,
            "breakdown": breakdown,
            "forecast": forecast,
            "insights": [self._insight_to_dict(i) for i in insights],
            "llm_used": llm_used,
        }
        self._score_cache[(year, month)] = (sig, result)
        return result

    def _forecast_ai_context(self, year: int, month: int) -> Optional[dict]:
        """Monta o contexto da previsão determinística para a IA.

        Devolve None se nenhum ForecastService foi injetado (mantém o
        comportamento antigo). Tolerante a falhas: qualquer erro na previsão
        não pode derrubar o score/conselho.
        """
        if self.forecast_service is None:
            return None
        try:
            ctx = self.forecast_service.ai_context(year, month)
            ctx["signature"] = self.forecast_service.signature(year, month)
            return ctx
        except Exception:
            logger.exception("Falha ao montar contexto de previsão (ignorada)")
            return None

    def _score_breakdown(self, year: int, month: int, summary: dict) -> dict:
        """Calcula as 5 sub-métricas (cada uma 0-100) com seus pesos."""
        incomes = summary["total_incomes"]
        expenses = summary["total_expenses"]
        balance = summary["balance"]

        # 1) Taxa de poupança (peso 30): 20%+ da receita poupada = nota máxima.
        if incomes > 0:
            rate = balance / incomes
            poupanca = self._clamp(rate / 0.20 * 100)
        else:
            poupanca = 0.0

        # 2) Controle de despesas (peso 25): gastar até a média histórica = 100;
        #    50% acima da média = 0. Sem histórico, nota neutra.
        averages, months_used = self._category_averages(year, month, months_back=3)
        avg_total = sum(averages.values()) if averages else 0.0
        if months_used == 0 or avg_total <= 0:
            controle = 60.0
        else:
            ratio = expenses / avg_total
            controle = self._clamp(100 - (ratio - 1) / 0.5 * 100)

        # 3) Saldo positivo (peso 20): no azul = 100; quanto mais no vermelho, pior.
        if balance >= 0:
            saldo = 100.0
        elif incomes > 0:
            saldo = self._clamp(100 + (balance / incomes) * 200)
        else:
            saldo = 0.0

        # 4) Diversificação de receita (peso 15): mais fontes = menos dependência.
        fontes = self._income_sources(summary)
        diversificacao = 0.0 if fontes == 0 else self._clamp(25 + fontes * 25)

        # 5) Progresso de metas (peso 10): média do progresso; sem metas, neutro.
        metas = self._goals_score(year, month)

        return {
            "poupanca": {"score": round(poupanca), "weight": 30, "label": "Taxa de poupança"},
            "controle": {"score": round(controle), "weight": 25, "label": "Controle de despesas"},
            "saldo": {"score": round(saldo), "weight": 20, "label": "Saldo positivo"},
            "diversificacao": {"score": round(diversificacao), "weight": 15, "label": "Diversificação de receita"},
            "metas": {"score": round(metas), "weight": 10, "label": "Progresso de metas"},
        }

    def _forecast_block(self, year, month, summary, fin_ctx) -> dict:
        """Bloco de previsão da página de IA — usa a previsão DETERMINÍSTICA.

        Antes havia DUAS previsões brigando: a determinística (saldo + salário a
        receber − contas a pagar) e uma estatística que extrapolava o ritmo de
        gastos E ignorava o salário (mostrava receita prevista R$ 0). Esta última
        confundia. Agora, quando há ForecastService (fin_ctx), usamos só a
        determinística; sem ele, caímos na estatística (compatibilidade).

        Mapeamento para o formato {projected_balance, projected_income,
        projected_expense, is_projection}:
          - mês corrente/futuro: income = ainda a receber, expense = ainda a
            pagar, balance = saldo previsto (saldo atual + a receber − a pagar);
          - mês fechado: números reais do mês.
        """
        is_proj = (year, month) >= (date.today().year, date.today().month)
        if fin_ctx and is_proj:
            return {
                "projected_balance": round(fin_ctx["projected_balance"], 2),
                "projected_income": round(fin_ctx["remaining_to_receive"], 2),
                "projected_expense": round(fin_ctx["remaining_to_pay"], 2),
                "is_projection": True,
            }
        if fin_ctx and not is_proj:
            return {
                "projected_balance": round(summary["balance"], 2),
                "projected_income": round(summary["total_incomes"], 2),
                "projected_expense": round(summary["total_expenses"], 2),
                "is_projection": False,
            }
        # Sem ForecastService injetado: mantém a extrapolação estatística.
        return self.forecast_balance(year, month, summary)

    def forecast_balance(self, year: int, month: int, summary: dict | None = None) -> dict:
        """Projeta o saldo do mês ao final.

        Para o mês CORRENTE, extrapola as despesas pelo ritmo diário e usa as
        receitas já lançadas ou a média dos meses anteriores (o que for maior,
        já que salário costuma cair perto do fim do mês). Para meses fechados,
        devolve o saldo real.

        Mantido como FALLBACK: só é usado quando não há ForecastService (ver
        _forecast_block). A análise principal usa a previsão determinística.
        """
        summary = summary or self.report_service.monthly_summary(year, month)
        incomes = summary["total_incomes"]
        expenses = summary["total_expenses"]
        balance = summary["balance"]

        today = date.today()
        is_current = (year == today.year and month == today.month)
        if not is_current:
            return {
                "projected_balance": round(balance, 2),
                "projected_income": round(incomes, 2),
                "projected_expense": round(expenses, 2),
                "is_projection": False,
            }

        days_in_month = self._days_in_month(year, month)
        days_elapsed = max(today.day, 1)
        progress = days_elapsed / days_in_month

        # Extrapolação linear pura "explode" no início do mês quando contas
        # fixas grandes (aluguel) caem cedo. Por isso, quando há histórico,
        # misturamos a projeção linear com a média dos meses anteriores,
        # dando mais peso à linear conforme o mês avança.
        linear_expense = expenses / progress
        avg_expense = self._avg_expense(year, month, months_back=3)
        if avg_expense > 0:
            proj_expense = progress * linear_expense + (1 - progress) * avg_expense
            proj_expense = max(proj_expense, expenses)  # nunca menos que o já gasto
        else:
            proj_expense = linear_expense

        avg_income = self._avg_income(year, month, months_back=3)
        proj_income = max(incomes, avg_income)

        return {
            "projected_balance": round(proj_income - proj_expense, 2),
            "projected_income": round(proj_income, 2),
            "projected_expense": round(proj_expense, 2),
            "is_projection": True,
        }

    # ---------- Insights do score (regras) ----------

    def _score_insights(self, score, faixa, breakdown, forecast, summary, fin_ctx=None) -> list[Insight]:
        insights: list[Insight] = []
        sev = {"saudavel": SEVERITY_SUCCESS, "atencao": SEVERITY_WARNING, "critica": SEVERITY_DANGER}[faixa]
        insights.append(Insight(
            category="resumo", severity=sev,
            title=f"Score de saúde: {score}/100",
            message=f"Sua saúde financeira está na faixa '{self._faixa_label(faixa)}'.",
        ))

        # Aponta a pior e a melhor sub-métrica.
        ordenado = sorted(breakdown.values(), key=lambda b: b["score"])
        pior = ordenado[0]
        melhor = ordenado[-1]
        if pior["score"] < 60:
            insights.append(Insight(
                category="economia", severity=SEVERITY_WARNING,
                title=f"Ponto a melhorar: {pior['label']}",
                message=f"'{pior['label']}' está em {pior['score']}/100 — é onde você mais ganha subindo o score.",
            ))
        if melhor["score"] >= 80:
            insights.append(Insight(
                category="resumo", severity=SEVERITY_SUCCESS,
                title=f"Destaque: {melhor['label']}",
                message=f"'{melhor['label']}' está ótimo ({melhor['score']}/100). Continue assim!",
            ))

        # Previsão de fim de mês: SÓ a determinística (salário + contas). Sem
        # ForecastService, cai na estatística (ritmo de gastos) como fallback.
        det = self._deterministic_forecast_insight(fin_ctx)
        insights.append(det if det is not None else self._forecast_insight(forecast))
        return insights

    def _deterministic_forecast_insight(self, fin_ctx: Optional[dict]) -> Optional[Insight]:
        """Conselho baseado na previsão determinística do ForecastService.

        Usa os números concretos (saldo previsto, quanto falta receber/pagar,
        status) para um conselho prático no estilo do exemplo pedido. Vale
        tanto no modo offline (regras) quanto como fallback do LLM.
        """
        if not fin_ctx:
            return None
        status = fin_ctx.get("status")
        projected = fin_ctx.get("projected_balance", 0.0)
        to_receive = fin_ctx.get("remaining_to_receive", 0.0)
        to_pay = fin_ctx.get("remaining_to_pay", 0.0)

        base = (
            f"Com base na sua previsão, você deve fechar o mês com "
            f"aproximadamente {format_brl(projected)}. "
            f"Ainda faltam {format_brl(to_receive)} a receber e "
            f"{format_brl(to_pay)} a pagar até o fim do mês."
        )
        if status == "risco":
            return Insight(
                category="alerta", severity=SEVERITY_DANGER,
                title="Risco de fechar o mês no vermelho",
                message=base + " Evite novos gastos não essenciais e, se possível, "
                               "antecipe entradas ou renegocie contas.",
            )
        if status == "atencao":
            return Insight(
                category="economia", severity=SEVERITY_WARNING,
                title="Mês apertado — segure os gastos",
                message=base + " A margem está pequena: o ideal é evitar gastos com "
                               "lazer e compras até o próximo pagamento.",
            )
        return Insight(
            category="resumo", severity=SEVERITY_SUCCESS,
            title="Previsão do mês positiva",
            message=base + " Há folga no orçamento — bom momento para reforçar a "
                           "reserva ou adiantar uma meta.",
        )

    def _forecast_insight(self, forecast: dict) -> Insight:
        """Insight da previsão de fim de mês (usado nas regras e na análise Groq)."""
        pb = forecast["projected_balance"]
        if forecast["is_projection"]:
            msg = (
                f"No ritmo atual, seu saldo deve fechar o mês em {format_brl(pb)} "
                f"(receita prevista {format_brl(forecast['projected_income'])}, "
                f"despesa prevista {format_brl(forecast['projected_expense'])})."
            )
        else:
            msg = f"O mês fechou com saldo de {format_brl(pb)}."
        return Insight(
            category="resumo",
            severity=SEVERITY_SUCCESS if pb >= 0 else SEVERITY_DANGER,
            title="Previsão de fim de mês",
            message=msg,
        )

    def _llm_analysis(self, year, month, score, faixa, breakdown, forecast, summary, fin_ctx=None) -> list[Insight]:
        """Pede à Groq a análise COMPLETA (resumo + insights + recomendações).

        A Groq devolve um JSON estruturado, que convertemos em Insights. É a
        fonte principal da página de IA quando há chave configurada. Tolerante
        a falha: qualquer erro devolve [] e o chamador cai nas regras locais.

        Para soar como um GESTOR (e não um conselho genérico), alimentamos o
        modelo com fatos específicos: cada categoria com % e variação vs a média
        histórica, os maiores gastos individuais, assinaturas, a carga de
        faturas/parcelas já comprometidas nos próximos meses, metas e a previsão.
        """
        try:
            linhas = "; ".join(f"{b['label']}: {b['score']}/100" for b in breakdown.values())
            fatos = self._llm_facts(year, month, summary)
            # Bloco extra com a previsão determinística (salário + recorrentes +
            # contas). Só entra se houver ForecastService injetado.
            previsao_txt = self._forecast_prompt_block(fin_ctx, forecast)
            prompt = (
                "Você é o GESTOR FINANCEIRO PESSOAL deste usuário (brasileiro), no "
                "estilo de um consultor que acompanha de perto e fala com franqueza. "
                "Sua análise tem que ser ESPECÍFICA e ACIONÁVEL: cite categorias, "
                "valores em reais e percentuais REAIS dos dados; aponte exatamente "
                "ONDE cortar e QUANTO dá para economizar; comente os maiores gastos "
                "pelo nome; avalie a carga de parcelas/faturas futuras e o risco de "
                "fechar o mês no vermelho; diga claramente se dá para gastar mais ou "
                "se precisa segurar. Nada de conselho genérico tipo 'monte um "
                "orçamento' — fale do caso REAL abaixo.\n\n"
                "Responda APENAS um JSON VÁLIDO (sem markdown, sem texto fora do "
                "JSON), neste formato:\n"
                '{"resumo": "2-3 frases com diagnóstico específico citando números", '
                '"insights": [{"titulo": "curto e concreto", "texto": "1-2 frases '
                'com números reais", "severidade": "success|info|warning|danger"}], '
                '"recomendacoes": ["ação prática COM valor/categoria", "...", "..."]}\n\n'
                "Gere de 4 a 5 insights (cada um sobre um ponto DIFERENTE: poupança, "
                "categoria que pesou, parcelas futuras, previsão de fim de mês, metas) "
                "e de 3 a 4 recomendações, cada uma com um número concreto (ex.: "
                "'cortar ~R$ 150/mês em X'). Use SOMENTE os números fornecidos; "
                "não invente dados.\n\n"
                f"== DADOS DO MÊS ({month:02d}/{year}) ==\n"
                f"Score de saúde: {score}/100 (faixa {self._faixa_label(faixa)}).\n"
                f"Sub-métricas: {linhas}.\n"
                f"Receitas: {format_brl(summary['total_incomes'])}; "
                f"Despesas: {format_brl(summary['total_expenses'])}; "
                f"Saldo: {format_brl(summary['balance'])} "
                f"({summary['count']} transações).\n"
                f"{fatos}\n"
                f"{previsao_txt}"
            )
            data = self._extract_json(
                self._groq_generate(prompt, max_tokens=1100, temperature=0.5)
            )
            if not data:
                return []

            sev_geral = {
                "saudavel": SEVERITY_SUCCESS, "atencao": SEVERITY_WARNING,
                "critica": SEVERITY_DANGER,
            }[faixa]
            valid_sev = (SEVERITY_SUCCESS, SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_DANGER)

            insights: list[Insight] = []
            resumo = (data.get("resumo") or "").strip()
            if resumo:
                insights.append(Insight(
                    category="resumo", severity=sev_geral,
                    title=f"Score {score}/100 — {self._faixa_label(faixa)}",
                    message=resumo, source=SOURCE_LLM,
                ))
            for it in (data.get("insights") or [])[:5]:
                if not isinstance(it, dict):
                    continue
                titulo = (it.get("titulo") or "").strip()
                texto = (it.get("texto") or "").strip()
                if not (titulo and texto):
                    continue
                severidade = it.get("severidade")
                if severidade not in valid_sev:
                    severidade = SEVERITY_INFO
                insights.append(Insight(
                    category="alerta", severity=severidade,
                    title=titulo, message=texto, source=SOURCE_LLM,
                ))
            recs = [r.strip() for r in (data.get("recomendacoes") or [])
                    if isinstance(r, str) and r.strip()]
            if recs:
                msg = "  ".join(f"• {r}" for r in recs[:4])
                insights.append(Insight(
                    category="economia", severity=SEVERITY_INFO,
                    title="Recomendações da IA", message=msg, source=SOURCE_LLM,
                ))
            # Previsão de fim de mês: só a determinística (sem duplicar com a
            # estatística). Estatística só como fallback se não houver fin_ctx.
            det = self._deterministic_forecast_insight(fin_ctx)
            insights.append(det if det is not None else self._forecast_insight(forecast))
            return insights
        except Exception:
            logger.exception("Falha na análise Groq (ignorada)")
            return []

    def _llm_facts(self, year: int, month: int, summary: dict) -> str:
        """Bloco de FATOS específicos do mês para a IA soar como gestor.

        Inclui: categorias com % do total e variação vs média histórica, os
        maiores gastos individuais, assinaturas, a carga de faturas futuras já
        comprometidas e o progresso de metas. Só entram as seções com dados.
        """
        linhas: list[str] = []
        total_exp = summary["total_expenses"]
        expenses = summary["expenses_by_category"]
        averages, months_used = self._category_averages(year, month, months_back=3)

        # Categorias: valor, % do total e variação vs média dos últimos meses.
        if expenses:
            partes = []
            for cat, val in list(expenses.items())[:6]:
                pct = (val / total_exp * 100) if total_exp else 0
                avg = averages.get(cat)
                if avg and avg > 0:
                    delta = (val / avg - 1) * 100
                    sinal = "+" if delta >= 0 else ""
                    partes.append(
                        f"{cat} {format_brl(val)} ({pct:.0f}% do total, "
                        f"{sinal}{delta:.0f}% vs média {months_used}m)"
                    )
                else:
                    partes.append(f"{cat} {format_brl(val)} ({pct:.0f}% do total)")
            linhas.append("Gastos por categoria: " + "; ".join(partes) + ".")

        # Maiores gastos individuais (com parcela, se houver).
        exps = [t for t in summary["transactions"] if t.type == TYPE_EXPENSE]
        if exps:
            maiores = sorted(exps, key=lambda t: t.amount, reverse=True)[:3]
            partes = []
            for t in maiores:
                extra = (
                    f" (parcela {t.installment_no}/{t.installments_total})"
                    if t.installments_total > 1 else ""
                )
                partes.append(f"{t.description} {format_brl(t.amount)} [{t.category}]{extra}")
            linhas.append("Maiores gastos do mês: " + "; ".join(partes) + ".")

        # Assinaturas (gasto recorrente fácil de cortar).
        subs = expenses.get("Assinaturas", 0.0)
        if subs > 0:
            n = sum(1 for t in exps if t.category == "Assinaturas")
            linhas.append(f"Assinaturas: {n} cobrança(s) somando {format_brl(subs)}.")

        # Carga de faturas/parcelas já comprometidas nos próximos meses.
        futuro = self._future_card_load(year, month, months=3)
        if futuro["total"] > 0:
            meses = "; ".join(f"{lbl} {format_brl(v)}" for lbl, v in futuro["por_mes"])
            linhas.append(
                f"Faturas de cartão já comprometidas adiante: {meses} "
                f"(total {format_brl(futuro['total'])} nos próximos meses)."
            )

        metas_txt = self._goals_facts(year, month)
        if metas_txt:
            linhas.append(metas_txt)

        return "\n".join(f"- {l}" for l in linhas)

    def _future_card_load(self, year: int, month: int, months: int = 3) -> dict:
        """Soma as faturas de cartão dos próximos `months` meses (parcelas já lançadas)."""
        por_mes = []
        total = 0.0
        for i in range(1, months + 1):
            y, m = self._add_months(year, month, i)
            invoices = self.repository.expenses_by_card_in_month(y, m)
            s = sum(invoices.values())
            if s > 0:
                por_mes.append((self._month_label(y, m), s))
                total += s
        return {"por_mes": por_mes, "total": total}

    def _goals_facts(self, year: int, month: int) -> str:
        """Texto curto com o progresso das metas (vazio se não houver)."""
        try:
            metas = self.goal_service.list_with_progress(year, month)
        except Exception:
            return ""
        if not metas:
            return ""
        partes = []
        for m in metas[:4]:
            nome = m.get("name", "meta")
            pct = m.get("pct", 0)
            if m.get("kind") == "limite_gasto":
                estado = "ESTOUROU o teto" if m.get("exceeded") else f"{pct:.0f}% do teto"
                partes.append(f"{nome} (limite): {estado}")
            else:
                partes.append(f"{nome}: {pct:.0f}% da meta")
        return "Metas: " + "; ".join(partes) + "."

    @staticmethod
    def _add_months(year: int, month: int, count: int) -> tuple[int, int]:
        """Avança `count` meses a partir de (year, month)."""
        index = (year * 12 + (month - 1)) + count
        return index // 12, (index % 12) + 1

    @staticmethod
    def _month_label(year: int, month: int) -> str:
        nomes = [
            "jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez",
        ]
        return f"{nomes[month - 1]}/{year}"

    @staticmethod
    def _forecast_prompt_block(fin_ctx: Optional[dict], forecast: dict) -> str:
        """Texto com a previsão para o prompt da Groq.

        Prefere a previsão DETERMINÍSTICA (salário + recorrentes + contas)
        quando disponível; senão, usa a estatística. Assim a IA sempre tem
        noção de quanto falta receber/pagar e do risco de fechar negativo.
        """
        if fin_ctx:
            return (
                f"Saldo atual: {format_brl(fin_ctx['current_balance'])}.\n"
                f"Previsão de saldo no fim do mês: {format_brl(fin_ctx['projected_balance'])}.\n"
                f"Ainda falta RECEBER no mês: {format_brl(fin_ctx['remaining_to_receive'])}.\n"
                f"Ainda falta PAGAR no mês: {format_brl(fin_ctx['remaining_to_pay'])} "
                f"(recorrentes {format_brl(fin_ctx['future_recurring'])}, "
                f"contas a pagar {format_brl(fin_ctx['future_vencimentos'])}, "
                f"fatura do cartão {format_brl(fin_ctx.get('future_card', 0.0))}).\n"
                f"Salário líquido estimado: {format_brl(fin_ctx['net_salary'])}.\n"
                f"Status da previsão: {fin_ctx['status']}.\n"
            )
        return f"Previsão de saldo no fim do mês: {format_brl(forecast['projected_balance'])}.\n"

    @staticmethod
    def _extract_json(raw: str):
        """Extrai o primeiro objeto JSON de um texto (a Groq às vezes embrulha)."""
        if not raw:
            return None
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return None

    # ---------- Auxiliares do score ----------

    @staticmethod
    def _insight_to_dict(i: Insight) -> dict:
        return {
            "category": i.category, "severity": i.severity,
            "title": i.title, "message": i.message, "source": i.source,
        }

    @staticmethod
    def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, v))

    @staticmethod
    def _faixa(score: int) -> str:
        if score >= 70:
            return "saudavel"
        if score >= 40:
            return "atencao"
        return "critica"

    @staticmethod
    def _faixa_label(faixa: str) -> str:
        return {"saudavel": "Saudável", "atencao": "Atenção", "critica": "Crítica"}.get(faixa, faixa)

    @staticmethod
    def _income_sources(summary: dict) -> int:
        """Quantas categorias de receita distintas tiveram entrada no mês."""
        cats = set()
        for t in summary["transactions"]:
            if t.type != TYPE_EXPENSE and t.amount > 0:
                cats.add(t.category)
        return len(cats)

    def _goals_score(self, year: int, month: int) -> float:
        """Nota de progresso das metas (neutra se não houver metas)."""
        try:
            metas = self.goal_service.list_with_progress(year, month)
        except Exception:
            return 60.0
        if not metas:
            return 60.0
        notas = []
        for m in metas:
            if m["kind"] == "limite_gasto":
                # Não estourar o teto = bom; estourar = ruim.
                notas.append(0.0 if m["exceeded"] else self._clamp(100 - m["pct"]))
            else:
                notas.append(self._clamp(m["pct"]))
        return sum(notas) / len(notas) if notas else 60.0

    def _avg_income(self, year: int, month: int, months_back: int = 3) -> float:
        """Média de receitas dos meses anteriores (para a previsão)."""
        return self._avg_metric(year, month, "total_incomes", months_back)

    def _avg_expense(self, year: int, month: int, months_back: int = 3) -> float:
        """Média de despesas dos meses anteriores (para a previsão)."""
        return self._avg_metric(year, month, "total_expenses", months_back)

    def _avg_metric(self, year: int, month: int, key: str, months_back: int) -> float:
        """Média de uma métrica do resumo nos meses anteriores que tiveram dados."""
        total = 0.0
        n = 0
        for i in range(1, months_back + 1):
            m, y = month - i, year
            while m <= 0:
                m += 12
                y -= 1
            s = self.report_service.monthly_summary(y, m)
            if s[key] > 0:
                total += s[key]
                n += 1
        return total / n if n else 0.0

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        if month == 12:
            return 31
        return (date(year, month + 1, 1) - date(year, month, 1)).days

    # ═══════════════════════════════════════════════════════
    # MONTAGEM DO CONTEXTO
    # ═══════════════════════════════════════════════════════

    def _build_context(self, year: int, month: int) -> AnalysisContext:
        """Calcula tudo que as regras precisam, uma única vez."""
        summary = self.report_service.monthly_summary(year, month)

        # Média de gastos por categoria nos meses ANTERIORES (até 3).
        category_averages, months_used = self._category_averages(
            year, month, months_back=3
        )

        return AnalysisContext(
            year=year,
            month=month,
            total_incomes=summary["total_incomes"],
            total_expenses=summary["total_expenses"],
            balance=summary["balance"],
            expenses_by_category=summary["expenses_by_category"],
            transactions=summary["transactions"],
            category_averages=category_averages,
            months_of_history=months_used,
        )

    def _category_averages(
        self, year: int, month: int, months_back: int = 3
    ) -> tuple[dict, int]:
        """Calcula a média de gasto por categoria nos meses anteriores.

        Retorna ({categoria: média}, quantos_meses_tinham_dados).
        Só conta meses que realmente tiveram despesas, para a média
        não ficar distorcida por meses vazios.
        """
        totals: dict[str, float] = {}
        months_with_data = 0

        for i in range(1, months_back + 1):
            m, y = month - i, year
            while m <= 0:
                m += 12
                y -= 1

            summary = self.report_service.monthly_summary(y, m)
            if summary["total_expenses"] > 0:
                months_with_data += 1
                for cat, val in summary["expenses_by_category"].items():
                    totals[cat] = totals.get(cat, 0.0) + val

        if months_with_data == 0:
            return ({}, 0)

        averages = {cat: total / months_with_data for cat, total in totals.items()}
        return (averages, months_with_data)

    # ═══════════════════════════════════════════════════════
    # RESUMO (sempre aparece)
    # ═══════════════════════════════════════════════════════

    def _build_summary(self, ctx: AnalysisContext) -> Insight:
        """Monta o resumo do mês em linguagem simples."""
        n_transactions = len(ctx.transactions)
        n_categories = len(ctx.expenses_by_category)

        if ctx.balance >= 0:
            saldo_txt = f"sobraram {format_brl(ctx.balance)}"
            severity = SEVERITY_SUCCESS
        else:
            saldo_txt = f"faltaram {format_brl(abs(ctx.balance))}"
            severity = SEVERITY_WARNING

        message = (
            f"Neste mês você registrou {n_transactions} transações em "
            f"{n_categories} categorias de despesa. "
            f"Receitas de {format_brl(ctx.total_incomes)} e despesas de "
            f"{format_brl(ctx.total_expenses)} — ou seja, {saldo_txt}."
        )

        return Insight(
            category="resumo",
            severity=severity,
            title="Resumo do mês",
            message=message,
        )

    # ═══════════════════════════════════════════════════════
    # REGRAS DE ANÁLISE
    # Cada regra olha o contexto e devolve um Insight ou None.
    # ═══════════════════════════════════════════════════════

    def _rule_savings_rate(self, ctx: AnalysisContext) -> Optional[Insight]:
        """Avalia a taxa de poupança (quanto da receita sobrou)."""
        if ctx.total_incomes <= 0:
            return None

        rate = ctx.balance / ctx.total_incomes  # ex: 0.2 = poupou 20%

        if rate >= 0.2:
            return Insight(
                category="resumo",
                severity=SEVERITY_SUCCESS,
                title="Ótima taxa de poupança",
                message=(
                    f"Você poupou {rate:.0%} da sua receita este mês. "
                    f"Excelente! Manter acima de 20% é uma meta saudável."
                ),
            )
        if rate < 0:
            return None  # saldo negativo é tratado por outra regra.
        if rate < 0.1:
            return Insight(
                category="economia",
                severity=SEVERITY_WARNING,
                title="Taxa de poupança baixa",
                message=(
                    f"Você poupou apenas {rate:.0%} da receita. "
                    f"Tente reservar pelo menos 10-20% para emergências e metas."
                ),
            )
        return None

    def _rule_balance_negative(self, ctx: AnalysisContext) -> Optional[Insight]:
        """Alerta se as despesas superaram as receitas."""
        if ctx.balance >= 0:
            return None
        return Insight(
            category="alerta",
            severity=SEVERITY_DANGER,
            title="Você gastou mais do que ganhou",
            message=(
                f"Suas despesas ({format_brl(ctx.total_expenses)}) superaram "
                f"as receitas ({format_brl(ctx.total_incomes)}) em "
                f"{format_brl(abs(ctx.balance))}. Vale revisar os maiores gastos "
                f"e cortar o que for possível."
            ),
        )

    def _rule_category_above_average(self, ctx: AnalysisContext) -> Optional[Insight]:
        """Alerta categorias que estouraram a média dos meses anteriores."""
        if not ctx.category_averages:
            return None  # sem histórico para comparar.

        # Procura a categoria que mais passou da média (em valor absoluto).
        worst_category = None
        worst_excess = 0.0
        worst_pct = 0.0

        for cat, current in ctx.expenses_by_category.items():
            average = ctx.category_averages.get(cat)
            if average is None or average <= 0:
                continue
            # Só considera estouros relevantes (>20% acima da média).
            if current > average * 1.2:
                excess = current - average
                if excess > worst_excess:
                    worst_excess = excess
                    worst_category = cat
                    worst_pct = (current / average - 1)

        if worst_category is None:
            return None

        return Insight(
            category="alerta",
            severity=SEVERITY_WARNING,
            title=f"Gasto alto em {worst_category}",
            message=(
                f"Você gastou {format_brl(ctx.expenses_by_category[worst_category])} "
                f"em {worst_category} este mês — {worst_pct:.0%} acima da sua média "
                f"dos últimos {ctx.months_of_history} "
                f"{'mês' if ctx.months_of_history == 1 else 'meses'} "
                f"({format_brl(ctx.category_averages[worst_category])}). "
                f"Vale checar se houve algo fora do comum."
            ),
        )

    def _rule_biggest_expense(self, ctx: AnalysisContext) -> Optional[Insight]:
        """Destaca a maior despesa individual do mês."""
        expenses = [t for t in ctx.transactions if t.type == TYPE_EXPENSE]
        if not expenses:
            return None

        biggest = max(expenses, key=lambda t: t.amount)

        # Só vira insight se for relevante (>15% do total de despesas).
        if ctx.total_expenses > 0 and biggest.amount < ctx.total_expenses * 0.15:
            return None

        return Insight(
            category="resumo",
            severity=SEVERITY_INFO,
            title="Maior despesa do mês",
            message=(
                f"Seu maior gasto foi '{biggest.description}' "
                f"({format_brl(biggest.amount)} em {biggest.category}). "
                f"Isso representa {biggest.amount / ctx.total_expenses:.0%} "
                f"das suas despesas do mês."
            ),
        )

    def _rule_subscriptions_weight(self, ctx: AnalysisContext) -> Optional[Insight]:
        """Avalia o peso de assinaturas no orçamento."""
        subscriptions = ctx.expenses_by_category.get("Assinaturas", 0.0)
        if subscriptions <= 0:
            return None

        # Conta quantas transações de assinatura houve.
        n_subs = sum(
            1 for t in ctx.transactions
            if t.type == TYPE_EXPENSE and t.category == "Assinaturas"
        )

        message = (
            f"Você tem {n_subs} "
            f"{'assinatura' if n_subs == 1 else 'assinaturas'} "
            f"somando {format_brl(subscriptions)} este mês"
        )

        # Se assinaturas passam de 10% das despesas, vira dica de economia.
        if ctx.total_expenses > 0 and subscriptions > ctx.total_expenses * 0.1:
            return Insight(
                category="economia",
                severity=SEVERITY_INFO,
                title="Atenção às assinaturas",
                message=(
                    f"{message} — isso é "
                    f"{subscriptions / ctx.total_expenses:.0%} das suas despesas. "
                    f"Revise se está usando todas. Cancelar as esquecidas é uma "
                    f"economia fácil e recorrente."
                ),
            )
        return Insight(
            category="resumo",
            severity=SEVERITY_INFO,
            title="Assinaturas do mês",
            message=f"{message}.",
        )

    def _rule_expense_concentration(self, ctx: AnalysisContext) -> Optional[Insight]:
        """Avisa se os gastos estão muito concentrados numa categoria."""
        if not ctx.expenses_by_category or ctx.total_expenses <= 0:
            return None

        top_category, top_value = next(iter(ctx.expenses_by_category.items()))
        share = top_value / ctx.total_expenses

        # Se uma única categoria passa de 50% de tudo, é concentração alta.
        if share > 0.5:
            return Insight(
                category="economia",
                severity=SEVERITY_INFO,
                title="Gastos concentrados",
                message=(
                    f"{share:.0%} das suas despesas foram em {top_category}. "
                    f"Quando um gasto domina o orçamento, é onde mora a maior "
                    f"oportunidade de economia — vale olhar com carinho."
                ),
            )
        return None

    def _rule_top_category_tip(self, ctx: AnalysisContext) -> Optional[Insight]:
        """Dá uma dica prática conforme a categoria que mais pesou."""
        if not ctx.expenses_by_category:
            return None

        top_category = next(iter(ctx.expenses_by_category.keys()))

        # Dicas específicas por categoria. Você pode adicionar mais!
        tips = {
            "Alimentação": (
                "Cozinhar em casa e levar marmita reduz bastante o gasto com "
                "alimentação. Pedir delivery 1x a menos por semana já faz diferença."
            ),
            "Mercado": (
                "Fazer uma lista antes de ir ao mercado e evitar ir com fome "
                "ajuda a não comprar por impulso."
            ),
            "Transporte": (
                "Agrupar trajetos, caronas ou transporte público em alguns dias "
                "pode reduzir o gasto com transporte."
            ),
            "Lazer": (
                "Lazer é importante! Mas vale definir um teto mensal para não "
                "comprometer suas metas financeiras."
            ),
            "Compras": (
                "Para compras não essenciais, experimente a regra das 24h: espere "
                "um dia antes de comprar. Muitas vontades passam."
            ),
        }

        tip = tips.get(top_category)
        if tip is None:
            return None

        return Insight(
            category="economia",
            severity=SEVERITY_SUCCESS,
            title=f"Dica para {top_category}",
            message=tip,
        )

    # ═══════════════════════════════════════════════════════
    # REFINO COM LLM (Groq) — conselho personalizado
    # ═══════════════════════════════════════════════════════

    def _refine_with_llm(
        self, insights: list[Insight], ctx: AnalysisContext
    ) -> list[Insight]:
        """Acrescenta um conselho personalizado gerado pela Groq.

        As regras determinísticas (acima) continuam valendo: este método
        NÃO altera os insights existentes, apenas adiciona um novo no fim,
        escrito pelo LLM em linguagem natural a partir dos mesmos dados.

        É tolerante a falhas de propósito: se não houver GROQ_API_KEY, a API
        falhar ou demorar demais, devolvemos a lista original sem o conselho
        extra. A IA aqui é um BÔNUS, nunca um requisito.
        """
        if not self._groq_available():
            logger.info("GROQ_API_KEY ausente; conselho LLM pulado.")
            return insights

        try:
            advice = self._generate_advice(insights, ctx)
        except Exception:
            # Qualquer erro (rede, modelo, timeout) não pode derrubar a análise.
            logger.exception("Falha ao gerar conselho com a Groq (ignorada)")
            return insights

        if not advice:
            return insights

        logger.info("Groq gerou conselho personalizado (%d caracteres).", len(advice))
        insights.append(Insight(
            category="economia",
            severity=SEVERITY_INFO,
            title="Conselho personalizado",
            message=advice,
            source=SOURCE_LLM,
        ))
        return insights

    @staticmethod
    def _groq_available() -> bool:
        """Há uma GROQ_API_KEY configurada? Sem ela, o refino é pulado."""
        return bool(GROQ_API_KEY)

    def _generate_advice(
        self, insights: list[Insight], ctx: AnalysisContext
    ) -> str:
        """Monta o prompt, chama a Groq e devolve o conselho em texto limpo."""
        prompt = self._build_advice_prompt(insights, ctx)
        raw = self._groq_generate(prompt)
        # Tira aspas/markdown que alguns modelos colocam em volta da resposta.
        return raw.strip().strip('"').strip()

    def _build_advice_prompt(
        self, insights: list[Insight], ctx: AnalysisContext
    ) -> str:
        """Resume os dados do mês + os insights das regras num prompt curto.

        Damos ao modelo os números já calculados E os títulos dos insights
        que dispararam, para ele não inventar dados e sim COMENTAR o que já
        sabemos, num tom de consultor amigável.
        """
        # Top 3 categorias de despesa (o dict já vem ordenado por valor).
        top = list(ctx.expenses_by_category.items())[:3]
        categorias_txt = (
            "; ".join(f"{cat}: {format_brl(val)}" for cat, val in top)
            or "nenhuma despesa registrada"
        )

        if ctx.total_incomes > 0:
            taxa = ctx.balance / ctx.total_incomes
            taxa_txt = f"{taxa:.0%}"
        else:
            taxa_txt = "indefinida (sem receitas)"

        # Os títulos dos insights já dão ao modelo o "diagnóstico" das regras.
        diagnostico = "\n".join(f"- {i.title}: {i.message}" for i in insights)

        return (
            "Você é um consultor financeiro pessoal, simpático e direto, que "
            "fala português do Brasil. Com base nos dados abaixo, escreva UM "
            "conselho personalizado e prático para o usuário.\n\n"
            "REGRAS DA RESPOSTA:\n"
            "- No máximo 3 frases curtas.\n"
            "- Tom encorajador, sem julgar.\n"
            "- Use os números fornecidos; NÃO invente dados.\n"
            "- Não use markdown, listas ou títulos. Apenas o texto do conselho.\n\n"
            f"DADOS DO MÊS:\n"
            f"- Receitas: {format_brl(ctx.total_incomes)}\n"
            f"- Despesas: {format_brl(ctx.total_expenses)}\n"
            f"- Saldo: {format_brl(ctx.balance)}\n"
            f"- Taxa de poupança: {taxa_txt}\n"
            f"- Maiores categorias de despesa: {categorias_txt}\n\n"
            f"ANÁLISE JÁ FEITA (comente e amarre estes pontos):\n{diagnostico}\n\n"
            "CONSELHO:"
        )

    @staticmethod
    def _groq_generate(prompt: str, max_tokens: int = 800, temperature: float = 0.4) -> str:
        """Chama a API de chat da Groq e devolve o texto gerado.

        Usa só a biblioteca padrão (urllib) — nenhuma dependência extra.
        A Groq é compatível com a OpenAI: mandamos uma lista de mensagens
        em /chat/completions e lemos a resposta em choices[0].message.content.

        max_tokens/temperature são ajustáveis: a análise completa (gestor) pede
        mais espaço e um pouco mais de temperatura para soar específica; o
        conselho curto usa o padrão mais conservador.
        """
        payload = json.dumps({
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            GROQ_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}",
                # A borda da Groq (Cloudflare) bloqueia o User-Agent padrão
                # do urllib ("Python-urllib/..."), devolvendo 403. Mandamos
                # um User-Agent comum para a requisição passar.
                "User-Agent": "finance-app/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=GROQ_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 401/403 = chave inválida/rejeitada (causa mais comum: chave
            # incompleta/colada pela metade). Log claro para o usuário saber
            # que NÃO é falha do modelo — e a IA cai no modo offline (regras).
            if exc.code in (401, 403):
                logger.error(
                    "Groq recusou a chave (HTTP %s). Verifique GROQ_API_KEY no .env "
                    "— a chave deve ter ~56 caracteres (gsk_ + 52). Usando modo offline.",
                    exc.code,
                )
            raise

        # A API devolve o texto no campo choices[0].message.content.
        choices = data.get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""
