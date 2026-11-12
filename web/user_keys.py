"""Per-user provider API keys: encrypted at rest, never returned in the clear.

Each user brings their own Pollo / Venice / OpenRouter keys (entered in
Settings) instead of the shared .env — so each person pays their own way. The
keys are stored Fernet-encrypted (keyed off KEYS_SECRET, else the session
secret) and the API only ever exposes whether a key is set plus a short hint.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from web import caches
from web.auth import user_secret
from web.core.metadata import User, get_db
from web.dev_login import store_keys_plaintext
from web.users import require_user

KEY_PROVIDERS = ("pollo", "venice", "openrouter")

router = APIRouter(prefix="/api/keys")


def _fernet() -> Fernet:
    secret = os.getenv("KEYS_SECRET", "").strip().encode() or user_secret()
    material = hashlib.sha256(b"pollo-keys-v1\x00" + secret).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def _encrypt(keys: dict[str, str]) -> str:
    # In dev (DEV_LOGIN, fresh DB) store plaintext JSON — no secret to set,
    # nothing to lose. A Fernet token is never valid JSON, so reads tell the
    # two apart. See web/dev_login.py.
    if store_keys_plaintext():
        return json.dumps(keys)
    return _fernet().encrypt(json.dumps(keys).encode()).decode()


def _decrypt(blob: str | None) -> dict[str, str]:
    if not blob:
        return {}
    try:  # plaintext JSON (dev / no-encryption)
        data = json.loads(blob)
        if isinstance(data, dict):
            return data
    except (ValueError, TypeError):
        pass
    try:
        return json.loads(_fernet().decrypt(blob.encode()).decode())
    except (InvalidToken, ValueError):
        return {}  # secret rotated or corrupt: treat as unset


def get_user_keys(user: User) -> dict[str, str]:
    """The user's decrypted {provider: key} (server-side use only)."""
    return _decrypt(getattr(user, "api_keys_json", None))


def _masked(user: User) -> dict[str, dict[str, str | bool]]:
    keys = get_user_keys(user)
    out = {}
    for p in KEY_PROVIDERS:
        value = keys.get(p)
        hint = f"…{value[-4:]}" if value and len(value) >= 4 else ("set" if value else "")
        out[p] = {"set": bool(value), "hint": hint}
    return out


class KeysUpdate(BaseModel):
    """Provider keys to set, clear or leave unchanged."""

    # {provider: "newkey"} to set, {provider: null/""} to clear; omit to keep
    keys: dict[str, str | None]


@router.get("")
async def get_keys(user: Annotated[User, Depends(require_user)]) -> dict[str, dict[str, dict[str, str | bool]]]:
    """Return whether each provider key is set and its masked hint."""
    return {"keys": _masked(user)}


@router.put("")
async def set_keys(
    data: KeysUpdate, user: Annotated[User, Depends(require_user)]
) -> dict[str, dict[str, dict[str, str | bool]]]:
    """Update the signed-in user's provider keys."""
    current = get_user_keys(user)
    for provider, value in data.keys.items():
        if provider not in KEY_PROVIDERS:
            continue
        if value is None or not value.strip():
            current.pop(provider, None)  # clear
        else:
            current[provider] = value.strip()
    get_db().set_user_api_keys(user.id, _encrypt(current))
    caches.keys_changed()  # catalogues and balances are per user, built from their keys
    return {"keys": _masked(get_db().get_user(user.id))}
