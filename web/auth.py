"""
API Authentication & Authorization system using FastAPI security.

Provides API key validation for securing endpoints.
Supports both header and query parameter authentication:
  - Header: Authorization: Bearer <api_key>
  - Query: ?api_key=<api_key>
"""
import os
from typing import Optional
from fastapi import Depends, HTTPException, status, Header, Query, Cookie
from functools import lru_cache

# ── Configuration ────────────────────────────────────────────────────

# API keys authorized to access protected endpoints
# Set via environment: API_KEYS=key1,key2,key3 (comma-separated)
# Or: API_KEY=single_key for a single key
@lru_cache(maxsize=1)
def get_api_keys() -> set[str]:
    """Load authorized API keys from environment variables.

    Supports two formats:
    - API_KEY=single_key (single key)
    - API_KEYS=key1,key2,key3 (multiple keys, comma-separated)

    If neither is set, returns an empty set (auth disabled for development).
    """
    # Try multiple keys first
    api_keys_str = os.getenv("API_KEYS", "").strip()
    if api_keys_str:
        return {k.strip() for k in api_keys_str.split(",") if k.strip()}

    # Fall back to single key
    single_key = os.getenv("API_KEY", "").strip()
    if single_key:
        return {single_key}

    return set()


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return len(get_api_keys()) > 0


# ── API Key Validation ───────────────────────────────────────────────

async def verify_api_key(
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
    session: Optional[str] = Cookie(None),
) -> str:
    """
    Verify API key from Authorization header, query parameter, or session cookie.

    Supports:
    - Cookie: session=<api_key> (HttpOnly, set via /api/auth/login)
    - Header: Authorization: Bearer <api_key>
    - Query: ?api_key=<api_key>

    Returns the validated API key.
    Raises HTTPException(401) if key is invalid or missing.
    """
    auth_keys = get_api_keys()

    if not auth_keys:
        return "unauthenticated"

    # Session cookie (primary path for browser clients)
    if session:
        key = session.strip()
        if key in auth_keys:
            return key
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session cookie",
        )

    # Authorization header (Bearer token)
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

    # Query parameter
    if api_key:
        api_key = api_key.strip()
        if api_key in auth_keys:
            return api_key
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key in query parameter",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def optional_api_key(
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
    session: Optional[str] = Cookie(None),
) -> Optional[str]:
    """
    Optional API key validation. Returns key if valid, None if absent, raises on invalid.
    """
    auth_keys = get_api_keys()

    if not auth_keys:
        return None

    if session:
        key = session.strip()
        if key in auth_keys:
            return key
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session cookie",
        )

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
        api_key = api_key.strip()
        if api_key in auth_keys:
            return api_key
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key in query parameter",
        )

    return None


# ── Rate Limiting Helpers (Optional) ─────────────────────────────────

class RateLimitTracker:
    """Simple in-memory rate limiter by API key."""

    def __init__(self):
        self.requests: dict[str, list[float]] = {}

    def is_allowed(self, api_key: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
        """Check if API key is within rate limits."""
        import time
        now = time.time()
        cutoff = now - window_seconds

        if api_key not in self.requests:
            self.requests[api_key] = []

        # Remove old requests outside the window
        self.requests[api_key] = [ts for ts in self.requests[api_key] if ts > cutoff]

        # Check if limit exceeded
        if len(self.requests[api_key]) >= max_requests:
            return False

        # Record this request
        self.requests[api_key].append(now)
        return True


# Global rate limiter instance
_rate_limiter = RateLimitTracker()


def check_rate_limit(api_key: str, max_requests: int = 100, window_seconds: int = 60) -> None:
    """
    Check and enforce rate limits. Raises HTTPException(429) if limit exceeded.

    Args:
        api_key: The API key to rate limit
        max_requests: Maximum requests allowed per window
        window_seconds: Time window in seconds
    """
    if not _rate_limiter.is_allowed(api_key, max_requests, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {max_requests} requests per {window_seconds} seconds",
            headers={"Retry-After": str(window_seconds)},
        )

