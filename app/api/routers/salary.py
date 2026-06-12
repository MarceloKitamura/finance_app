"""
Endpoints de salário (bruto / líquido / divisão de recebimento).

Rotas (prefixo /salary):
- GET /salary  → configuração atual + líquido estimado + divisão 15/30
- PUT /salary  → salva a configuração e devolve o cálculo atualizado

O cálculo do líquido (INSS, IRRF, VT, descontos avulsos) e a divisão por
dia vivem no SalaryService. Aqui só validamos a entrada e repassamos.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_salary_service
from app.api.schemas import SalaryConfigIn, SalaryOut
from app.models.salary import OtherDiscount, SalaryConfig
from app.services.salary_service import SalaryService

router = APIRouter()


@router.get("", response_model=SalaryOut)
def get_salary(service: SalaryService = Depends(get_salary_service)):
    """Devolve a configuração de salário e o líquido/divisão calculados."""
    return SalaryOut(**service.summary())


@router.put("", response_model=SalaryOut)
def save_salary(
    payload: SalaryConfigIn,
    service: SalaryService = Depends(get_salary_service),
):
    """Salva a configuração de salário e devolve o cálculo atualizado."""
    config = SalaryConfig(
        gross=payload.gross,
        dependents=payload.dependents,
        inss_enabled=payload.inss_enabled,
        irrf_enabled=payload.irrf_enabled,
        vt_enabled=payload.vt_enabled,
        vt_monthly_cost=payload.vt_monthly_cost,
        other_discounts=[
            OtherDiscount(label=d.label, amount=d.amount) for d in payload.other_discounts
        ],
        pay_day_1=payload.pay_day_1,
        pay_day_2=payload.pay_day_2,
        split_mode=payload.split_mode,
        amount_day_1=payload.amount_day_1,
        amount_day_2=payload.amount_day_2,
        enabled=payload.enabled,
    )
    service.save_config(config)
    return SalaryOut(**service.summary(config))
