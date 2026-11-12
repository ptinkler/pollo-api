"""Reusable characters (name, description, reference images)."""

from datetime import datetime

from sqlalchemy import func

from web.core.metadata._base import DBBase
from web.core.metadata.models import Character, ChatConversation, ChatSettings, ChatSpace
from web.types import JsonValue


class CharacterMixin(DBBase):
    """Provide CRUD operations for reusable and chat-specific characters."""

    def create_character(self, name: str, description: str = "", conversation_id: str | None = None) -> Character:
        """Create a character with no reference images."""
        with self._session() as session:
            char = Character(name=name, description=description, conversation_id=conversation_id, images=[])
            session.add(char)
            session.commit()
            session.refresh(char)
            session.expunge(char)
            return char

    def get_character(self, character_id: int) -> Character | None:
        """Return a character by id, or ``None`` if it does not exist."""
        with self._session() as session:
            char = session.get(Character, character_id)
            if char:
                session.expunge(char)
            return char

    def list_characters(self) -> list[Character]:
        """Return all characters ordered by name and then id."""
        with self._session() as session:
            chars = session.query(Character).order_by(func.lower(Character.name), Character.id).all()
            for c in chars:
                session.expunge(c)
            return chars

    def update_character(self, character_id: int, **fields: JsonValue) -> Character | None:
        """Set name / description / images (list of filenames) / conversation_id."""
        with self._session() as session:
            char = session.get(Character, character_id)
            if not char:
                return None
            for key, value in fields.items():
                setattr(char, key, value)
            char.updated_at = datetime.now().astimezone().replace(tzinfo=None)
            session.commit()
            session.refresh(char)
            session.expunge(char)
            return char

    def delete_character(self, character_id: int) -> bool:
        """Delete a character and detach it from chats and defaults.

        Returns whether the character existed and was deleted.
        """
        with self._session() as session:
            char = session.get(Character, character_id)
            if not char:
                return False
            self._detach_id(
                session, ChatConversation, ChatConversation.character_ids_json, "character_ids", character_id
            )
            self._detach_id(
                session, ChatSpace, ChatSpace.default_character_ids_json, "default_character_ids", character_id
            )
            self._detach_id(
                session, ChatSettings, ChatSettings.default_character_ids_json, "default_character_ids", character_id
            )
            session.delete(char)
            session.commit()
            return True
