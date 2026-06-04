"""
Pacote da API REST (FastAPI).

Esta é apenas mais uma INTERFACE do projeto — irmã da CLI
(`app/interfaces/cli.py`) e do Streamlit (`app/interfaces/streamlit_app.py`).

Princípio que não muda: a API só recebe requisições HTTP, chama os
services e devolve JSON. Nenhum SQL, nenhum cálculo de saldo aqui.
Toda a regra de negócio continua em services/, repositories/ e models/.
"""
