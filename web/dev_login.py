"""Local development sign-in (DEV_LOGIN) — a small, self-contained side-door.

Everything the dev login touches lives in this one module, so it's easy to
audit and remove. It is INERT unless DEV_LOGIN is set: the endpoint 404s,
nothing is seeded at startup, and key storage stays encrypted. The only hooks
in the real code are one-line, flag-gated calls (see web/user_keys.py,
web/oauth_routes.py and the api.py lifespan).
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Request, Response

from img2vid.common.metadata import get_db

router = APIRouter(prefix="/api/auth")

# A throwaway local account: one-click sign-in, no password/OAuth, so a lost
# SESSION_SECRET/KEYS_SECRET in dev never locks you out.
DEV_USER = {"provider": "local", "sub": "dev", "name": "Dev", "avatar": None}


def dev_login_enabled() -> bool:
    return os.getenv("DEV_LOGIN", "").strip().lower() in {"1", "true", "yes", "on"}


def dev_email() -> str:
    return os.getenv("DEV_EMAIL", "dev@local").strip().lower() or "dev@local"


def dev_user():
    """The dev account, created on first use as an admin (so owner/VPN controls
    are testable). Matched by email, like the local admin."""
    db = get_db()
    existing = db.get_user_by_email(dev_email())
    if existing:
        return existing
    return db.upsert_oauth_user({**DEV_USER, "email": dev_email()}, is_admin=True)


def _looks_encrypted(blob: str | None) -> bool:
    """A stored key blob that isn't plaintext JSON — i.e. a Fernet token."""
    if not blob:
        return False
    try:
        return not isinstance(json.loads(blob), dict)
    except (ValueError, TypeError):
        return True


def db_has_encrypted_keys() -> bool:
    """Any user's keys are encrypted at rest — i.e. a real/prod DB. You can't
    un-encrypt those, so dev no-encryption mode must refuse to touch it."""
    return any(_looks_encrypted(b) for b in get_db().list_api_key_blobs())


def store_keys_plaintext() -> bool:
    """Whether provider keys should be stored unencrypted: dev only, and only on
    a DB that was never encrypted (so prod is never silently downgraded)."""
    return dev_login_enabled() and not db_has_encrypted_keys()


def seed_dev_user() -> None:
    """Ensure the dev account exists at startup, when enabled and safe. A no-op
    otherwise (so this never runs in production)."""
    if not dev_login_enabled():
        return
    if db_has_encrypted_keys():
        print("🛠 DEV_LOGIN set but the database holds encrypted keys — dev login is refused here.")
        return
    dev_user()
    print(f"🛠 DEV_LOGIN on: one-click dev account '{dev_email()}' ready (keys stored unencrypted).")


@router.post("/dev-login")
async def dev_login(response: Response, request: Request):
    """One-click sign-in as the local dev account — no password or OAuth. 404
    unless DEV_LOGIN is set; refused (403) on a DB that already holds encrypted
    keys (can't un-encrypt a prod database)."""
    if not dev_login_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    if db_has_encrypted_keys():
        raise HTTPException(
            status_code=403,
            detail="DEV_LOGIN is refused: this database already has encrypted keys (looks like production). "
            "Use a fresh dev database.",
        )
    from .api import _set_user_cookie  # lazy: avoid an import cycle with api.py

    user = dev_user()
    _set_user_cookie(response, request, user.id)
    return {"ok": True, "email": user.email, "name": user.name}
