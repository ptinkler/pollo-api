"""Chat messages: the branch tree, media items on a message, spend totals,
truncation and whole-turn (exchange) deletion.
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from web.core.metadata.models import ChatConversation, ChatLibraryItem, ChatMessage

# add_chat_message's default parent: continue the branch being shown
_APPEND = object()


def _media_row(conv_id: str, at, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_id": conv_id,
        "at": at,
        "model": item.get("model"),
        "kind": item.get("kind") or "image",
        "usd": item.get("cost") or 0,
        "credits": item.get("credits") or 0,
    }


class MessageMixin:
    def add_chat_message(
        self,
        conversation_id: str,
        role: str,
        content: str = "",
        media: list[dict[str, Any]] | None = None,
        model: str | None = None,
        status: str = "done",
        parent_id: Any = _APPEND,
        mode: str | None = None,
        lane: str | None = None,
    ) -> ChatMessage:
        """Add a message and make it the shown branch's last message. By
        default it continues the shown branch; pass `parent_id` (None for a
        first message) to start a new branch beside an existing message.
        A `lane` message starts its own standalone exchange: it never joins
        or moves the shown branch.
        """
        with self._session() as session:
            conv = session.get(ChatConversation, conversation_id)
            if parent_id is _APPEND:
                parent_id = None if lane else (self._chat_leaf_id(session, conv) if conv else None)
            msg = ChatMessage(
                conversation_id=conversation_id,
                parent_id=parent_id,
                role=role,
                content=content,
                media_json=json.dumps(media) if media else None,
                model=model,
                mode=mode,
                lane=lane,
                status=status,
            )
            session.add(msg)
            session.flush()
            if conv:
                conv.updated_at = datetime.now()
                if not lane:
                    conv.current_leaf_id = msg.id
            session.commit()
            session.refresh(msg)
            session.expunge(msg)
            return msg

    def add_chat_branch(self, conversation_id: str, rows: list[dict[str, Any]]) -> None:
        """Add messages one after another (the first starts the chat) in one
        transaction, and show the branch they make. `rows`: ChatMessage
        fields, `media` as a list. One commit, not one per message: a long
        chat's copy is slow on a NAS otherwise.
        """
        with self._session() as session:
            conv = session.get(ChatConversation, conversation_id)
            parent_id = None
            for row in rows:
                fields = {**row, "media_json": json.dumps(row["media"]) if row.get("media") else None}
                fields.pop("media", None)
                msg = ChatMessage(conversation_id=conversation_id, parent_id=parent_id, **fields)
                session.add(msg)
                session.flush()
                parent_id = msg.id
            if conv and parent_id is not None:
                conv.current_leaf_id = parent_id
                conv.updated_at = datetime.now()
            session.commit()

    @staticmethod
    def _chat_leaf_id(session: Session, conv: ChatConversation) -> int | None:
        """The shown branch's last message, falling back to the newest one."""
        if conv.current_leaf_id and session.get(ChatMessage, conv.current_leaf_id):
            return conv.current_leaf_id
        return (
            session.query(func.max(ChatMessage.id))
            .filter(ChatMessage.conversation_id == conv.id, ChatMessage.lane.is_(None))
            .scalar()
        )

    def get_chat_leaf_id(self, conversation_id: str) -> int | None:
        with self._session() as session:
            conv = session.get(ChatConversation, conversation_id)
            return self._chat_leaf_id(session, conv) if conv else None

    def set_chat_leaf(self, conversation_id: str, leaf_id: int) -> None:
        """Show another branch. Not an edit, so the chat keeps its place in the list."""
        with self._session() as session:
            session.query(ChatConversation).filter(ChatConversation.id == conversation_id).update(
                {ChatConversation.current_leaf_id: leaf_id, ChatConversation.updated_at: ChatConversation.updated_at}
            )
            session.commit()

    def get_chat_sibling_ids(self, conversation_id: str, parent_id: int | None, lane: str | None = None) -> list[int]:
        """Ids of every version of a turn (messages sharing a parent in the
        same lane), oldest first.
        """
        with self._session() as session:
            rows = (
                session.query(ChatMessage.id)
                .filter(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.parent_id == parent_id,
                    ChatMessage.lane.is_(None) if lane is None else ChatMessage.lane == lane,
                )
                .order_by(ChatMessage.id)
                .all()
            )
            return [r[0] for r in rows]

    def update_chat_message(
        self, message_id: int, media: list[dict[str, Any]] | None = None, **fields: Any
    ) -> ChatMessage | None:
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if not msg:
                return None
            for key, value in fields.items():
                if hasattr(msg, key):
                    setattr(msg, key, value)
            if media is not None:
                msg.media_json = json.dumps(media) if media else None
            session.commit()
            session.refresh(msg)
            session.expunge(msg)
            return msg

    def update_chat_media_item(self, message_id: int, media_id: str, **fields: Any) -> ChatMessage | None:
        """Atomically merge `fields` into one media item.

        Looks in the message first, then the library (the message may have
        been removed by an edit/retry while a video was still rendering).
        Returns the message if the item was updated there, else None.
        Background video pollers update items while the chat stream may be
        appending others, so the read-modify-write must happen under one lock.
        """
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if msg:
                media = msg.media
                for item in media:
                    if item.get("id") == media_id:
                        item.update(fields)
                        msg.media_json = json.dumps(media)
                        session.commit()
                        session.refresh(msg)
                        session.expunge(msg)
                        return msg
            lib = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            if lib:
                lib.item_json = json.dumps({**lib.item, **fields})
                session.commit()
            return None

    def find_chat_media_item(self, message_id: int, media_id: str) -> dict[str, Any] | None:
        """The media item's current state, wherever it lives (message or library)."""
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if msg:
                item = next((i for i in msg.media if i.get("id") == media_id), None)
                if item:
                    return item
            lib = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            return lib.item if lib else None

    def append_chat_media_item(self, message_id: int, item: dict[str, Any]) -> ChatMessage | None:
        """Atomically append one media item to a message."""
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if not msg:
                return None
            msg.media_json = json.dumps([*msg.media, item])
            session.commit()
            session.refresh(msg)
            session.expunge(msg)
            return msg

    def get_chat_messages_by_status(self, status: str) -> list[ChatMessage]:
        with self._session() as session:
            msgs = session.query(ChatMessage).filter(ChatMessage.status == status).all()
            for m in msgs:
                session.expunge(m)
            return msgs

    def get_chat_message(self, message_id: int) -> ChatMessage | None:
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if msg:
                session.expunge(msg)
            return msg

    def get_chat_spend(self, conversation_id: str) -> tuple[float, int]:
        """What a chat has cost on every branch: dollars (OpenRouter/Venice —
        a reply's cost includes its media) and Pollo credits (per media item).
        Media detached into the library still counts; its message is gone.
        """
        with self._session() as session:
            usd, credits = 0.0, 0
            for cost, media_json in session.query(ChatMessage.cost, ChatMessage.media_json).filter(
                ChatMessage.conversation_id == conversation_id
            ):
                usd += cost or 0
                for item in json.loads(media_json) if media_json else []:
                    credits += item.get("credits") or 0
            for lib in session.query(ChatLibraryItem).filter(ChatLibraryItem.conversation_id == conversation_id):
                usd += lib.item.get("cost") or 0
                credits += lib.item.get("credits") or 0
            return round(usd, 6), int(credits)

    def spend_rows(self, conversation_ids: list[str]) -> list[dict[str, Any]]:
        """One row per charge across the given chats, for the usage breakdown:
        {conversation_id, at, model, kind, usd, credits}. A Pollo media item is
        one row (credits); a message's dollar cost (OpenRouter/Venice, media
        included) is one row. Media detached into the library still counts.
        """
        rows: list[dict[str, Any]] = []
        if not conversation_ids:
            return rows
        with self._session() as session:
            msgs = session.query(
                ChatMessage.conversation_id,
                ChatMessage.created_at,
                ChatMessage.model,
                ChatMessage.cost,
                ChatMessage.media_json,
            ).filter(ChatMessage.conversation_id.in_(conversation_ids))
            for conv_id, at, model, cost, media_json in msgs:
                if cost:
                    rows.append(
                        {
                            "conversation_id": conv_id,
                            "at": at,
                            "model": model,
                            "kind": "chat",
                            "usd": cost,
                            "credits": 0,
                        }
                    )
                rows.extend(
                    _media_row(conv_id, at, item)
                    for item in (json.loads(media_json) if media_json else [])
                    if item.get("credits")
                )
            libs = session.query(ChatLibraryItem).filter(ChatLibraryItem.conversation_id.in_(conversation_ids))
            rows.extend(
                _media_row(lib.conversation_id, lib.created_at, lib.item)
                for lib in libs
                if lib.item.get("credits") or lib.item.get("cost")
            )
        return rows

    def get_chat_messages(self, conversation_id: str) -> list[ChatMessage]:
        with self._session() as session:
            msgs = (
                session.query(ChatMessage)
                .filter(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.id)
                .all()
            )
            for m in msgs:
                session.expunge(m)
            return msgs

    def truncate_chat(self, conversation_id: str, after_id: int) -> list[dict[str, Any]]:
        """Delete every message with id > after_id, moving their generated
        media into the library first. (Edit/retry used this before chats had
        branches; library items from then remain.) Uploaded
        attachments are the user's own inputs and aren't kept.

        Returns the detached media items.
        """
        with self._session() as session:
            msgs = (
                session.query(ChatMessage)
                .filter(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.id > after_id,
                )
                .all()
            )
            detached = []
            for msg in msgs:
                for item in msg.media:
                    if item.get("source") == "upload" or not (item.get("file") or item.get("job_id")):
                        continue
                    session.add(
                        ChatLibraryItem(
                            media_id=item["id"],
                            conversation_id=conversation_id,
                            item_json=json.dumps(item),
                            created_at=msg.created_at,
                        )
                    )
                    detached.append(item)
                session.delete(msg)
            session.commit()
            return detached

    def _chat_exchange_plan(self, session: Session, conversation_id: str, user_message_id: int) -> dict | None:
        """What deleting a prompt's turn removes and keeps (see delete_chat_exchange)."""
        prompt = session.get(ChatMessage, user_message_id)
        if not prompt or prompt.conversation_id != conversation_id or prompt.role != "user":
            return None
        msgs = {
            m.id: m for m in session.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).all()
        }
        if prompt.lane:
            # A standalone exchange: just the prompt and its replies
            doomed = [prompt.id] + [m.id for m in msgs.values() if m.parent_id == prompt.id]
            return {
                "prompt": prompt,
                "msgs": msgs,
                "doomed": doomed,
                "kept_next": [],
                "other_versions": 0,
                "other_messages": 0,
            }
        msgs = {i: m for i, m in msgs.items() if not m.lane}
        children: dict[int | None, list[int]] = {}
        for m in msgs.values():
            children.setdefault(m.parent_id, []).append(m.id)
        # The turn: every version of the prompt, and every reply to any of them
        versions = [i for i in children.get(prompt.parent_id, []) if msgs[i].role == "user"]
        replies = [r for v in versions for r in children.get(v, [])]
        # The shown branch's reply in this turn: what follows it is kept
        conv = session.get(ChatConversation, conversation_id)
        path, node = set(), self._chat_leaf_id(session, conv) if conv else None
        while node is not None and node in msgs and node not in path:
            path.add(node)
            node = msgs[node].parent_id
        kept_reply = next((r for r in replies if r in path), None)
        kept_next = children.get(kept_reply, []) if kept_reply else []
        # Everything else under the turn goes: the turn itself plus what grew
        # from its other versions/replies
        doomed: list[int] = []
        stack = list(versions)
        while stack:
            mid = stack.pop()
            doomed.append(mid)
            stack += [c for c in children.get(mid, []) if c not in kept_next]
        turn = set(versions) | set(replies)
        return {
            "prompt": prompt,
            "msgs": msgs,
            "doomed": doomed,
            "kept_next": kept_next,
            "other_versions": len(versions) - 1,
            "other_messages": len([d for d in doomed if d not in turn]),
        }

    def chat_exchange_delete_info(self, conversation_id: str, user_message_id: int) -> dict | None:
        """How much deleting this prompt's turn removes, for the confirmation:
        the other versions/messages that go with it, and the generated files it
        holds, per kind — the ones the "also delete its media" box decides on
        (a turn that generated nothing, or only failed, has none).
        """
        with self._session() as session:
            plan = self._chat_exchange_plan(session, conversation_id, user_message_id)
            if not plan:
                return None
            media: dict[str, int] = {}
            for mid in plan["doomed"]:
                for item in plan["msgs"][mid].media or []:
                    if item.get("source") == "upload" or not item.get("file"):
                        continue
                    kind = item.get("kind") or "file"
                    media[kind] = media.get(kind, 0) + 1
            return {
                "other_versions": plan["other_versions"],
                "other_messages": plan["other_messages"],
                "media": media,
            }

    def delete_chat_exchange(self, conversation_id: str, user_message_id: int) -> list[dict[str, Any]]:
        """Delete a prompt's whole turn — every version of the prompt and every
        reply to them — moving generated media into the library. What follows
        the shown branch's reply is kept, re-attached to the message before
        the prompt, so the chat reads on as if the turn never happened. What
        grew from the turn's other versions has nothing left to follow, so
        it's deleted too (its media also goes to the library).

        Returns the detached media items.
        """
        with self._session() as session:
            plan = self._chat_exchange_plan(session, conversation_id, user_message_id)
            if not plan:
                return []
            prompt, msgs = plan["prompt"], plan["msgs"]
            for mid in plan["kept_next"]:
                msgs[mid].parent_id = prompt.parent_id
            detached = []
            for mid in plan["doomed"]:
                msg = msgs[mid]
                for item in msg.media:
                    if item.get("source") == "upload" or not (item.get("file") or item.get("job_id")):
                        continue
                    session.add(
                        ChatLibraryItem(
                            media_id=item["id"],
                            conversation_id=conversation_id,
                            item_json=json.dumps(item),
                            created_at=msg.created_at,
                        )
                    )
                    detached.append(item)
                session.delete(msg)
            conv = session.get(ChatConversation, conversation_id)
            if conv and conv.current_leaf_id in set(plan["doomed"]):
                conv.current_leaf_id = prompt.parent_id  # the branch now ends before the turn
            session.commit()
            return detached

    def get_chat_messages_with_media(self) -> list[ChatMessage]:
        with self._session() as session:
            msgs = (
                session.query(ChatMessage)
                .filter(ChatMessage.media_json.isnot(None))
                .order_by(ChatMessage.id.desc())
                .all()
            )
            for m in msgs:
                session.expunge(m)
            return msgs

    def get_chat_messages_with_pending_media(self) -> list[ChatMessage]:
        with self._session() as session:
            msgs = session.query(ChatMessage).filter(ChatMessage.media_json.contains('"status": "pending"')).all()
            for m in msgs:
                session.expunge(m)
            return msgs

    def get_chat_messages_by_ids(self, ids: list[int]) -> list[ChatMessage]:
        if not ids:
            return []
        with self._session() as session:
            msgs = session.query(ChatMessage).filter(ChatMessage.id.in_(ids)).all()
            for m in msgs:
                session.expunge(m)
            return msgs
