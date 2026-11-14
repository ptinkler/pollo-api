"""Track imported chats and apply their message updates.

The importer in ``web/chatgpt_import.py`` uses these methods to preserve source
ids and apply each chat's changes in a single transaction.
"""

import json
import uuid
from datetime import datetime
from typing import NotRequired, TypedDict

from web.core.metadata._base import DBBase
from web.core.metadata.models import ChatConversation, ChatImportSkip, ChatLibraryItem, ChatMessage
from web.types import JsonValue


class ImportedMessage(TypedDict):
    """Represent one message staged by the chat importer."""

    import_id: str
    role: str
    content: str
    media: list[dict[str, JsonValue]]
    created_at: datetime
    parent_id: NotRequired[int | None]
    parent_import_id: NotRequired[str]
    model: NotRequired[str | None]


class ImportedMessageUpdate(TypedDict):
    """Represent optional content and media changes to an imported message."""

    content: NotRequired[str]
    media: NotRequired[list[dict[str, JsonValue]]]


class NativeMessage(TypedDict):
    """One message from this app's own export, keyed by its id on the exporting server."""

    import_id: str
    parent_import_id: str | None
    role: str
    content: str
    media: list[dict[str, JsonValue]]
    model: str | None
    mode: str | None
    lane: str | None
    status: str
    error: str | None
    cost: float | None
    text_versions_json: str | None
    created_at: datetime


class NativeLibraryItem(TypedDict):
    """Detached media from this app's own export."""

    media_id: str
    item: dict[str, JsonValue]
    created_at: datetime
    detached_at: datetime


