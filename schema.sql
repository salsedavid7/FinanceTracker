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

    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id)
);
