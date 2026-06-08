"""
Configurações centralizadas do projeto.

Aqui definimos caminhos de pastas e arquivos, e garantimos
que as pastas necessárias existam antes do programa rodar.
"""

import os
from pathlib import Path

# BASE_DIR aponta para a raiz do projeto (a pasta finance_app/).
# __file__ é o caminho deste arquivo (config.py).
# .resolve() converte para caminho absoluto.
# .parent sobe um nível na árvore de pastas.
BASE_DIR = Path(__file__).resolve().parent.parent

# Pastas principais.
# DATA_DIR pode ser sobrescrita pela variável de ambiente DATA_DIR. Em produção
# (Render), apontamos para um DISCO PERSISTENTE (ex.: /var/data) para que o
# banco SQLite sobreviva a reinícios/deploys. Em local, fica em ./data.
_data_dir_env = os.getenv("DATA_DIR")
DATA_DIR = Path(_data_dir_env) if _data_dir_env else (BASE_DIR / "data")
EXPORTS_DIR = DATA_DIR / "exports"
CHARTS_DIR = DATA_DIR / "charts"
LOGS_DIR = BASE_DIR / "logs"

# Arquivos
DATABASE_PATH = DATA_DIR / "database.db"
LOG_FILE = LOGS_DIR / "app.log"


def ensure_directories() -> None:
    """
    Cria as pastas necessárias caso ainda não existam.
    
    exist_ok=True evita erro caso a pasta já exista.
    parents=True cria pastas-pai também (ex: data/exports cria data/ junto).
    """
    for directory in (DATA_DIR, EXPORTS_DIR, CHARTS_DIR, LOGS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