class ImportMixin(DBBase):
    """Provide database operations for imported conversations."""

    def get_imported_conversations(self, source: str) -> dict[str, ChatConversation]:
        """Chats imported from `source`, by their id there."""
        with self._session() as session:
            convs = session.query(ChatConversation).filter(ChatConversation.import_source == source).all()
            result: dict[str, ChatConversation] = {}
            for conv in convs:
                session.expunge(conv)
                if conv.import_id is not None:
                    result[conv.import_id] = conv
            return result

    def get_import_skips(self, source: str) -> set[str]:
        """Ids of chats imported from `source` and since deleted."""
        with self._session() as session:
            return {r[0] for r in session.query(ChatImportSkip.import_id).filter(ChatImportSkip.source == source)}

    def add_imported_messages(
        self,
        conversation_id: str,
        rows: list[ImportedMessage],
        updates: dict[int, ImportedMessageUpdate],
        import_updated_at: float | None,
        updated_at: datetime | None,
        show: bool,
    ) -> None:
        """Apply one chat's import in one transaction.

        ``rows`` are new
        messages in order, each with its `import_id` and either `parent_id`
        or `parent_import_id` (a message imported earlier in `rows`);
        `updates` maps existing message ids to new `content`/`media`. With
        `show`, the last new message becomes the shown branch's end.
        """
        with self._session() as session:
            conv = session.get(ChatConversation, conversation_id)
            if conv is None:
                raise LookupError(conversation_id)
            ids: dict[str, int] = {}
            last = None
            for row in rows:
                if "parent_id" in row:
                    parent = row["parent_id"]
                else:
                    parent_import_id = row.get("parent_import_id")
                    if parent_import_id is None:
                        raise ValueError(conversation_id)
                    parent = ids[parent_import_id]
                msg = ChatMessage(
                    conversation_id=conversation_id,
                    parent_id=parent,
                    role=row["role"],
                    content=row["content"],
                    media_json=json.dumps(row["media"]) if row["media"] else None,
                    model=row.get("model"),
                    status="done",
                    import_id=row["import_id"],
                    created_at=row["created_at"],
                )
                session.add(msg)
                session.flush()
                ids[row["import_id"]] = last = msg.id
            for msg_id, fields in updates.items():
                msg = session.get(ChatMessage, msg_id)
                if not msg:
                    continue
                if "content" in fields:
                    msg.content = fields["content"]
                if "media" in fields:
                    media = fields["media"]
                    msg.media_json = json.dumps(media) if media else None
            conv.import_updated_at = import_updated_at
            if show and last is not None:
                conv.current_leaf_id = last
            conv.updated_at = updated_at or datetime.now().astimezone().replace(tzinfo=None)
            session.commit()

    def get_chat_import_ids(self, conversation_id: str) -> dict[str, ChatMessage]:
        """A chat's imported messages, by the id they were imported from."""
        with self._session() as session:
            msgs = (
                session.query(ChatMessage)
                .filter(ChatMessage.conversation_id == conversation_id, ChatMessage.import_id.isnot(None))
                .all()
            )
            for m in msgs:
                session.expunge(m)
            return {m.import_id: m for m in msgs if m.import_id is not None}

    def add_native_import(
        self,
        conversation_id: str,
        messages: list[NativeMessage],
        library: list[NativeLibraryItem],
        leaf_import_id: str | None,
        import_updated_at: float | None,
        updated_at: datetime | None,
    ) -> tuple[int, int]:
        """Merge one chat from this app's own export, in one transaction.

        Messages already imported (same `import_id`) are brought up to date;
        the rest are added under their parent (by `parent_import_id`; a parent
        that wasn't exported starts a branch). Library items are added once. The exported shown branch is shown here
        unless the chat has been carried on here. Returns (added, updated).
        """
        with self._session() as session:
            conv = session.get(ChatConversation, conversation_id)
            if conv is None:
                raise LookupError(conversation_id)
            existing = {
                m.import_id: m
                for m in session.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id)
                if m.import_id is not None
            }
            carried_on = conv.current_leaf_id is not None and not any(
                m.id == conv.current_leaf_id for m in existing.values()
            )
            ids = {key: m.id for key, m in existing.items()}
            added = updated = 0
            for row in messages:
                media_json = json.dumps(row["media"]) if row["media"] else None
                fields = {
                    "content": row["content"],
                    "media_json": media_json,
                    "status": row["status"],
                    "error": row["error"],
                    "cost": row["cost"],
                    "text_versions_json": row["text_versions_json"],
                }
                prev = existing.get(row["import_id"])
                if prev is not None:
                    if any(getattr(prev, k) != v for k, v in fields.items()):
                        for k, v in fields.items():
                            setattr(prev, k, v)
                        updated += 1
                    continue
                parent = row["parent_import_id"]
                msg = ChatMessage(
                    conversation_id=conversation_id,
                    parent_id=ids.get(parent) if parent is not None else None,
                    role=row["role"],
                    model=row["model"],
                    mode=row["mode"],
                    lane=row["lane"],
                    import_id=row["import_id"],
                    created_at=row["created_at"],
                    **fields,
                )
                session.add(msg)
                session.flush()
                ids[row["import_id"]] = msg.id
                added += 1
            # Already brought over by an earlier import of this chat
            have = {
                str(lib.item.get("import_media_id"))
                for lib in session.query(ChatLibraryItem).filter(ChatLibraryItem.conversation_id == conversation_id)
            }
            taken = {
                r[0]
                for r in session.query(ChatLibraryItem.media_id).filter(
                    ChatLibraryItem.media_id.in_([i["media_id"] for i in library])
                )
            }
            for lib in library:
                if lib["media_id"] in have:
                    continue
                # Media ids are unique server-wide: importing into the server it
                # came from (a copy of the chat) needs a fresh one
                media_id = uuid.uuid4().hex[:8] if lib["media_id"] in taken else lib["media_id"]
                item = {**lib["item"], "id": media_id, "import_media_id": lib["media_id"]}
                session.add(
                    ChatLibraryItem(
                        media_id=media_id,
                        conversation_id=conversation_id,
                        item_json=json.dumps(item),
                        created_at=lib["created_at"],
                        detached_at=lib["detached_at"],
                    )
                )
            if not carried_on and leaf_import_id in ids:
                conv.current_leaf_id = ids[leaf_import_id]
            conv.import_updated_at = import_updated_at
            conv.updated_at = updated_at or datetime.now().astimezone().replace(tzinfo=None)
            session.commit()
            return added, updated
