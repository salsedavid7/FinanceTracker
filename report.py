"""
Spend analysis / reporting layer -- the whole point of the project.
Reads straight out of SQLite into a pandas DataFrame and answers:
where does my money go, what's recurring, and how is cash flow trending.
"""

import pandas as pd

from db import get_connection, DB_PATH  # noqa: F401 -- DB_PATH re-exported for dashboard.py


def load_transactions() -> pd.DataFrame:
    # get_connection() (not a raw sqlite3.connect) guarantees tables exist
    # even on a completely fresh clone, before any script has run yet.
    conn = get_connection()
    query = """
        SELECT
            t.txn_date,
            t.description,
            t.amount,
            c.name AS category
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        ORDER BY t.txn_date
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df["txn_date"] = pd.to_datetime(df["txn_date"])
    return df


def _real_spend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rows that represent actual spending: money out, excluding transfers
    between your own accounts (credit card/loan payments funded from
    checking aren't spending -- they're just moving money you already
    counted as spent once, elsewhere).
    """
    spend = df[(df["amount"] < 0) & (df["category"] != "Transfer")].copy()
    spend["amount"] = spend["amount"].abs()
    return spend


def spend_by_category(df: pd.DataFrame) -> pd.Series:
    return _real_spend(df).groupby("category")["amount"].sum().sort_values(ascending=False)


def monthly_net(df: pd.DataFrame) -> pd.Series:
    return df.groupby(df["txn_date"].dt.to_period("M"))["amount"].sum()


def top_merchants(df: pd.DataFrame, n: int = 5) -> pd.Series:
    return _real_spend(df).groupby("description")["amount"].sum().sort_values(ascending=False).head(n)


def recurring_candidates(df: pd.DataFrame) -> pd.Series:
    """Merchants appearing 2+ times -- likely recurring charges/subscriptions."""
    counts = _real_spend(df).groupby("description").size()
    return counts[counts >= 2].sort_values(ascending=False)


def main():
    df = load_transactions()

    print("=== Spend by category ===")
    print(spend_by_category(df).round(2))

    print("\n=== Net cash flow by month ===")
    print(monthly_net(df).round(2))

    print("\n=== Top merchants by spend ===")
    print(top_merchants(df).round(2))

    print("\n=== Recurring merchants (2+ appearances) ===")
    print(recurring_candidates(df))


if __name__ == "__main__":
    main()
