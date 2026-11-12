"""Helpers shared by the chat routes and the turn engine: chat-folder paths,.

media-item builders, branch/message shaping, ownership/idle guards, spend, and
the live default-inheritance resolution.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from web.chat.constants import KINDS, REMEMBERED_SETTINGS
from web.core import config
from web.core.metadata import get_db
from web.providers import openrouter, venice

if TYPE_CHECKING:
    from pathlib import Path

    from web.chat.models import TurnSettings
    from web.core.metadata.models import ChatConversation, ChatMessage


def chat_root() -> Path:
    """Return the chat data directory for the current tenant."""
    # Read config at call time so tests can redirect ROOT_DIR
    return config.ROOT_DIR / "chat"


def conversation_dir(conv_id: str) -> Path:
    """A chat's media folder, created if it isn't there yet.

    (It is made here
    rather than on upload because every path that writes into it goes
    through this.).
    """
    d = chat_root() / conv_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_media(kind: str, source: str, **fields: Any) -> dict[str, Any]:
    """Build a pending media item with a stable ID and optional fields."""
    return {"id": uuid.uuid4().hex[:8], "kind": kind, "source": source, "status": "pending", "file": None, **fields}


def saved_media(kind: str, source: str, file: str, **fields: Any) -> dict[str, Any]:
    """A media item whose file is already on disk."""
    return {**new_media(kind, source, **fields), "status": "done", "file": file}


def require_conv(conv_id: str) -> ChatConversation:
    """Return a conversation or raise 404 when it does not exist."""
    conv = get_db().get_conversation(conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


def branch_to(messages: list[ChatMessage], leaf_id: int | None) -> list[ChatMessage]:
    """The branch ending at `leaf_id`, first message first."""
    by_id = {m.id: m for m in messages}
    path = []
    msg = by_id.get(leaf_id)
    while msg:
        path.append(msg)
        msg = by_id.get(msg.parent_id)
    return path[::-1]


def message_out(msg: ChatMessage) -> dict[str, Any]:
    """A message for the UI, with its siblings for the ‹ 1/2 › branch arrows."""
    return {**msg.to_dict(), "siblings": get_db().get_chat_sibling_ids(msg.conversation_id, msg.parent_id, msg.lane)}


def shown_branch(conv_id: str) -> list[dict[str, Any]]:
    """Shape the shown conversation branch and its standalone gallery exchanges."""
    db = get_db()
    messages = db.get_chat_messages(conv_id)
    siblings: dict[tuple, list[int]] = {}
    for m in messages:
        siblings.setdefault((m.lane, m.parent_id), []).append(m.id)
    # The chat's branch, then the standalone gallery exchanges beside it
    shown = [*branch_to(messages, db.get_chat_leaf_id(conv_id)), *(m for m in messages if m.lane)]
    return [{**m.to_dict(), "siblings": siblings[(m.lane, m.parent_id)]} for m in shown]


def require_text_provider(mode: str | None = None) -> None:
    """Chat needs a text-model provider — OpenRouter or Venice.

    Image, Video
    and Audio modes send the prompt straight to the media model, so they
    don't (hence the mode check rather than a blanket gate).
    """
    if mode in ("image", "video", "audio"):
        return
    if not (openrouter.is_configured() or venice.is_configured()):
        raise HTTPException(503, "No chat provider key set — add an OpenRouter or Venice key in Settings → Keys")


def _inherited(conv: ChatConversation | None) -> dict[str, list[int]]:
    """Resolve the live defaults inherited by a chat.

    Global and space defaults are deduplicated by kind, excluding defaults
    hidden by this conversation.
    """
    db = get_db()
    buckets = [db.get_settings()]
    space = db.get_space(conv.space_id) if conv and conv.space_id is not None else None
    if space:
        buckets.append(space)
    hidden = conv.hidden_defaults if conv else {}
    return {
        k: [
            i
            for i in dict.fromkeys(i for b in buckets for i in getattr(b, f"default_{k}_ids"))
            if i not in hidden.get(k, [])
        ]
        for k in KINDS
    }


def effective_ids(conv: ChatConversation | None, kind: str) -> list[int]:
    """A chat's `kind` ids in use: inherited from the defaults, then its own."""
    own = getattr(conv, f"{kind}_ids") if conv else []
    return list(dict.fromkeys([*_inherited(conv)[kind], *own]))


def spend(conv: ChatConversation) -> dict[str, float | int]:
    """What the chat cost: `usd` and `credits` in total, of which `inherited_*`.

    came with the messages copied in when it was branched off another chat.
    """
    usd, credits = get_db().get_chat_spend(conv.id)
    return {
        "usd": usd,
        "credits": credits,
        "inherited_usd": conv.inherited_cost or 0,
        "inherited_credits": conv.inherited_credits or 0,
    }


def require_own_conversation(conv_id: str) -> None:
    """404 unless the conversation belongs to the current user (get_conversation.

    is tenant-scoped, so another user's id reads as not found).
    """
    if not get_db().get_conversation(conv_id):
        raise HTTPException(404, "Not found")


def require_idle(conv_id: str, lane: str | None = None) -> None:
    """Edits/retries rewrite history, so they can't overlap a running reply.

    in the same lane (gallery exchanges never block the chat or each other).
    """
    if lane:
        return
    if any(m.status == "streaming" and not m.lane for m in get_db().get_chat_messages(conv_id)):
        raise HTTPException(409, "Wait for the current reply to finish (or stop it) first")


def remember_settings(conv: ChatConversation, settings: TurnSettings) -> None:
    """Persist the model picks and composer settings on the conversation so.

    reopening it restores them.
    """
    fields: dict[str, Any] = {
        k: getattr(settings, k)
        for k in ("text_model", "image_model", "video_model")
        if getattr(settings, k) and getattr(settings, k) != getattr(conv, k)
    }
    composer = settings.model_dump(include=REMEMBERED_SETTINGS)
    if composer != conv.settings:
        fields["settings"] = composer
    if fields:
        get_db().update_conversation(conv.id, **fields)


def add_message_cost(message_id: int, cost: float | None) -> None:
    """Add a provider cost to a message, rounded to the database precision."""
    if not cost:
        return
    db = get_db()
    msg = db.get_chat_message(message_id)
    if msg:
        db.update_chat_message(message_id, cost=round((msg.cost or 0) + float(cost), 6))


def find_media(msg: ChatMessage | None, media_id: str) -> dict[str, Any] | None:
    """Find a media item by ID on a message, if present."""
    return next((i for i in msg.media if i.get("id") == media_id), None) if msg else None
