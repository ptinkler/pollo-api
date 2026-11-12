"""Track imported chats and apply their message updates.

The importer in ``web/chatgpt_import.py`` uses these methods to preserve source
ids and apply each chat's changes in a single transaction.
"""

import json
from datetime import datetime
from typing import Any

from web.core.metadata.models import ChatConversation, ChatImportSkip, ChatMessage


class ImportMixin:
    """Provide database operations for imported conversations."""

    def get_imported_conversations(self, source: str) -> dict[str, ChatConversation]:
        """Chats imported from `source`, by their id there."""
        with self._session() as session:
            convs = session.query(ChatConversation).filter(ChatConversation.import_source == source).all()
            for c in convs:
                session.expunge(c)
            return {c.import_id: c for c in convs if c.import_id}

    def get_import_skips(self, source: str) -> set[str]:
        """Ids of chats imported from `source` and since deleted."""
        with self._session() as session:
            return {r[0] for r in session.query(ChatImportSkip.import_id).filter(ChatImportSkip.source == source)}

    def add_imported_messages(
        self,
        conversation_id: str,
        rows: list[dict[str, Any]],
        updates: dict[int, dict[str, Any]],
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
            ids: dict[str, int] = {}
            last = None
            for row in rows:
                parent = row["parent_id"] if "parent_id" in row else ids[row["parent_import_id"]]
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
                    msg.media_json = json.dumps(fields["media"]) if fields["media"] else None
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
            return {m.import_id: m for m in msgs}
