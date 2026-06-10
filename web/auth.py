"""
API Authentication & Authorization system using FastAPI security.

Provides API key validation for securing endpoints.
Supports cookie, Bearer header, and query parameter authentication.
"""
import os
from typing import Optional
from fastapi import HTTPException, status, Header, Query, Cookie
from functools import lru_cache

# ── Configuration ────────────────────────────────────────────────────

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


# ── Shared key extraction ────────────────────────────────────────────

def _extract_key(
    auth_keys: set[str],
    session: str | None,
    authorization: str | None,
    api_key: str | None,
) -> str | None:
    """Extract and validate a key from session/header/query.

    Returns the validated key, None if no credentials were provided,
    or raises HTTPException(401) on invalid credentials.
    """
    if session:
        key = session.strip()
        if key in auth_keys:
            return key
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid session cookie")

    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            key = parts[1].strip()
            if key in auth_keys:
                return key
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

    if api_key:
        key = api_key.strip()
        if key in auth_keys:
            return key
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid API key in query parameter")

    return None


# ── API Key Validation ───────────────────────────────────────────────

async def verify_api_key(
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
    session: Optional[str] = Cookie(None),
) -> str:
    """Verify API key from session cookie, Authorization header, or query param.

    Returns the validated key, or raises HTTPException(401).
    """
    auth_keys = get_api_keys()
    if not auth_keys:
        return "unauthenticated"
    key = _extract_key(auth_keys, session, authorization, api_key)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return key


def optional_api_key(
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
    session: Optional[str] = Cookie(None),
) -> Optional[str]:
    """Optional API key validation. Returns key if valid, None if absent, raises on invalid."""
    auth_keys = get_api_keys()
    if not auth_keys:
        return None
    return _extract_key(auth_keys, session, authorization, api_key)

