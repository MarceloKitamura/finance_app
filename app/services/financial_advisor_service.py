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
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from app.constants.transaction_types import TYPE_EXPENSE
from app.repositories.transaction_repository import TransactionRepository
from app.services.report_service import ReportService
from app.utils.logger import get_logger
from app.utils.money_utils import format_brl

logger = get_logger(__name__)


# ───────────────────────────────────────────────────────────
# Carregamento do .env (sem dependências externas)
# ───────────────────────────────────────────────────────────
# A GROQ_API_KEY fica no arquivo .env na raiz do projeto. Como o projeto
# evita dependências extras, lemos o .env com um parser simples da stdlib
# em vez de usar python-dotenv. Variáveis já definidas no ambiente têm
# prioridade — o .env nunca sobrescreve o que já existe.

def _load_env_file() -> None:
    """Lê o .env da raiz do projeto e popula os.environ (se ainda não estiver)."""
    # __file__ = app/services/financial_advisor_service.py → raiz = 2 níveis acima.
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # Ignora linhas vazias, comentários e linhas sem "=".
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            # Tira espaços e aspas que às vezes envolvem o valor.
            value = value.strip().strip('"').strip("'").strip()
            if key:
                os.environ.setdefault(key, value)
    except OSError:
        # Sem .env legível seguimos sem LLM — não é um erro fatal.
        pass


_load_env_file()


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
    ):
        self.report_service = report_service or ReportService()
        self.repository = repository or TransactionRepository()
        # use_llm=True liga o conselho personalizado via Groq.
        # Sem GROQ_API_KEY, é ignorado sem quebrar nada.
        self.use_llm = use_llm

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
    def _groq_generate(prompt: str) -> str:
        """Chama a API de chat da Groq e devolve o texto gerado.

        Usa só a biblioteca padrão (urllib) — nenhuma dependência extra.
        A Groq é compatível com a OpenAI: mandamos uma lista de mensagens
        em /chat/completions e lemos a resposta em choices[0].message.content.
        """
        payload = json.dumps({
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            # temperatura baixa = conselho mais consistente e menos "viajado".
            "temperature": 0.4,
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

        with urllib.request.urlopen(req, timeout=GROQ_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # A API devolve o texto no campo choices[0].message.content.
        choices = data.get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""
