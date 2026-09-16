"""Symmetric encryption for secrets we store at rest (a user's own API key).

Keyed off ``JWT_SECRET`` — already a required, unique-per-deploy secret — so
there's no second secret to provision or forget to set in production.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(plain: str) -> str:
    """Encrypt a plaintext secret for storage. Raises on empty input."""
    if not plain:
        raise ValueError("cannot encrypt an empty secret")
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str | None) -> str | None:
    """Decrypt a stored secret. Returns None (never raises) if it's missing,
    malformed, or was encrypted under a since-rotated JWT_SECRET — callers
    should treat that as "no custom key" and fall back to the shared one."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
