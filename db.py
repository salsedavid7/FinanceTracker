"""
SQLite connection, schema bootstrap, and insert/dedupe helpers.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "finance.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """
    Open a connection AND guarantee the schema is fully up to date --
    tables created, pending migrations applied -- before handing it back.

    This used to be two separate steps (get_connection(), then a caller
    had to remember to also call init_db()). That was the actual root
    cause of a real bug: reextract_counterparties.py called only
    get_connection() and crashed with "no such column: counterparty_id"
    on a database that hadn't been migrated yet, because nothing forced
    init_db() to run. Folding the guarantee into get_connection() itself
    means every caller gets a correct connection automatically -- there's
    no second step left to forget. init_db() is kept below as a public
    function too (existing callers that call it explicitly still work
    fine; it's just redundant now, and cheap to run twice).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores FK constraints unless told to enforce them
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables from schema.sql if they don't already exist, then apply
    any pending migrations (see MIGRATIONS below). Safe to call every run."""
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    _apply_migrations(conn)


# Each entry exists because a column was added to schema.sql *after* some
# copy of finance.db already had that table created -- CREATE TABLE IF NOT
# EXISTS only creates missing tables, it never adds columns to a table
# that's already there. This list is a minimal hand-written version of
# what real migration tools (Alembic, dbt migrations, etc.) automate: a
# record of "what changed, in what order," applied once each, skipped if
# already applied. (table, column, SQLite column type)
MIGRATIONS = [
    ("accounts", "plaid_item_id", "INTEGER"),
    ("accounts", "plaid_account_id", "TEXT"),
    ("transactions", "counterparty_id", "INTEGER"),
    ("accounts", "current_balance", "REAL"),
    ("accounts", "available_balance", "REAL"),
    ("accounts", "balance_updated_at", "TEXT"),
    ("transactions", "is_joint_payment", "INTEGER NOT NULL DEFAULT 0"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, column, column_type in MIGRATIONS:
        # PRAGMA table_info returns one row per existing column; row[1] is
        # the column name. table/column here are hardcoded in MIGRATIONS
        # above, not user input, so building this string directly (rather
        # than with a `?` placeholder, which only works for values, never
        # for table/column names) is safe.
        existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
            conn.commit()


def get_or_create_account(conn: sqlite3.Connection, name: str, account_type: str, owner_id: str = "david") -> int:
    cur = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO accounts (name, account_type, owner_id) VALUES (?, ?, ?)",
        (name, account_type, owner_id),
    )
    conn.commit()
    return cur.lastrowid


def get_or_create_category(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("SELECT id FROM categories WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def get_or_create_counterparty(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("SELECT id FROM counterparties WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO counterparties (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def update_account_balance(
    conn: sqlite3.Connection,
    plaid_account_id: str,
    current_balance: float,
    available_balance: float,
) -> None:
    """Store the latest bank-reported balance for one Plaid-linked account.
    Matches on plaid_account_id (Plaid's own identifier), not our internal
    id, since that's what callers get back from Plaid's API."""
    conn.execute(
        """
        UPDATE accounts
        SET current_balance = ?, available_balance = ?, balance_updated_at = CURRENT_TIMESTAMP
        WHERE plaid_account_id = ?
        """,
        (current_balance, available_balance, plaid_account_id),
    )
    conn.commit()


def set_joint_payment(conn: sqlite3.Connection, transaction_id: int, is_joint: bool) -> bool:
    """Toggle the manually-set is_joint_payment flag on one transaction.
    Returns False if no transaction with that id exists."""
    cur = conn.execute(
        "UPDATE transactions SET is_joint_payment = ? WHERE id = ?",
        (1 if is_joint else 0, transaction_id),
    )
    conn.commit()
    return cur.rowcount > 0


def insert_transaction(conn: sqlite3.Connection, txn) -> bool:
    """
    Insert a transaction. Returns False (no-op) instead of raising if
    import_hash already exists -- i.e. this exact row was already imported.
    """
    try:
        conn.execute(
            """
            INSERT INTO transactions
                (account_id, category_id, counterparty_id, txn_date, description, amount, txn_type, import_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                txn.account_id,
                txn.category_id,
                txn.counterparty_id,
                txn.txn_date,
                txn.description,
                txn.amount,
                txn.txn_type,
                txn.import_hash(),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # UNIQUE constraint on import_hash tripped -> duplicate, not a real error
        return False
