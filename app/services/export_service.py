"""
Service de exportação para Excel.

Usamos pandas para criar um DataFrame a partir das transações
e o método to_excel (que internamente usa openpyxl) para gerar
o arquivo .xlsx.
"""

from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from app.config import EXPORTS_DIR, ensure_directories
from app.models.transaction import Transaction
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ExportService:
    """Exportação de transações para Excel."""

    def export_to_excel(
        self,
        transactions: List[Transaction],
        filename: str | None = None,
    ) -> Path:
        """
        Exporta uma lista de transações para um arquivo .xlsx
        dentro da pasta data/exports.

        Retorna o caminho do arquivo gerado.
        """
        ensure_directories()

        if not transactions:
            raise ValueError("Nenhuma transação para exportar.")

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"transacoes_{timestamp}.xlsx"

        # Converte a lista de Transaction em uma lista de dicionários,
        # que é o formato que o pandas espera.
        data = [
            {
                "ID": t.id,
                "Data": t.date,
                "Descrição": t.description,
                "Valor": t.amount,
                "Tipo": t.type,
                "Categoria": t.category,
                "Pagamento": t.payment_method,
                "Quem gastou": t.spent_by,
                "Criado em": t.created_at,
            }
            for t in transactions
        ]

        df = pd.DataFrame(data)

        output_path = EXPORTS_DIR / filename

        # index=False evita exportar o índice numérico do pandas.
        # engine="openpyxl" é o motor de escrita de .xlsx.
        df.to_excel(output_path, index=False, engine="openpyxl")

        logger.info("Exportação realizada: %s (%d linhas)", output_path, len(df))
        return output_path
