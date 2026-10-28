"""User access policy (allowlist / admin / open sign-up) and current-user
resolution for OAuth sessions.

Env:
  OPEN_SIGNUP=true           anyone who authenticates may create an account
  ALLOWED_EMAILS=a@x,b@y     only these (plus admins) may sign in
  ADMIN_EMAILS=you@x         admins; they also control the VPN

When none are set, the first user to sign in bootstraps as the sole admin and
no one else is admitted (fail-closed) until ALLOWED_EMAILS / OPEN_SIGNUP is set.
"""

from __future__ import annotations

import os

from fastapi import Cookie, Header, HTTPException

from img2vid.common.metadata import get_db

from . import auth
from .auth import resolve_user_session

# The owner's account. They sign in over the LAN with the API key (no OAuth, no
# internet); that key session resolves to this single local admin user, so the
# owner's data is a tenant bucket like any OAuth user's.
LOCAL_ADMIN = {"provider": "local", "sub": "admin", "name": "Admin", "avatar": None}


def _email_set(var: str) -> set[str]:
    return {e.strip().lower() for e in os.getenv(var, "").split(",") if e.strip()}


def open_signup() -> bool:
    return os.getenv("OPEN_SIGNUP", "").strip().lower() in {"1", "true", "yes", "on"}


def allowed_emails() -> set[str]:
    return _email_set("ALLOWED_EMAILS")


def admin_emails() -> set[str]:
    return _email_set("ADMIN_EMAILS")


def is_admin_email(email: str | None) -> bool:
    return bool(email) and email.lower() in admin_emails()


def admit(email: str | None, is_first_user: bool) -> tuple[bool, bool]:
    """(allowed, is_admin) for an authenticating email."""
    email = (email or "").lower()
    if not email:
        return False, False
    admin = is_admin_email(email) or (is_first_user and not admin_emails())
    if open_signup():
        return True, admin
    allow = allowed_emails()
    if allow:
        return (email in allow or admin), admin
    if admin_emails():  # admins only, no open list
        return admin, admin
    return is_first_user, admin  # first-ever user bootstraps as admin


def current_user(user_cookie: str | None):
    """The signed-in User for a user-session cookie (OAuth), or None."""
    user_id = resolve_user_session(user_cookie)
    if not user_id:
        return None
    return get_db().get_user(user_id)


def admin_user():
    """The owner's local admin account, created on first use."""
    email = next(iter(admin_emails()), "admin@local")
    return get_db().upsert_oauth_user({**LOCAL_ADMIN, "email": email}, is_admin=True)


def _key_authenticated(session: str | None, authorization: str | None) -> bool:
    """Whether the request carries a valid API key (session cookie, Bearer
    header, or an explicit dev opt-out)."""
    if auth.resolve_session(session):
        return True
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer" and auth._valid_key(parts[1], auth.get_api_keys()):
            return True
    return not auth.is_auth_enabled() and auth.allow_no_auth()  # dev: everything open → owner


def resolve_current_user(user_cookie: str | None, session: str | None = None, authorization: str | None = None):
    """The current User: an OAuth user by their session cookie, else the local
    admin when the request is API-key authenticated, else None."""
    user = current_user(user_cookie)
    if user:
        return user
    if _key_authenticated(session, authorization):
        return admin_user()
    return None


# ── FastAPI dependencies ─────────────────────────────────────────────


def current_user_dep(
    user_session: str | None = Cookie(None),
    session: str | None = Cookie(None),
    authorization: str | None = Header(None),
):
    """The signed-in User for this request, or None."""
    return resolve_current_user(user_session, session, authorization)


def require_user(
    user_session: str | None = Cookie(None),
    session: str | None = Cookie(None),
    authorization: str | None = Header(None),
):
    """Dependency: a signed-in user, else 401."""
    user = resolve_current_user(user_session, session, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def require_admin(
    user_session: str | None = Cookie(None),
    session: str | None = Cookie(None),
    authorization: str | None = Header(None),
):
    """Dependency: the admin (the instance owner), else 401/403. Used for VPN
    controls and other owner-only actions."""
    user = resolve_current_user(user_session, session, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
