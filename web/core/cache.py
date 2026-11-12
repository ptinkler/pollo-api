"""Small in-process caches.

Several things are worth remembering for a while but not worth a database: a
price quote, a finished job's download link, a provider's answer to a question
whose answer rarely changes. They all want the same three properties — entries
expire, the map can't grow without bound, and threads don't corrupt it — so
they share one class instead of each hand-rolling it.

A cache here lives in one process and vanishes on restart, so nothing may
depend on a hit. Anything that must survive a restart belongs in the database;
anything another user must not see belongs under a per-tenant key.
"""

import threading
import time
from collections import OrderedDict


# Tells a cached None apart from a miss, for callers that cache "no answer".
class _Missing:
    """Sentinel returned for cache misses that differ from a cached None."""


MISS = _Missing()


class TTLCache[K, V]:
    """A bounded, expiring, thread-safe mapping.

    `get` returns `default` for an entry that is missing or past its time;
    `put` drops lapsed entries and then the oldest, so `maxsize` is a hard cap.
    """

    __slots__ = ("_entries", "_lock", "_maxsize", "_ttl")

    def __init__(self, ttl: float, maxsize: int = 512) -> None:
        """Build a cache whose entries expire after `ttl` seconds."""
        self._ttl = ttl
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._entries: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K, default: V | None = None) -> V | None:
        """Return a live value for ``key``, or ``default`` on a miss."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return default
            if time.monotonic() - entry[0] > self._ttl:
                del self._entries[key]
                return default
            return entry[1]

    def put(self, key: K, value: V) -> None:
        """Store ``value`` under ``key``, evicting expired or oldest entries."""
        with self._lock:
            now = time.monotonic()
            self._entries[key] = (now, value)
            self._entries.move_to_end(key)
            for lapsed in [k for k, (at, _) in self._entries.items() if now - at > self._ttl]:
                del self._entries[lapsed]
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        """The number of entries held, expired ones included."""
        with self._lock:
            return len(self._entries)
