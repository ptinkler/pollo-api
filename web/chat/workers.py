"""Background-worker helpers: run a thread inside the request's context (tenant
+ keys), and bind a conversation owner's provider keys for work that outlives
the request (pollers, retries, startup resume)."""

import contextlib
import contextvars
import functools
import threading

from web.core.metadata import get_db


def _ctx_thread(target, *args, name: str | None = None) -> "threading.Thread":
    """A daemon thread that runs `target(*args)` inside a copy of the CURRENT
    context, so it inherits the request's tenant + provider keys (plain threads
    don't). Started from a request handler or another context-bearing thread."""
    ctx = contextvars.copy_context()
    return threading.Thread(target=lambda: ctx.run(target, *args), daemon=True, name=name)


@contextlib.contextmanager
def _owner_keys(conv_id: str):
    """Bind the conversation owner's provider keys for a background worker that
    runs outside the request (pollers, retries, startup resume). Keys live only
    in the DB per user, so without this the worker would have no key. It binds
    keys only — the worker acts on a specific id, so it needs no tenant scope."""
    from .. import keyctx, user_keys

    conv = get_db().get_conversation(conv_id)
    owner = get_db().get_user(conv.user_id) if conv and getattr(conv, "user_id", None) else None
    token = keyctx.set_keys(user_keys.get_user_keys(owner) if owner else {})
    try:
        yield
    finally:
        keyctx.reset_keys(token)


def _with_owner_keys(fn):
    """Decorator for background workers whose first arg is conv_id: run them
    with the conversation owner's provider keys bound."""

    @functools.wraps(fn)
    def wrapper(conv_id, *args, **kwargs):
        with _owner_keys(conv_id):
            return fn(conv_id, *args, **kwargs)

    return wrapper
