"""Instruction snippets and groups, the per-user defaults bucket, and spaces."""

from datetime import datetime
from typing import Any

from web.core.metadata.models import ChatConversation, ChatInstruction, ChatInstructionGroup, ChatSettings, ChatSpace


class InstructionMixin:
    """Manage instruction snippets, groups, defaults, and chat spaces."""

    def list_instructions(self) -> list[ChatInstruction]:
        """Return instruction snippets ordered by name."""
        return self._list(ChatInstruction, ChatInstruction.name)

    def get_instruction(self, instruction_id: int) -> ChatInstruction | None:
        """Return a snippet by id, or ``None`` if it does not exist."""
        return self._get(ChatInstruction, instruction_id)

    def get_instructions(self, ids: list[int]) -> list[ChatInstruction]:
        """Snippets for the given ids, in that order; unknown ids drop out."""
        if not ids:
            return []
        with self._session() as session:
            by_id = {i.id: i for i in session.query(ChatInstruction).filter(ChatInstruction.id.in_(ids))}
            items = [by_id[i] for i in ids if i in by_id]
            for i in items:
                session.expunge(i)
            return items

    def save_instruction(self, instruction_id: int | None = None, **fields: Any) -> ChatInstruction | None:
        """Create (id None) or update a snippet."""
        return self._save(ChatInstruction, instruction_id, **fields)

    def delete_instruction(self, instruction_id: int) -> bool:
        """Delete a snippet and detach it from chats, groups, and defaults."""
        with self._session() as session:
            item = session.get(ChatInstruction, instruction_id)
            if not item:
                return False
            self._detach_id(
                session, ChatConversation, ChatConversation.instruction_ids_json, "instruction_ids", instruction_id
            )
            self._detach_id(
                session, ChatInstructionGroup, ChatInstructionGroup.snippet_ids_json, "snippet_ids", instruction_id
            )
            self._detach_id(
                session, ChatSpace, ChatSpace.default_instruction_ids_json, "default_instruction_ids", instruction_id
            )
            self._detach_id(
                session,
                ChatSettings,
                ChatSettings.default_instruction_ids_json,
                "default_instruction_ids",
                instruction_id,
            )
            session.delete(item)
            session.commit()
            return True

    def list_instruction_groups(self) -> list[ChatInstructionGroup]:
        """Return instruction groups ordered by name."""
        return self._list(ChatInstructionGroup, ChatInstructionGroup.name)

    def get_instruction_group(self, group_id: int) -> ChatInstructionGroup | None:
        """Return a group by id, or ``None`` if it does not exist."""
        return self._get(ChatInstructionGroup, group_id)

    def save_instruction_group(self, group_id: int | None = None, **fields: Any) -> ChatInstructionGroup | None:
        """Create (id None) or update a group."""
        return self._save(ChatInstructionGroup, group_id, **fields)

    def delete_instruction_group(self, group_id: int) -> bool:
        """Delete a group and detach it from chats and defaults.

        The group's snippets are not deleted.
        """
        with self._session() as session:
            item = session.get(ChatInstructionGroup, group_id)
            if not item:
                return False
            self._detach_id(
                session,
                ChatConversation,
                ChatConversation.instruction_group_ids_json,
                "instruction_group_ids",
                group_id,
            )
            self._detach_id(
                session,
                ChatSpace,
                ChatSpace.default_instruction_group_ids_json,
                "default_instruction_group_ids",
                group_id,
            )
            self._detach_id(
                session,
                ChatSettings,
                ChatSettings.default_instruction_group_ids_json,
                "default_instruction_group_ids",
                group_id,
            )
            session.delete(item)
            session.commit()
            return True

    # One ChatSettings row per user. The ORM tenant filter scopes the query to
    # the current user, so each person has their own defaults (the admin keeps
    # the pre-login global row, backfilled to them in 0020).

    def get_settings(self) -> ChatSettings:
        """The current user's defaults row, created empty on first access."""
        with self._session() as session:
            item = session.query(ChatSettings).first()
            if not item:
                item = ChatSettings()
                session.add(item)
                session.commit()
                session.refresh(item)
            session.expunge(item)
            return item

    def save_settings(self, **fields: Any) -> ChatSettings:
        """Update the current user's defaults row and return it."""
        with self._session() as session:
            item = session.query(ChatSettings).first() or ChatSettings()
            session.add(item)
            for key, value in fields.items():
                setattr(item, key, value)
            item.updated_at = datetime.now()
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def list_spaces(self) -> list[ChatSpace]:
        """Return chat spaces ordered by name."""
        return self._list(ChatSpace, ChatSpace.name)

    def get_space(self, space_id: int) -> ChatSpace | None:
        """Return a space by id, or ``None`` if it does not exist."""
        return self._get(ChatSpace, space_id)

    def save_space(self, space_id: int | None = None, **fields: Any) -> ChatSpace | None:
        """Create (id None) or update a space."""
        return self._save(ChatSpace, space_id, **fields)

    def delete_space(self, space_id: int) -> bool:
        """Delete a space; its chats become unfiled (space_id null), not deleted."""
        with self._session() as session:
            item = session.get(ChatSpace, space_id)
            if not item:
                return False
            session.query(ChatConversation).filter(ChatConversation.space_id == space_id).update(
                {ChatConversation.space_id: None}
            )
            session.delete(item)
            session.commit()
            return True
