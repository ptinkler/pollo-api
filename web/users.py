"""User access policy for sign-in and current-user resolution.

The policy supports email allowlists, admin accounts, open signup and OAuth sessions.

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
from web.core.metadata import User, get_db


def open_signup() -> bool:
    """Return whether anyone who authenticates may create an account."""
    return bool_env("OPEN_SIGNUP")


def allowed_emails() -> set[str]:
    """Return the normalized email allowlist."""
    return email_set("ALLOWED_EMAILS")


def admin_emails() -> set[str]:
    """Return the normalized set of administrator email addresses."""
    return email_set("ADMIN_EMAILS")


def is_admin_email(email: str | None) -> bool:
    """Check whether an email belongs to an administrator."""
    return bool(email) and email.lower() in admin_emails()


def admit(email: str | None, is_first_user: bool) -> tuple[bool, bool]:
    """Decide whether an authenticating email may sign in.

    Return an ``(allowed, is_admin)`` pair.
    """
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


def current_user(user_cookie: str | None) -> User | None:
    """The signed-in User for a user-session cookie (OAuth), or None."""
    user_id = resolve_user_session(user_cookie)
    if not user_id:
        return None
    return get_db().get_user(user_id)


def resolve_current_user(user_cookie: str | None) -> User | None:
    """Resolve the current user from the signed session cookie.

    Local email-password login and OAuth both mint the same cookie.
    """
    return current_user(user_cookie)


def require_user(user_session: str | None = Cookie(None)) -> User:
    """Dependency: a signed-in user, else 401."""
    user = resolve_current_user(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def require_admin(user_session: str | None = Cookie(None)) -> User:
    """Require the instance administrator for an owner-only action.

    Raise 401 when unsigned and 403 when the signed-in user is not an admin.
    """
    user = resolve_current_user(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
