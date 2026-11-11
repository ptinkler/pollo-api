"""Metadata database (SQLAlchemy ORM), split by concern.

    models       ORM models + the `iso` timestamp helper
    tenant       multi-tenant row scoping (ORM events) + set/reset/current
    _base        engine, schema catch-up, the locked session, _detach_id
    users / conversations / instructions / characters / messages / imports /
    library      the MetadataDB method mixins, by domain
    manager      MetadataDB (composed from the mixins) + get_db

Public surface is unchanged: import Base, MetadataDB, get_db, iso, set_tenant,
reset_tenant and current_tenant straight from `web.core.metadata` as before.
"""

from web.core.metadata.manager import MetadataDB, get_db
from web.core.metadata.models import (
    Base,
    Character,
    ChatConversation,
    ChatImportSkip,
    ChatInstruction,
    ChatInstructionGroup,
    ChatLibraryItem,
    ChatMessage,
    ChatSettings,
    ChatSpace,
    User,
    iso,
)
from web.core.metadata.tenant import TENANT_MODELS, current_tenant, reset_tenant, set_tenant

__all__ = [
    "TENANT_MODELS",
    "Base",
    "Character",
    "ChatConversation",
    "ChatImportSkip",
    "ChatInstruction",
    "ChatInstructionGroup",
    "ChatLibraryItem",
    "ChatMessage",
    "ChatSettings",
    "ChatSpace",
    "MetadataDB",
    "User",
    "current_tenant",
    "get_db",
    "iso",
    "reset_tenant",
    "set_tenant",
]
