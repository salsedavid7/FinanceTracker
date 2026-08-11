"""
Data models for FinanceTracker.

Plain classes (dataclasses), not an ORM -- keeps the mapping between Python
objects and the tables in schema.sql obvious. dataclasses just remove the
boilerplate of writing __init__ by hand for simple "bag of fields" classes.
"""

from dataclasses import dataclass
from typing import Optional
import hashlib


@dataclass
class Account:
    name: str
    account_type: str
    owner_id: str = "david"  # single-user app; kept only because schema still has the column
    id: Optional[int] = None


@dataclass
class CategoryRule:
    """Maps a substring found in a raw transaction description to a category name."""
    pattern: str    # matched case-insensitively as a substring of the description
    category: str


@dataclass
class Transaction:
    account_id: int
    txn_date: str            # ISO format, e.g. '2026-07-05'
    description: str
    amount: float
    txn_type: Optional[str] = None
    category_id: Optional[int] = None
    counterparty_id: Optional[int] = None
    id: Optional[int] = None

    def import_hash(self) -> str:
        """
        Deterministic fingerprint used to detect duplicate imports: same
        account + date + amount + description always produces the same hash.
        This is what schema.sql's UNIQUE constraint on import_hash enforces --
        re-running ingest.py against a CSV you've already imported is a no-op.
        """
        raw = f"{self.account_id}|{self.txn_date}|{self.amount}|{self.description}"
        return hashlib.sha256(raw.encode()).hexdigest()
