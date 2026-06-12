"""
Inicialização e conexão com o banco SQLite.

Este arquivo NÃO contém SQL de negócio (insert/select de transação).
Ele só gerencia:
- abertura da conexão;
- criação da tabela se não existir.

Quem precisa de SQL específico de transações usa o repository.
"""

import sqlite3
from sqlite3 import Connection

from app.config import DATABASE_PATH, ensure_directories


def get_connection() -> Connection:
    """
    Abre uma conexão com o banco SQLite e a retorna.

    row_factory = sqlite3.Row faz com que os resultados venham
    como dicionários (acessíveis por nome de coluna), em vez de tuplas.
    Isso facilita muito a vida no repository.
    """
    ensure_directories()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    """
    Cria a tabela transactions se ainda não existir.

    Esta função é idempotente: pode ser chamada várias vezes
    sem causar problemas (graças ao IF NOT EXISTS).
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        description TEXT NOT NULL,
        amount REAL NOT NULL CHECK (amount > 0),
        type TEXT NOT NULL CHECK (type IN ('receita', 'despesa')),
        category TEXT NOT NULL,
        payment_method TEXT NOT NULL,
        spent_by TEXT NOT NULL DEFAULT 'Eu',
        account TEXT NOT NULL DEFAULT 'Carteira',
        card TEXT NOT NULL DEFAULT '',
        payment_origin TEXT NOT NULL DEFAULT 'account',
        installment_no INTEGER NOT NULL DEFAULT 1,
        installments_total INTEGER NOT NULL DEFAULT 1,
        purchase_group TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    """

    # Tabela de contas/saldos (múltiplos saldos). O saldo ATUAL não fica
    # aqui — é calculado somando as transações (ver AccountService). Só o
    # saldo INICIAL e os metadados de exibição são persistidos.
    create_accounts_sql = """
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL DEFAULT 'outro',
        initial_balance REAL NOT NULL DEFAULT 0,
        color TEXT NOT NULL DEFAULT '#3B82F6',
        icon TEXT NOT NULL DEFAULT '💰',
        created_at TEXT NOT NULL
    );
    """

    # Tabela de metas financeiras. O progresso é calculado (limite_gasto) ou
    # informado manualmente (poupanca/divida) — ver GoalService.
    create_goals_sql = """
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'poupanca',
        target_amount REAL NOT NULL DEFAULT 0,
        category TEXT NOT NULL DEFAULT '',
        start_date TEXT NOT NULL DEFAULT '',
        end_date TEXT NOT NULL DEFAULT '',
        current_amount REAL NOT NULL DEFAULT 0,
        color TEXT NOT NULL DEFAULT '#10B981',
        created_at TEXT NOT NULL
    );
    """

    # Tabela de cartões de crédito. O saldo devedor/fatura é calculado a
    # partir das despesas lançadas no cartão (ver CardService).
    create_cards_sql = """
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        brand TEXT NOT NULL DEFAULT 'Outra',
        limit_total REAL NOT NULL DEFAULT 0,
        closing_day INTEGER NOT NULL DEFAULT 1,
        due_day INTEGER NOT NULL DEFAULT 10,
        color TEXT NOT NULL DEFAULT '#8B5CF6',
        status TEXT NOT NULL DEFAULT 'ativo',
        created_at TEXT NOT NULL
    );
    """

    # Tabela de gastos recorrentes (templates salvos pelo usuário). Espelha
    # os campos de uma transação + dia esperado da cobrança (Fase 3).
    create_recurring_sql = """
    CREATE TABLE IF NOT EXISTS recurring_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT NOT NULL,
        amount REAL NOT NULL CHECK (amount > 0),
        type TEXT NOT NULL DEFAULT 'despesa',
        category TEXT NOT NULL DEFAULT '',
        payment_method TEXT NOT NULL DEFAULT 'Outros',
        spent_by TEXT NOT NULL DEFAULT 'Eu',
        account TEXT NOT NULL DEFAULT 'Carteira',
        card TEXT NOT NULL DEFAULT '',
        day_of_month INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """

    # Tabela genérica de configurações (chave -> valor JSON). Hoje guarda a
    # configuração de salário (chave "salary_config"); ver SettingsRepository.
    # Usar JSON evita criar uma coluna/tabela nova a cada preferência futura.
    create_settings_sql = """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    );
    """

    # Tabela da agenda de vencimentos / fluxo de caixa (Fase 3).
    create_vencimentos_sql = """
    CREATE TABLE IF NOT EXISTS vencimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        due_date TEXT NOT NULL,
        amount REAL NOT NULL DEFAULT 0,
        kind TEXT NOT NULL DEFAULT 'conta',
        status TEXT NOT NULL DEFAULT 'pendente',
        notify_days INTEGER NOT NULL DEFAULT 3,
        recurrence TEXT NOT NULL DEFAULT 'unica',
        category TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        paid_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    """

    # Usar "with conn" garante commit automático em sucesso
    # e rollback em caso de erro. Conexão é fechada no final do bloco.
    with get_connection() as conn:
        conn.execute(create_table_sql)
        conn.execute(create_accounts_sql)
        conn.execute(create_cards_sql)
        conn.execute(create_goals_sql)
        conn.execute(create_recurring_sql)
        conn.execute(create_vencimentos_sql)
        conn.execute(create_settings_sql)
        _run_migrations(conn)
        _seed_default_account(conn)


