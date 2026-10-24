"""Resolution of provider API keys: panel-stored (encrypted) first, env var fallback.

The panel stores the key encrypted with the same scheme as connector
credentials; the env var referenced by api_key_env remains a valid source
(so existing installs keep working and Terraform/secret-manager setups
still function).
"""

import logging
import os

from ..connectors.crypto import decrypt_credential

logger = logging.getLogger("obsygpt.providers.keys")


def resolve_provider_api_key(encrypted: str | None, api_key_env: str | None) -> str | None:
    if encrypted:
        try:
            return decrypt_credential(encrypted)
        except ValueError:
            logger.warning("Stored provider API key cannot be decrypted; falling back to env var.")
    return os.getenv(api_key_env) if api_key_env else None
