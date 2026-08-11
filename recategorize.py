"""
Re-applies categorize.py's current rules to every existing transaction.

Categorization happens once, at import/sync time, and is written into
category_id -- so updating the RULES list in categorize.py only affects
transactions synced from that point forward. Run this any time you add or
change a categorization rule and want it applied retroactively to
everything already sitting in finance.db.
"""

from categorize import categorize
from db import get_connection, get_or_create_category


def main():
    conn = get_connection()

    rows = conn.execute("SELECT id, description FROM transactions").fetchall()

    updated = 0
    for txn_id, description in rows:
        category_name = categorize(description)
        category_id = get_or_create_category(conn, category_name)

        conn.execute(
            "UPDATE transactions SET category_id = ? WHERE id = ?",
            (category_id, txn_id),
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"Re-categorized {updated} transactions.")


if __name__ == "__main__":
    main()