def _run_migrations(conn: Connection) -> None:
    """
    Aplica ajustes de esquema em bancos que JÁ existem.

    O CREATE TABLE acima só roda na primeira vez (IF NOT EXISTS).
    Para quem já tinha um banco antigo, precisamos adicionar as
    colunas novas manualmente, sem perder os dados existentes.

    Cada migração é idempotente: checamos se a coluna já existe
    antes de tentar criá-la.
    """
    # PRAGMA table_info devolve uma linha por coluna; o nome fica em row["name"].
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(transactions)")
    }

    if "spent_by" not in existing_columns:
        # Em transações antigas não sabíamos quem gastou, então assumimos "Eu".
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN spent_by TEXT NOT NULL DEFAULT 'Eu'"
        )

    if "account" not in existing_columns:
        # Transações antigas não tinham conta: caem na conta padrão "Carteira".
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN account TEXT NOT NULL DEFAULT 'Carteira'"
        )

    if "card" not in existing_columns:
        # Transações antigas não tinham cartão associado (string vazia).
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN card TEXT NOT NULL DEFAULT ''"
        )

    # --- Origem do pagamento (conta x cartão) + parcelamento ---
    if "payment_origin" not in existing_columns:
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN payment_origin TEXT NOT NULL DEFAULT 'account'"
        )
        # Backfill: transações antigas com cartão preenchido eram, na prática,
        # gastos no cartão. Marcamos a origem como 'card' para que parem de
        # descontar do saldo da conta (novo comportamento correto). As demais
        # ficam como 'account' (padrão da coluna).
        conn.execute(
            "UPDATE transactions SET payment_origin = 'card' "
            "WHERE card IS NOT NULL AND card <> '' AND type = 'despesa'"
        )

    if "installment_no" not in existing_columns:
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN installment_no INTEGER NOT NULL DEFAULT 1"
        )

    if "installments_total" not in existing_columns:
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN installments_total INTEGER NOT NULL DEFAULT 1"
        )

    if "purchase_group" not in existing_columns:
        conn.execute(
            "ALTER TABLE transactions "
            "ADD COLUMN purchase_group TEXT NOT NULL DEFAULT ''"
        )


def _seed_default_account(conn: Connection) -> None:
    """Garante que exista ao menos uma conta (a "Carteira" padrão).

    Sem nenhuma conta, as transações antigas (migradas para 'Carteira')
    ficariam sem um card correspondente no dashboard. Criamos a conta
    padrão só se a tabela estiver vazia — nunca recriamos se o usuário já
    tem contas próprias.
    """
    from datetime import datetime

    row = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
    if row and row["n"] == 0:
        conn.execute(
            "INSERT INTO accounts (name, kind, initial_balance, color, icon, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "Carteira", "dinheiro", 0.0, "#10B981", "👛",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
