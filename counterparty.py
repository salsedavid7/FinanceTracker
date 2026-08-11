"""
Extracts the "other party" in a transaction from its raw description, when
recognizable -- either a person (Zelle/Venmo/PayPal/Cash App) or a company
(ACH debits/credits that surface a NACHA "ORIG CO NAME" field, e.g. paying
a credit card bill by bank transfer). Mirrors categorize.py's shape: same
idea, different target field. "Counterparty" is used broadly here to mean
either kind -- both get stored in the same counterparties table, since the
underlying question ("who specifically was on the other end of this
transaction") is the same one whether it's a person or a business.

IMPORTANT, verified before writing this: Plaid's Sandbox data contains NO
P2P or ACH-company transactions at all (checked every distinct description
in finance.db). So all patterns here are written from general knowledge of
common bank description formats, NOT validated against real examples.
Treat this as a first draft: once real transactions of these kinds flow
through from an actual bank account, check what extract_counterparty()
returns None for that should have matched, and add/fix a pattern.
"""

import re
from typing import Optional

# Each pattern must have exactly one capture group: the counterparty's name.
# Ordered roughly most-specific to least-specific.
PATTERNS = [
    # Person-to-person (Zelle, Venmo, PayPal, Cash App)
    re.compile(r"^ZELLE PAYMENT (?:TO|FROM)\s+(.+?)(?:\s+\d{1,2}/\d{1,2}.*)?$", re.IGNORECASE),
    re.compile(r"^ZELLE (?:TO|FROM)\s+(.+?)(?:\s+\d{1,2}/\d{1,2}.*)?$", re.IGNORECASE),
    re.compile(r"^VENMO(?:\s+PAYMENT)?(?:\s+(?:TO|FROM))?\s+(.+)$", re.IGNORECASE),
    re.compile(r"^PAYPAL\s*\*\s*(.+)$", re.IGNORECASE),
    re.compile(r"^CASH\s?APP\s*\*\s*(.+)$", re.IGNORECASE),

    # ACH company-initiated transactions -- "ORIG CO NAME:" is a standard
    # NACHA field banks sometimes surface directly in the description.
    # Captures up to the next known ACH field label (ORIG ID, DESC DATE,
    # SEC, CO ENTRY DESCR, TRACE) or end of string. Deliberately lists
    # specific field names here rather than a generic "any uppercase
    # phrase followed by a colon" pattern -- an earlier version used the
    # generic form and it wrongly matched into the company name itself
    # when the name was also in all-caps (e.g. cut "CITI CARD ONLINE"
    # down to just "CITI" because "CARD ONLINE ORIG ID:" looked like a
    # label too).
    re.compile(
        r"ORIG CO NAME:\s*(.+?)(?:\s+(?:ORIG ID|DESC DATE|SEC|CO ENTRY DESCR|TRACE)[: ].*)?$",
        re.IGNORECASE,
    ),
]


def extract_counterparty(description: str) -> Optional[str]:
    """Returns the recipient/sender's name if this looks like a P2P
    payment, otherwise None."""
    cleaned = description.strip()
    for pattern in PATTERNS:
        match = pattern.match(cleaned)
        if match:
            return match.group(1).strip().title()
    return None
