"""
Endpoints de IA de apoio ao cadastro.

Rotas (prefixo /ai):
- GET /ai/suggest-category?description=&type=  → sugere a categoria

Expõe o AIService (camada de palavras-chave + LLM opcional). O frontend
usa isso para PREENCHER automaticamente a categoria enquanto o usuário
digita a descrição da transação.
"""

import os

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_ai_service
from app.api.schemas import AIStatusOut, CategorySuggestionOut
from app.services.ai_service import AIService
from app.utils.env import load_env_file

router = APIRouter()


@router.get("/status", response_model=AIStatusOut)
def ai_status():
    """Diz se as integrações de IA (Groq / OpenAI) estão configuradas.

    O frontend usa isto para mostrar um aviso amigável de "configure sua chave"
    quando a IA está rodando só com as regras offline. Não expõe a chave em si.
    """
    load_env_file()  # garante o .env carregado mesmo sem outro import antes.
    groq = bool(os.getenv("GROQ_API_KEY"))
    openai = bool(os.getenv("OPENAI_API_KEY"))
    return AIStatusOut(
        groq_configured=groq,
        openai_configured=openai,
        advice_provider="groq" if groq else "offline",
        category_provider="openai" if openai else "offline",
    )


@router.get("/suggest-category", response_model=CategorySuggestionOut)
def suggest_category(
    description: str = Query(..., min_length=1, description="Descrição digitada."),
    type: str = Query("despesa", description="'receita' ou 'despesa'."),
    service: AIService = Depends(get_ai_service),
):
    """Sugere a categoria mais provável para a descrição informada.

    Devolve category=None quando não há sugestão confiável (o usuário
    então escolhe manualmente). É barato e rápido: a camada de palavras-
    chave roda offline; o LLM só é consultado se configurado.
    """
    category, confidence = service.suggest_category(description, type)
    return CategorySuggestionOut(category=category, confidence=confidence)
