"""Derived facts about media files, cached beside the thumbnails.

A video's length is read by opening the file with OpenCV, which on a NAS costs
a fraction of a second each — enough to make listing a library of videos take
the best part of a minute. The answers are kept here rather than in the
metadata database: this is a cache of what's on disk, not anything a user
wrote, so it lives with the thumbnails under <data>/cache, where deleting the
folder wipes it and nothing is left among real records.

It can't grow unchecked:

  • the file's path is the primary key, so a re-encoded file replaces its row
    instead of adding one — at most one row per file that exists;
  • deleting media drops its row, next to the thumbnail it already deletes;
  • a sweep on first use drops rows whose file has since gone.

Every call degrades to "not cached" if the file can't be opened or read: it's
a cache, so losing it costs time, never correctness.
"""

import logging
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from web.core import config

log = logging.getLogger(__name__)

_SCHEMA = "CREATE TABLE IF NOT EXISTS durations (path TEXT PRIMARY KEY, mtime_ns INTEGER, seconds REAL)"
_TIMEOUT = 5.0
_swept = False
_sweep_lock = threading.Lock()


def db_path() -> Path:
    """Return the SQLite file path used for cached media durations."""
    # Read config at call time so tests can redirect ROOT_DIR
    return config.ROOT_DIR / "cache" / "media-cache.sqlite"


def _with_db(work: Callable[[sqlite3.Connection], Any], default: Any = None) -> Any:
    """Run `work` against the cache, or return `default` if it can't be used.

    The connection is opened per call: these happen once per process, once per
    filled page and once per delete, so there's nothing to gain from a shared
    one and a lock to hold. Any failure — a missing folder, a locked or corrupt
    file — is reported and shrugged off, because a cache must never break the
    request that used it.
    """
    conn = None
    try:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=_TIMEOUT)
        conn.execute(_SCHEMA)
        result = work(conn)
        conn.commit()
        return result
    except Exception as e:  # see above
        log.warning("media cache unusable (%s) — lengths will be read from the files", e)
        return default
    finally:
        if conn is not None:
            conn.close()


def durations() -> dict[str, tuple[int, float | None]]:
    """Every known length: path → (the mtime it was read at, seconds)."""
    read = "SELECT path, mtime_ns, seconds FROM durations"
    return _with_db(lambda c: {r[0]: (r[1], r[2]) for r in c.execute(read)}, {})


def remember(rows: list[tuple[str, int, float | None]]) -> None:
    """Record lengths just read, one transaction for the lot."""
    if rows:
        _with_db(lambda c: c.executemany("INSERT OR REPLACE INTO durations VALUES (?, ?, ?)", rows))


def forget(path: Path | str) -> None:
    """Drop a deleted file's row, so nothing is left behind for it."""
    _with_db(lambda c: c.execute("DELETE FROM durations WHERE path = ?", (str(path),)))


def sweep() -> int:
    """Drop rows whose file has gone or changed. Returns how many went."""
    return _with_db(_sweep, 0)


def _sweep(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT path, mtime_ns FROM durations").fetchall()
    stale = [(p,) for p, mtime_ns in rows if not _still_there(p, mtime_ns)]
    conn.executemany("DELETE FROM durations WHERE path = ?", stale)
    return len(stale)


def _still_there(path: str, mtime_ns: int) -> bool:
    try:
        return Path(path).stat().st_mtime_ns == mtime_ns
    except OSError:
        return False


def sweep_in_background() -> None:
    """Start the one-time stale-row sweep in a daemon thread.

    The sweep stats every cached path, so requests do not wait for it.
    """
    global _swept
    with _sweep_lock:
        if _swept:
            return
        _swept = True
    threading.Thread(target=sweep, daemon=True, name="media-cache-sweep").start()
