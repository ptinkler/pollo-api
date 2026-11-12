"""Provide infrastructure shared by the metadata database mixins.

This module configures the engine and SQLite pragmas, provides the locked
session context manager and shared list/get/save helpers, and detaches ids from
JSON-backed lists. Alembic owns the schema; see ``schema.py``.
"""

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TypeVar, cast

import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.elements import ColumnElement

from web.core.config import DB_PATH
from web.core.metadata.models import Base
from web.types import JsonValue

ModelT = TypeVar("ModelT", bound=Base)
OrderByT = TypeVar("OrderByT")


class DBBase:
    """Provide the engine and locked sessions used by domain mixins.

    Also handles fresh-database initialization and shared ORM helpers.
    """

    def __init__(self, db_path: Path | None = None) -> None:
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
        def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _connection_record: sa.pool.ConnectionPoolEntry) -> None:
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
    def _session(self) -> Generator[Session]:
        """Yield a Session while holding the thread lock.

        Because StaticPool shares one raw connection across threads, we
        serialise all database work through a threading.Lock so two
        threads never interleave SQL on the same connection.
        """
        with self._lock, Session(self.engine) as session:
            yield session

    # ── small helpers the domain mixins share. Each opens a session, does the
    #    one thing, and detaches what it returns so callers hold plain objects.

    def _list(
        self,
        model: type[ModelT],
        order_by: ColumnElement[OrderByT] | InstrumentedAttribute[OrderByT] | None = None,
    ) -> list[ModelT]:
        with self._session() as session:
            query = session.query(model)
            items = (query.order_by(order_by) if order_by is not None else query).all()
            for item in items:
                session.expunge(item)
            return items

    def _get(self, model: type[ModelT], pk: int | str) -> ModelT | None:
        with self._session() as session:
            item = session.get(model, pk)
            if item:
                session.expunge(item)
            return item

    def _save(self, model: type[ModelT], pk: int | str | None, **fields: JsonValue) -> ModelT | None:
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
                setattr(item, "updated_at", datetime.now().astimezone().replace(tzinfo=None))  # noqa: B010
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    @staticmethod
    def _detach_id(
        session: Session,
        model: type[ModelT],
        json_column: InstrumentedAttribute[OrderByT],
        list_attr: str,
        target_id: int,
    ) -> None:
        """Remove an id from a JSON-backed list on matching rows.

        The SQL ``LIKE`` narrows the rows; membership is checked exactly
        before the id is removed.
        """
        for row in session.query(model).filter(json_column.like(f"%{target_id}%")).all():
            ids = cast("list[int]", getattr(row, list_attr))
            if target_id in ids:
                setattr(row, list_attr, [i for i in ids if i != target_id])
