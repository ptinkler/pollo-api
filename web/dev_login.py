"""Local development sign-in (DEV_LOGIN) — a small, self-contained side-door.

Everything the dev login touches lives in this one module, so it's easy to
audit and remove. It is INERT unless DEV_LOGIN is set: the endpoint 404s,
nothing is seeded at startup, and key storage stays encrypted. The only hooks
in the real code are one-line, flag-gated calls (see web/user_keys.py,
web/oauth_routes.py and the api.py lifespan).
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response

from web.auth import set_user_cookie
from web.core.env import bool_env
from web.core.metadata import User, get_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

# A throwaway local account: one-click sign-in, no password/OAuth, so a lost
# SESSION_SECRET/KEYS_SECRET in dev never locks you out.
DEV_USER = {"provider": "local", "sub": "dev", "name": "Dev", "avatar": None}


def dev_login_enabled() -> bool:
    """Return whether local development sign-in is enabled."""
    return bool_env("DEV_LOGIN")


def dev_email() -> str:
    """Return the normalized email address for the development account."""
    return os.getenv("DEV_EMAIL", "dev@local").strip().lower() or "dev@local"


def dev_user() -> User:
    """Return the dev account, creating it as an admin if needed.

    It is matched by email, like the local admin, so owner controls are testable.
    """
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
    """Check whether any user's keys are encrypted at rest.

    Dev no-encryption mode must not touch a database whose keys cannot be decrypted.
    """
    return any(_looks_encrypted(b) for b in get_db().list_api_key_blobs())


def store_keys_plaintext() -> bool:
    """Check whether dev mode may store provider keys as plaintext.

    This is allowed only for a database that has never stored encrypted keys.
    """
    return dev_login_enabled() and not db_has_encrypted_keys()


def seed_dev_user() -> None:
    """Create the development account at startup when enabled and safe.

    This is a no-op otherwise, so it never runs in production.
    """
    if not dev_login_enabled():
        return
    if db_has_encrypted_keys():
        log.warning("DEV_LOGIN set but the database holds encrypted keys — dev login is refused here")
        return
    dev_user()
    log.info("DEV_LOGIN on: one-click dev account %r ready (keys stored unencrypted)", dev_email())


@router.post("/dev-login")
async def dev_login(response: Response, request: Request) -> dict[str, str | bool | None]:
    """Sign in as the local development account without a password or OAuth.

    The route returns 404 when disabled and refuses databases with encrypted keys.
    """
    if not dev_login_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    if db_has_encrypted_keys():
        raise HTTPException(
            status_code=403,
            detail="DEV_LOGIN is refused: this database already has encrypted keys (looks like production). "
            "Use a fresh dev database.",
        )
    user = dev_user()
    set_user_cookie(response, request, user.id)
    return {"ok": True, "email": user.email, "name": user.name}
