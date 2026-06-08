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

import os

import uvicorn

if __name__ == "__main__":
    # Em desenvolvimento (na sua máquina) os padrões valem: 127.0.0.1:8000
    # com reload ligado. Em produção (Render), estas variáveis de ambiente
    # mudam o comportamento sem alterar o código:
    #   HOST=0.0.0.0   -> aceita conexões de fora (obrigatório no Render)
    #   PORT=...       -> o Render injeta a porta automaticamente
    #   RELOAD=false   -> sem auto-reload em produção
    uvicorn.run(
        "app.api.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "true").lower() == "true",
    )
