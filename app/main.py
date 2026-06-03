"""
Ponto de entrada do programa.

Mantemos este arquivo enxuto de propósito:
- inicializa o banco;
- inicia a CLI.

Toda a lógica está em services, repositories e interfaces.
"""

from app.database import initialize_database
from app.interfaces.cli import CLI
from app.utils.logger import get_logger


def main() -> None:
    logger = get_logger(__name__)
    logger.info("Iniciando aplicação")

    initialize_database()

    cli = CLI()
    cli.run()

    logger.info("Aplicação encerrada")


if __name__ == "__main__":
    main()
