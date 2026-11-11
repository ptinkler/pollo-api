"""The database manager, composed from the domain mixins, plus the global
singleton accessor.
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
    """SQLAlchemy-based database manager. The engine, schema catch-up and the
    locked session live on _DBBase; each domain's methods come from a mixin.
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
