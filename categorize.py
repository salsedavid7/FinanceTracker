"""
Rules-based categorization: substring match against the raw bank
description, first match wins. This is the simplest possible version of
what wealthAgent (and every finance app) does -- pattern -> category label.
Extend RULES as you see more merchants in your real bank exports.
"""

from models import CategoryRule

RULES = [
    # Dining
    CategoryRule("BLUE BOTTLE", "Dining"),
    CategoryRule("CHIPOTLE", "Dining"),
    CategoryRule("STARBUCKS", "Dining"),
    CategoryRule("MCDONALD", "Dining"),
    CategoryRule("KFC", "Dining"),

    # Groceries
    CategoryRule("TRADER JOES", "Groceries"),

    # Transportation
    CategoryRule("SHELL OIL", "Transportation"),
    CategoryRule("UBER", "Transportation"),

    # Travel
    CategoryRule("UNITED AIRLINES", "Travel"),

    # Subscriptions
    CategoryRule("NETFLIX", "Subscriptions"),
    CategoryRule("SPOTIFY", "Subscriptions"),

    # Shopping
    CategoryRule("AMAZON", "Shopping"),
    CategoryRule("SPARKFUN", "Shopping"),
    CategoryRule("MADISON BICYCLE", "Shopping"),

    # Recreation
    CategoryRule("TOUCHSTONE CLIMBING", "Recreation"),

    # Income (deposits into an account -- paychecks, employer names Plaid's
    # sandbox uses for simulated direct deposits)
    CategoryRule("PAYCHECK", "Income"),
    CategoryRule("PAYROLL", "Income"),

    # Recurring fixed-amount outflow (-$500/month in the sandbox data) --
    # looks like a loan or bill payment, not a purchase. Not confidently
    # matched to a specific category, so grouped as "Bills" rather than
    # guessed at incorrectly (an earlier version of this rule wrongly
    # labeled it "Income" based on a bad assumption about the name).
    CategoryRule("TECTRA", "Bills"),

    # Interest earned or charged -- kept separate from Income/spend since
    # it's neither a purchase nor a deposit you control
    CategoryRule("INTRST", "Interest"),

    # Person-to-person payments (Zelle, Venmo, etc.) -- real spend (or real
    # income, if incoming), NOT a transfer between your own accounts, so
    # deliberately placed BEFORE the generic "PAYMENT" Transfer catch-all
    # below, which would otherwise wrongly swallow these (see counterparty.py
    # for extracting *who* specifically, alongside this category label).
    CategoryRule("ZELLE", "P2P Payment"),
    CategoryRule("VENMO", "P2P Payment"),
    CategoryRule("CASH APP", "P2P Payment"),
    CategoryRule("PAYPAL", "P2P Payment"),

    # ACH company-initiated debits/credits (e.g. "ORIG CO NAME: CITI CARD
    # ONLINE") -- a standard NACHA description format. Categorized as real
    # spend (Bills), not Transfer, on the assumption the paid company isn't
    # also an account tracked in this app -- if it were (e.g. you'd linked
    # that card via Plaid too), this really would be an internal transfer
    # and should move to the Transfer category to avoid double-counting.
    CategoryRule("ORIG CO NAME", "Bills"),

    # Transfers between your OWN accounts (credit card/loan payments funded
    # from checking) -- not real spending, so report.py excludes this
    # category from spend-by-category and top-merchants. Kept generic
    # ("PAYMENT", "CREDIT CARD") last so more specific rules above win first.
    CategoryRule("AUTOMATIC PAYMENT", "Transfer"),
    CategoryRule("CREDIT CARD", "Transfer"),
    CategoryRule("PAYMENT", "Transfer"),
]


def categorize(description: str) -> str:
    upper = description.upper()
    for rule in RULES:
        if rule.pattern in upper:
            return rule.category
    return "Uncategorized"
