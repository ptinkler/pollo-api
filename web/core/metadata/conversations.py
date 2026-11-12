"""Conversation (chat thread) CRUD, listing, search, forks and deletion."""

import re
import uuid
from datetime import datetime

from web.core.metadata._base import DBBase
from web.core.metadata.models import ChatConversation, ChatImportSkip, ChatLibraryItem, ChatMessage
from web.core.metadata.tenant import reset_tenant, set_tenant
from web.types import JsonValue


class ConversationMixin(DBBase):
    """Provide conversation creation, lookup, search, and deletion operations."""

    def create_conversation(self, title: str = "New chat", **fields: JsonValue) -> ChatConversation:
        """Create a conversation with a generated id."""
        with self._session() as session:
            conv = ChatConversation(id=uuid.uuid4().hex, title=title, **fields)
            session.add(conv)
            session.commit()
            session.refresh(conv)
            session.expunge(conv)
            return conv

    def conversation_titles(self) -> dict[str, str]:
        """Return conversation titles keyed by id.

        Used to label media and characters with the chat they came from.
        """
        return {c.id: c.title for c in self.list_conversations(limit=None)}

    def get_conversation(self, conv_id: str) -> ChatConversation | None:
        """Return a conversation by id, or ``None`` if it does not exist."""
        with self._session() as session:
            conv = session.get(ChatConversation, conv_id)
            if conv:
                session.expunge(conv)
            return conv

    def conversation_exists_any_tenant(self, conv_id: str) -> bool:
        """Check whether a conversation id belongs to any tenant.

        Bypasses tenant scope to distinguish another user's conversation from
        an orphaned chat folder with no corresponding database row.
        """
        token = set_tenant(None)  # None disables the per-tenant select filter
        try:
            with self._session() as session:
                return session.get(ChatConversation, conv_id) is not None
        finally:
            reset_tenant(token)

    def list_conversations(self, limit: int | None = 200) -> list[ChatConversation]:
        """Return pinned conversations first, then recently active ones.

        Pass ``limit=None`` to return every conversation.
        """
        with self._session() as session:
            query = session.query(ChatConversation).order_by(
                ChatConversation.pinned.desc(), ChatConversation.updated_at.desc()
            )
            convs = (query.limit(limit) if limit is not None else query).all()
            for c in convs:
                session.expunge(c)
            return convs

    def conversation_thumbs(self, conv_ids: list[str]) -> dict[str, str]:
        """Return each conversation's newest completed image file.

        Conversations without one are omitted; all ids are queried together.
        """
        out: dict[str, str] = {}
        if not conv_ids:
            return out
        with self._session() as session:
            rows = (
                session.query(ChatMessage)
                .filter(ChatMessage.conversation_id.in_(conv_ids), ChatMessage.media_json.isnot(None))
                .order_by(ChatMessage.id.desc())
            )
            for msg in rows:
                if msg.conversation_id in out:
                    continue
                for item in msg.media:
                    file = item.get("file")
                    if item.get("kind") == "image" and item.get("status") == "done" and isinstance(file, str):
                        out[msg.conversation_id] = file
                        break
        return out

    def search_conversations(self, query: str, limit: int = 100) -> list[tuple[ChatConversation, str | None]]:
        """Find conversations whose title or messages contain a query.

        Searches all branches without regard to case, returning most recently
        active conversations first with the first matching message's text (or
        ``None`` when only the title matched).
        """
        pattern = "%" + re.sub(r"([\\%_])", r"\\\1", query) + "%"
        with self._session() as session:
            snippets: dict[str, str] = {}
            for msg in (
                session.query(ChatMessage)
                .filter(ChatMessage.content.ilike(pattern, escape="\\"))
                .order_by(ChatMessage.id)
            ):
                snippets.setdefault(msg.conversation_id, msg.content)
            convs = (
                session.query(ChatConversation)
                .filter(
                    ChatConversation.title.ilike(pattern, escape="\\") | ChatConversation.id.in_(list(snippets)),
                )
                .order_by(ChatConversation.updated_at.desc())
                .limit(limit)
                .all()
            )
            for c in convs:
                session.expunge(c)
            return [(c, None if query.lower() in c.title.lower() else snippets.get(c.id)) for c in convs]

    def list_conversation_forks(self, conv_id: str) -> list[ChatConversation]:
        """Chats branched off this one, oldest first."""
        with self._session() as session:
            convs = (
                session.query(ChatConversation)
                .filter(ChatConversation.forked_from_id == conv_id)
                .order_by(ChatConversation.created_at)
                .all()
            )
            for c in convs:
                session.expunge(c)
            return convs

    def set_conversation_pinned(self, conv_id: str, pinned: bool) -> None:
        """Pin or unpin. Not an edit, so the chat keeps its place among the rest."""
        with self._session() as session:
            session.query(ChatConversation).filter(ChatConversation.id == conv_id).update(
                {ChatConversation.pinned: pinned, ChatConversation.updated_at: ChatConversation.updated_at}
            )
            session.commit()

    def update_conversation(self, conv_id: str, **fields: JsonValue | datetime) -> ChatConversation | None:
        """Update supported conversation fields, or return ``None`` if missing."""
        with self._session() as session:
            conv = session.get(ChatConversation, conv_id)
            if not conv:
                return None
            for key, value in fields.items():
                if hasattr(conv, key):
                    setattr(conv, key, value)
            conv.updated_at = datetime.now().astimezone().replace(tzinfo=None)
            session.commit()
            session.refresh(conv)
            session.expunge(conv)
            return conv

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation and its messages and library items."""
        with self._session() as session:
            conv = session.get(ChatConversation, conv_id)
            if not conv:
                return False
            if conv.import_source and conv.import_id:
                session.merge(ChatImportSkip(source=conv.import_source, import_id=conv.import_id))
            # In bulk: the cascade would load and delete each message on its own
            for model in (ChatMessage, ChatLibraryItem):
                session.query(model).filter(model.conversation_id == conv_id).delete(synchronize_session=False)
            session.delete(conv)
            session.commit()
            return True
