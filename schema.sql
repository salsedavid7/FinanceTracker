-- Personal finance tracker schema
-- Inspired by github.com/NoPointExc/wealthAgent, redesigned for single-user
-- Python/SQLite use as a data engineering learning project.

CREATE TABLE IF NOT EXISTS plaid_items (
    id INTEGER PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE,       -- Plaid's identifier for this bank connection
    access_token TEXT NOT NULL,         -- used to call /transactions/sync etc for this item
    institution_name TEXT,
    cursor TEXT,                        -- /transactions/sync cursor, lets sync be incremental
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,   -- OPEN QUESTION: needed for a single-user app? revisit
    account_type TEXT NOT NULL,
    plaid_item_id INTEGER,              -- NULL for CSV-only accounts
    plaid_account_id TEXT UNIQUE,       -- Plaid's per-account identifier within an Item

    -- Real bank-reported balances, not derived from our own transaction
    -- ledger -- pulled from Plaid's /accounts/get (see plaid_client.get_accounts,
    -- refresh_balances.py). NULL for CSV-only accounts, since there's no API
    -- to ask for a live balance; the dashboard falls back to summing that
    -- account's own transactions when these are NULL.
    current_balance REAL,               -- checking/savings: cash in the account. Credit/loan: amount owed (positive)
    available_balance REAL,             -- Plaid's "available" balance (current minus holds), depository accounts only
    balance_updated_at TEXT,            -- when current_balance/available_balance were last refreshed from Plaid

    FOREIGN KEY (plaid_item_id) REFERENCES plaid_items(id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Person-to-person payment counterparties (Zelle/Venmo/PayPal/Cash App
-- recipients or senders), normalized the same way categories are: one
-- name lives in one place, rather than repeated free text on every row.
CREATE TABLE IF NOT EXISTS counterparties (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    category_id INTEGER,               -- nullable: raw imports start uncategorized
    counterparty_id INTEGER,           -- nullable: only set for recognized P2P payments
    txn_date TEXT NOT NULL,            -- ISO 8601, e.g. '2026-07-05'
    description TEXT NOT NULL,         -- raw bank description, never edited after import
    amount NUMERIC NOT NULL,           -- signed: negative = money out, positive = money in
    txn_type TEXT,                     -- e.g. 'purchase', 'refund', 'fee', 'transfer'
    import_hash TEXT NOT NULL UNIQUE,  -- dedupe key: hash(account_id + txn_date + amount + description)
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,

    -- Manually set by the user (not inferred) -- flags a transaction as a
    -- shared/joint expense, e.g. you paid the full restaurant bill but a
    -- friend owes half back. Deliberately just a flag for now, not a full
    -- expense-split system: it doesn't record WHO it's shared with or HOW
    -- MUCH they owe, since a joint charge (a restaurant bill) isn't itself
    -- a P2P transaction with a counterparty attached. See dashboard.py's
    -- p2p_debt logic for what this can and can't compute today.
    is_joint_payment INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id)
);
