"""The database manager, composed from the domain mixins, plus the global
singleton accessor."""

import threading

from ._base import _DBBase
from .characters import CharacterMixin
from .conversations import ConversationMixin
from .imports import ImportMixin
from .instructions import InstructionMixin
from .library import LibraryMixin
from .messages import MessageMixin
from .users import UserMixin


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
    """SQLAlchemy-based database manager. The engine, schema catch-up and the
    locked session live on _DBBase; each domain's methods come from a mixin."""


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
