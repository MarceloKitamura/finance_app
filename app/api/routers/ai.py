"""
Endpoints de IA de apoio ao cadastro.

Rotas (prefixo /ai):
- GET /ai/suggest-category?description=&type=  → sugere a categoria

Expõe o AIService (camada de palavras-chave + LLM opcional). O frontend
usa isso para PREENCHER automaticamente a categoria enquanto o usuário
digita a descrição da transação.
"""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_ai_service
from app.api.schemas import CategorySuggestionOut
from app.services.ai_service import AIService

router = APIRouter()


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
