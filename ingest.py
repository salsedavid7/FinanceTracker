"""
Full ingestion pipeline:
  1. Read every CSV in data/
  2. Normalize each row into a Transaction
  3. Categorize it (simple substring rules)
  4. Load into SQLite, de-duplicating on import_hash so re-running this
     against a file you've already imported doesn't create duplicate rows.
"""

from pathlib import Path
import csv

from models import Transaction
from categorize import categorize
from counterparty import extract_counterparty
from db import (
    get_connection,
    init_db,
    get_or_create_account,
    get_or_create_category,
    get_or_create_counterparty,
    insert_transaction,
)

DATA_DIR = Path(__file__).parent / "data"
ACCOUNT_NAME = "Chase Checking"   # hardcoded single account for now -- multi-account is a later step
ACCOUNT_TYPE = "checking"


def load_csv_rows(csv_path: Path):
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def main():
    conn = get_connection()
    init_db(conn)

    account_id = get_or_create_account(conn, ACCOUNT_NAME, ACCOUNT_TYPE)

    inserted = 0
    skipped = 0

    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {DATA_DIR}")
        return

    for csv_path in csv_files:
        for row in load_csv_rows(csv_path):
            description = row["Description"]
            category_name = categorize(description)
            category_id = get_or_create_category(conn, category_name)

            counterparty_name = extract_counterparty(description)
            counterparty_id = get_or_create_counterparty(conn, counterparty_name) if counterparty_name else None

            txn = Transaction(
                account_id=account_id,
                txn_date=row["Date"],
                description=description,
                amount=float(row["Amount"]),
                category_id=category_id,
                counterparty_id=counterparty_id,
            )

            if insert_transaction(conn, txn):
                inserted += 1
            else:
                skipped += 1

    print(f"Inserted {inserted} new transactions, skipped {skipped} duplicates.")
    conn.close()


if __name__ == "__main__":
    main()
