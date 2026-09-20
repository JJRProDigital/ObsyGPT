"""Encrypted storage for connector credentials."""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings


def _fernet() -> Fernet:
    explicit_key = os.getenv("CONNECTOR_ENCRYPTION_KEY")
    if explicit_key:
        return Fernet(explicit_key.encode() if isinstance(explicit_key, str) else explicit_key)
    derived = hashlib.sha256(f"{get_settings().session_secret}:connector-credentials".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_credential(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_credential(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise ValueError("Stored credential cannot be decrypted. Check CONNECTOR_ENCRYPTION_KEY.") from error


def mask_credential(plain: str) -> str:
    if len(plain) <= 8:
        return "*" * len(plain)
    return f"{plain[:4]}...{plain[-4:]}"
