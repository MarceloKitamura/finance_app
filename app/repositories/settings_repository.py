"""
Repository de configurações (key/value).

A camada repository é a ÚNICA que escreve SQL. Esta tabela `settings`
guarda configurações pontuais do app no formato chave -> valor JSON.
Usamos JSON para que uma configuração possa ter qualquer formato (um
número, uma lista, um objeto inteiro) sem precisar criar uma coluna nova
no banco a cada nova preferência.

Hoje o único uso é a configuração de salário (chave "salary_config"), mas
qualquer preferência futura (ex: moeda, tema padrão) pode reutilizar isto.
"""

import json
from datetime import datetime
from typing import Optional

from app.database import get_connection


class SettingsRepository:
    """Acesso a dados da tabela settings (chave/valor JSON)."""

    def get(self, key: str) -> Optional[dict]:
        """Lê o valor de uma chave e o desserializa de JSON.

        Retorna None se a chave não existe ou se o JSON estiver corrompido
        (nesse caso o chamador usa o padrão, sem quebrar).
        """
        sql = "SELECT value FROM settings WHERE key = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (key,)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value"])
        except (ValueError, TypeError):
            return None

    def get_updated_at(self, key: str) -> Optional[str]:
        """Devolve o carimbo de data/hora da última gravação da chave.

        Útil para invalidar caches (ex: o conselho da IA) quando a
        configuração muda sem que as transações mudem.
        """
        sql = "SELECT updated_at FROM settings WHERE key = ?"
        with get_connection() as conn:
            row = conn.execute(sql, (key,)).fetchone()
        return row["updated_at"] if row else None

    def set(self, key: str, value: dict) -> None:
        """Grava (cria ou atualiza) o valor de uma chave, serializado em JSON.

        Usa UPSERT (INSERT ... ON CONFLICT) para ser idempotente: se a chave
        já existe, atualiza; se não, cria.
        """
        payload = json.dumps(value, ensure_ascii=False)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                       updated_at = excluded.updated_at
        """
        with get_connection() as conn:
            conn.execute(sql, (key, payload, now))
