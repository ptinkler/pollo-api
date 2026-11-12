"""Compose the metadata database from domain mixins.

This module also provides the process-wide database singleton accessor.
"""

import threading

from web.core.metadata._base import _DBBase
from web.core.metadata.characters import CharacterMixin
from web.core.metadata.conversations import ConversationMixin
from web.core.metadata.imports import ImportMixin
from web.core.metadata.instructions import InstructionMixin
from web.core.metadata.library import LibraryMixin
from web.core.metadata.messages import MessageMixin
from web.core.metadata.users import UserMixin


class MetadataDB(
    _DBBase,
    UserMixin,
    ConversationMixin,
    InstructionMixin,
    CharacterMixin,
    MessageMixin,
    ImportMixin,
    LibraryMixin,
):
    """Manage metadata through a SQLAlchemy engine.

    The engine, schema catch-up, and locked session live on ``_DBBase``; domain
    methods come from the mixins.
    """


_db_instance: MetadataDB | None = None
_db_init_lock = threading.Lock()


def get_db() -> MetadataDB:
    """Get the global metadata database instance."""
    global _db_instance
    if _db_instance is None:
        with _db_init_lock:
            if _db_instance is None:
                _db_instance = MetadataDB()
    return _db_instance
