"""Password hashing for local (email + password) admin accounts:

    argon2id( HMAC-SHA256(pepper, password) )   # unique salt is embedded by argon2

The pepper (PASSWORD_PEPPER) is a server-only secret, never stored with the
hash, so a DB leak alone can't verify guesses. Set it once and never change it.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def _pepper() -> bytes:
    """PASSWORD_PEPPER, else derived from SESSION_SECRET, else a dev fallback."""
    explicit = os.getenv("PASSWORD_PEPPER", "").strip()
    if explicit:
        return hashlib.sha256(b"pollo-pepper-v1\x00" + explicit.encode()).digest()
    session_secret = os.getenv("SESSION_SECRET", "").strip()
    if session_secret:
        return hashlib.sha256(b"pollo-pepper-v1\x00" + session_secret.encode()).digest()
    return hashlib.sha256(b"pollo-pepper-v1-dev").digest()


def _peppered(password: str) -> bytes:
    """The password mixed with the server pepper via HMAC, ready for argon2."""
    return hmac.new(_pepper(), password.encode("utf-8"), hashlib.sha256).digest()


def hash_password(password: str) -> str:
    """A storable argon2id hash of the peppered password (unique salt inside)."""
    return _hasher.hash(_peppered(password))


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Whether `password` matches the stored hash. False (never raises) for a
    missing hash, a wrong password, or a malformed/foreign hash string."""
    if not stored_hash:
        return False
    try:
        return _hasher.verify(stored_hash, _peppered(password))
    except (VerifyMismatchError, InvalidHashError, Exception):  # noqa: BLE001 — any failure is "no match"
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Whether a stored hash was made with weaker-than-current argon2 params
    (so it can be transparently upgraded on the next successful login)."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except Exception:  # noqa: BLE001
        return False
