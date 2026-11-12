"""The chat library: media detached from its message (edits/retries)."""

from web.core.metadata.models import ChatLibraryItem


class LibraryMixin:
    """Provide lookup and deletion operations for detached chat media."""

    def list_chat_library(self) -> list[ChatLibraryItem]:
        """Return detached media items, newest first."""
        with self._session() as session:
            items = session.query(ChatLibraryItem).order_by(ChatLibraryItem.created_at.desc()).all()
            for i in items:
                session.expunge(i)
            return items

    def get_chat_library_item(self, media_id: str) -> ChatLibraryItem | None:
        """Return the detached item with this media id, if present."""
        with self._session() as session:
            item = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            if item:
                session.expunge(item)
            return item

    def delete_chat_library_item(self, media_id: str) -> bool:
        """Delete a detached media item and report whether it existed."""
        with self._session() as session:
            item = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            if not item:
                return False
            session.delete(item)
            session.commit()
            return True
