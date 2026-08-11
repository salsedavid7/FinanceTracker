"""
Local-only visual dashboard: spend by category, cash flow over time, top
merchants, recurring charges -- the same numbers report.py prints to your
terminal, now as charts.

Kept as its own file/Flask app rather than folded into app.py -- app.py's
whole job is the Plaid Link handshake (see its own docstring: "This is NOT
meant to be a dashboard"). This file's only job is "render what's already
in finance.db." Same single-responsibility pattern as the rest of the
codebase: one file, one job.

Run with `python3 dashboard.py`, then open http://localhost:5001.
Uses a different port than app.py (5000) so both could theoretically run
at once, though you won't normally need to.
"""

import sqlite3

from flask import Flask, render_template, jsonify, request

from db import get_connection, set_joint_payment
from report import (
    load_transactions,
    spend_by_category,
    monthly_net,
    top_merchants,
    recurring_candidates,
    filter_date_range,
    summary_totals,
    p2p_by_recipient,
    p2p_debt_by_recipient,
    previous_month_summary,
    account_summary,
    data_as_of,
)

app = Flask(__name__)

OWNER_NAME = "David"  # single-user app -- same pattern as owner_id="david" already in the schema


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/data")
def data():
    """
    Powers the charts AND the summary KPI cards. Accepts optional
    start_date/end_date query params -- when present, every *chart* number
    returned is scoped to that range, so the charts reflect one consistent
    time window. account_summary (real bank balances) and previous_month
    (always literally last calendar month) intentionally ignore the date
    filter -- "what's my checking balance right now" and "what did I
    spend last month" aren't questions a date-range picker should change.

    Also accepts include_p2p ("true"/"false", default false) -- toggles
    whether Zelle/Venmo/etc payments count toward top_merchants.
    """
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    include_p2p = request.args.get("include_p2p", "false").strip().lower() == "true"

    full_df = load_transactions()
    df = filter_date_range(full_df, start_date, end_date)

    empty_response = {
        "categories": {"labels": [], "values": []},
        "monthly_net": {"labels": [], "values": []},
        "top_merchants": {"labels": [], "values": []},
        "p2p_by_recipient": {"labels": [], "values": []},
        "p2p_debt": [],
        "recurring": [],
        "summary": {"income": 0, "spend": 0, "net": 0},
        "previous_month": previous_month_summary(full_df),
        "account_summary": account_summary(),
        "data_as_of": data_as_of(full_df),
        "owner_name": OWNER_NAME,
    }

    if df.empty:
        return jsonify(empty_response)

    category = spend_by_category(df)
    monthly = monthly_net(df)
    merchants = top_merchants(df, n=8, include_p2p=include_p2p)
    p2p_recipients = p2p_by_recipient(df, n=8)
    p2p_debt = p2p_debt_by_recipient(df)
    # Capped at 20 here (not just relying on the frontend slider) so a
    # long transaction history doesn't ship an unbounded list over the
    # wire -- the slider on the dashboard defaults to showing 5 of these.
    recurring = recurring_candidates(df).head(20)
    summary = summary_totals(df)

    return jsonify({
        "categories": {
            "labels": category.index.tolist(),
            "values": category.round(2).tolist(),
        },
        # PeriodIndex (e.g. 2026-07) isn't JSON-serializable directly --
        # convert each period to its string form first.
        "monthly_net": {
            "labels": [str(period) for period in monthly.index],
            "values": monthly.round(2).tolist(),
        },
        "top_merchants": {
            "labels": merchants.index.tolist(),
            "values": merchants.round(2).tolist(),
        },
        "p2p_by_recipient": {
            "labels": p2p_recipients.index.tolist(),
            "values": p2p_recipients.round(2).tolist(),
        },
        "p2p_debt": p2p_debt,
        "recurring": [
            {"description": desc, "count": int(count)}
            for desc, count in recurring.items()
        ],
        "summary": summary,
        "previous_month": previous_month_summary(full_df),
        "account_summary": account_summary(),
        "data_as_of": data_as_of(full_df),
        "owner_name": OWNER_NAME,
    })


@app.route("/api/filters")
def filters():
    """Distinct category/account/counterparty names, to populate the search dropdowns."""
    conn = get_connection()
    categories = [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY name")]
    accounts = [r[0] for r in conn.execute("SELECT name FROM accounts ORDER BY name")]
    counterparties = [r[0] for r in conn.execute("SELECT name FROM counterparties ORDER BY name")]
    conn.close()
    return jsonify({"categories": categories, "accounts": accounts, "counterparties": counterparties})


@app.route("/api/transactions")
def transactions():
    """
    Searchable transaction lookup. All filters are optional and combine
    with AND. Every value is passed as a bound parameter (the `?`
    placeholders below) rather than pasted into the SQL string directly --
    that's what prevents SQL injection from whatever a user (here, just
    you) types into the search box. Never build a query with an f-string
    containing raw user input.
    """
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    account = request.args.get("account", "").strip()
    counterparty = request.args.get("counterparty", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    conn = get_connection()
    conn.row_factory = sqlite3.Row

    query = """
        SELECT
            t.id,
            t.txn_date,
            t.description,
            t.amount,
            c.name AS category,
            a.name AS account,
            cp.name AS counterparty,
            t.is_joint_payment
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN counterparties cp ON t.counterparty_id = cp.id
        WHERE 1 = 1
    """
    params = []

    if q:
        query += " AND (t.description LIKE ? OR cp.name LIKE ?)"
        like = f"%{q}%"
        params += [like, like]
    if category:
        query += " AND c.name = ?"
        params.append(category)
    if account:
        query += " AND a.name = ?"
        params.append(account)
    if counterparty:
        query += " AND cp.name = ?"
        params.append(counterparty)
    if start_date:
        query += " AND t.txn_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND t.txn_date <= ?"
        params.append(end_date)

    query += " ORDER BY t.txn_date DESC LIMIT 500"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])


@app.route("/api/transactions/<int:transaction_id>/joint", methods=["POST"])
def toggle_joint_payment(transaction_id):
    """
    Manually flip a transaction's is_joint_payment flag. Body: {"is_joint": true|false}.
    This is the write side of the P2P Payment Debt feature -- see
    report.p2p_debt_by_recipient's docstring for what the flag does and
    doesn't compute today.
    """
    is_joint = bool(request.json.get("is_joint", False))
    conn = get_connection()
    found = set_joint_payment(conn, transaction_id, is_joint)
    conn.close()

    if not found:
        return jsonify({"error": "transaction not found"}), 404
    return jsonify({"id": transaction_id, "is_joint_payment": is_joint})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
