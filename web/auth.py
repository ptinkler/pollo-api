"""User session tokens for signed-in accounts.

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

from fastapi import Request, Response

from web.core.env import bool_env_or_none

# The session token and the cookie carrying it expire together.
SESSION_TTL = 60 * 60 * 24 * 30  # 30 days

USER_COOKIE = "user_session"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


#
# The cookie holds a signed, expiring user id — not a raw credential — so a
# leaked cookie isn't a permanent password and sessions expire on their own.
# Signed with SESSION_SECRET when set, else a dev fallback.


def user_secret() -> bytes:
    explicit = os.getenv("SESSION_SECRET", "").strip()
    if explicit:
        return hashlib.sha256(b"pollo-user-v1\x00" + explicit.encode()).digest()
    return hashlib.sha256(b"pollo-user-v1-dev").digest()


def make_user_session(user_id: str) -> str:
    """A signed cookie value for a signed-in user id."""
    payload = f"{user_id}.{int(time.time()) + SESSION_TTL}"
    sig = hmac.new(user_secret(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(sig)}"


def cookie_secure(request: Request) -> bool:
    """Whether the session cookie should be marked Secure (HTTPS-only).

    Secure by default, so a TLS deployment (e.g. the NAS) needs no config. The
    one automatic exemption is plain-HTTP access to a loopback host, where
    local dev would otherwise break — browsers treat localhost as secure, so
    the cookie still works there. COOKIE_SECURE=true/false overrides either
    way: set it false only to serve auth over plain HTTP on a LAN.
    """
    override = bool_env_or_none("COOKIE_SECURE")
    if override is not None:
        return override
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if request.url.scheme == "https" or forwarded == "https":
        return True
    host = (request.url.hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "::1"}


def set_user_cookie(response: Response, request: Request, user_id: str) -> None:
    """Sign this user in on `response`. The one place the login cookie is set —
    password login, OAuth and dev login all come through here.
    """
    response.set_cookie(
        key=USER_COOKIE,
        value=make_user_session(user_id),
        httponly=True,
        samesite="lax",  # lax so the OAuth redirect back from the provider keeps it
        secure=cookie_secure(request),
        max_age=SESSION_TTL,
    )


def resolve_user_session(token: str | None) -> str | None:
    """The user id a user-session cookie authenticates, or None (bad signature
    or expired). User ids are uuid hex, so they carry no '.' of their own.
    """
    if not token:
        return None
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    user_id, exp_s, sig_b64 = parts
    payload = f"{user_id}.{exp_s}"
    expected = hmac.new(user_secret(), payload.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        if time.time() > int(exp_s):
            return None
    except (ValueError, TypeError):
        return None
    return user_id
