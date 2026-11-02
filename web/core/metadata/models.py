"""SQLAlchemy ORM models for the metadata database, plus the `iso` timestamp
helper and the JSON-list / defaults-bucket descriptors the models use."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def iso(dt: datetime | None) -> str | None:
    """A stored timestamp as ISO 8601 with its UTC offset. Timestamps are
    saved as naive server-local time (datetime.now); without an offset the
    browser reads them as *its* local time, which is wrong whenever the
    server's timezone differs (e.g. a UTC container and a UTC+1 browser)."""
    return dt.astimezone().isoformat() if dt else None


class Base(DeclarativeBase):
    pass


class User(Base):
    """A person who signs in via OAuth (Google/Microsoft/X). Multi-tenant: each
    user owns their own threads/media (user_id added to those tables in a later
    migration). Provider API keys are per-user (api_keys_json), so each person
    pays their own way; the admin (the instance owner) also controls the VPN."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # uuid hex
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    provider: Mapped[str] = mapped_column(String(32))  # google | microsoft | x | local
    provider_sub: Mapped[str] = mapped_column(String(255))  # stable per-provider user id
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # argon2id hash for a local (email + password) admin account; null for OAuth users
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-user provider keys, JSON {"pollo": "...", "venice": "...", "openrouter": "..."}
    api_keys_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JsonIds:
    """A list kept as JSON in the text column named after it plus "_json"
    (`character_ids` → `character_ids_json`). Reads [] when empty or
    unreadable; writes it without repeats unless `unique=False`."""

    def __init__(self, unique: bool = True):
        self.unique = unique

    def __set_name__(self, owner, name: str) -> None:
        self.column = f"{name}_json"

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        raw = getattr(obj, self.column)
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []

    def __set__(self, obj, value) -> None:
        items = list(value or [])
        setattr(obj, self.column, json.dumps(list(dict.fromkeys(items)) if self.unique else items))


class DefaultsBucket:
    """The chat defaults kept by ChatSettings (every chat) and ChatSpace (the
    chats in it): default characters, instruction snippets and groups."""

    default_character_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_instruction_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_instruction_group_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_character_ids = JsonIds()
    default_instruction_ids = JsonIds()
    default_instruction_group_ids = JsonIds()

    def defaults_dict(self) -> dict[str, list[int]]:
        return {
            "default_character_ids": self.default_character_ids,
            "default_instruction_ids": self.default_instruction_ids,
            "default_instruction_group_ids": self.default_instruction_group_ids,
        }


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    text_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Legacy single attachment (superseded by instruction_ids_json; kept so old
    # rows migrate and the column isn't dropped out from under existing data)
    instruction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Instruction snippets attached individually (ChatInstruction.id list, JSON)
    instruction_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Instruction groups attached (ChatInstructionGroup.id list, JSON); each
    # contributes all its snippets. Groups + individual snippets are flattened
    # and de-duped into the instructions sent to the model (see web/chat.py).
    instruction_group_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The space this chat belongs to (ChatSpace.id); null = unfiled. A space is
    # a chat-only grouping that seeds new chats with its default characters and
    # instructions — unrelated to generation Projects.
    space_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # The last message of the branch being shown (messages form a tree: an
    # edit or retry adds a sibling instead of deleting what came after)
    current_leaf_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Characters attached to this chat (Character.id list, JSON)
    character_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A branch of another chat: the chat and the message it was branched at
    # (the original may since have been deleted)
    forked_from_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    forked_from_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # What the messages copied into a branch had cost, so the chat's total
    # can say how much was spent before it branched
    inherited_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    inherited_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which view a thread opens on: "chat" or "gallery". Both views (the
    # conversation and the generations gallery) exist on every thread; this
    # only sets the default landing view and the sidebar filter bucket.
    kind: Mapped[str] = mapped_column(String(10), default="chat", server_default="chat")
    # The composer settings last used here (mode, sliders, media options; JSON)
    settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Defaults (global or its space's) switched off in this chat only:
    # {"character" | "instruction" | "instruction_group": [ids]} (JSON)
    hidden_defaults_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Instruction snippets/groups paused in this chat: still attached (own or
    # inherited) but temporarily not sent to the model, until resumed.
    # {"instruction" | "instruction_group": [ids]} (JSON)
    paused_instructions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Imported from another app (web/chatgpt_import.py): where from, its id
    # there and when it was last changed there, so a later import of the
    # same export only adds what's new
    import_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    import_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    import_updated_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )
    library_items: Mapped[list["ChatLibraryItem"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "text_model": self.text_model,
            "image_model": self.image_model,
            "video_model": self.video_model,
            "instruction_ids": self.instruction_ids,
            "instruction_group_ids": self.instruction_group_ids,
            "space_id": self.space_id,
            "current_leaf_id": self.current_leaf_id,
            "character_ids": self.character_ids,
            "forked_from_id": self.forked_from_id,
            "forked_from_message_id": self.forked_from_message_id,
            "pinned": bool(self.pinned),
            "kind": self.kind or "chat",
            "settings": self.settings,
            "hidden_defaults": self.hidden_defaults,
            "paused_instructions": self.paused_instructions,
            "import_source": self.import_source,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }

    @property
    def hidden_defaults(self) -> dict[str, list[int]]:
        try:
            raw = json.loads(self.hidden_defaults_json) if self.hidden_defaults_json else {}
        except json.JSONDecodeError:
            raw = {}
        return {k: raw.get(k) or [] for k in ("character", "instruction", "instruction_group")}

    @hidden_defaults.setter
    def hidden_defaults(self, value: dict[str, list[int]] | None) -> None:
        kept = {k: list(dict.fromkeys(ids)) for k, ids in (value or {}).items() if ids}
        self.hidden_defaults_json = json.dumps(kept) if kept else None

    @property
    def paused_instructions(self) -> dict[str, list[int]]:
        try:
            raw = json.loads(self.paused_instructions_json) if self.paused_instructions_json else {}
        except json.JSONDecodeError:
            raw = {}
        return {k: raw.get(k) or [] for k in ("instruction", "instruction_group")}

    @paused_instructions.setter
    def paused_instructions(self, value: dict[str, list[int]] | None) -> None:
        kept = {k: list(dict.fromkeys(ids)) for k, ids in (value or {}).items() if ids}
        self.paused_instructions_json = json.dumps(kept) if kept else None

    @property
    def settings(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.settings_json) if self.settings_json else None
        except json.JSONDecodeError:
            return None

    @settings.setter
    def settings(self, value: dict[str, Any] | None) -> None:
        self.settings_json = json.dumps(value) if value else None

    character_ids = JsonIds()
    instruction_ids = JsonIds()
    instruction_group_ids = JsonIds()


class Character(Base):
    """A reusable character: a name, a description and a few reference images
    (files under <data>/characters/<id>/, see web/characters.py), attachable
    to chats and generations. With `conversation_id` set it's ad hoc — made
    in that chat and deleted with it — until promoted (conversation_id None)."""

    __tablename__ = "characters"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    images_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    images = JsonIds(unique=False)  # in the order shown

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "images": self.images,
            "conversation_id": self.conversation_id,
            "adhoc": self.conversation_id is not None,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class ChatInstruction(Base):
    """A reusable instruction snippet. Which snippets a new chat starts with is
    decided by the settings buckets (ChatSettings, ChatSpace), not a per-snippet
    flag."""

    __tablename__ = "chat_instructions"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class ChatInstructionGroup(Base):
    """A named bundle of instruction snippets (ChatInstruction). Attaching a
    group to a chat contributes all its snippets; a snippet may be in several
    groups and is sent only once. Which groups a new chat starts with is decided
    by the settings buckets (ChatSettings, ChatSpace)."""

    __tablename__ = "chat_instruction_groups"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    snippet_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    snippet_ids = JsonIds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "snippet_ids": self.snippet_ids,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class ChatSpace(DefaultsBucket, Base):
    """A chat-only grouping of conversations, with its own default characters
    and instruction snippets/groups: every chat in it uses them, live (on top
    of the global ones). Unrelated to the generation-side Project."""

    __tablename__ = "chat_spaces"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            **self.defaults_dict(),
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class ChatSettings(DefaultsBucket, Base):
    """Global chat defaults (a single row, id=1): the characters and instruction
    snippets/groups every chat uses, live. A space's own defaults stack on top
    of these; the two are kept as separate buckets."""

    __tablename__ = "chat_settings"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)  # always 1
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return self.defaults_dict()


class ChatMessage(Base):
    """One chat turn. `media_json` is a list of media items (images/videos,
    uploaded or generated) — see web/chat.py for the item shape.

    Messages form a tree through `parent_id` (None = first message of a
    branch); siblings are alternative versions of the same turn."""

    __tablename__ = "chat_messages"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(20))  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, default="")
    media_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The composer mode the turn ran in (auto/text/image/video), so an edit or
    # retry reruns it the same way; None on messages from before it was kept
    mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="done")  # 'streaming' | 'done' | 'error'
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The message it was imported from (see ChatConversation.import_id)
    import_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    conversation: Mapped["ChatConversation"] = relationship(back_populates="messages")

    @property
    def media(self) -> list[dict[str, Any]]:
        if not self.media_json:
            return []
        try:
            return json.loads(self.media_json)
        except json.JSONDecodeError:
            return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "parent_id": self.parent_id,
            "role": self.role,
            "content": self.content,
            "media": self.media,
            "model": self.model,
            "mode": self.mode,
            "status": self.status,
            "error": self.error,
            "cost": self.cost,
            "created_at": iso(self.created_at),
        }


class ChatImportSkip(Base):
    """An imported chat the user deleted, so importing it again doesn't bring it back."""

    __tablename__ = "chat_import_skips"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    import_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ChatLibraryItem(Base):
    """Chat media detached from its message (the message was removed by an
    edit or retry). Media still attached to messages lives in
    ChatMessage.media_json; the library view shows both."""

    __tablename__ = "chat_library_items"
    # Tenant owner (multi-tenant isolation); backfilled to the admin in 0020
    user_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    conversation_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    item_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    detached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    conversation: Mapped["ChatConversation"] = relationship(back_populates="library_items")

    @property
    def item(self) -> dict[str, Any]:
        try:
            return json.loads(self.item_json)
        except json.JSONDecodeError:
            return {}
