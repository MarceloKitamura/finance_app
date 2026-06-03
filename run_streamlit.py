"""
Launcher do Streamlit.

Streamlit precisa de um arquivo Python como entrypoint. Este arquivo
importa a app de verdade (app/interfaces/streamlit_app.py) e chama main().

Como executar:
    streamlit run run_streamlit.py

Ou com mais opções:
    streamlit run run_streamlit.py --logger.level=debug

Por que não chamar app/interfaces/streamlit_app.py diretamente?
Porque o arquivo precisa estar na raiz ou em um lugar que Streamlit
consegue encontrar facilmente. Deixar em app/interfaces/ fica mais limpo.
"""

import sys
from pathlib import Path

# Adiciona o diretório do projeto ao path do Python.
sys.path.insert(0, str(Path(__file__).parent))

from app.interfaces.streamlit_app import main

if __name__ == "__main__":
    main()
