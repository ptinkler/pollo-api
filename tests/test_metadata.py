"""Tests for web.core.metadata — MetadataDB singleton and timestamp handling."""

import time
from datetime import UTC, datetime

import pytest

import web.core.config as config_mod
from web.core.metadata import MetadataDB, _base, get_db, manager


@pytest.fixture
def db(tmp_path):
    """Return a MetadataDB backed by a fresh temp file."""
    return MetadataDB(db_path=tmp_path / "test.db")


class TestGlobalDB:
    """Tests for global db."""

    def test_get_db_returns_singleton(self, tmp_path, monkeypatch):
        """Test that get db returns singleton."""
        old = manager._db_instance
        monkeypatch.setattr(config_mod, "DB_PATH", tmp_path / "data" / "singleton.db")
        monkeypatch.setattr(_base, "DB_PATH", tmp_path / "data" / "singleton.db")
        try:
            manager._db_instance = None
            assert get_db() is get_db()
        finally:
            manager._db_instance = old


@pytest.mark.parametrize("tz", ["UTC", "Europe/London", "America/New_York"])
def test_timestamps_carry_the_servers_utc_offset(tmp_path, monkeypatch, tz):
    """Stored timestamps are naive server-local time. Serialised without an.

    offset, a browser in another timezone misreads them (a UTC server and a
    UTC+1 browser showed a 1:20 render as 61:20).
    """
    monkeypatch.setenv("TZ", tz)
    time.tzset()
    try:
        db = MetadataDB(db_path=tmp_path / "m.db")
        conv = db.create_conversation()
        stamp = db.add_chat_message(conv.id, "user", "hi").to_dict()["created_at"]
        assert isinstance(stamp, str)
        parsed = datetime.fromisoformat(stamp)
        assert parsed.tzinfo is not None
        assert abs((datetime.now(UTC) - parsed).total_seconds()) < 5
    finally:
        monkeypatch.undo()
        time.tzset()
