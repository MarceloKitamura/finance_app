"""
Service de gráficos.

Usamos matplotlib para gerar gráficos simples e salvá-los como PNG
na pasta data/charts.

Note que usamos matplotlib.use("Agg") para gerar gráficos
sem precisar abrir uma janela (útil em CLI e em servidores).
"""

from datetime import datetime
from pathlib import Path
from typing import Dict

import matplotlib
matplotlib.use("Agg")  # Backend "headless" — gera imagens sem precisar de tela.
import matplotlib.pyplot as plt  # noqa: E402

from app.config import CHARTS_DIR, ensure_directories
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ChartService:
    """Geração de gráficos financeiros."""

    def expenses_by_category_chart(
        self,
        expenses_by_category: Dict[str, float],
        filename: str | None = None,
    ) -> Path:
        """
        Gera um gráfico de barras horizontal com os gastos por categoria.

        Recebe um dicionário {categoria: total} e salva um PNG.
        """
        ensure_directories()

        if not expenses_by_category:
            raise ValueError("Nenhum dado de gastos para gerar gráfico.")

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"gastos_por_categoria_{timestamp}.png"

        # Listas de categorias e valores na mesma ordem.
        categories = list(expenses_by_category.keys())
        values = list(expenses_by_category.values())

        # Figura e eixos. figsize em polegadas.
        fig, ax = plt.subplots(figsize=(10, max(4, len(categories) * 0.5)))

        bars = ax.barh(categories, values, color="#4C9BE8")
        ax.set_title("Gastos por categoria")
        ax.set_xlabel("Valor (R$)")
        ax.invert_yaxis()  # Maior valor no topo.

        # Mostra o valor ao lado de cada barra.
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_width(),
                bar.get_y() + bar.get_height() / 2,
                f" R$ {value:,.2f}",
                va="center",
            )

        plt.tight_layout()

        output_path = CHARTS_DIR / filename
        plt.savefig(output_path, dpi=120)
        plt.close(fig)  # Libera memória.

        logger.info("Gráfico gerado: %s", output_path)
        return output_path
