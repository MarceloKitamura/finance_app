"""
Carregador simples do arquivo .env (sem dependências externas).

Por que existe: o projeto guarda as chaves de IA (GROQ_API_KEY, OPENAI_API_KEY)
no arquivo .env da raiz, mas evita o pacote python-dotenv. Antes, o .env só era
lido dentro do financial_advisor_service — então o ai_service (categorização via
OpenAI) dependia da ORDEM de import para enxergar a chave, e em CLI/testes podia
nem carregar. Centralizar aqui garante que qualquer service que precise de uma
chave chame load_env_file() e a encontre, não importa por onde o app começou.

Regras (iguais às de antes):
- Variáveis já presentes no ambiente têm prioridade (os.environ.setdefault):
  o .env nunca sobrescreve o que já foi exportado pelo sistema/deploy.
- Idempotente: lê o arquivo uma única vez por processo.
- Tolerante a falhas: sem .env (ou ilegível), segue sem erro — a IA é opcional.
"""

import os
from pathlib import Path

# Raiz do projeto: utils/env.py -> app/ -> raiz (2 níveis acima).
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

_loaded = False


def load_env_file() -> None:
    """Lê o .env da raiz e popula os.environ (só na 1ª chamada do processo)."""
    global _loaded
    if _loaded:
        return
    _loaded = True  # marca antes para não reprocessar mesmo se der erro.

    if not _ENV_PATH.exists():
        return
    try:
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # Ignora linhas vazias, comentários e linhas sem "=".
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            # Tira espaços e aspas que às vezes envolvem o valor.
            value = value.strip().strip('"').strip("'").strip()
            if key:
                os.environ.setdefault(key, value)
    except OSError:
        # Sem .env legível seguimos sem as chaves — não é erro fatal.
        pass
