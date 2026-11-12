"""Request-scoped provider keys.

The middleware binds per-user credentials for provider calls during a request.

Provider keys (Pollo / Venice / OpenRouter) live ONLY in the database, encrypted
per user — never in .env. The middleware in api.py binds the signed-in user's
decrypted keys to a context variable per request; provider code calls
`provider_key(provider)` to get the right one. No .env fallback: a user with no
key for a provider simply can't use it.

Caveat: a ContextVar is bound to the current task. Synchronous request handling
(text chat, model lists, estimates) sees the user's keys; background media
generation that outlives the request resolves keys from the owning job's user
once jobs carry a user_id (the multi-tenant step).
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_current_keys: ContextVar[dict | None] = ContextVar("current_keys", default=None)


def set_keys(keys: dict[str, str] | None) -> Token[dict[str, str] | None]:
    """Bind the current request's user keys; returns a token for reset_keys."""
    return _current_keys.set(keys or {})


def reset_keys(token: Token[dict[str, str] | None]) -> None:
    """Restore the key context to the state captured by ``set_keys``."""
    _current_keys.reset(token)


def provider_key(provider: str) -> str | None:
    """Return the current user's key for a provider, if set.

    Keys are read from their encrypted database value with no .env fallback.
    """
    return (_current_keys.get() or {}).get(provider) or None
