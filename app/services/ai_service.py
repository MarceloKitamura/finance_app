"""
Service de IA para categorização automática de transações.

═══════════════════════════════════════════════════════════════════
⭐ COMO ESTE SERVICE FUNCIONA (leia antes de estudar o código)
═══════════════════════════════════════════════════════════════════
Quando o usuário digita uma descrição ("MERCADO EXTRA JUNDIAI"), este
service tenta adivinhar a categoria ("Mercado").

A estratégia tem 2 camadas, da mais barata para a mais cara:

  Camada 1 — PALAVRAS-CHAVE (pattern matching)
    Procura palavras conhecidas na descrição (de category_patterns.py).
    Rápido, offline, de graça. Resolve ~80% dos casos comuns.

  Camada 2 — LLM (opcional)
    Se a camada 1 não achar nada E houver uma API key configurada,
    pergunta para um modelo de IA (ex: OpenAI). Mais preciso, mas
    requer internet e tem custo.

Se nenhuma camada funcionar, devolve (None, 0.0) — e o usuário escolhe
manualmente, como antes. A IA é uma AJUDA, nunca uma obrigação.

Por que isso é um "service" e não fica no Streamlit?
Porque é regra de negócio (lógica de categorização). Assim, tanto o
Streamlit quanto a CLU (ou uma futura API) podem usar a mesma IA.
═══════════════════════════════════════════════════════════════════
"""

import os
import re
import unicodedata
from typing import Optional

from app.constants.category_patterns import EXPENSE_PATTERNS, INCOME_PATTERNS
from app.constants.transaction_types import TYPE_EXPENSE, TYPE_INCOME
from app.utils.env import load_env_file
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Garante que o .env (com OPENAI_API_KEY) seja lido mesmo quando este service é
# usado sozinho (CLI/testes), sem depender de outro módulo ter carregado antes.
load_env_file()


# Resultado de uma sugestão: (categoria_ou_None, confianca_de_0_a_1).
# Ex: ("Mercado", 0.95) significa "95% de certeza que é Mercado".
Suggestion = tuple[Optional[str], float]


