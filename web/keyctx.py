"""Request-scoped provider keys.

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

from contextvars import ContextVar

_current_keys: ContextVar[dict | None] = ContextVar("current_keys", default=None)


def set_keys(keys: dict | None):
    """Bind the current request's user keys; returns a token for reset_keys."""
    return _current_keys.set(keys or {})


def reset_keys(token) -> None:
    _current_keys.reset(token)


def provider_key(provider: str) -> str | None:
    """The current user's key for a provider (from their encrypted DB keys), or
    None. There is no .env fallback — keys are per user only."""
    return (_current_keys.get() or {}).get(provider) or None
