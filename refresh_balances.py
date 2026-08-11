"""
Re-pulls current account balances from Plaid for every already-connected
bank (every row in plaid_items) and updates accounts.current_balance /
available_balance / balance_updated_at.

Why this needs to exist separately from app.py: app.py only captures a
balance once, at the moment you connect a bank via Link. Balances change
constantly (every purchase moves them) but the Link handshake doesn't
repeat, so without this script the dashboard's "Current Checking Balance"
and "Total Debt" cards would go stale the day after you connect. Run this
alongside plaid_sync.py -- sync pulls new transactions, this refreshes
the balance snapshot -- same "re-runnable enrichment step" pattern as
recategorize.py.

NOTE: unlike the rest of this project's business logic, this file hasn't
been run against a live Plaid connection yet -- I don't have your .env
credentials, so I can't call Plaid myself to verify it end-to-end. The
account-matching logic (plaid_account_id) and the balances dict shape
(acct["balances"]["current"/"available"]) both match Plaid's documented
AccountsGetResponse though, and mirror what app.py already does at
connect time. Worth running once and eyeballing the printed balances
before trusting the dashboard cards.
"""

from db import get_connection, update_account_balance
import plaid_client


def main():
    conn = get_connection()

    plaid_items = conn.execute("SELECT id, item_id, access_token, institution_name FROM plaid_items").fetchall()
    if not plaid_items:
        print("No connected Plaid items yet -- run app.py and connect a bank first.")
        return

    updated = 0
    for item_id_row, item_id, access_token, institution_name in plaid_items:
        accounts = plaid_client.get_accounts(access_token)
        for acct in accounts:
            balances = acct["balances"]
            update_account_balance(
                conn,
                plaid_account_id=acct["account_id"],
                current_balance=balances["current"],
                available_balance=balances["available"],
            )
            updated += 1
            print(f"  {acct['name']}: current={balances['current']}, available={balances['available']}")

    conn.close()
    print(f"Refreshed balances for {updated} account(s).")


if __name__ == "__main__":
    main()
