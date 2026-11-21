"""Scheduled backups of the SQLite database.

Every BACKUP_INTERVAL_HOURS (default 24; 0 turns it off) a consistent copy goes to
<data dir>/backups/metadata-<timestamp>.db, and all but the newest BACKUP_KEEP (default 7) are deleted.
A restored copy is unusable without the original KEYS_SECRET and PASSWORD_PEPPER: back those up too.
"""

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from web.core import config
from web.core.env import number_env
from web.core.metadata import get_db

log = logging.getLogger(__name__)

PREFIX = "metadata-"
SUFFIX = ".db"
DEFAULT_INTERVAL_HOURS = 24.0
DEFAULT_KEEP = 7


def interval_seconds() -> float:
    """Seconds between backups; 0 means backups are off."""
    return number_env("BACKUP_INTERVAL_HOURS", DEFAULT_INTERVAL_HOURS) * 3600


def keep_count() -> int:
    """How many backups to keep (at least 1)."""
    return int(number_env("BACKUP_KEEP", DEFAULT_KEEP, minimum=1))


def list_backups(directory: Path | None = None) -> list[Path]:
    """The backups in `directory` (default: the configured folder), oldest first (the timestamp in the name sorts)."""
    return sorted((directory or config.backup_dir()).glob(f"{PREFIX}*{SUFFIX}"))


def prune(directory: Path, keep: int) -> int:
    """Delete all but the newest `keep` backups; returns how many were removed."""
    old = list_backups(directory)[:-keep]
    for path in old:
        path.unlink(missing_ok=True)
    return len(old)


def run_backup(directory: Path | None = None, keep: int | None = None) -> Path:
    """Write one backup (to a temp name first, so a crash never leaves a half file that looks real), then prune."""
    directory = directory or config.backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    final = directory / f"{PREFIX}{stamp}{SUFFIX}"
    partial = final.with_suffix(".partial")
    partial.unlink(missing_ok=True)
    get_db().backup_to(partial)
    partial.replace(final)
    prune(directory, keep or keep_count())
    return final


def seconds_until_due(interval: float, directory: Path | None = None) -> float:
    """How long until the next backup: restarts must not push it back, so the newest file's age counts."""
    existing = list_backups(directory)
    if not existing:
        return 60.0  # first run: shortly after startup, once the app is settled
    return max(60.0, interval - (time.time() - existing[-1].stat().st_mtime))


def _loop(stop: threading.Event, interval: float) -> None:
    wait = seconds_until_due(interval)
    while not stop.wait(wait):
        wait = interval
        try:
            log.info("database backup: %s", run_backup().name)
        except Exception:  # a failed backup must not stop the next one
            log.exception("database backup failed")


def start_backups() -> threading.Event | None:
    """Start the backup thread unless disabled; returns the event that stops it."""
    interval = interval_seconds()
    if not interval:
        log.info("database backups are off (BACKUP_INTERVAL_HOURS=0)")
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop, interval), daemon=True, name="db-backup").start()
    log.info("database backups every %g h, keeping %d, in %s", interval / 3600, keep_count(), config.backup_dir())
    return stop
