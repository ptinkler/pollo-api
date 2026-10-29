"""
User session tokens for signed-in accounts.

Login is by user session only: a local admin signs in with email + password, an
allowed user signs in via OAuth, and either way the browser carries a signed
`user_session` cookie holding the user id. There is no API key — every
protected endpoint requires a resolvable session (see web/users.py).
"""

import base64
import hashlib
import hmac
import os
import time

SESSION_TTL = 60 * 60 * 24 * 30  # 30 days — matches the login cookie's max-age

USER_COOKIE = "user_session"


# ── base64url helpers ────────────────────────────────────────────────


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ── Signed user-session tokens ───────────────────────────────────────
#
# The cookie holds a signed, expiring user id — not a raw credential — so a
# leaked cookie isn't a permanent password and sessions expire on their own.
# Signed with SESSION_SECRET when set, else a dev fallback.


def _user_secret() -> bytes:
    explicit = os.getenv("SESSION_SECRET", "").strip()
    if explicit:
        return hashlib.sha256(b"pollo-user-v1\x00" + explicit.encode()).digest()
    return hashlib.sha256(b"pollo-user-v1-dev").digest()


def make_user_session(user_id: str) -> str:
    """A signed cookie value for a signed-in user id."""
    payload = f"{user_id}.{int(time.time()) + SESSION_TTL}"
    sig = hmac.new(_user_secret(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(sig)}"


def resolve_user_session(token: str | None) -> str | None:
    """The user id a user-session cookie authenticates, or None (bad signature
    or expired). User ids are uuid hex, so they carry no '.' of their own."""
    if not token:
        return None
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    user_id, exp_s, sig_b64 = parts
    payload = f"{user_id}.{exp_s}"
    expected = hmac.new(_user_secret(), payload.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        if time.time() > int(exp_s):
            return None
    except (ValueError, TypeError):
        return None
    return user_id
