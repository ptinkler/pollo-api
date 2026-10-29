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

from fastapi import Cookie, HTTPException

from img2vid.common.metadata import get_db

from .auth import resolve_user_session

# The owner's account. They sign in with their email + password (provider
# "local", no OAuth, no internet needed); that session resolves to this single
# local admin user, so the owner's data is a tenant bucket like any OAuth user's.
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


def admin_email() -> str:
    """The owner's email — the first ADMIN_EMAILS entry, else a local default.
    The admin account is keyed on this, so the email+password login and an OAuth
    login with the same email resolve to the SAME account."""
    return next(iter(admin_emails()), "admin@local")


def admin_user():
    """The owner's account, matched by email so the key and Google paths unify.
    Created on first use; reads first and only writes to create."""
    db = get_db()
    existing = db.get_user_by_email(admin_email())
    if existing:
        return existing
    return db.upsert_oauth_user({**LOCAL_ADMIN, "email": admin_email()}, is_admin=True)


def resolve_current_user(user_cookie: str | None):
    """The current User, resolved from the signed user-session cookie, or None.
    Email+password (local admin) and OAuth both mint that same cookie."""
    return current_user(user_cookie)


# ── FastAPI dependencies ─────────────────────────────────────────────


def current_user_dep(user_session: str | None = Cookie(None)):
    """The signed-in User for this request, or None."""
    return resolve_current_user(user_session)


def require_user(user_session: str | None = Cookie(None)):
    """Dependency: a signed-in user, else 401."""
    user = resolve_current_user(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def require_admin(user_session: str | None = Cookie(None)):
    """Dependency: the admin (the instance owner), else 401/403. Used for VPN
    controls and other owner-only actions."""
    user = resolve_current_user(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