class AIService:
    """Sugere categorias automaticamente a partir da descrição."""

    def __init__(self, use_llm: bool = True):
        """
        use_llm: se True, tenta usar LLM quando as palavras-chave falham.
                 Só funciona se houver uma API key no ambiente.
                 Se False, usa SOMENTE palavras-chave (100% offline).
        """
        self.use_llm = use_llm

    # ───────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL (o que o Streamlit chama)
    # ───────────────────────────────────────────────────────────

    def suggest_category(self, description: str, transaction_type: str) -> Suggestion:
        """
        Sugere uma categoria para a descrição informada.

        Retorna uma tupla (categoria, confianca):
          - ("Mercado", 0.95)  → sugestão com 95% de confiança
          - (None, 0.0)        → não conseguiu sugerir nada

        O transaction_type ("receita"/"despesa") define em qual conjunto
        de palavras-chave procurar.
        """
        if not description or not description.strip():
            return (None, 0.0)

        # Camada 1: palavras-chave.
        pattern_result = self._match_by_pattern(description, transaction_type)
        if pattern_result[0] is not None:
            logger.info(
                "IA (pattern) sugeriu %r para %r",
                pattern_result[0], description,
            )
            return pattern_result

        # Camada 2: LLM (opcional).
        if self.use_llm and self._llm_available():
            llm_result = self._classify_with_llm(description, transaction_type)
            if llm_result[0] is not None:
                logger.info(
                    "IA (LLM) sugeriu %r para %r",
                    llm_result[0], description,
                )
                return llm_result

        # Nada funcionou.
        return (None, 0.0)

    # ───────────────────────────────────────────────────────────
    # CAMADA 1: PALAVRAS-CHAVE
    # ───────────────────────────────────────────────────────────

    def _match_by_pattern(
        self, description: str, transaction_type: str
    ) -> Suggestion:
        """
        Procura palavras-chave conhecidas na descrição.

        Como funciona o "score":
        - Para cada categoria, contamos quantas palavras-chave aparecem.
        - A categoria com mais palavras vence.
        - A confiança aumenta com o número de palavras encontradas.
        """
        normalized = self._normalize(description)

        # Escolhe o conjunto de palavras-chave conforme o tipo.
        patterns = (
            INCOME_PATTERNS if transaction_type == TYPE_INCOME else EXPENSE_PATTERNS
        )

        best_category: Optional[str] = None
        best_score = 0

        for category, keywords in patterns.items():
            score = 0
            for keyword in keywords:
                # \b = "fronteira de palavra", evita que "gas" case com "gasto".
                # Usamos re.search para achar a palavra em qualquer posição.
                if re.search(rf"\b{re.escape(keyword)}\b", normalized):
                    score += 1

            if score > best_score:
                best_score = score
                best_category = category

        if best_category is None:
            return (None, 0.0)

        # Converte o score em confiança (0 a 1).
        # 1 palavra = 0.85, 2 palavras = 0.92, 3+ palavras = 0.97.
        confidence = min(0.85 + (best_score - 1) * 0.06, 0.97)
        return (best_category, confidence)

    # ───────────────────────────────────────────────────────────
    # CAMADA 2: LLM (opcional)
    # ───────────────────────────────────────────────────────────

    @staticmethod
    def _llm_available() -> bool:
        """
        Verifica se há uma API key de LLM configurada no ambiente.

        Para ativar, defina a variável de ambiente OPENAI_API_KEY:
            export OPENAI_API_KEY="sua-chave"   (Linux/Mac)
            set OPENAI_API_KEY=sua-chave         (Windows)

        Sem a chave, esta camada é simplesmente pulada.
        """
        return bool(os.getenv("OPENAI_API_KEY"))

    def _classify_with_llm(
        self, description: str, transaction_type: str
    ) -> Suggestion:
        """
        Pergunta a um LLM (OpenAI) qual a categoria mais provável.

        Esta função só roda se houver API key. Está isolada para que o
        resto do projeto funcione sem nenhuma dependência de IA externa.

        NOTA DE ESTUDO: este é um exemplo de integração. Para usá-lo de
        verdade você precisaria instalar o pacote: pip install openai
        """
        try:
            # Import local: só carrega o pacote se realmente formos usar.
            # Assim, quem não usa LLM não precisa instalar a biblioteca.
            from openai import OpenAI

            from app.constants.categories import (
                EXPENSE_CATEGORIES,
                INCOME_CATEGORIES,
            )

            valid_categories = (
                INCOME_CATEGORIES
                if transaction_type == TYPE_INCOME
                else EXPENSE_CATEGORIES
            )
            categories_str = ", ".join(valid_categories)

            client = OpenAI()  # Lê a OPENAI_API_KEY do ambiente automaticamente.

            prompt = (
                f"Categorize esta transação financeira: {description!r}.\n"
                f"Escolha UMA categoria desta lista: {categories_str}.\n"
                f"Responda APENAS com o nome exato da categoria, nada mais."
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Modelo barato e rápido.
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0,  # 0 = respostas consistentes.
            )

            suggested = response.choices[0].message.content.strip()

            # Confere se a resposta é uma categoria válida.
            if suggested in valid_categories:
                return (suggested, 0.90)
            return (None, 0.0)

        except Exception:
            # Qualquer erro (sem internet, sem pacote, API fora) → ignora.
            # A IA é opcional, então falha dela não pode quebrar o cadastro.
            logger.exception("Falha ao consultar LLM (ignorada)")
            return (None, 0.0)

    # ───────────────────────────────────────────────────────────
    # AUXILIAR
    # ───────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Prepara a descrição para comparação: minúsculas e sem acento.

        Ex: "Pão de Açúcar" → "pao de acucar"

        Reaproveitamos a mesma técnica dos normalizers: NFD separa letra
        do acento, e removemos os acentos (categoria 'Mn').
        """
        text = text.strip().lower()
        nfd = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
