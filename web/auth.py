"""
API Authentication & Authorization system using FastAPI security.

Provides API key validation for securing endpoints.
Supports cookie (signed session token) and Bearer header authentication.
"""

import base64
import hashlib
import hmac
import os
import time
from functools import lru_cache

from fastapi import Cookie, Header, HTTPException, status

# ── Configuration ────────────────────────────────────────────────────

SESSION_TTL = 60 * 60 * 24 * 30  # 30 days — matches the login cookie's max-age


@lru_cache(maxsize=1)
def get_api_keys() -> set[str]:
    """Load authorized API keys from environment (API_KEYS=k1,k2 or API_KEY=k)."""
    api_keys_str = os.getenv("API_KEYS", "").strip()
    if api_keys_str:
        return {k.strip() for k in api_keys_str.split(",") if k.strip()}
    single_key = os.getenv("API_KEY", "").strip()
    if single_key:
        return {single_key}
    return set()


def is_auth_enabled() -> bool:
    return len(get_api_keys()) > 0


def allow_no_auth() -> bool:
    """True if running without any API key is explicitly permitted (dev only).

    Set ALLOW_NO_AUTH=true to opt out of auth. Without it, a server that has
    no API_KEY/API_KEYS configured refuses protected requests (fail closed)
    rather than silently serving everyone — so a missing/unloaded key env in
    production can't flip the whole API open.
    """
    return os.getenv("ALLOW_NO_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}


def auth_misconfigured() -> bool:
    """No keys configured and no explicit opt-out — the fail-closed state."""
    return not get_api_keys() and not allow_no_auth()


# ── Constant-time key matching ───────────────────────────────────────


def _valid_key(candidate: str, auth_keys: set[str]) -> bool:
    """Whether *candidate* is one of the configured keys, compared in constant
    time so a timing side-channel can't reveal a key character by character."""
    # Compare against every key (no early exit) and OR the results together.
    matched = False
    for key in auth_keys:
        if hmac.compare_digest(candidate, key):
            matched = True
    return matched


# ── Signed session tokens ────────────────────────────────────────────
#
# The login cookie holds a signed, expiring token — not the raw API key — so
# a leaked cookie isn't the permanent credential and sessions expire on their
# own. The signing secret is derived from the configured keys, so it needs no
# extra config and rotating a key invalidates every session signed under it.


def _signing_secret(auth_keys: set[str]) -> bytes:
    material = "\x00".join(sorted(auth_keys)).encode()
    return hashlib.sha256(b"pollo-session-v1\x00" + material).digest()


def _fingerprint(key: str) -> str:
    """A short, non-reversible tag identifying which key a token was issued for."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_session_token(key: str) -> str:
    """A signed cookie value for an already-validated key."""
    auth_keys = get_api_keys()
    payload = f"{_fingerprint(key)}.{int(time.time()) + SESSION_TTL}"
    sig = hmac.new(_signing_secret(auth_keys), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(sig)}"


def _key_from_token(token: str, auth_keys: set[str]) -> str | None:
    """The key a signed token was issued for, if its signature and expiry check
    out and that key is still configured; otherwise None."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    fp, exp_s, sig_b64 = parts
    payload = f"{fp}.{exp_s}"
    expected = hmac.new(_signing_secret(auth_keys), payload.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        if time.time() > int(exp_s):
            return None
    except (ValueError, TypeError):
        return None
    for key in auth_keys:
        if hmac.compare_digest(_fingerprint(key), fp):
            return key
    return None


def resolve_session(session: str | None) -> str | None:
    """The key a session cookie authenticates, or None. Accepts a signed token
    or, for sessions issued before signing, the raw key (legacy fallback)."""
    if not session:
        return None
    token = session.strip()
    auth_keys = get_api_keys()
    key = _key_from_token(token, auth_keys)
    if key:
        return key
    if _valid_key(token, auth_keys):  # legacy cookie: raw key
        return token
    return None


# ── User sessions (OAuth sign-in) ────────────────────────────────────
#
# A separate cookie from the API-key "session": it holds a signed user id, so
# OAuth users have real sessions independent of the shared key. Signed with
# SESSION_SECRET when set, else derived from the API keys (rotating a key ends
# all sessions), else a dev fallback.

USER_COOKIE = "user_session"


def _user_secret() -> bytes:
    explicit = os.getenv("SESSION_SECRET", "").strip()
    if explicit:
        return hashlib.sha256(b"pollo-user-v1\x00" + explicit.encode()).digest()
    keys = get_api_keys()
    if keys:
        return hashlib.sha256(b"pollo-user-v1\x00" + _signing_secret(keys)).digest()
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


# ── Shared key extraction ────────────────────────────────────────────


def _extract_key(
    auth_keys: set[str],
    session: str | None,
    authorization: str | None,
) -> str | None:
    """Extract and validate a key from the session cookie or Bearer header.

    Returns the validated key, None if no credentials were provided,
    or raises HTTPException(401) on invalid credentials.
    """
    if session:
        key = resolve_session(session)
        if key:
            return key
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session cookie")

    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            if _valid_key(parts[1].strip(), auth_keys):
                return parts[1].strip()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key in Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return None


def _require_configured() -> set[str] | None:
    """The configured keys, or None when auth is disabled via the dev opt-out.
    Raises 503 when no keys are set and the opt-out is absent (fail closed)."""
    auth_keys = get_api_keys()
    if auth_keys:
        return auth_keys
    if allow_no_auth():
        return None
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Server authentication is not configured. Set API_KEY (or API_KEYS), "
            "or set ALLOW_NO_AUTH=true to run without auth (development only)."
        ),
    )


# ── API Key Validation ───────────────────────────────────────────────


async def verify_api_key(
    authorization: str | None = Header(None),
    session: str | None = Cookie(None),
) -> str:
    """Verify auth from the session cookie or Authorization header.

    Returns the validated key, or raises HTTPException(401/503).
    """
    auth_keys = _require_configured()
    if auth_keys is None:
        return "unauthenticated"
    key = _extract_key(auth_keys, session, authorization)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return key


def optional_api_key(
    authorization: str | None = Header(None),
    session: str | None = Cookie(None),
) -> str | None:
    """Optional API key validation. Returns key if valid, None if absent, raises on invalid."""
    auth_keys = _require_configured()
    if auth_keys is None:
        return None
    return _extract_key(auth_keys, session, authorization)
