"""Chat CRUD + catalogue/media HTTP routes (everything but the turn-engine,
media-generation and SSE endpoints, which stay in the package root). They hang
off the shared router in deps.py and lean on helpers.py for the common bits.
"""

import shutil
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from web import characters, media, request_log
from web.chat.catalogue import get_models
from web.chat.constants import (
    CHAT_PREVIEW_SIZE,
    CONVERSATION_LIST_LIMIT,
    DEFAULT_TITLE,
    KINDS,
    PARAM_FILES,
    PAUSE_KINDS,
    SNIPPET_CHARS,
    THREAD_KINDS,
)
from web.chat.deps import router
from web.chat.helpers import (
    branch_to,
    chat_root,
    conversation_dir,
    message_out,
    require_conv,
    require_idle,
    require_own_conversation,
    require_text_provider,
    shown_branch,
    spend,
)
from web.chat.models import (
    ConversationCreate,
    ConversationUpdate,
    DefaultsIn,
    ForkConversation,
    InstructionGroupIn,
    InstructionIn,
    SpaceIn,
    SwitchBranch,
    TitleModelIn,
)
from web.core import config
from web.core.metadata import get_db, iso
from web.media_types import VIDEO_SUFFIXES
from web.providers import openrouter, venice
from web.uploads import read_audio_upload, read_image_upload, read_video_upload, safe_filename, store_deduped


@router.get("/status")
def api_chat_status():
    return {
        "configured": openrouter.is_configured() or venice.is_configured(),
        "openrouter": openrouter.is_configured(),
        "venice": venice.is_configured(),
    }


@router.get("/credits")
def api_chat_credits():
    """OpenRouter balance for the chat header (Pollo's is /api/usage/balance)."""
    require_text_provider()
    try:
        return openrouter.get_credits()
    except openrouter.OpenRouterError as e:
        raise HTTPException(502, f"Couldn't fetch the OpenRouter balance: {e}") from e


@router.get("/venice-balance")
def api_venice_balance():
    """Venice balance for the chat header: USD, and the plan's bundled credits."""
    if not venice.is_configured():
        raise HTTPException(503, "No Venice API key set — add one in Settings → Keys")
    return venice.get_balances()


@router.get("/models")
def api_chat_models(refresh: bool = False):
    # No provider gate: the catalogue lists each provider independently
    # (get_models swallows a provider's failure and an unconfigured provider
    # returns []), so media models show with only a Pollo key, and new
    # providers slot in without touching this endpoint. Chat generation still
    # requires a text provider — that gate lives on the turn routes.
    return get_models(refresh)


@router.get("/conversations")
def api_list_conversations(q: str = ""):
    """Pinned chats, then the most recent (`more` = older ones left out).
    With `q`, chats whose title or messages contain it, each with a snippet
    of the matching message when the title didn't match.
    """
    db = get_db()
    q = q.strip()
    if q:
        return {
            "conversations": [
                {**c.to_dict(), "snippet": _snippet(text, q) if text else None}
                for c, text in db.search_conversations(q)
            ],
            "more": False,
        }
    convs = db.list_conversations(limit=CONVERSATION_LIST_LIMIT + 1)
    return {
        "conversations": [c.to_dict() for c in convs[:CONVERSATION_LIST_LIMIT]],
        "more": len(convs) > CONVERSATION_LIST_LIMIT,
    }


@router.get("/conversations/thumbs")
def api_conversation_thumbs(ids: str = ""):
    """Newest image file per conversation id (comma-separated), for gallery
    cover thumbnails. Declared before /conversations/{conv_id} so "thumbs"
    isn't read as an id.
    """
    conv_ids = [i for i in ids.split(",") if i]
    return {"thumbs": get_db().conversation_thumbs(conv_ids)}


