"""
Minimal Flask app whose only job is the Plaid Link handshake:
  1. Serve a page that opens the Plaid Link widget (templates/link.html)
  2. Give that widget a link_token to start with
  3. Receive the public_token it returns and exchange it for a permanent
     access_token, then store the connected bank + its accounts in our
     own SQLite database.

This is NOT meant to be a dashboard -- report.py / the CLI stays the
daily driver. This server only needs to run while you're connecting a
new bank account.
"""

from flask import Flask, render_template, jsonify, request

import plaid_client
from db import get_connection, init_db, get_or_create_account

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("link.html")


@app.route("/api/create_link_token", methods=["POST"])
def create_link_token():
    link_token = plaid_client.create_link_token()
    return jsonify({"link_token": link_token})


@app.route("/api/exchange_public_token", methods=["POST"])
def exchange_public_token():
    public_token = request.json["public_token"]

    exchange_result = plaid_client.exchange_public_token(public_token)
    access_token = exchange_result["access_token"]
    item_id = exchange_result["item_id"]

    conn = get_connection()
    init_db(conn)

    # Store the Plaid Item (the bank connection itself)
    cur = conn.execute(
        "INSERT INTO plaid_items (item_id, access_token) VALUES (?, ?)",
        (item_id, access_token),
    )
    conn.commit()
    plaid_item_row_id = cur.lastrowid

    # Fetch the real accounts (checking, savings, credit card, ...) under
    # this Item and create matching rows in our own accounts table.
    plaid_accounts = plaid_client.get_accounts(access_token)
    created = []
    for acct in plaid_accounts:
        account_id = get_or_create_account(
            conn,
            name=acct["name"],
            account_type=str(acct["type"]),
        )
        conn.execute(
            "UPDATE accounts SET plaid_item_id = ?, plaid_account_id = ? WHERE id = ?",
            (plaid_item_row_id, acct["account_id"], account_id),
        )
        conn.commit()
        created.append(acct["name"])

    conn.close()
    return jsonify({"status": "connected", "accounts": created})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
