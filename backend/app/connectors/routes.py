"""User-facing connector endpoints: catalog, accounts, token tests, and OAuth flows."""

import secrets
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth.routes import require_user
from ..config import get_settings
from . import higgsfield
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
                "auth_type": definition.auth_type,
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


@router.get("/{connector_slug}/oauth/start")
def start_oauth(connector_slug: str, request: Request):
    user_id = require_user(request)
    try:
        definition = get_connector_definition(connector_slug)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if definition.auth_type != "oauth":
        raise HTTPException(status_code=400, detail="Connector does not support OAuth.")
    redirect_uri = str(request.base_url).rstrip("/") + f"/api/connectors/{connector_slug}/oauth/callback"
    try:
        client = higgsfield.register_client(redirect_uri)
        code_verifier, code_challenge = higgsfield.create_pkce_pair()
        state = secrets.token_urlsafe(32)
        ConnectorStore().create_oauth_state(user_id, connector_slug, state, code_verifier, redirect_uri, str(client["client_id"]))
        authorize_url = higgsfield.build_authorization_url(str(client["client_id"]), redirect_uri, state, code_challenge)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OAuth setup failed: {error}") from error
    return {"authorize_url": authorize_url}


@router.get("/{connector_slug}/oauth/callback")
def oauth_callback(connector_slug: str, request: Request, code: str = "", state: str = "", error: str = ""):
    user_id = require_user(request)
    frontend_url = get_settings().frontend_url

    def _redirect(status: str, detail: str = "") -> RedirectResponse:
        target = f"{frontend_url}/app/?connector={connector_slug}&status={status}"
        if detail:
            target += f"&detail={quote(detail[:200])}"
        return RedirectResponse(target, status_code=303)

    if error:
        return _redirect("error", error)
    store = ConnectorStore()
    try:
        definition = get_connector_definition(connector_slug)
    except ValueError:
        return _redirect("error", "Unknown connector.")
    saved_state = store.consume_oauth_state(user_id, connector_slug, state)
    if not saved_state:
        return _redirect("error", "Estado OAuth invalido o expirado.")
    client_id = str(saved_state.get("client_id", ""))
    try:
        if not code:
            raise RuntimeError("Higgsfield no devolvio un codigo de autorizacion.")
        tokens = higgsfield.exchange_code(code, saved_state["code_verifier"], client_id, saved_state["redirect_uri"])
        if tokens.get("error"):
            raise RuntimeError(str(tokens["error"]))
        blob = higgsfield.dump_credentials(
            str(tokens.get("access_token", "")),
            str(tokens.get("refresh_token", "")),
            int(tokens.get("expires_in") or 3600),
            client_id,
        )
        verification = definition.test_token(blob)
        store.create_account(
            user_id=user_id,
            connector_slug=connector_slug,
            credentials_encrypted=encrypt_credential(blob),
            display_name=definition.name,
        )
    except Exception as callback_error:  # noqa: BLE001
        return _redirect("error", str(callback_error))
    return _redirect("connected", str(verification.get("detail", "")))
