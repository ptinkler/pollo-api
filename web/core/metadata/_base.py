"""The database manager's shared infrastructure: engine setup, the SQLite
pragmas, schema catch-up (late columns / backfills + the settings seed), the
locked session context manager, and the one cross-domain helper (_detach_id)."""

import json
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

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

        Base.metadata.create_all(self.engine)
        self._add_missing_columns()
        self._seed_global_settings()

    def _seed_global_settings(self) -> None:
        """Carry the old per-snippet/group `is_default` flag into the global
        settings bucket, once, when upgrading a database that still has those
        columns (Docker does this in Alembic; a local dev server does it here)."""
        from sqlalchemy import inspect, text

        # Read schema first (the inspector rolls back after each query, which
        # would undo writes if interleaved with the transaction below)
        insp = inspect(self.engine)
        picks = {
            "default_instruction_ids_json": "chat_instructions",
            "default_instruction_group_ids_json": "chat_instruction_groups",
        }
        has_flag = {
            table: insp.has_table(table) and "is_default" in {c["name"] for c in insp.get_columns(table)}
            for table in picks.values()
        }
        with self.engine.begin() as conn:
            if conn.execute(text("SELECT 1 FROM chat_settings WHERE id = 1")).first():
                return  # already set up
            values: dict[str, str] = {}
            for field, table in picks.items():
                if has_flag[table]:
                    ids = [r[0] for r in conn.execute(text(f"SELECT id FROM {table} WHERE is_default = 1"))]
                    if ids:
                        values[field] = json.dumps(ids)
            cols = ", ".join(["id", "updated_at", *values])
            placeholders = ", ".join(["1", ":updated_at", *(f":{k}" for k in values)])
            params = {"updated_at": datetime.now().isoformat(sep=" "), **values}
            conn.execute(text(f"INSERT INTO chat_settings ({cols}) VALUES ({placeholders})"), params)

    # Columns added after a table first existed. create_all() only creates
    # missing *tables*; Docker runs Alembic on start, but a local dev server
    # doesn't, so add them here too (same as the Alembic migration).
    _LATE_COLUMNS = {
        "chat_conversations": {
            "instruction_id": "INTEGER",
            "instruction_ids_json": "TEXT",
            "instruction_group_ids_json": "TEXT",
            "space_id": "INTEGER",
            "current_leaf_id": "INTEGER",
            "character_ids_json": "TEXT",
            "forked_from_id": "VARCHAR(50)",
            "forked_from_message_id": "INTEGER",
            "inherited_cost": "FLOAT",
            "inherited_credits": "INTEGER",
            "pinned": "BOOLEAN NOT NULL DEFAULT 0",
            "kind": "VARCHAR(10) NOT NULL DEFAULT 'chat'",
            "settings_json": "TEXT",
            "hidden_defaults_json": "TEXT",
            "paused_instructions_json": "TEXT",
            "import_source": "VARCHAR(20)",
            "import_id": "VARCHAR(100)",
            "import_updated_at": "FLOAT",
            "user_id": "VARCHAR(50)",
        },
        "chat_messages": {
            "parent_id": "INTEGER",
            "mode": "VARCHAR(10)",
            "lane": "VARCHAR(10)",
            "import_id": "VARCHAR(100)",
            "user_id": "VARCHAR(50)",
        },
        # Tenant ownership on the remaining user-owned tables (the local-dev
        # counterpart to Alembic 0020)
        "characters": {"user_id": "VARCHAR(50)"},
        "chat_instructions": {"user_id": "VARCHAR(50)"},
        "chat_instruction_groups": {"user_id": "VARCHAR(50)"},
        "chat_spaces": {"user_id": "VARCHAR(50)"},
        "chat_settings": {"user_id": "VARCHAR(50)"},
        "chat_library_items": {"user_id": "VARCHAR(50)"},
        "chat_import_skips": {"user_id": "VARCHAR(50)"},
        "users": {"password_hash": "TEXT"},
    }
    # Run once when the column is added: chats from before branching were
    # linear, so each message's parent is the one before it
    _BACKFILLS = {
        "parent_id": "UPDATE chat_messages SET parent_id = (SELECT MAX(p.id) FROM chat_messages p "
        "WHERE p.conversation_id = chat_messages.conversation_id AND p.id < chat_messages.id)",
        "current_leaf_id": "UPDATE chat_conversations SET current_leaf_id = (SELECT MAX(m.id) "
        "FROM chat_messages m WHERE m.conversation_id = chat_conversations.id)",
        # Carry the old single attachment into the new list (instruction_id is
        # added just above, so the column exists even on older databases)
        "instruction_ids_json": "UPDATE chat_conversations SET instruction_ids_json = '[' || instruction_id || ']' "
        "WHERE instruction_id IS NOT NULL AND instruction_ids_json IS NULL",
    }

    def _add_missing_columns(self) -> None:
        from sqlalchemy import inspect, text

        # Read the schema first: the inspector shares the one StaticPool
        # connection and rolls back after each query, which would undo the
        # backfill UPDATEs if it ran between them
        insp = inspect(self.engine)
        existing = {t: {c["name"] for c in insp.get_columns(t)} for t in self._LATE_COLUMNS if insp.has_table(t)}
        with self.engine.begin() as conn:
            for table, columns in self._LATE_COLUMNS.items():
                if table not in existing:
                    continue
                for name, ddl in columns.items():
                    if name not in existing[table]:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                        if name in self._BACKFILLS:
                            conn.execute(text(self._BACKFILLS[name]))

    @contextmanager
    def _session(self):
        """Yield a Session while holding the thread lock.

        Because StaticPool shares one raw connection across threads, we
        serialise all database work through a threading.Lock so two
        threads never interleave SQL on the same connection.
        """
        with self._lock, Session(self.engine) as session:
            yield session

    @staticmethod
    def _detach_id(session, model, json_column, list_attr: str, target_id: int) -> None:
        """Remove target_id from the JSON id-list (`list_attr`) of every row
        whose `json_column` text mentions it (exact check after the LIKE)."""
        for row in session.query(model).filter(json_column.like(f"%{target_id}%")).all():
            ids = getattr(row, list_attr)
            if target_id in ids:
                setattr(row, list_attr, [i for i in ids if i != target_id])
