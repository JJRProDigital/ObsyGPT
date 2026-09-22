"""Encrypted storage for connector credentials."""

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings, using_default_session_secret

logger = logging.getLogger("obsygpt.connectors.crypto")

_warned_default_key = False


def _fernet() -> Fernet:
    global _warned_default_key
    explicit_key = os.getenv("CONNECTOR_ENCRYPTION_KEY")
    if explicit_key:
        return Fernet(explicit_key.encode() if isinstance(explicit_key, str) else explicit_key)
    if using_default_session_secret() and not _warned_default_key:
        _warned_default_key = True
        logger.critical(
            "Connector credentials are encrypted with a key derived from the DEFAULT "
            "SESSION_SECRET: anyone with database access can decrypt them. Set "
            "CONNECTOR_ENCRYPTION_KEY (or a strong SESSION_SECRET) now; rotating it later "
            "makes existing credentials undecryptable."
        )
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
