"""
Endpoint de conselhos financeiros (IA gestora).

Rotas (prefixo /advice):
- GET /advice?year=&month=  → lista de insights do mês

Expõe o FinancialAdvisorService: as regras determinísticas (offline,
privadas) SEMPRE rodam; se houver GROQ_API_KEY configurada, um conselho
personalizado gerado pela Groq é acrescentado (source="llm").

O frontend usa esses insights tanto na página "Conselhos IA" quanto na
"Dica do mês" do dashboard.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_advisor_service
from app.api.schemas import AdviceOut, InsightOut
from app.services.financial_advisor_service import SOURCE_LLM, FinancialAdvisorService

router = APIRouter()


@router.get("", response_model=AdviceOut)
def get_advice(
    year: int = Query(default=date.today().year, description="Ano da análise."),
    month: int = Query(default=date.today().month, ge=1, le=12, description="Mês (1-12)."),
    service: FinancialAdvisorService = Depends(get_advisor_service),
):
    """Gera os insights (alertas, economia, resumo) do mês informado.

    A chamada pode demorar alguns segundos quando a IA da Groq está ativa
    (ela gera o conselho personalizado). As regras locais são instantâneas.
    """
    insights = service.generate_insights(year, month)
    llm_used = any(i.source == SOURCE_LLM for i in insights)
    return AdviceOut(
        year=year,
        month=month,
        llm_used=llm_used,
        insights=[
            InsightOut(
                category=i.category,
                severity=i.severity,
                title=i.title,
                message=i.message,
                source=i.source,
            )
            for i in insights
        ],
    )
