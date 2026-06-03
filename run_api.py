"""
Launcher da API REST (FastAPI + Uvicorn).

Espelha o run_streamlit.py: um jeito simples de subir o servidor sem
decorar o comando do uvicorn.

Uso:
    python run_api.py

Depois abra http://127.0.0.1:8000/docs no navegador.

reload=True reinicia o servidor sozinho quando você salva um arquivo
.py — ótimo em desenvolvimento. Em produção, use reload=False.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
