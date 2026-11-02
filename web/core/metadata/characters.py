"""Reusable characters (name, description, reference images)."""

from datetime import datetime

from sqlalchemy import func

from .models import Character, ChatConversation, ChatSettings, ChatSpace


class CharacterMixin:
    def create_character(self, name: str, description: str = "", conversation_id: str | None = None) -> Character:
        with self._session() as session:
            char = Character(name=name, description=description, conversation_id=conversation_id, images=[])
            session.add(char)
            session.commit()
            session.refresh(char)
            session.expunge(char)
            return char

    def get_character(self, character_id: int) -> Character | None:
        with self._session() as session:
            char = session.get(Character, character_id)
            if char:
                session.expunge(char)
            return char

    def list_characters(self) -> list[Character]:
        with self._session() as session:
            chars = session.query(Character).order_by(func.lower(Character.name), Character.id).all()
            for c in chars:
                session.expunge(c)
            return chars

    def update_character(self, character_id: int, **fields) -> Character | None:
        """Set name / description / images (list of filenames) / conversation_id."""
        with self._session() as session:
            char = session.get(Character, character_id)
            if not char:
                return None
            for key, value in fields.items():
                setattr(char, key, value)
            char.updated_at = datetime.now()
            session.commit()
            session.refresh(char)
            session.expunge(char)
            return char

    def delete_character(self, character_id: int) -> bool:
        """Delete a character and remove it from any chats and from the global
        and space default buckets using it (symmetric with delete_instruction)."""
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
