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

from fastapi import Cookie, HTTPException

from web.auth import resolve_user_session
from web.core.env import bool_env, email_set
from web.core.metadata import get_db


def open_signup() -> bool:
    return bool_env("OPEN_SIGNUP")


def allowed_emails() -> set[str]:
    return email_set("ALLOWED_EMAILS")


def admin_emails() -> set[str]:
    return email_set("ADMIN_EMAILS")


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


def resolve_current_user(user_cookie: str | None):
    """The current User, resolved from the signed user-session cookie, or None.
    Email+password (local admin) and OAuth both mint that same cookie.
    """
    return current_user(user_cookie)


def require_user(user_session: str | None = Cookie(None)):
    """Dependency: a signed-in user, else 401."""
    user = resolve_current_user(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def require_admin(user_session: str | None = Cookie(None)):
    """Dependency: the admin (the instance owner), else 401/403. Used for VPN
    controls and other owner-only actions.
    """
    user = resolve_current_user(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
