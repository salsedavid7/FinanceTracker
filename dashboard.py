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

from db import get_connection
from report import (
    load_transactions,
    spend_by_category,
    monthly_net,
    top_merchants,
    recurring_candidates,
)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/data")
def data():
    df = load_transactions()

    if df.empty:
        return jsonify({
            "categories": {"labels": [], "values": []},
            "monthly_net": {"labels": [], "values": []},
            "top_merchants": {"labels": [], "values": []},
            "recurring": [],
        })

    category = spend_by_category(df)
    monthly = monthly_net(df)
    merchants = top_merchants(df, n=8)
    recurring = recurring_candidates(df)

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
        "recurring": [
            {"description": desc, "count": int(count)}
            for desc, count in recurring.items()
        ],
    })


@app.route("/api/filters")
def filters():
    """Distinct category/account names, to populate the search dropdowns."""
    conn = get_connection()
    categories = [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY name")]
    accounts = [r[0] for r in conn.execute("SELECT name FROM accounts ORDER BY name")]
    conn.close()
    return jsonify({"categories": categories, "accounts": accounts})


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
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    conn = get_connection()
    conn.row_factory = sqlite3.Row

    query = """
        SELECT
            t.txn_date,
            t.description,
            t.amount,
            c.name AS category,
            a.name AS account,
            cp.name AS counterparty
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


if __name__ == "__main__":
    app.run(debug=True, port=5001)
