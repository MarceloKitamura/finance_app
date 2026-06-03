"""
Configuração centralizada do sistema de logs.

Por que usar logging em vez de print?
- Tem níveis (DEBUG, INFO, WARNING, ERROR, CRITICAL).
- Pode gravar em arquivo sem alterar o código que loga.
- Mostra data/hora automaticamente.
- É o padrão profissional em Python.
"""

import logging
from app.config import LOG_FILE, ensure_directories


def get_logger(name: str = "finance_app") -> logging.Logger:
    """
    Retorna um logger configurado.

    Se este logger já foi configurado antes, retorna o mesmo
    (evita duplicar handlers e logar a mesma mensagem várias vezes).
    """
    # Garante que a pasta logs/ existe antes de tentar escrever nela.
    ensure_directories()

    logger = logging.getLogger(name)

    # Se já tem handlers, já foi configurado. Retorna como está.
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Formato: 2026-05-25 18:30:01 [INFO] finance_app: mensagem
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler 1: grava no arquivo de log.
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Handler 2: mostra no terminal.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Evita que mensagens subam para o logger raiz e dupliquem.
    logger.propagate = False

    return logger
