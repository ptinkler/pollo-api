"""Bringing the database up to date.

Alembic owns the schema. This runs it at startup so a server started any way
— `make dev-api`, uvicorn directly, the container — lands on the same schema,
rather than Docker running migrations while a local run quietly didn't.

That gap is why there used to be a second, hand-maintained copy of the schema
in _base.py (`_LATE_COLUMNS` / `_BACKFILLS`): a list of ALTER TABLEs that had
to be kept in step with the migrations by hand, and drifted.
"""

import logging
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]

# A database this app created before Alembic was wired in here has no version
# row, but its schema was kept current by that hand-maintained catch-up — which
# reproduced everything up to and including 0026. Such a database is adopted at
# that revision, so only the migrations after it run. A brand-new file gets its
# tables from create_all() and is stamped at head instead.
ADOPT_AT = "0026"


def _config(db_path: Path) -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def ensure_schema(engine: sa.Engine, db_path: Path, fresh: bool) -> None:
    """Stamp an unversioned database, then upgrade to head. Never raises: a
    server that can't migrate should still start and say so.

    The engine is disposed first. Our connections hold
    `PRAGMA locking_mode=EXCLUSIVE` for their lifetime (see _base.py), so
    while one is open Alembic's own connection can't write — it would block
    until SQLite's busy timeout and then fail. Disposing releases the lock;
    the pool reconnects on the next query.
    """
    try:
        # Ask before disposing: inspecting reconnects, which would retake the lock.
        versioned = sa.inspect(engine).has_table("alembic_version")
        engine.dispose()
        cfg = _config(db_path)
        if not versioned:
            at = "head" if fresh else ADOPT_AT
            log.info("database has no Alembic version: adopting it at %s", at)
            command.stamp(cfg, at)
        command.upgrade(cfg, "head")
    except Exception:
        log.exception("could not bring the database up to date")
