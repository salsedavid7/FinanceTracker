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
            c.name AS category,
            cp.name AS counterparty
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN counterparties cp ON t.counterparty_id = cp.id
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


def top_merchants(df: pd.DataFrame, n: int = 5, include_p2p: bool = False) -> pd.Series:
    """Biggest merchants by spend. P2P payments (Zelle/Venmo/etc) are
    excluded by default -- paying a friend back isn't really "a merchant,"
    and left in, a couple of frequent Zelle contacts can crowd out actual
    merchants. Pass include_p2p=True to fold them in anyway."""
    spend = _real_spend(df)
    if not include_p2p:
        spend = spend[spend["category"] != "P2P Payment"]
    return spend.groupby("description")["amount"].sum().sort_values(ascending=False).head(n)


def p2p_by_recipient(df: pd.DataFrame, n: int = 8) -> pd.Series:
    """Money sent to each Zelle/Venmo/etc recipient -- same shape as
    top_merchants, just scoped to outgoing P2P payments specifically."""
    p2p_out = df[(df["amount"] < 0) & (df["category"] == "P2P Payment")].copy()
    p2p_out["amount"] = p2p_out["amount"].abs()
    return p2p_out.groupby("counterparty")["amount"].sum().sort_values(ascending=False).head(n)


def p2p_debt_by_recipient(df: pd.DataFrame) -> list:
    """
    Net P2P flow per person: money sent to them minus money received from
    them, using only their actual Zelle/Venmo/etc history.

    Deliberately scoped to just that -- NOT a general "who owes me for
    what" ledger. is_joint_payment (see schema.sql) flags a transaction as
    a shared expense, but a joint restaurant charge isn't itself a P2P
    payment with a counterparty attached, so there's no reliable way yet
    to attribute a specific joint charge to a specific person or amount.
    What IS reliably computable from data we actually have: if you've sent
    a friend more via Zelle than they've sent back, that's a real signal
    they may owe you (or it was a one-way gift/expense) -- that's what
    this returns.
    """
    p2p = df[df["category"] == "P2P Payment"].dropna(subset=["counterparty"])
    if p2p.empty:
        return []

    net = p2p.groupby("counterparty")["amount"].sum().sort_values()
    results = []
    for name, amount in net.items():
        amount = round(float(amount), 2)
        if amount < 0:
            status = "owes_you"  # you've sent them more than they've sent back
        elif amount > 0:
            status = "you_owe"   # they've sent you more than you've sent back
        else:
            status = "settled"
        results.append({"counterparty": name, "net_amount": amount, "status": status})
    return results


def previous_month_summary(df: pd.DataFrame, as_of=None) -> dict:
    """Income and spend for the calendar month before `as_of` (default:
    today) -- e.g. run this in August, get all of July."""
    as_of = pd.Timestamp.now() if as_of is None else pd.Timestamp(as_of)
    first_of_this_month = as_of.replace(day=1)
    last_month_end = first_of_this_month - pd.Timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    month_df = df[(df["txn_date"] >= last_month_start) & (df["txn_date"] <= last_month_end)]
    totals = summary_totals(month_df)
    return {
        "income": totals["income"],
        "spend": totals["spend"],
        "label": last_month_start.strftime("%B %Y"),
    }


def account_summary() -> dict:
    """
    Checking balance + total debt, sourced from accounts.current_balance
    (real bank-reported balances via Plaid -- see refresh_balances.py),
    NOT derived from summing transactions, since the transaction ledger
    here is only ever a partial view (whatever's been imported/synced) and
    can lag or miss pending activity that a live balance already reflects.

    Exception: CSV-only accounts have no Plaid connection, so there's no
    API to ask for a live balance -- current_balance stays NULL for those.
    For those specifically, this falls back to summing that account's own
    transactions as a best-effort estimate (labeled as such in the
    response), so the demo/CSV-only path still shows a real number instead
    of $0.
    """
    conn = get_connection()
    accounts = conn.execute(
        "SELECT id, name, account_type, current_balance FROM accounts"
    ).fetchall()

    checking_balance = 0.0
    total_debt = 0.0
    estimated_any = False

    for account_id, name, account_type, current_balance in accounts:
        account_type_lower = (account_type or "").lower()
        is_debt_type = "credit" in account_type_lower or "loan" in account_type_lower

        if current_balance is None:
            # No Plaid balance on file -- fall back to net of this
            # account's own transactions as a rough estimate.
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            current_balance = row[0]
            estimated_any = True

        if is_debt_type:
            total_debt += current_balance
        else:
            checking_balance += current_balance

    account_count = len(accounts)
    conn.close()

    return {
        "checking_balance": round(float(checking_balance), 2),
        "total_debt": round(float(total_debt), 2),
        "account_count": account_count,
        "balance_is_estimated": estimated_any,
    }


def data_as_of(df: pd.DataFrame) -> str:
    """Freshness indicator for the header -- the date of the most recent
    transaction currently in the database, which is a more honest "data as
    of" than a sync timestamp would be (a sync can succeed and still only
    pull data through a few days ago, depending on the bank)."""
    if df.empty:
        return ""
    return df["txn_date"].max().strftime("%Y-%m-%d")


def recurring_candidates(df: pd.DataFrame) -> pd.Series:
    """Merchants appearing 2+ times -- likely recurring charges/subscriptions."""
    counts = _real_spend(df).groupby("description").size()
    return counts[counts >= 2].sort_values(ascending=False)


def filter_date_range(df: pd.DataFrame, start_date: str = "", end_date: str = "") -> pd.DataFrame:
    """Narrow a transactions DataFrame to [start_date, end_date], inclusive.
    Either bound can be blank/omitted to mean "no limit" on that side."""
    if start_date:
        df = df[df["txn_date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["txn_date"] <= pd.to_datetime(end_date)]
    return df


def summary_totals(df: pd.DataFrame) -> dict:
    """Total income, total real spend, and net cash flow for whatever
    date range df has already been filtered to."""
    income = df[df["amount"] > 0]["amount"].sum()
    spend = _real_spend(df)["amount"].sum()
    net = df["amount"].sum()
    return {"income": round(float(income), 2), "spend": round(float(spend), 2), "net": round(float(net), 2)}


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
