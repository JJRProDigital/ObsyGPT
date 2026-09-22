"""User-facing connector endpoints: catalog, accounts, and token tests."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..auth.routes import require_user
from .catalog import CONNECTOR_DEFINITIONS, get_connector_definition
from .crypto import decrypt_credential, encrypt_credential
from .store import ConnectorStore

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorAccountPayload(BaseModel):
    token: str
    display_name: str = ""


def _catalog_response(user_id: int) -> dict:
    store = ConnectorStore()
    accounts = {account["connector_slug"]: account for account in store.list_accounts(user_id)}
    connectors = []
    for slug, definition in CONNECTOR_DEFINITIONS.items():
        account = accounts.get(slug)
        connectors.append(
            {
                "slug": slug,
                "name": definition.name,
                "description": definition.description,
                "token_label": definition.token_label,
                "token_help": definition.token_help,
                "tool_names": definition.tool_names,
                "account": {"id": account["id"], "display_name": account["display_name"], "status": account["status"]} if account else None,
            }
        )
    return {"connectors": connectors}


@router.get("")
def list_connectors(request: Request):
    user_id = require_user(request)
    return _catalog_response(user_id)


@router.post("/{connector_slug}/accounts")
def connect_account(connector_slug: str, payload: ConnectorAccountPayload, request: Request):
    user_id = require_user(request)
    try:
        definition = get_connector_definition(connector_slug)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required.")
    try:
        verification = definition.test_token(token)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Token rejected: {error}") from error
    if not verification.get("ok"):
        raise HTTPException(status_code=400, detail=f"Token rejected: {verification.get('detail', 'unknown error')}")
    encrypted = encrypt_credential(token)
    account = ConnectorStore().create_account(
        user_id=user_id,
        connector_slug=connector_slug,
        credentials_encrypted=encrypted,
        display_name=payload.display_name.strip() or verification.get("detail", "")[:100],
    )
    return {"account": account, "verification": verification}


@router.delete("/accounts/{account_id}")
def disconnect_account(account_id: int, request: Request):
    user_id = require_user(request)
    if not ConnectorStore().delete_account(account_id, user_id):
        raise HTTPException(status_code=404, detail="Connector account not found.")
    return {"id": account_id, "deleted": True}


@router.post("/accounts/{account_id}/test")
def test_account(account_id: int, request: Request):
    user_id = require_user(request)
    store = ConnectorStore()
    accounts = [account for account in store.list_accounts(user_id) if account["id"] == account_id]
    if not accounts:
        raise HTTPException(status_code=404, detail="Connector account not found.")
    account = accounts[0]
    try:
        definition = get_connector_definition(account["connector_slug"])
        encrypted = store.get_credential(user_id, account["connector_slug"])
        if encrypted is None:
            raise HTTPException(status_code=400, detail="Account has no stored credential.")
        verification = definition.test_token(decrypt_credential(encrypted))
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "detail": str(error)[:300]}
    return verification
