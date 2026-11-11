"""The database manager's shared infrastructure: engine setup, the SQLite
pragmas, the locked session context manager, the small list/get/save helpers
the domain mixins share, and the one cross-domain helper (_detach_id).

The schema itself is Alembic's — see web/core/metadata/schema.py."""

import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ..config import DB_PATH
from .models import Base


class _DBBase:
    """Engine, schema catch-up and the locked session context the domain mixins
    (users, conversations, …) build on."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # StaticPool keeps a single connection open for the process lifetime.
        # This avoids repeated file-lock acquire/release cycles, which is
        # critical when the DB file lives on a NAS (NFS/SMB) where POSIX
        # locking may be unreliable.
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=DELETE")
            cursor.execute("PRAGMA synchronous=NORMAL")
            # Hold an exclusive lock for the lifetime of the connection so
            # SQLite never re-negotiates locks against the filesystem.
            cursor.execute("PRAGMA locking_mode=EXCLUSIVE")
            cursor.close()

        # Alembic owns the schema (see schema.ensure_schema, run at startup).
        # create_all only has to make the tables of a brand-new file.
        fresh = not sa.inspect(self.engine).has_table("chat_conversations")
        Base.metadata.create_all(self.engine)
        self._fresh = fresh

    @contextmanager
    def _session(self):
        """Yield a Session while holding the thread lock.

        Because StaticPool shares one raw connection across threads, we
        serialise all database work through a threading.Lock so two
        threads never interleave SQL on the same connection.
        """
        with self._lock, Session(self.engine) as session:
            yield session

    # ── small helpers the domain mixins share. Each opens a session, does the
    #    one thing, and detaches what it returns so callers hold plain objects.

    def _list(self, model, order_by=None) -> list:
        with self._session() as session:
            query = session.query(model)
            items = (query.order_by(order_by) if order_by is not None else query).all()
            for item in items:
                session.expunge(item)
            return items

    def _get(self, model, pk):
        with self._session() as session:
            item = session.get(model, pk)
            if item:
                session.expunge(item)
            return item

    def _save(self, model, pk, **fields):
        """Create (pk None) or update one row; None if the pk isn't there."""
        with self._session() as session:
            if pk is None:
                item = model(**fields)
                session.add(item)
            else:
                item = session.get(model, pk)
                if not item:
                    return None
                for key, value in fields.items():
                    setattr(item, key, value)
                item.updated_at = datetime.now()
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    @staticmethod
    def _detach_id(session, model, json_column, list_attr: str, target_id: int) -> None:
        """Remove target_id from the JSON id-list (`list_attr`) of every row
        whose `json_column` text mentions it (exact check after the LIKE)."""
        for row in session.query(model).filter(json_column.like(f"%{target_id}%")).all():
            ids = getattr(row, list_attr)
            if target_id in ids:
                setattr(row, list_attr, [i for i in ids if i != target_id])
