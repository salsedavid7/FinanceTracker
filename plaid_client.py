"""
Thin wrapper around the Plaid Python SDK. Everything here is just
"how do I call Plaid," kept separate from app.py (the web layer) and
plaid_sync.py (the "load into our own database" layer).

Import style and response access here deliberately match the patterns in
Plaid's own plaid-python README (import plaid; plaid.Configuration;
dict-style response access) rather than attribute access, since that's
the documented, guaranteed-stable interface.
"""

import os
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from dotenv import load_dotenv

load_dotenv()

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}

_configuration = plaid.Configuration(
    host=_ENV_MAP[PLAID_ENV],
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
    },
)
_api_client = plaid.ApiClient(_configuration)
client = plaid_api.PlaidApi(_api_client)


def create_link_token(user_id: str = "david-personal") -> str:
    """
    Step 1 of the Link flow: ask Plaid for a short-lived link_token that
    the frontend widget uses to open the Plaid Link modal.
    """
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="FinanceTracker",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
    )
    response = client.link_token_create(request)
    return response["link_token"]


def exchange_public_token(public_token: str) -> dict:
    """
    Step 2: once the user finishes the Link flow in the browser, the
    frontend sends us a public_token. Exchange it for a permanent
    access_token (what we actually use to call /transactions/sync later)
    plus the item_id (Plaid's identifier for this bank connection).
    """
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)
    return {
        "access_token": response["access_token"],
        "item_id": response["item_id"],
    }


def get_accounts(access_token: str) -> list:
    """List the actual bank accounts (checking, savings, credit card, ...)
    attached to a given Plaid Item."""
    request = AccountsGetRequest(access_token=access_token)
    response = client.accounts_get(request)
    return response["accounts"]
