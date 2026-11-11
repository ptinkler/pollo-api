"""Tests for web.core.metadata.schema — Alembic brings the database up to date.

This replaces the hand-maintained `_LATE_COLUMNS` / `_BACKFILLS` catch-up that
used to live in _base.py and had to be kept in step with the migrations by hand.
The case that matters is the real one: a database this app created *before*
Alembic was wired in here, which has no version row but a current schema.
"""

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

import web.core.metadata._base as base
from web.core.metadata import MetadataDB
from web.core.metadata.schema import ADOPT_AT, ensure_schema

pytestmark = pytest.mark.no_tenant


def _version(path):
    eng = sa.create_engine(f"sqlite:///{path}")
    with eng.begin() as c:
        return c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


def test_a_new_database_is_stamped_at_head(tmp_path):
    """create_all already made the current schema, so nothing should re-run."""
    path = tmp_path / "new.db"
    db = MetadataDB(db_path=path)
    assert db._fresh is True
    ensure_schema(db.engine, path, fresh=True)

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    assert _version(path) == ScriptDirectory.from_config(cfg).get_current_head()


def test_an_unversioned_database_is_adopted_not_replayed(tmp_path):
    """Replaying from 0001 fails on a populated database (0002 re-adds a
    column), so one without a version row is adopted at ADOPT_AT instead."""
    path = tmp_path / "old.db"
    db = MetadataDB(db_path=path)
    conv = db.create_conversation(title="Fox")
    db.engine.dispose()
    # forget that Alembic was ever here — this is the shape of a pre-Alembic DB
    eng = sa.create_engine(f"sqlite:///{path}")
    with eng.begin() as c:
        c.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    eng.dispose()

    db2 = MetadataDB(db_path=path)
    ensure_schema(db2.engine, path, fresh=False)
    assert _version(path) is not None
    assert db2.get_conversation(conv.id).title == "Fox"  # data untouched


def test_adopting_still_runs_the_migrations_after_it(tmp_path):
    """The point of adopting at ADOPT_AT rather than head: anything newer
    must still run. 0027 rewrites stored Pollo model ids."""
    path = tmp_path / "old.db"
    db = MetadataDB(db_path=path)
    conv = db.create_conversation(title="Fox")
    msg = db.add_chat_message(
        conv.id,
        "assistant",
        "here",
        media=[{"id": "m1", "kind": "image", "source": "generated", "status": "done", "model": "pollo/seedreamv1"}],
    )
    db.engine.dispose()
    eng = sa.create_engine(f"sqlite:///{path}")
    with eng.begin() as c:
        c.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    eng.dispose()

    db2 = MetadataDB(db_path=path)
    ensure_schema(db2.engine, path, fresh=False)
    assert _version(path) > ADOPT_AT  # moved past the adoption point
    media = db2.get_chat_message(msg.id).media
    assert media[0]["model"] == "pollo/seedream"  # 0027 ran


def test_a_broken_migration_does_not_stop_the_server(tmp_path, monkeypatch):
    """A server that can't migrate should still start and say so."""
    path = tmp_path / "x.db"
    db = MetadataDB(db_path=path)
    monkeypatch.setattr(
        "web.core.metadata.schema.command.upgrade", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    ensure_schema(db.engine, path, fresh=True)  # must not raise


def test_the_old_handwritten_catch_up_is_gone(tmp_path):
    """It was a second copy of the schema; Alembic is the only one now."""

    src = __import__("pathlib").Path(base.__file__).read_text()
    assert "_LATE_COLUMNS" not in src and "_BACKFILLS" not in src