def _snippet(text: str, q: str) -> str:
    """The part of `text` around the first match of `q`, on one line."""
    text = " ".join(text.split())
    i = text.lower().find(q.lower())
    if i == -1 or len(text) <= SNIPPET_CHARS:
        return text[:SNIPPET_CHARS]
    start = max(0, min(i - SNIPPET_CHARS // 3, len(text) - SNIPPET_CHARS))
    return (
        ("…" if start else "")
        + text[start : start + SNIPPET_CHARS].strip()
        + ("…" if start + SNIPPET_CHARS < len(text) else "")
    )


def _clean_kind(kind: str | None) -> str:
    """A thread's landing view: 'chat' or 'gallery' (default 'chat')."""
    return kind if kind in THREAD_KINDS else "chat"


@router.post("/conversations")
def api_create_conversation(data: ConversationCreate):
    db = get_db()
    space = _require_space(data.space_id) if data.space_id is not None else None
    # Only what's attached to this chat itself: the global and space defaults
    # apply live on top (see _inherited), so they aren't copied in
    instruction_ids = _require_instructions(data.instruction_ids)
    instruction_group_ids = _require_instruction_groups(data.instruction_group_ids)
    characters.require(data.character_ids, db)
    character_ids = list(dict.fromkeys(data.character_ids))
    hidden_defaults = _require_hidden_defaults(data.hidden_defaults)
    paused_instructions = _require_paused(data.paused_instructions)

    conv = db.create_conversation(
        title=(data.title or DEFAULT_TITLE).strip()[:255] or DEFAULT_TITLE,
        kind=_clean_kind(data.kind),
        text_model=data.text_model,
        image_model=data.image_model,
        video_model=data.video_model,
        space_id=space.id if space else None,
        instruction_ids=instruction_ids,
        instruction_group_ids=instruction_group_ids,
        character_ids=character_ids,
        hidden_defaults=hidden_defaults,
        paused_instructions=paused_instructions,
    )
    return conv.to_dict()


def _require_hidden_defaults(value: dict | None) -> dict[str, list[int]]:
    unknown = set(value or {}) - set(KINDS)
    if unknown:
        raise HTTPException(400, f"Unknown kind of default: {', '.join(sorted(unknown))}")
    return {k: list(dict.fromkeys(ids)) for k, ids in (value or {}).items()}


def _require_paused(value: dict | None) -> dict[str, list[int]]:
    unknown = set(value or {}) - set(PAUSE_KINDS)
    if unknown:
        raise HTTPException(400, f"Can't pause kind: {', '.join(sorted(unknown))}")
    return {k: list(dict.fromkeys(ids)) for k, ids in (value or {}).items()}


def _require_ids(ids: list[int], get, label: str) -> list[int]:
    """`ids` without repeats, or 400 naming the first that `get` can't find."""
    for i in ids:
        if not get(i):
            raise HTTPException(400, f"{label} {i} not found")
    return list(dict.fromkeys(ids))


def _require_instructions(ids: list[int]) -> list[int]:
    return _require_ids(ids, get_db().get_instruction, "Instruction")


def _require_instruction_groups(ids: list[int]) -> list[int]:
    return _require_ids(ids, get_db().get_instruction_group, "Instruction group")


def _require_space(space_id: int):
    space = get_db().get_space(space_id)
    if not space:
        raise HTTPException(400, "Space not found")
    return space


def _require_characters(ids: list[int]) -> list[int]:
    characters.require(ids, get_db())
    return list(dict.fromkeys(ids))


def _defaults_fields(data: DefaultsIn) -> dict:
    """Validated default id-lists for a settings bucket (global or a space)."""
    return {
        "default_character_ids": _require_characters(data.default_character_ids),
        "default_instruction_ids": _require_instructions(data.default_instruction_ids),
        "default_instruction_group_ids": _require_instruction_groups(data.default_instruction_group_ids),
    }


@router.get("/settings")
def api_get_settings():
    return get_db().get_settings().to_dict()


@router.put("/settings")
def api_update_settings(data: DefaultsIn):
    return get_db().save_settings(**_defaults_fields(data)).to_dict()


@router.put("/settings/title-model")
def api_set_title_model(data: TitleModelIn):
    """The text model that names new chats (empty = the chat's own model)."""
    return get_db().save_settings(title_model=(data.title_model or "").strip() or None).to_dict()


@router.get("/instructions")
def api_list_instructions():
    return {
        "instructions": [i.to_dict() for i in get_db().list_instructions()],
        "groups": [g.to_dict() for g in get_db().list_instruction_groups()],
    }


@router.post("/instructions")
def api_create_instruction(data: InstructionIn):
    return get_db().save_instruction(name=data.name.strip(), content=data.content).to_dict()


@router.put("/instructions/{instruction_id}")
def api_update_instruction(instruction_id: int, data: InstructionIn):
    item = get_db().save_instruction(instruction_id, name=data.name.strip(), content=data.content)
    if not item:
        raise HTTPException(404, "Instruction not found")
    return item.to_dict()


@router.delete("/instructions/{instruction_id}")
def api_delete_instruction(instruction_id: int):
    if not get_db().delete_instruction(instruction_id):
        raise HTTPException(404, "Instruction not found")
    return {"deleted": instruction_id}


@router.post("/instruction-groups")
def api_create_instruction_group(data: InstructionGroupIn):
    return (
        get_db()
        .save_instruction_group(name=data.name.strip(), snippet_ids=_require_instructions(data.snippet_ids))
        .to_dict()
    )


@router.put("/instruction-groups/{group_id}")
def api_update_instruction_group(group_id: int, data: InstructionGroupIn):
    item = get_db().save_instruction_group(
        group_id, name=data.name.strip(), snippet_ids=_require_instructions(data.snippet_ids)
    )
    if not item:
        raise HTTPException(404, "Instruction group not found")
    return item.to_dict()


@router.delete("/instruction-groups/{group_id}")
def api_delete_instruction_group(group_id: int):
    if not get_db().delete_instruction_group(group_id):
        raise HTTPException(404, "Instruction group not found")
    return {"deleted": group_id}


@router.get("/spaces")
def api_list_spaces():
    return {"spaces": [s.to_dict() for s in get_db().list_spaces()]}


@router.post("/spaces")
def api_create_space(data: SpaceIn):
    return get_db().save_space(name=data.name.strip(), **_defaults_fields(data)).to_dict()


@router.put("/spaces/{space_id}")
def api_update_space(space_id: int, data: SpaceIn):
    item = get_db().save_space(space_id, name=data.name.strip(), **_defaults_fields(data))
    if not item:
        raise HTTPException(404, "Space not found")
    return item.to_dict()


@router.delete("/spaces/{space_id}")
def api_delete_space(space_id: int):
    if not get_db().delete_space(space_id):
        raise HTTPException(404, "Space not found")
    return {"deleted": space_id}


@router.get("/conversations/{conv_id}")
def api_get_conversation(conv_id: str):
    conv = require_conv(conv_id)
    db = get_db()
    origin = None
    if conv.forked_from_id:
        parent = db.get_conversation(conv.forked_from_id)
        origin = {
            "id": conv.forked_from_id,
            "title": parent.title if parent else None,
            "message_id": conv.forked_from_message_id,
            "exists": parent is not None,
        }
    forks: dict[int, list[dict]] = {}
    for f in db.list_conversation_forks(conv_id):
        forks.setdefault(f.forked_from_message_id, []).append({"id": f.id, "title": f.title})
    return {
        "conversation": {**conv.to_dict(), "forked_from": origin, "spend": spend(conv)},
        "messages": [{**m, "forks": forks.get(m["id"], [])} for m in shown_branch(conv_id)],
    }


@router.get("/spend/breakdown")
def api_spend_breakdown(days: int = 0):
    """What the user's money went on: per model (and kind) over the last `days`
    days (0 = all time). Pollo's credits are converted to USD at its fixed rate
    so everything adds up in one currency; the credits stay alongside.
    """
    db = get_db()
    cutoff = datetime.now() - timedelta(days=days) if days > 0 else None
    groups: dict[tuple[str, str], dict] = {}
    for r in db.spend_rows([c.id for c in db.list_conversations(limit=None)]):
        if cutoff and r["at"] and r["at"] < cutoff:
            continue
        g = groups.setdefault(
            (r["model"] or "unknown", r["kind"]),
            {"model": r["model"] or "unknown", "kind": r["kind"], "usd": 0.0, "credits": 0, "count": 0},
        )
        g["usd"] += r["usd"] + r["credits"] * config.POLLO_USD_PER_CREDIT
        g["credits"] += r["credits"]
        g["count"] += 1
    rows = sorted(groups.values(), key=lambda g: -g["usd"])
    for g in rows:
        g["usd"] = round(g["usd"], 4)
    return {"days": days, "total_usd": round(sum(g["usd"] for g in rows), 4), "rows": rows}


@router.get("/conversations/{conv_id}/spend")
def api_conversation_spend(conv_id: str):
    return spend(require_conv(conv_id))


@router.post("/conversations/{conv_id}/branch")
def api_switch_branch(conv_id: str, data: SwitchBranch):
    """Show the branch through `message_id`, down to its newest message."""
    require_conv(conv_id)
    require_idle(conv_id)
    db = get_db()
    messages = db.get_chat_messages(conv_id)
    if not any(m.id == data.message_id for m in messages):
        raise HTTPException(400, "Message not in this conversation")
    # Children are always newer than their parent, so the newest message
    # under this one is the end of its most recent branch
    below = {data.message_id}
    for m in messages:
        if m.parent_id in below:
            below.add(m.id)
    db.set_chat_leaf(conv_id, max(below))
    return api_get_conversation(conv_id)


@router.post("/conversations/{conv_id}/fork")
def api_fork_conversation(conv_id: str, data: ForkConversation):
    """Branch a new chat off at a prompt or reply: it gets the messages
    leading up to it, it and (for a prompt) its shown reply — nothing that
    came after — plus this chat's models, instructions, characters and
    composer settings. It remembers where it came from. Media files are
    linked (or copied) into the new chat and characters made in this chat
    are copied into it, so either chat can be edited or deleted on its own.
    """
    conv = require_conv(conv_id)
    require_idle(conv_id)
    db = get_db()
    messages = db.get_chat_messages(conv_id)
    at = next((m for m in messages if m.id == data.message_id), None)
    if not at:
        raise HTTPException(400, "Message not in this conversation")
    path = branch_to(messages, at.id)
    replies = [m for m in messages if m.parent_id == at.id] if at.role == "user" else []
    if replies:
        shown = {m.id for m in branch_to(messages, db.get_chat_leaf_id(conv_id))}
        path.append(next((m for m in replies if m.id in shown), replies[-1]))

    new = db.create_conversation(
        title=f"{conv.title} (branch)"[:255],
        text_model=conv.text_model,
        image_model=conv.image_model,
        video_model=conv.video_model,
        space_id=conv.space_id,
        instruction_ids=conv.instruction_ids,
        instruction_group_ids=conv.instruction_group_ids,
        hidden_defaults=conv.hidden_defaults,
        paused_instructions=conv.paused_instructions,
        settings=conv.settings,
        forked_from_id=conv_id,
        forked_from_message_id=at.id,
        inherited_cost=round(sum(m.cost or 0 for m in path), 6) or None,
        inherited_credits=sum(i.get("credits") or 0 for m in path for i in m.media) or None,
    )
    # This chat's own characters, attached or used by the copied media, get
    # copies owned by the new chat; saved characters are shared as they are
    used = set(conv.character_ids)
    for msg in path:
        for item in msg.media:
            used.update(_media_character_ids(item.get("params") or {}))
    char_map = {
        c.id: characters.copy_to_conversation(c, new.id, db).id
        for c in characters.load(sorted(used), db)
        if c.conversation_id == conv_id
    }
    db.update_conversation(new.id, character_ids=[char_map.get(i, i) for i in conv.character_ids])

    fork = _Fork(chat_root() / conv_id, conversation_dir(new.id), char_map)
    db.add_chat_branch(
        new.id,
        [
            {
                "role": msg.role,
                "content": msg.content,
                "media": [fork.media_item(item) for item in msg.media],
                "model": msg.model,
                "status": msg.status,
                "mode": msg.mode,
                "error": msg.error,
                "cost": msg.cost,
            }
            for msg in path
        ],
    )
    return db.get_conversation(new.id).to_dict()


def _media_character_ids(params: dict) -> set[int]:
    """Characters a media item was made with: by id, or through their images."""
    ids = {i for i in params.get("characters") or [] if isinstance(i, int)}
    for ref in [*(params.get("refs") or []), *(params.get(k) for k in PARAM_FILES)]:
        if isinstance(ref, str) and ref.startswith(characters.REF_PREFIX):
            cid = ref[len(characters.REF_PREFIX) :].partition("/")[0]
            if cid.isdigit():
                ids.add(int(cid))
    return ids


class _Fork:
    """Copies media items into a branched chat: files are linked into its
    folder under the same names (Media shows each pair once) and references
    to copied characters point at the copies, so regenerating works there.
    """

    def __init__(self, src: Path, dst: Path, char_map: dict[int, int]) -> None:
        self.src, self.dst, self.char_map = src, dst, char_map

    def media_item(self, item: dict) -> dict:
        item = {**item, "id": uuid.uuid4().hex[:8]}
        if item.get("status") == "pending":
            # Its poller keeps updating the original chat only
            return {
                **item,
                "status": "error",
                "error": "Still rendering in the original chat when this one was branched",
            }
        if item.get("file"):
            self._link(item["file"])
        if item.get("params"):
            params = item["params"] = {**item["params"]}
            if params.get("characters"):
                params["characters"] = [self.char_map.get(i, i) for i in params["characters"]]
            if params.get("refs"):
                params["refs"] = [self._ref(r) for r in params["refs"]]
            for key in PARAM_FILES:
                if params.get(key):
                    params[key] = self._ref(params[key])
        return item

    def _ref(self, ref: str) -> str:
        """A reference for the new chat: a copied character's image, or a chat file (linked over)."""
        if ref.startswith(characters.REF_PREFIX):
            cid, _, file = ref[len(characters.REF_PREFIX) :].partition("/")
            if cid.isdigit() and int(cid) in self.char_map:
                return characters.image_ref(self.char_map[int(cid)], file)
            return ref
        self._link(ref)
        return ref

    def _link(self, name: str) -> None:
        if (
            Path(name).name != name
            or name.startswith(".")
            or not (self.src / name).is_file()
            or (self.dst / name).exists()
        ):
            return
        try:
            (self.dst / name).hardlink_to(self.src / name)
        except OSError:
            shutil.copy2(self.src / name, self.dst / name)


def _clean_conv_update(fields: dict) -> None:
    """Normalize/validate the mutable ConversationUpdate fields in place
    (everything except `pinned`, which the route handles separately).
    """
    if "instruction_ids" in fields:
        fields["instruction_ids"] = _require_instructions(fields["instruction_ids"] or [])
    if "instruction_group_ids" in fields:
        fields["instruction_group_ids"] = _require_instruction_groups(fields["instruction_group_ids"] or [])
    if fields.get("space_id") is not None:
        _require_space(fields["space_id"])
    if "title" in fields:
        fields["title"] = (fields["title"] or "").strip()[:255] or DEFAULT_TITLE
    if "kind" in fields:
        fields["kind"] = _clean_kind(fields["kind"])
    if "character_ids" in fields:
        characters.require(fields["character_ids"], get_db())
    if "hidden_defaults" in fields:
        fields["hidden_defaults"] = _require_hidden_defaults(fields["hidden_defaults"])
    if "paused_instructions" in fields:
        fields["paused_instructions"] = _require_paused(fields["paused_instructions"])


@router.patch("/conversations/{conv_id}")
def api_update_conversation(conv_id: str, data: ConversationUpdate):
    require_conv(conv_id)
    fields = data.model_dump(exclude_unset=True)
    _clean_conv_update(fields)
    if "pinned" in fields:
        # Not an edit: the chat keeps its place among the rest
        get_db().set_conversation_pinned(conv_id, bool(fields.pop("pinned")))
    if not fields:
        return get_db().get_conversation(conv_id).to_dict()
    return get_db().update_conversation(conv_id, **fields).to_dict()


@router.delete("/conversations/{conv_id}")
def api_delete_conversation(conv_id: str, delete_media: bool = True):
    """Delete a chat. Its images/videos/uploads go with it unless delete_media=false
    (the files then stay and show up under "Orphaned" in the Media library).
    """
    require_conv(conv_id)
    characters.delete_for_conversation(conv_id, get_db())
    get_db().delete_conversation(conv_id)
    # Its files go in the background: hundreds of images take a while on a NAS
    folder = chat_root() / conv_id
    if delete_media and folder.exists():
        folder.rename(folder.with_name(f".deleting-{conv_id}"))  # out of the way at once
        threading.Thread(target=_empty_trash, daemon=True).start()
    return {"deleted": conv_id}


def _empty_trash() -> None:
    """Remove deleted chats' folders (any left by a restart mid-delete too)."""
    for trash in chat_root().glob(".deleting-*"):
        shutil.rmtree(trash, ignore_errors=True)


@router.post("/conversations/{conv_id}/attachments")
async def api_upload_attachment(conv_id: str, file: UploadFile = File(...)):
    require_conv(conv_id)
    content, ext = await read_image_upload(file)
    return {"file": store_deduped(conversation_dir(conv_id), "up_", content, ext)}


@router.post("/conversations/{conv_id}/attachments/video")
async def api_upload_video_attachment(conv_id: str, file: UploadFile = File(...)):
    """A source video upload (e.g. Recast). Saved with a 'upv_' prefix so the
    message endpoint records it as a video (not image) media item.
    """
    require_conv(conv_id)
    content, ext = await read_video_upload(file)
    return {"file": store_deduped(conversation_dir(conv_id), "upv_", content, ext)}


@router.post("/conversations/{conv_id}/attachments/audio")
async def api_upload_audio_attachment(conv_id: str, file: UploadFile = File(...)):
    """A lip-sync audio upload. Saved with a 'upa_' prefix so the message
    endpoint records it as an audio (not image) media item.
    """
    require_conv(conv_id)
    content, ext = await read_audio_upload(file)
    return {"file": store_deduped(conversation_dir(conv_id), "upa_", content, ext)}


@router.delete("/conversations/{conv_id}/attachments/{filename}")
def api_discard_attachment(conv_id: str, filename: str):
    """Drop an attachment that was uploaded but never sent (removed from the
    composer). Files any message or library entry still uses are kept.
    """
    require_conv(conv_id)
    name = safe_filename(filename)
    if not name.startswith(("up_", "upv_", "upa_")):
        return {"deleted": False}
    db = get_db()
    in_use = any(name in media.referenced_files(i) for m in db.get_chat_messages(conv_id) for i in m.media) or any(
        lib.conversation_id == conv_id and name in media.referenced_files(lib.item) for lib in db.list_chat_library()
    )
    path = conversation_dir(conv_id) / name
    if in_use or not path.is_file():
        return {"deleted": False}
    path.unlink()
    return {"deleted": True}


@router.get("/media/{conv_id}/{filename}")
def api_chat_media(conv_id: str, filename: str):
    path = chat_root() / safe_filename(conv_id) / safe_filename(filename)  # rejects traversal (400)
    require_own_conversation(conv_id)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/media/{conv_id}/{filename}/preview")
async def api_chat_media_preview(conv_id: str, filename: str):
    """A chat image (or a video's first frame) scaled down for showing in the
    chat, cached; the full file is for the lightbox and downloads.
    """
    path = chat_root() / safe_filename(conv_id) / safe_filename(filename)  # rejects traversal (400)
    require_own_conversation(conv_id)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    try:
        return await media.thumb_response(path, CHAT_PREVIEW_SIZE)
    except HTTPException:
        # No thumbnail could be made (odd format, half-written file): show the
        # image itself rather than a broken tile. Videos have nothing to fall back to.
        if path.suffix.lower() in VIDEO_SUFFIXES:
            raise
        return FileResponse(path, headers={"Cache-Control": "no-cache"})


@router.get("/request-log")
def api_request_log(limit: int = 100):
    """The latest provider requests (Venice image/video calls): what was sent
    and what came back, newest first. See web/request_log.py.
    """
    return {"entries": request_log.recent(max(1, min(limit, 1000)))}


@router.get("/library")
def api_chat_library():
    """Every generated image/video across chats, newest first. `attached`
    items are still in their chat (on some branch); the rest were detached
    by edits/retries made before chats had branches.
    """
    db = get_db()
    titles = db.conversation_titles()
    items = []
    for msg in db.get_chat_messages_with_media():
        items.extend(
            {
                **item,
                "conversation_id": msg.conversation_id,
                "message_id": msg.id,
                "attached": True,
                "created_at": iso(msg.created_at),
            }
            for item in msg.media
            if item.get("source") != "upload"
        )
    for lib in db.list_chat_library():
        if lib.item.get("source") == "upload":
            continue
        items.append(
            {
                **lib.item,
                "conversation_id": lib.conversation_id,
                "message_id": None,
                "attached": False,
                "created_at": iso(lib.created_at),
            }
        )
    items.sort(key=lambda i: i["created_at"], reverse=True)
    for i in items:
        i["conversation_title"] = titles.get(i["conversation_id"])
    return {"items": items}


@router.delete("/library/{media_id}")
def api_delete_library_item(media_id: str):
    """Delete an unattached library item and its file. Attached media goes
    away with its message/chat instead.
    """
    db = get_db()
    lib = db.get_chat_library_item(media_id)
    if not lib:
        raise HTTPException(404, "Not in the library (only unattached items can be deleted here)")
    db.delete_chat_library_item(media_id)
    if lib.item.get("file"):
        (chat_root() / lib.conversation_id / safe_filename(lib.item["file"])).unlink(missing_ok=True)
    return {"deleted": media_id}


@router.get("/messages/{message_id}")
def api_get_message(message_id: int):
    msg = get_db().get_chat_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    return message_out(msg)


@router.get("/messages/{message_id}/delete-info")
def api_delete_exchange_info(message_id: int):
    """What deleting this prompt would also remove (other versions of it and
    the messages that followed them), for the confirmation.
    """
    msg = get_db().get_chat_message(message_id)
    info = msg and get_db().chat_exchange_delete_info(msg.conversation_id, message_id)
    if not info:
        raise HTTPException(404, "Prompt not found")
    return info


@router.delete("/messages/{message_id}")
def api_delete_exchange(message_id: int, delete_media: bool = False):
    """Delete a prompt's turn (every version of the prompt and its replies)
    from the chat, so the models no longer see it; what followed on the shown
    branch is kept. Generated images and videos move to the library, or are
    deleted with delete_media=true. Returns the conversation as now shown.
    """
    db = get_db()
    msg = db.get_chat_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.role != "user":
        raise HTTPException(400, "Delete the prompt; its reply goes with it")
    require_idle(msg.conversation_id)
    detached = db.delete_chat_exchange(msg.conversation_id, message_id)
    if delete_media:
        for item in detached:
            if item.get("file"):
                (conversation_dir(msg.conversation_id) / safe_filename(item["file"])).unlink(missing_ok=True)
            db.delete_chat_library_item(item["id"])
    return {
        "conversation": db.get_conversation(msg.conversation_id).to_dict(),
        "messages": shown_branch(msg.conversation_id),
    }
