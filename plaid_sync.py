"""
Sync transactions from Plaid into the same SQLite database and pipeline
that CSV imports use -- Plaid becomes a second data source alongside
data/*.csv, both flowing through the same insert_transaction/dedupe path.

Uses /transactions/sync (Plaid's current recommended endpoint), which is
incremental: each connected bank (Plaid "Item") has a stored cursor
marking how far we've already synced, so re-running this script only
pulls new/changed transactions instead of re-fetching everything.

IMPORTANT sign convention note: Plaid reports a transaction's amount as
POSITIVE when money leaves your account (a purchase) and NEGATIVE when
money comes in (a deposit/refund) -- the opposite of the convention this
project's schema uses (negative = money out, positive = money in, matching
how a plain-English bank statement reads). This script flips the sign on
the way in so everything downstream (report.py, categorize.py) works
identically regardless of whether a transaction came from a CSV or Plaid.
"""

from plaid.model.transactions_sync_request import TransactionsSyncRequest

from plaid_client import client
from models import Transaction
from categorize import categorize
from counterparty import extract_counterparty
from db import (
    get_connection,
    init_db,
    get_or_create_category,
    get_or_create_counterparty,
    insert_transaction,
)


def get_plaid_items(conn):
    """All connected bank connections (Plaid Items) stored so far."""
    cur = conn.execute("SELECT id, item_id, access_token, cursor FROM plaid_items")
    return cur.fetchall()


def get_account_id_for_plaid_account(conn, plaid_account_id: str):
    cur = conn.execute(
        "SELECT id FROM accounts WHERE plaid_account_id = ?", (plaid_account_id,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def sync_item(conn, plaid_item_row_id: int, access_token: str, cursor: str) -> int:
    """
    Pull every new/changed transaction for one Item since the last sync
    (or from the beginning, if cursor is None), and load them via the
    same insert_transaction/dedupe path the CSV pipeline uses.
    """
    added_count = 0
    has_more = True

    while has_more:
        request = TransactionsSyncRequest(access_token=access_token, cursor=cursor) \
            if cursor else TransactionsSyncRequest(access_token=access_token)

        response = client.transactions_sync(request)

        for txn in response["added"]:
            account_id = get_account_id_for_plaid_account(conn, txn["account_id"])
            if account_id is None:
                # Shouldn't normally happen -- every Plaid account is created
                # during the Link exchange step in app.py.
                continue

            category_name = categorize(txn["name"])
            category_id = get_or_create_category(conn, category_name)

            counterparty_name = extract_counterparty(txn["name"])
            counterparty_id = get_or_create_counterparty(conn, counterparty_name) if counterparty_name else None

            transaction = Transaction(
                account_id=account_id,
                txn_date=str(txn["date"]),
                description=txn["name"],
                amount=-float(txn["amount"]),  # flip sign -- see module docstring
                category_id=category_id,
                counterparty_id=counterparty_id,
            )

            if insert_transaction(conn, transaction):
                added_count += 1

        cursor = response["next_cursor"]
        has_more = response["has_more"]

    # Persist the cursor so the next run only fetches what's new
    conn.execute("UPDATE plaid_items SET cursor = ? WHERE id = ?", (cursor, plaid_item_row_id))
    conn.commit()

    return added_count


def main():
    conn = get_connection()
    init_db(conn)

    items = get_plaid_items(conn)
    if not items:
        print("No connected Plaid accounts yet -- run app.py and connect one first.")
        return

    for plaid_item_row_id, item_id, access_token, cursor in items:
        added = sync_item(conn, plaid_item_row_id, access_token, cursor)
        print(f"Item {item_id}: {added} new transactions synced.")

    conn.close()


if __name__ == "__main__":
    main()
