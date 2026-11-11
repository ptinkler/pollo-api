"""Tests for web.core.cache — the shared in-process TTL cache."""

import time

from web.core.cache import MISS, TTLCache


def test_returns_what_was_put():
    c = TTLCache(ttl=60)
    c.put("k", 1)
    assert c.get("k") == 1
    assert c.get("missing") is None
    assert c.get("missing", MISS) is MISS


def test_a_cached_none_is_not_a_miss():
    """Callers cache 'no answer' (a refused estimate, an unpriced model)."""
    c = TTLCache(ttl=60)
    c.put("k", None)
    assert c.get("k", MISS) is None


def test_entries_expire():
    c = TTLCache(ttl=0.01)
    c.put("k", 1)
    time.sleep(0.02)
    assert c.get("k", MISS) is MISS


def test_maxsize_is_a_hard_cap_evicting_oldest_first():
    c = TTLCache(ttl=60, maxsize=3)
    for i in range(10):
        c.put(i, i)
    assert len(c) == 3
    assert c.get(0, MISS) is MISS  # the oldest went
    assert c.get(9) == 9  # the newest stayed


def test_put_refreshes_an_existing_key():
    c = TTLCache(ttl=60, maxsize=2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 3)  # now the newest, so "b" is evicted next
    c.put("c", 4)
    assert c.get("a") == 3
    assert c.get("b", MISS) is MISS


def test_lapsed_entries_are_dropped_on_write():
    c = TTLCache(ttl=0.01, maxsize=100)
    c.put("old", 1)
    time.sleep(0.02)
    c.put("new", 2)
    assert len(c) == 1  # the lapsed entry didn't just sit there


def test_clear():
    c = TTLCache(ttl=60)
    c.put("k", 1)
    c.clear()
    assert len(c) == 0
    assert c.get("k", MISS) is MISS
