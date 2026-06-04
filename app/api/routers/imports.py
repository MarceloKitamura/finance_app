"""
Endpoints de importação de extrato (Fase 3).

Rotas (prefixo /import):
- POST /import/preview        → extrai e pré-visualiza as transações
- POST /import/transactions   → grava as transações revisadas

O fluxo é em dois passos para o usuário conferir antes de gravar: primeiro
o preview (com categoria sugerida e duplicatas marcadas), depois a
confirmação. Toda a inteligência fica no ImportService.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_import_service
from app.api.schemas import (
    ImportConfirmIn,
    ImportPreviewIn,
    ImportPreviewOut,
    ImportResultOut,
)
from app.services.import_service import ImportService

router = APIRouter()


@router.post("/preview", response_model=ImportPreviewOut)
def preview_import(
    payload: ImportPreviewIn,
    service: ImportService = Depends(get_import_service),
):
    """Pré-visualiza um extrato.

    Para CSV sem mapeamento de colunas, devolve só os cabeçalhos + amostra
    (o frontend então pergunta qual coluna é data/valor/descrição). Com
    mapeamento (ou para OFX), devolve as transações candidatas já com
    categoria sugerida e marcação de duplicata.
    """
    result = service.preview(payload.format, payload.content, payload.mapping)
    return ImportPreviewOut(
        headers=result.get("headers", []),
        delimiter=result.get("delimiter", ""),
        sample=result.get("sample", []),
        items=result.get("items", []),
    )


@router.post("/transactions", response_model=ImportResultOut)
def confirm_import(
    payload: ImportConfirmIn,
    service: ImportService = Depends(get_import_service),
):
    """Grava as transações revisadas. Itens com include=False são pulados."""
    result = service.import_transactions([it.model_dump() for it in payload.items])
    return ImportResultOut(**result)
