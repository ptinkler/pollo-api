"""Track imported chats and apply their message updates.

The importer in ``web/chatgpt_import.py`` uses these methods to preserve source
ids and apply each chat's changes in a single transaction.
"""

import json
from datetime import datetime
from typing import NotRequired, TypedDict

from web.core.metadata._base import DBBase
from web.core.metadata.models import ChatConversation, ChatImportSkip, ChatMessage
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
