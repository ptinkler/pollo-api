"""Caches that have to be dropped when the signed-in user's keys change.

A provider key decides what that user's model catalogue contains and what
their balance is, so changing one must invalidate both. The caches live in
`web/chat/catalogue.py` and `web/providers/venice.py`; the code that saves a
key lives in `web/user_keys.py`.

Having user_keys import those directly would make a cycle (web.chat imports
web.user_keys), so they register here instead. This module imports nothing,
so anything may import it.
"""

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

_clearers: list[Callable[[], None]] = []


def on_keys_changed(fn: Callable[[], None]) -> Callable[[], None]:
    """Register a cache to be dropped when a user's provider keys change.

    Usable as a decorator; returns the function unchanged.
    """
    _clearers.append(fn)
    return fn


def keys_changed() -> None:
    """Drop every registered cache. One failing must not stop the others, or.

    block the key from being saved.
    """
    for fn in _clearers:
        try:
            fn()
        except Exception:
            log.exception("could not clear %s", getattr(fn, "__qualname__", fn))
