"""Background-worker helpers: run a thread inside the request's context (tenant.

+ keys), and bind a conversation owner's provider keys for work that outlives
the request (pollers, retries, startup resume).
"""

import contextlib
import contextvars
import functools
import threading
from collections.abc import Callable, Iterator
from typing import Concatenate

from web import keyctx, user_keys
from web.core.metadata import get_db


def ctx_thread(target: Callable[[], None], *, name: str | None = None) -> threading.Thread:
    """Create a daemon thread that inherits the current request context.

    The copied context carries tenant and provider-key values into the worker.
    """
    ctx = contextvars.copy_context()
    return threading.Thread(target=lambda: ctx.run(target), daemon=True, name=name)


@contextlib.contextmanager
def _owner_keys(conv_id: str) -> Iterator[None]:
    """Bind the conversation owner's provider keys for background work.

    The conversation ID scopes operations, so no tenant context is needed.
    """
    conv = get_db().get_conversation(conv_id)
    owner = get_db().get_user(conv.user_id) if conv and getattr(conv, "user_id", None) else None
    token = keyctx.set_keys(user_keys.get_user_keys(owner) if owner else {})
    try:
        yield
    finally:
        keyctx.reset_keys(token)


def with_owner_keys[**P, R](
    fn: Callable[Concatenate[str, P], R],
) -> Callable[Concatenate[str, P], R]:
    """Decorate a worker to bind its conversation owner's provider keys.

    The wrapped worker must accept its conversation ID as the first argument.
    """

    @functools.wraps(fn)
    def wrapper(conv_id: str, *args: P.args, **kwargs: P.kwargs) -> R:
        with _owner_keys(conv_id):
            return fn(conv_id, *args, **kwargs)

    return wrapper
