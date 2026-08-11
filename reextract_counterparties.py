"""
Re-applies counterparty.py's current extraction patterns to every existing
transaction. Same reason recategorize.py exists: counterparty_id is set
once, at import/sync time -- updating counterparty.py's patterns only
affects transactions synced from that point forward. Run this any time you
add or fix a P2P pattern and want it applied retroactively.
"""

from counterparty import extract_counterparty
from db import get_connection, get_or_create_counterparty


def main():
    conn = get_connection()

    rows = conn.execute("SELECT id, description FROM transactions").fetchall()

    updated = 0
    for txn_id, description in rows:
        counterparty_name = extract_counterparty(description)
        counterparty_id = get_or_create_counterparty(conn, counterparty_name) if counterparty_name else None

        conn.execute(
            "UPDATE transactions SET counterparty_id = ? WHERE id = ?",
            (counterparty_id, txn_id),
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"Re-checked {updated} transactions for P2P counterparties.")


if __name__ == "__main__":
    main()
