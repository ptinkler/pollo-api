"""
Chat mode — a Gemini/Grok-style multimodal chat backed by OpenRouter.

A conversation has three model slots: a text model that drives the chat, an
image model and a video model. In "auto" mode the text model is given
generate_image / generate_video tools and decides itself when to use them;
the tools run on whichever image/video model is selected. "text", "image"
and "video" modes bypass that decision and hit one model directly.

Media item shape (stored in ChatMessage.media_json, sent to the frontend):
    {
      "id": "a1b2c3d4",              # stable per item; the UI upserts by it
      "kind": "image" | "video",
      "source": "upload" | "generated",
      "status": "pending" | "done" | "error",
      "file": "img_….png" | None,    # under <data>/chat/<conversation_id>/
      "pinned": optional bool,        # user pinned this image: sent as a reference with every new image
      "prompt", "model", "job_id", "error", "cost": optional,
      "credits": optional             # Pollo images bill in credits, not dollars
    }

Characters (web/characters.py): only characters the user attached to the
chat are used — never one just because its name comes up. The chat model is
told about the attached ones and names those in each picture via the tools'
`characters` argument (an attached name in the image prompt counts too, in
case it forgets). Their descriptions go into the media prompt and their
images go to the image model as references. The model can also save a new
character from images in the chat when asked (create_character), which
attaches it. Image mode uses every attached character.

Image and video models come from OpenRouter, plus Pollo's own models
("pollo/<key>", see web/pollo_chat.py) when POLLO_API_KEY is set, and
Venice's text, image and video models ("venice/<id>", see
web/venice_chat.py) when VENICE_API_KEY is set.

Messages form a tree (ChatMessage.parent_id): editing a prompt or retrying
a reply adds a sibling — a new branch — rather than deleting what came after,
and the conversation remembers which branch is shown (current_leaf_id).
Only the shown branch is sent to the models.

Turns run in a worker thread that owns all persistence; the SSE response
just relays its events. Closing the tab therefore doesn't lose the reply,
and videos keep polling in their own threads until they land on disk.
"""
import base64
import io
import json
import mimetypes
import queue
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field

from img2vid.common import config
from img2vid.common.metadata import get_db, iso

from . import characters, openrouter, pollo_chat, venice_chat
from .auth import verify_api_key
from .uploads import read_image_upload, safe_filename

router = APIRouter(prefix="/api/chat", dependencies=[Depends(verify_api_key)])

MAX_TOOL_ROUNDS = 4
CONSISTENCY_REFS = 2              # recent images passed to the image model to keep characters consistent
DEFAULT_IMAGE_LIMIT = 6           # chat images per request unless the composer's slider says otherwise: the most
                                  # recent images sent to the chat model as pixels, and the cap on chat images sent
                                  # as references (edit source + recent + pins + attachments). Character images
                                  # come on top, uncapped (each model trims to its own maximum).
MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024   # larger images are downscaled before sending
MODELS_CACHE_TTL = 30 * 60
CHAT_ROUND_SECONDS = 300          # cap on one LLM call (long stories stream for a while)
VIDEO_POLL_INTERVAL = 10
VIDEO_POLL_TIMEOUT = 45 * 60
VIDEO_MAX_POLL_ERRORS = 10
DEFAULT_TITLE = "New chat"

IMAGE_EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/svg+xml": ".svg"}

SYSTEM_PROMPT = """You are an assistant in a chat app. You have generate_image and generate_video \
tools, which create media with the image and video models the user has selected; the result is shown \
to the user in the chat.

When tools aren't available, bracketed notes in the conversation history record media that was \
produced earlier.

Today's date is {today}."""

IMAGE_TOOL_RESULT = "Image generated; it is shown to the user."
VIDEO_TOOL_RESULT = "Video job started; it is shown to the user once rendering finishes."

TOOLS_IMAGE = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": "Generate an image from a text prompt. Earlier images in the conversation can be passed to the image model as references, to keep characters consistent or to edit an image.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed description of the image to create."},
                "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
                                 "description": "Aspect ratio. Omit to use the image model's default."},
                "source_image": {"type": "string", "enum": ["none", "latest"],
                                 "description": "'latest' to edit/transform the most recent image in the conversation."},
                "keep_consistent": {"type": "boolean",
                                    "description": "true = also send the 2 most recent images in the conversation to the "
                                                   "image model as reference images. Default false. Images the user "
                                                   "has pinned are always sent as references."},
            },
            "required": ["prompt"],
        },
    },
}

TOOLS_CREATE_CHARACTER = {
    "type": "function",
    "function": {
        "name": "create_character",
        "description": "Save a character (person, creature, mascot…) from the most recent image(s) in the "
                       "conversation, so later images keep their look: from then on their description and "
                       "reference images are sent to the image model whenever they appear. Use it when the user "
                       "asks to make, save or keep using a character from an image. It's kept in this chat; "
                       "the user can save it for use in other chats.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The character's name, as the user calls them."},
                "description": {"type": "string",
                                "description": "Their appearance in detail, from the image: face, hair, build, "
                                               "age, clothing, distinctive features, art style."},
                "images": {"type": "integer", "minimum": 1, "maximum": 4,
                           "description": "How many of the most recent images show them (default 1: the latest)."},
            },
            "required": ["name", "description"],
        },
    },
}

TOOLS_VIDEO = {
    "type": "function",
    "function": {
        "name": "generate_video",
        "description": "Generate a short video from a text prompt, optionally animating the latest image in the conversation (used as the first frame). Runs in the background for a few minutes.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed description of the scene, action and camera motion."},
                "duration": {"type": "integer", "description": "Length in seconds. Omit to use the model default."},
                "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]},
                "source_image": {"type": "string", "enum": ["none", "latest"],
                                 "description": "'latest' to animate the most recent image in the conversation."},
            },
            "required": ["prompt"],
        },
    },
}


# ── Request models ──────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    instruction_id: int | None = None   # omitted = the default instruction, if one is set
    character_ids: list[int] = []


class ConversationUpdate(BaseModel):
    title: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    instruction_id: int | None = None   # explicit null detaches
    character_ids: list[int] | None = None


class InstructionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(default="", max_length=20000)
    is_default: bool = False


class TurnOptions(BaseModel):
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | None = None
    generate_audio: bool | None = None


class TurnSettings(BaseModel):
    mode: str = "auto"                 # auto | text | image | video
    history_limit: int | None = Field(default=None, ge=1)   # past messages sent to the chat model; None = all
    image_limit: int | None = Field(default=DEFAULT_IMAGE_LIMIT, ge=0)   # chat images per request; None = all
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    # The composer's picks, applied in every mode (Auto included). Unset =
    # the chat model's choice (Auto), else the media model's default.
    image_options: TurnOptions = TurnOptions()
    video_options: TurnOptions = TurnOptions()


class SendMessage(TurnSettings):
    content: str = ""
    attachments: list[str] = []        # filenames returned by the attachments endpoint


class RetryMessage(TurnSettings):
    message_id: int                    # the assistant message to regenerate


class EditMessage(TurnSettings):
    message_id: int                    # the user message to rewrite and resend
    content: str


class SwitchBranch(BaseModel):
    message_id: int                    # show the branch this message is on (its newest version)


# ── Paths & media helpers ───────────────────────────────────────────

def _chat_root() -> Path:
    # Read config at call time so tests can redirect ROOT_DIR
    return config.ROOT_DIR / "chat"


def _conv_dir(conv_id: str) -> Path:
    d = _chat_root() / conv_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _new_media(kind: str, source: str, **fields) -> dict[str, Any]:
    return {"id": uuid.uuid4().hex[:8], "kind": kind, "source": source,
            "status": "pending", "file": None, **fields}


def _saved_media(kind: str, source: str, file: str, **fields) -> dict[str, Any]:
    """A media item whose file is already on disk."""
    return {**_new_media(kind, source, **fields), "status": "done", "file": file}


def _file_to_data_url(path: Path) -> str:
    """Encode a local image as a data URL, downscaling big ones so request
    bodies stay reasonable (providers cap inline image sizes)."""
    raw = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    if len(raw) > MAX_INLINE_IMAGE_BYTES or mime == "image/gif":
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        img.thumbnail((2048, 2048))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        raw, mime = buf.getvalue(), "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _require_conv(conv_id: str):
    conv = get_db().get_conversation(conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


def _branch_to(messages: list, leaf_id: int | None) -> list:
    """The branch ending at `leaf_id`, first message first."""
    by_id = {m.id: m for m in messages}
    path = []
    msg = by_id.get(leaf_id)
    while msg:
        path.append(msg)
        msg = by_id.get(msg.parent_id)
    return path[::-1]


def _message_out(msg) -> dict:
    """A message for the UI, with its siblings for the ‹ 1/2 › branch arrows."""
    return {**msg.to_dict(), "siblings": get_db().get_chat_sibling_ids(msg.conversation_id, msg.parent_id)}


def _shown_branch(conv_id: str) -> list[dict]:
    db = get_db()
    messages = db.get_chat_messages(conv_id)
    siblings: dict[int | None, list[int]] = {}
    for m in messages:
        siblings.setdefault(m.parent_id, []).append(m.id)
    return [{**m.to_dict(), "siblings": siblings[m.parent_id]}
            for m in _branch_to(messages, db.get_chat_leaf_id(conv_id))]


def _require_openrouter():
    """Chat needs a text-model provider: OpenRouter or Venice."""
    if not (openrouter.is_configured() or venice_chat.is_configured()):
        raise HTTPException(503, "Neither OPENROUTER_API_KEY nor VENICE_API_KEY is set on the server")


# ── Model catalogue cache ───────────────────────────────────────────

_models_cache: dict[str, Any] = {"at": 0.0, "data": None}
_models_lock = threading.Lock()


def get_models(refresh: bool = False) -> dict[str, Any]:
    with _models_lock:
        if not refresh and _models_cache["data"] and time.time() - _models_cache["at"] < MODELS_CACHE_TTL:
            return _models_cache["data"]
        data: dict[str, Any] = {"errors": {}}
        for kind, fn in (("text", openrouter.list_text_models),
                         ("image", openrouter.list_image_models),
                         ("video", openrouter.list_video_models)):
            data[kind] = []
            if not openrouter.is_configured():
                continue
            try:
                data[kind] = fn()
            except (openrouter.OpenRouterError, Exception) as e:  # noqa: BLE001 — surface any failure per-kind
                data["errors"][kind] = str(e)
        for kind in ("text", "image", "video"):
            try:
                data[kind] = venice_chat.list_models(kind, refresh) + data[kind]
            except Exception as e:  # noqa: BLE001
                data["errors"][f"venice_{kind}"] = str(e)
        data["image"] = pollo_chat.list_image_models() + data["image"]
        data["video"] = pollo_chat.list_video_models() + data["video"]
        # Only cache a complete result, so a transient failure isn't sticky
        if not data["errors"]:
            _models_cache.update(at=time.time(), data=data)
        return data


def _model_info(kind: str, model_id: str | None) -> dict | None:
    """Look up cached catalogue info without triggering a fetch."""
    data = _models_cache["data"]
    if not data or not model_id:
        return None
    return next((m for m in data.get(kind, []) if m["id"] == model_id), None)


def _fit_video_params(model_id: str, duration: int | None, aspect_ratio: str | None,
                      resolution: str | None) -> tuple[int | None, str | None, str | None]:
    """Snap requested params onto what the video model supports (when known),
    so a model-chosen "7 seconds" doesn't fail on a 5/10-only model."""
    info = _model_info("video", model_id)
    if not info:
        return duration, aspect_ratio, resolution
    durations = info.get("durations") or []
    if duration and durations and duration not in durations:
        duration = min(durations, key=lambda d: abs(d - duration))
    if aspect_ratio and info.get("aspect_ratios") and aspect_ratio not in info["aspect_ratios"]:
        aspect_ratio = None
    if resolution and info.get("resolutions") and resolution not in info["resolutions"]:
        resolution = None
    return duration, aspect_ratio, resolution


# ── Routes: meta ────────────────────────────────────────────────────

@router.get("/status")
def api_chat_status():
    return {"configured": openrouter.is_configured() or venice_chat.is_configured(),
            "openrouter": openrouter.is_configured(), "venice": venice_chat.is_configured()}


@router.get("/credits")
def api_chat_credits():
    """OpenRouter balance for the chat header (Pollo's is /api/usage/balance)."""
    _require_openrouter()
    try:
        return openrouter.get_credits()
    except openrouter.OpenRouterError as e:
        raise HTTPException(502, f"Couldn't fetch the OpenRouter balance: {e}")


@router.get("/venice-balance")
def api_venice_balance():
    """Venice balance (USD) for the chat header."""
    if not venice_chat.is_configured():
        raise HTTPException(503, "VENICE_API_KEY is not set on the server")
    return {"usd": venice_chat.get_balance()}


@router.get("/models")
def api_chat_models(refresh: bool = False):
    _require_openrouter()
    return get_models(refresh)


# ── Routes: conversations ───────────────────────────────────────────

@router.get("/conversations")
def api_list_conversations():
    return {"conversations": [c.to_dict() for c in get_db().list_conversations()]}


@router.post("/conversations")
def api_create_conversation(data: ConversationCreate):
    db = get_db()
    if "instruction_id" in data.model_fields_set:
        instruction_id = _require_instruction(data.instruction_id)
    else:
        default = db.get_default_instruction()
        instruction_id = default.id if default else None
    characters.require(data.character_ids, db)
    conv = db.create_conversation(
        title=(data.title or DEFAULT_TITLE).strip()[:255] or DEFAULT_TITLE,
        text_model=data.text_model, image_model=data.image_model, video_model=data.video_model,
        instruction_id=instruction_id, character_ids=data.character_ids,
    )
    return conv.to_dict()


def _require_instruction(instruction_id: int | None) -> int | None:
    if instruction_id is not None and not get_db().get_instruction(instruction_id):
        raise HTTPException(400, "Instruction not found")
    return instruction_id


# ── Routes: custom instructions ─────────────────────────────────────

@router.get("/instructions")
def api_list_instructions():
    return {"instructions": [i.to_dict() for i in get_db().list_instructions()]}


@router.post("/instructions")
def api_create_instruction(data: InstructionIn):
    return get_db().save_instruction(name=data.name.strip(), content=data.content, is_default=data.is_default).to_dict()


@router.put("/instructions/{instruction_id}")
def api_update_instruction(instruction_id: int, data: InstructionIn):
    item = get_db().save_instruction(instruction_id, name=data.name.strip(), content=data.content,
                                     is_default=data.is_default)
    if not item:
        raise HTTPException(404, "Instruction not found")
    return item.to_dict()


@router.delete("/instructions/{instruction_id}")
def api_delete_instruction(instruction_id: int):
    if not get_db().delete_instruction(instruction_id):
        raise HTTPException(404, "Instruction not found")
    return {"deleted": instruction_id}


@router.get("/conversations/{conv_id}")
def api_get_conversation(conv_id: str):
    conv = _require_conv(conv_id)
    return {"conversation": conv.to_dict(), "messages": _shown_branch(conv_id)}


@router.post("/conversations/{conv_id}/branch")
def api_switch_branch(conv_id: str, data: SwitchBranch):
    """Show the branch through `message_id`, down to its newest message."""
    _require_conv(conv_id)
    _require_idle(conv_id)
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


@router.patch("/conversations/{conv_id}")
def api_update_conversation(conv_id: str, data: ConversationUpdate):
    _require_conv(conv_id)
    fields = data.model_dump(exclude_unset=True)
    if "instruction_id" in fields:
        _require_instruction(fields["instruction_id"])
    if "title" in fields:
        fields["title"] = (fields["title"] or "").strip()[:255] or DEFAULT_TITLE
    if "character_ids" in fields:
        characters.require(fields["character_ids"], get_db())
    return get_db().update_conversation(conv_id, **fields).to_dict()


@router.delete("/conversations/{conv_id}")
def api_delete_conversation(conv_id: str):
    _require_conv(conv_id)
    characters.delete_for_conversation(conv_id, get_db())
    get_db().delete_conversation(conv_id)
    shutil.rmtree(_chat_root() / conv_id, ignore_errors=True)
    return {"deleted": conv_id}


# ── Routes: media ───────────────────────────────────────────────────

@router.post("/conversations/{conv_id}/attachments")
async def api_upload_attachment(conv_id: str, file: UploadFile = File(...)):
    _require_conv(conv_id)
    content, ext = await read_image_upload(file)
    name = f"up_{uuid.uuid4().hex[:12]}{ext}"
    (_conv_dir(conv_id) / name).write_bytes(content)
    return {"file": name}


@router.get("/media/{conv_id}/{filename}")
def api_chat_media(conv_id: str, filename: str):
    path = _chat_root() / safe_filename(conv_id) / safe_filename(filename)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/library")
def api_chat_library():
    """Every generated image/video across chats, newest first. `attached`
    items are still in their chat (on some branch); the rest were detached
    by edits/retries made before chats had branches."""
    db = get_db()
    titles = {c.id: c.title for c in db.list_conversations(limit=100000)}
    items = []
    for msg in db.get_chat_messages_with_media():
        for item in msg.media:
            if item.get("source") != "upload":
                items.append({**item, "conversation_id": msg.conversation_id, "message_id": msg.id,
                              "attached": True, "created_at": iso(msg.created_at)})
    for lib in db.list_chat_library():
        items.append({**lib.item, "conversation_id": lib.conversation_id, "message_id": None,
                      "attached": False, "created_at": iso(lib.created_at)})
    items.sort(key=lambda i: i["created_at"], reverse=True)
    for i in items:
        i["conversation_title"] = titles.get(i["conversation_id"])
    return {"items": items}


@router.delete("/library/{media_id}")
def api_delete_library_item(media_id: str):
    """Delete an unattached library item and its file. Attached media goes
    away with its message/chat instead."""
    db = get_db()
    lib = db.get_chat_library_item(media_id)
    if not lib:
        raise HTTPException(404, "Not in the library (only unattached items can be deleted here)")
    db.delete_chat_library_item(media_id)
    if lib.item.get("file"):
        (_chat_root() / lib.conversation_id / safe_filename(lib.item["file"])).unlink(missing_ok=True)
    return {"deleted": media_id}


@router.get("/messages/{message_id}")
def api_get_message(message_id: int):
    msg = get_db().get_chat_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    return _message_out(msg)


@router.get("/messages/{message_id}/delete-info")
def api_delete_exchange_info(message_id: int):
    """What deleting this prompt would also remove (other versions of it and
    the messages that followed them), for the confirmation."""
    msg = get_db().get_chat_message(message_id)
    info = msg and get_db().chat_exchange_delete_info(msg.conversation_id, message_id)
    if not info:
        raise HTTPException(404, "Prompt not found")
    return info


@router.delete("/messages/{message_id}")
def api_delete_exchange(message_id: int):
    """Delete a prompt's turn (every version of the prompt and its replies)
    from the chat, so the models no longer see it; what followed on the shown
    branch is kept. Generated images and videos move to the library.
    Returns the conversation as now shown."""
    db = get_db()
    msg = db.get_chat_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.role != "user":
        raise HTTPException(400, "Delete the prompt; its reply goes with it")
    _require_idle(msg.conversation_id)
    db.delete_chat_exchange(msg.conversation_id, message_id)
    return {"conversation": db.get_conversation(msg.conversation_id).to_dict(),
            "messages": _shown_branch(msg.conversation_id)}


@router.post("/messages/{message_id}/cancel")
def api_cancel_message(message_id: int):
    ev = _cancel_events.get(message_id)
    if ev:
        ev.set()
    return {"cancelled": bool(ev)}


# ── Routes: turns (SSE) ─────────────────────────────────────────────

@router.post("/conversations/{conv_id}/messages")
def api_send_message(conv_id: str, data: SendMessage):
    _require_openrouter()
    conv = _require_conv(conv_id)
    content = data.content.strip()
    if not content and not data.attachments:
        raise HTTPException(400, "Message is empty")

    conv_dir = _conv_dir(conv_id)
    media = []
    for name in data.attachments[:8]:
        if not (conv_dir / safe_filename(name)).is_file():
            raise HTTPException(400, f"Attachment not found: {name}")
        media.append(_saved_media("image", "upload", name))

    db = get_db()
    user_msg = db.add_chat_message(conv_id, "user", content, media=media, mode=data.mode)
    _remember_models(conv, data)
    return _start_turn(conv_id, data, user_msg, parent_id=user_msg.id)


@router.post("/conversations/{conv_id}/retry")
def api_retry(conv_id: str, data: RetryMessage):
    """Generate another version of an assistant reply, as a new branch
    beside it. The old reply and everything after it stay on their branch."""
    _require_openrouter()
    conv = _require_conv(conv_id)
    _require_idle(conv_id)
    msg = get_db().get_chat_message(data.message_id)
    if not msg or msg.conversation_id != conv_id or msg.role != "assistant":
        raise HTTPException(400, "Can only retry an assistant message in this conversation")
    _remember_models(conv, data)
    return _start_turn(conv_id, data, None, parent_id=msg.parent_id)


@router.post("/conversations/{conv_id}/edit")
def api_edit(conv_id: str, data: EditMessage):
    """Resend a user message with new text, as a new branch beside it (same
    attachments), and stream a fresh reply. The original prompt and
    everything after it stay on their branch."""
    _require_openrouter()
    conv = _require_conv(conv_id)
    _require_idle(conv_id)
    db = get_db()
    msg = db.get_chat_message(data.message_id)
    if not msg or msg.conversation_id != conv_id or msg.role != "user":
        raise HTTPException(400, "Can only edit a user message in this conversation")
    content = data.content.strip()
    if not content and not msg.media:
        raise HTTPException(400, "Message is empty")
    media = [{**item, "id": uuid.uuid4().hex[:8]} for item in msg.media]
    user_msg = db.add_chat_message(conv_id, "user", content, media=media, parent_id=msg.parent_id,
                                   mode=data.mode)
    _remember_models(conv, data)
    return _start_turn(conv_id, data, user_msg, parent_id=user_msg.id)


def _require_idle(conv_id: str) -> None:
    """Edits/retries rewrite history, so they can't overlap a running reply."""
    if any(m.status == "streaming" for m in get_db().get_chat_messages(conv_id)):
        raise HTTPException(409, "Wait for the current reply to finish (or stop it) first")


def _remember_models(conv, settings: TurnSettings) -> None:
    """Persist the model picks on the conversation so reopening it restores them."""
    fields = {k: getattr(settings, k) for k in ("text_model", "image_model", "video_model")
              if getattr(settings, k) and getattr(settings, k) != getattr(conv, k)}
    if fields:
        get_db().update_conversation(conv.id, **fields)


_cancel_events: dict[int, threading.Event] = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _start_turn(conv_id: str, settings: TurnSettings, user_msg, parent_id: int | None) -> StreamingResponse:
    model = {"image": settings.image_model, "video": settings.video_model}.get(settings.mode, settings.text_model)
    assistant = get_db().add_chat_message(conv_id, "assistant", "", model=model, status="streaming",
                                          parent_id=parent_id, mode=settings.mode)
    start = {"type": "start", "user_message": _message_out(user_msg) if user_msg else None,
             "assistant_message": _message_out(assistant)}
    events: queue.Queue = queue.Queue()
    cancel = threading.Event()
    _cancel_events[assistant.id] = cancel

    def worker():
        try:
            Turn(conv_id, settings, assistant.id, events.put, cancel).run()
        finally:
            _cancel_events.pop(assistant.id, None)
            events.put(None)

    threading.Thread(target=worker, daemon=True, name=f"chat-turn-{assistant.id}").start()

    def stream() -> Iterator[str]:
        yield _sse(start)
        while True:
            try:
                ev = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if ev is None:
                return
            yield _sse(ev)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Turn orchestration ──────────────────────────────────────────────

class Turn:
    """Runs one assistant turn and persists it. `emit` receives UI events."""

    def __init__(self, conv_id: str, settings: TurnSettings, message_id: int, emit, cancel: threading.Event):
        self.conv_id = conv_id
        self.s = settings
        self.message_id = message_id
        self.emit = emit
        self.cancel = cancel
        self.db = get_db()
        # Only this reply's own branch — other versions of earlier turns aren't context
        self.history = _branch_to(self.db.get_chat_messages(conv_id), message_id)[:-1]
        self.instructions = _conversation_instructions(conv_id)
        conv = self.db.get_conversation(conv_id)
        self.characters = []            # attached by the user; the only ones a turn uses
        if self._characters_usable():   # attached ones stay attached, just unused, otherwise
            self.characters = characters.load(conv.character_ids if conv else [], self.db)
        self.content = ""
        self.cost = 0.0
        self.media: list[dict] = []

    # ― entry point ―
    def run(self) -> None:
        try:
            if self.s.mode == "image":
                self._direct_image()
            elif self.s.mode == "video":
                self._direct_video()
            else:
                self._chat(tools_enabled=self.s.mode == "auto")
            status, error = ("done", None)
        except openrouter.OpenRouterError as e:
            status, error = "error", str(e)
        except Exception as e:  # noqa: BLE001 — never leave a message stuck in "streaming"
            status, error = "error", f"{type(e).__name__}: {e}"
        if self.cancel.is_set() and status == "done":
            self.content = self.content.rstrip() + ("\n\n" if self.content else "") + "*(stopped)*"
        msg = self.db.update_chat_message(
            self.message_id, content=self.content, status=status, error=error,
            cost=round(self.cost, 6) if self.cost else None,
        )
        if error:
            self.emit({"type": "error", "message": error})
        self._maybe_title()
        self.emit({"type": "done", "message": _message_out(msg) if msg else None})

    # ― explicit modes ―
    def _last_user(self):
        return next((m for m in reversed(self.history) if m.role == "user"), None)

    def _direct_image(self) -> None:
        user = self._last_user()
        prompt = (user.content if user else "").strip()
        if not prompt:
            raise openrouter.OpenRouterError("Image mode needs a text prompt")
        chars = self.characters   # every attached character
        refs = [m["file"] for m in (user.media if user else []) if m["kind"] == "image" and m.get("file")]
        if self._accepts_refs():
            refs = _with_character_refs(refs + self._pinned_images(), chars, self.s.image_limit, after=len(refs))
        self._generate_image(prompt, self.s.image_options.aspect_ratio, refs, chars=chars)

    def _direct_video(self) -> None:
        user = self._last_user()
        prompt = (user.content if user else "").strip()
        frames = [m["file"] for m in (user.media if user else []) if m["kind"] == "image" and m.get("file")]
        if not prompt and not frames:
            raise openrouter.OpenRouterError("Video mode needs a prompt or an image")
        # Attached images: the first frame, the last frame (first+last-frame
        # models) and, for reference models, all of them are references
        self._generate_video(prompt, self.s.video_options.duration, self.s.video_options.aspect_ratio,
                             frames[0] if frames else None, chars=self.characters,
                             last_frame=frames[1] if len(frames) > 1 else None, attached=frames)

    # ― chat with tools ―
    def _chat(self, tools_enabled: bool) -> None:
        if not self.s.text_model:
            raise openrouter.OpenRouterError("No text model selected")
        info = _model_info("text", self.s.text_model)
        use_tools = tools_enabled and (info is None or info.get("supports_tools"))
        vision = info is None or "image" in (info.get("input_modalities") or [])
        messages = self._build_llm_messages(vision, as_tool_calls=bool(use_tools and self._tools()))

        offer_tools = True
        for round_no in range(MAX_TOOL_ROUNDS):
            # Last round: withhold tools so the loop can't run forever. Rebuilt
            # each round: a character created mid-turn joins the name lists.
            tools = self._tools() if use_tools else []
            round_tools = (tools or None) if offer_tools and round_no < MAX_TOOL_ROUNDS - 1 else None
            text, tool_calls = self._stream_round(messages, round_tools)
            if self.cancel.is_set() or not tool_calls:
                return
            messages.append({"role": "assistant", "content": text or None, "tool_calls": tool_calls})
            results = []
            for call in tool_calls:
                result = self._run_tool(call)
                results.append(result)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
                if self.cancel.is_set():
                    return
            # A moderation block ends the turn: the user chooses Retry or
            # another model on the failed card (no automatic re-attempt)
            if any(r.get("moderated") for r in results):
                return
            # Saving a character makes nothing to show — carry on (usually to draw them)
            made_media = any(c["function"]["name"] != "create_character" for c in tool_calls)
            if made_media and all(r.get("ok") for r in results):
                # The media was made. If the model also wrote its reply, the
                # reply is complete — asking it to continue just makes it
                # start over (duplicate story + duplicate image). If it called
                # the tool before writing anything, let it write, without tools.
                if text.strip():
                    return
                offer_tools = False
            # (After a non-moderation failure the model keeps its tools and
            # can explain or try again.)

    def _tools(self) -> list[dict]:
        names = [c.name for c in self.characters]
        tools = [TOOLS_CREATE_CHARACTER] if self.s.image_model else []
        if self.s.image_model:
            tools.insert(0, _with_character_arg(TOOLS_IMAGE, names))
        if self.s.video_model:
            tools.append(_with_character_arg(TOOLS_VIDEO, names))
        return tools

    def _stream_round(self, messages: list[dict], tools: list[dict] | None) -> tuple[str, list[dict]]:
        """One chat completion, streamed to the UI."""
        text = ""
        calls: dict[int, dict] = {}
        finish = None
        if self.content and not self.content.endswith("\n\n"):
            self._append("\n\n")
        stream_chat = venice_chat.stream_chat if venice_chat.is_venice(self.s.text_model) else openrouter.stream_chat
        for chunk in stream_chat(self.s.text_model, messages, tools, session_id=self.conv_id,
                                            max_seconds=CHAT_ROUND_SECONDS, should_stop=self.cancel.is_set):
            if self.cancel.is_set():
                break
            usage = chunk.get("usage")
            if usage and usage.get("cost"):
                self.cost += float(usage["cost"])
            for choice in chunk.get("choices") or []:
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    text += delta["content"]
                    self._append(delta["content"])
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {
                        "id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    slot["function"]["name"] += fn.get("name") or ""
                    slot["function"]["arguments"] += fn.get("arguments") or ""
        tool_calls = [c for _, c in sorted(calls.items()) if c["function"]["name"]]
        for i, c in enumerate(tool_calls):
            c["id"] = c["id"] or f"call_{i}"
        # Diagnostics: distinguishes "model never called the tool" from
        # "we failed to parse the call" when media goes missing
        print(f"💬 chat msg {self.message_id} {self.s.text_model}: finish={finish} "
              f"tools_offered={bool(tools)} tool_calls={[c['function']['name'] for c in tool_calls]} "
              f"raw_call_slots={len(calls)} text_chars={len(text)}")
        return text, tool_calls

    def _append(self, text: str) -> None:
        self.content += text
        self.emit({"type": "delta", "text": text})

    def _run_tool(self, call: dict) -> dict:
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "Arguments were not valid JSON"}
        if name == "create_character":
            return self._create_character(args)
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return {"ok": False, "error": "prompt is required"}
        source = self._latest_image() if args.get("source_image") == "latest" else None
        if args.get("source_image") == "latest" and not source:
            return {"ok": False, "error": "There is no earlier image in the conversation to use"}
        # A setting picked in the composer beats the model's guess. When
        # animating an image, the image's own shape beats the guess too.
        chars = self._pick_characters(args.get("characters"), prompt)
        opts = self.s.video_options if name == "generate_video" else self.s.image_options
        guess = None if name == "generate_video" and source else args.get("aspect_ratio")
        ratio = opts.aspect_ratio or guess
        try:
            if name == "generate_image":
                refs = self._image_refs(args, source, chars)
                ref_args = {k: args[k] for k in ("source_image", "keep_consistent", "characters") if k in args}
                self._generate_image(prompt, ratio, refs, ref_args, chars)
                result = {"ok": True, "result": IMAGE_TOOL_RESULT}
                if chars:
                    result["characters"] = [c.name for c in chars]
                if refs:
                    result["reference_images"] = len(refs)
                    pinned = len(set(refs) & set(self._pinned_images()))
                    if pinned:
                        result["pinned_by_user"] = pinned
                elif (ref_args or self._pinned_images()) and not self._accepts_refs():
                    result["note"] = "The selected image model can't take reference images, so none were sent."
                return result
            if name == "generate_video":
                duration = opts.duration or args.get("duration")
                last = None
                if "last_frame" in ((_model_info("video", self.s.video_model) or {}).get("frame_images") or []):
                    # First+last-frame models: the two most recent images, older one first
                    recent = self._latest_images(2)
                    if len(recent) == 2:
                        source, last = recent[1], recent[0]
                self._generate_video(prompt, duration, ratio, source, chars, last_frame=last)
                return {"ok": True, "result": VIDEO_TOOL_RESULT}
        except openrouter.OpenRouterError as e:
            return {"ok": False, "error": str(e), "moderated": _is_moderation_error(e)}
        return {"ok": False, "error": f"Unknown tool {name}"}

    def _latest_image(self) -> str | None:
        images = self._latest_images(1)
        return images[0] if images else None

    def _latest_images(self, n: int) -> list[str]:
        """The n most recent finished images (this turn first, then history)."""
        found: list[str] = []
        for item in reversed(self.media):
            if item["kind"] == "image" and item["status"] == "done" and item.get("file"):
                found.append(item["file"])
        for msg in reversed(self.history):
            for item in reversed(msg.media):
                if item["kind"] == "image" and item.get("status") == "done" and item.get("file"):
                    found.append(item["file"])
        return found[:n]

    def _pinned_images(self) -> list[str]:
        """Images the user pinned on this branch, oldest first."""
        return [item["file"] for msg in self.history for item in msg.media
                if item.get("pinned") and item["kind"] == "image" and item.get("status", "done") == "done"
                and item.get("file")]

    def _pick_characters(self, names, prompt: str) -> list:
        """The attached characters in a picture: those the model named in the
        tool call, plus any whose name is in its prompt (models sometimes
        forget the argument). Unattached characters are never used."""
        named = characters.named(self.characters, names)   # "Chloe" can mean attached "Chloe Muscle"
        # "Chloe" in the prompt of a picture of "Chloe Muscle" is her, not an attached "Chloe"
        mentioned = characters.mentioned(self.characters, prompt, prefer=named)
        return list({c.id: c for c in named + mentioned}.values())

    def _attach(self, chars: list) -> None:
        """Attach characters to the chat (they stay for later turns) and tell the UI."""
        new = [c for c in chars if c.id not in {a.id for a in self.characters}]
        if not new:
            return
        self.characters += new
        self.db.update_conversation(self.conv_id, character_ids=[c.id for c in self.characters])
        self.emit({"type": "characters", "character_ids": [c.id for c in self.characters],
                   "characters": [c.to_dict() for c in self.characters]})

    def _create_character(self, args: dict) -> dict:
        name = str(args.get("name") or "").strip()[:100]
        if not name:
            return {"ok": False, "error": "name is required"}
        existing = next((c for c in characters.available(self.conv_id, self.db)
                         if c.name.strip().lower() == name.lower()), None)
        if existing:
            how = ("use it by name" if existing.id in {c.id for c in self.characters}
                   else "the user can attach it to this chat with the characters button")
            return {"ok": False, "error": f"There's already a character called {name}; {how}"}
        try:
            n = max(1, min(4, int(args.get("images") or 1)))
        except (TypeError, ValueError):
            n = 1
        files = [p for p in (_conv_dir(self.conv_id) / f for f in self._latest_images(n)) if p.is_file()]
        if not files:
            return {"ok": False, "error": "There is no image in the conversation to make the character from"}
        char = characters.create_from_files(name, str(args.get("description") or "").strip()[:4000], files,
                                            self.conv_id, self.db)
        self._attach([char])
        return {"ok": True, "result": f"Character {name} saved with {len(files)} reference image(s) and attached "
                                      f"to this chat. Name them in generate_image's `characters` to use them."}

    def _characters_usable(self) -> bool:
        """Whether this turn can use characters — mirrors characterSupport in
        ChatView. Their point is reference images, so it takes an image model
        that accepts them (and, in Auto, a chat model that can call it).
        Chat mode just tells the chat model about them; Video mode only
        uses them with video models that take reference images."""
        if self.s.mode == "text":
            return True
        if self.s.mode == "video":
            # Only video models that take reference images (Venice's refs→video)
            info = _model_info("video", self.s.video_model) or {}
            return bool(info.get("reference_images") or info.get("family") == "motion")
        if not self.s.image_model or not self._accepts_refs():
            return False
        if self.s.mode == "auto":
            info = _model_info("text", self.s.text_model)
            return info is None or bool(info.get("supports_tools"))
        return True

    def _accepts_refs(self) -> bool:
        info = _model_info("image", self.s.image_model)
        return not info or "image" in (info.get("input_modalities") or [])

    def _image_refs(self, args: dict, source: str | None, chars: list) -> list[str]:
        """Reference images for generate_image: the edit source (source_image),
        the images of the characters it named, the images the user pinned,
        and the most recent images if the model asked (keep_consistent).
        That order is also the priority when a model takes fewer images than
        that (Venice's edit models): recent picks go first, then pins.
        Pins are the user's choice; the app never adds references on its own."""
        if not self._accepts_refs():
            return []  # this image model can't take references
        lead = [source] if source else []
        pinned = self._pinned_images()
        recent = []
        if args.get("keep_consistent") is True:
            recent = [f for f in self._latest_images(CONSISTENCY_REFS) if f not in pinned and f not in lead]
        chat_refs = _dedupe(lead + pinned + recent[:max(CONSISTENCY_REFS - len(lead), 0)])
        return _with_character_refs(chat_refs, chars, self.s.image_limit, after=len(lead))

    # ― generation ―
    def _add_media(self, item: dict) -> None:
        self.media.append(item)
        self.db.append_chat_media_item(self.message_id, item)
        self.emit({"type": "media", "message_id": self.message_id, "item": dict(item)})

    def _update_media(self, item: dict, **fields) -> None:
        item.update(fields)
        self.db.update_chat_media_item(self.message_id, item["id"], **fields)
        self.emit({"type": "media", "message_id": self.message_id, "item": dict(item)})

    def _generate_image(self, prompt: str, aspect_ratio: str | None, ref_files: list[str],
                        ref_args: dict | None = None, chars: list | None = None) -> None:
        if not self.s.image_model:
            raise openrouter.OpenRouterError("No image model selected")
        # Params are stored on the item so a failed image can be retried as-is
        params = {"aspect_ratio": aspect_ratio,
                  "resolution": self.s.image_options.resolution,
                  "refs": ref_files}
        if ref_args:
            params["ref_args"] = ref_args   # the model's own reference choices, replayed in history
        if chars:
            params["characters"] = [c.id for c in chars]   # described in the prompt at generation time
            params["character_names"] = [c.name for c in chars]   # for display
        context = None
        if _is_conversational(self.s.image_model):
            # Like the Gemini app: the image model gets the conversation
            direct = self.s.mode == "image"
            params.update(context=True, direct=direct, history_limit=self.s.history_limit,
                          image_limit=self.s.image_limit)
            context = _image_context(self.conv_id, self.history, self.s.history_limit, self.content,
                                     None if direct else prompt, ref_files, self.instructions, chars,
                                     self.s.image_limit)
        item = _new_media("image", "generated", prompt=prompt, model=self.s.image_model, params=params)
        self._add_media(item)
        try:
            names, cost, credits, sent = _run_image_generation(self.conv_id, self.s.image_model, prompt, params, context)
        except openrouter.OpenRouterError as e:
            self._update_media(item, **_failure_fields(e))
            raise
        if cost:
            self.cost += float(cost)
        for i, name in enumerate(names):
            if i == 0:
                self._update_media(item, status="done", file=name, cost=cost, credits=credits,
                                   params={**params, **sent})
            else:
                self._add_media(_saved_media("image", "generated", name, prompt=prompt, model=self.s.image_model))

    def _generate_video(self, prompt: str, duration: int | None, aspect_ratio: str | None,
                        first_frame: str | None, chars: list | None = None, last_frame: str | None = None,
                        attached: list[str] | None = None) -> None:
        if not self.s.video_model:
            raise openrouter.OpenRouterError("No video model selected")
        duration, aspect_ratio, resolution = _fit_video_params(
            self.s.video_model, duration, aspect_ratio, self.s.video_options.resolution)
        params = {"duration": duration, "aspect_ratio": aspect_ratio, "resolution": resolution,
                  "first_frame": first_frame, "generate_audio": self.s.video_options.generate_audio}
        if chars:
            params["characters"] = [c.id for c in chars]
        params.update(self._video_inputs(first_frame, last_frame, attached or [], chars or []))
        item = _new_media("video", "generated", prompt=prompt, model=self.s.video_model, params=params)
        self._add_media(item)
        try:
            job = _submit_video_generation(self.conv_id, self.s.video_model, prompt, params)
        except openrouter.OpenRouterError as e:
            self._update_media(item, **_failure_fields(e))
            raise
        # Pollo reports what it was actually sent, defaults included
        self._update_media(item, job_id=job["id"], params={**params, **job.get("params", {})})
        start_video_poller(self.conv_id, self.message_id, item["id"], job["id"])

    def _video_inputs(self, first_frame: str | None, last_frame: str | None, attached: list[str],
                      chars: list) -> dict:
        """The extra inputs the video model's family takes (Venice): reference
        images (attached ones, the frame, characters' images and pins), a
        last frame, or the chat's latest video."""
        info = _model_info("video", self.s.video_model) or {}
        out: dict[str, Any] = {}
        if info.get("reference_images") or info.get("family") == "motion":
            own = _dedupe([*attached, *([first_frame] if first_frame else []), *self._pinned_images()])
            out["refs"] = _with_character_refs(own, chars, None, after=len(attached) or (1 if first_frame else 0))
        if last_frame and "last_frame" in (info.get("frame_images") or []):
            out["last_frame"] = last_frame
        if info.get("video_input"):
            out["source_video"] = self._latest_video()
        return out

    def _latest_video(self) -> str | None:
        """The most recent finished video (this turn first, then history)."""
        for item in [*reversed(self.media), *(i for m in reversed(self.history) for i in reversed(m.media))]:
            if item["kind"] == "video" and item.get("status") == "done" and item.get("file"):
                return item["file"]
        return None

    # ― history → OpenRouter messages ―
    def _build_llm_messages(self, vision: bool, as_tool_calls: bool = False) -> list[dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(today=datetime.now().strftime("%A %d %B %Y"))}]
        if self.instructions:
            # The user's own custom instructions, verbatim
            messages.append({"role": "system", "content": self.instructions})
        note = _characters_note(self.characters)
        if note:
            messages.append({"role": "system", "content": note})
        return messages + _conversation(self.conv_id, self.history, self.s.history_limit, vision, as_tool_calls,
                                        self.s.image_limit)

    def _maybe_title(self) -> None:
        conv = self.db.get_conversation(self.conv_id)
        if not conv or conv.title != DEFAULT_TITLE:
            return
        first = next((m for m in self.history if m.role == "user" and m.content), None)
        if not first:
            return
        title = " ".join(first.content.split())
        if len(title) > 60:
            title = title[:57].rsplit(" ", 1)[0] + "…"
        self.db.update_conversation(self.conv_id, title=title)
        self.emit({"type": "title", "title": title})


def _with_character_arg(tool: dict, names: list[str]) -> dict:
    """A generate_* tool with a `characters` argument listing the usable characters."""
    if not names:
        return tool
    fn = tool["function"]
    params = fn["parameters"]
    return {**tool, "function": {**fn, "parameters": {**params, "properties": {
        **params["properties"],
        "characters": {"type": "array", "items": {"type": "string", "enum": names},
                       "description": "The user's characters who appear in it. Their descriptions and reference "
                                      "images are sent to the model automatically, so the prompt needn't "
                                      "describe their looks."},
    }}}}


def _characters_note(attached: list) -> str:
    """What the chat model is told about the attached characters ('' when there are none)."""
    if not attached:
        return ""
    parts = ["The user has attached these characters to the chat:\n\n" + characters.describe(attached)]
    parts.append("Whenever one of these characters is in an image or video you make, name them in the tool's "
                 "`characters` argument: their description and reference images are then sent to the model "
                 "for you, so they look the same as before.")
    return "\n\n".join(parts)


def _with_character_refs(chat_refs: list[str], chars: list, image_limit: int | None,
                         after: int | None = None) -> list[str]:
    """Chat images (up to `image_limit`, None = all) plus every image of the
    characters in the picture, which aren't capped. The character images go
    after the first `after` chat images (default: all of them)."""
    chat_refs = _dedupe(chat_refs)[:image_limit]
    split = len(chat_refs) if after is None else min(after, len(chat_refs))
    return chat_refs[:split] + characters.reference_refs(chars) + chat_refs[split:]


def _param_characters(params: dict) -> list:
    """The characters a media item was made with (deleted ones drop out)."""
    return characters.load(params.get("characters"), get_db())


def _ref_file(conv_id: str, ref: str) -> Path:
    """A reference image's file: a character image ("char:…") or a file in the chat."""
    return characters.ref_path(ref) or _conv_dir(conv_id) / ref


def _history_window(history: list, limit: int | None) -> list:
    """The last `limit` messages (None = all), starting on a user message so
    the model never sees a reply without the prompt that caused it."""
    if not limit or len(history) <= limit:
        return history
    window = history[-limit:]
    while window and window[0].role != "user":
        window = window[1:]
    return window or history[-1:]


def _conversation(conv_id: str, history: list, history_limit: int | None, vision: bool,
                  as_tool_calls: bool = False, image_limit: int | None = DEFAULT_IMAGE_LIMIT) -> list[dict]:
    """The chat history as OpenRouter messages (no system prompt): the last
    `history_limit` messages, with the `image_limit` most recent images as
    pixels (None = all).
    Shared by the chat model and conversational image models.

    `as_tool_calls` (only when tools are offered — providers reject tool
    calls otherwise) records generated media as the tool calls and results
    that produced it; without it, media is summarised in bracketed notes."""
    messages: list[dict] = []

    history = _history_window(history, history_limit)

    # The most recent few images — uploaded or generated — go over as
    # pixels so the model can see what's actually in them; older ones
    # are described by a note instead.
    image_budget = (float("inf") if image_limit is None else image_limit) if vision else 0
    pixel_files: set[str] = set()
    for msg in reversed(history):
        for item in reversed(msg.media):
            if (image_budget and item["kind"] == "image" and item.get("file")
                    and item.get("status", "done") == "done"):
                pixel_files.add(item["file"])
                image_budget -= 1

    conv_dir = _conv_dir(conv_id)

    def pixels(item: dict) -> dict | None:
        f = item.get("file")
        if f in pixel_files and (conv_dir / f).is_file():
            return {"type": "image_url", "image_url": {"url": _file_to_data_url(conv_dir / f)}}
        return None

    # Chat APIs don't accept images inside assistant messages, so images
    # the model generated ride along with the next user message.
    carried: list[dict] = []
    carried_label = {"type": "text", "text": "[The images you generated in your previous reply, "
                                             "attached so you can see them]"}
    for msg in history:
        if msg.role == "user":
            parts: list[dict] = []
            if carried:
                parts += [carried_label, *carried]
                carried = []
            if msg.content:
                parts.append({"type": "text", "text": msg.content})
            for item in msg.media:
                parts.append(pixels(item) or {"type": "text", "text": "[user attached an image]"})
            if parts:
                messages.append({"role": "user", "content": parts})
        elif msg.role == "assistant":
            carried += [p for p in (pixels(i) for i in msg.media if i["kind"] == "image") if p]
            generated = [i for i in msg.media if i.get("source") == "generated" and i.get("prompt")]
            if as_tool_calls and generated:
                # Record what actually happened: the model's tool calls and
                # the results it got back — not text it could imitate
                messages.append({"role": "assistant", "content": msg.content or None,
                                 "tool_calls": [_history_tool_call(i) for i in generated]})
                messages += [{"role": "tool", "tool_call_id": f"call_{i['id']}",
                              "content": json.dumps(_history_tool_result(i))} for i in generated]
                continue
            text = msg.content or ""
            notes = [_media_note(item) for item in msg.media]
            if notes:
                text = (text + "\n\n" if text else "") + "\n".join(notes)
            if msg.status == "error" and not text:
                continue
            if text:
                messages.append({"role": "assistant", "content": text})
    if carried:  # history ended on an assistant message
        messages.append({"role": "user", "content": [carried_label, *carried]})
    return messages


def _image_context(conv_id: str, history: list, history_limit: int | None, reply_text: str,
                   prompt: str | None, refs: list[str], instructions: str | None = None,
                   chars: list | None = None, image_limit: int | None = DEFAULT_IMAGE_LIMIT) -> list[dict]:
    """What a conversational image model is sent: the conversation, then —
    when the chat model called the tool — its reply so far and its prompt,
    verbatim, with any reference images it asked for. In Image mode
    (prompt=None) the user's own message is already the last one."""
    messages = _conversation(conv_id, history, history_limit, vision=True, image_limit=image_limit)
    system = [s for s in (instructions, characters.describe(chars or [])) if s]
    messages[:0] = [{"role": "system", "content": s} for s in system]
    if prompt is not None:
        if reply_text.strip():
            messages.append({"role": "assistant", "content": reply_text.strip()})
        paths = [_ref_file(conv_id, f) for f in refs]
        parts: list[dict] = [{"type": "text", "text": prompt}]
        parts += [{"type": "image_url", "image_url": {"url": _file_to_data_url(p)}} for p in paths if p.is_file()]
        messages.append({"role": "user", "content": parts})
    elif chars:
        # Image mode: the user's message is last; their characters' images go with it
        paths = [_ref_file(conv_id, f) for f in refs if f.startswith(characters.REF_PREFIX)]
        if paths and messages and messages[-1]["role"] == "user":
            messages[-1] = {**messages[-1], "content": messages[-1]["content"] + [
                {"type": "image_url", "image_url": {"url": _file_to_data_url(p)}} for p in paths if p.is_file()]}
    return messages


def _conversation_instructions(conv_id: str) -> str | None:
    """The custom instructions attached to a chat, if any (user's text, verbatim)."""
    db = get_db()
    conv = db.get_conversation(conv_id)
    if not conv or not conv.instruction_id:
        return None
    item = db.get_instruction(conv.instruction_id)
    return item.content if item and item.content.strip() else None


def _is_conversational(image_model: str | None) -> bool:
    info = _model_info("image", image_model)
    return bool(info and info.get("conversational"))


def _dedupe(files: list[str]) -> list[str]:
    return list(dict.fromkeys(files))


def _history_tool_call(item: dict) -> dict:
    params = item.get("params") or {}
    args: dict[str, Any] = {"prompt": item["prompt"]}
    if params.get("aspect_ratio"):
        args["aspect_ratio"] = params["aspect_ratio"]
    # Replay the reference choices too, so the history doesn't read as a
    # run of reference-free calls that the model then imitates
    if item["kind"] == "image":
        args.update(params.get("ref_args") or {})
    return {"id": f"call_{item['id']}", "type": "function",
            "function": {"name": "generate_image" if item["kind"] == "image" else "generate_video",
                         "arguments": json.dumps(args)}}


def _history_tool_result(item: dict) -> dict:
    if item.get("status") == "error":
        return {"ok": False, "error": item.get("error") or "failed"}
    result: dict[str, Any] = {"ok": True, "result": IMAGE_TOOL_RESULT if item["kind"] == "image" else VIDEO_TOOL_RESULT}
    refs = (item.get("params") or {}).get("refs") or []
    if item["kind"] == "image" and refs:
        result["reference_images"] = len(refs)
    return result


def _media_note(item: dict) -> str:
    kind = item["kind"]
    if item.get("source") == "upload":
        return f"[user attached a {kind}]"
    state = {"done": f"generated {kind}", "pending": f"{kind} rendering", "error": f"{kind} failed"}[item["status"]]
    return f"[{state}: {item.get('prompt') or ''}]"


# ── Generation helpers (shared by turns and media retries) ──────────

_MODERATION = re.compile(
    r"moderat|flagged|content[ _-]?polic|safety|nsfw|sexual|prohibited|violat|inappropriate|"
    r"sensitive content|not allowed|blocked",
    re.IGNORECASE,
)


def _is_moderation_error(e: openrouter.OpenRouterError) -> bool:
    """OpenRouter's own moderation returns 403; providers phrase their
    content-policy refusals in many ways, so also match on the message.
    Pollo's 403 means "model not enabled for API access", so for Pollo only
    the message counts."""
    if isinstance(e, pollo_chat.PolloError):
        return bool(_MODERATION.search(str(e)))
    return e.status == 403 or bool(_MODERATION.search(str(e)))


def _failure_fields(e: openrouter.OpenRouterError) -> dict[str, Any]:
    return {"status": "error", "error": str(e), "moderated": _is_moderation_error(e)}


def _run_image_generation(conv_id: str, model: str, prompt: str, params: dict[str, Any],
                          context: list[dict] | None = None
                          ) -> tuple[list[str], float | None, int | None, dict[str, Any]]:
    """Generate and save images; returns (filenames, dollar cost, Pollo credits,
    the params actually sent — Pollo and Venice, defaults included — for display).
    With `context` (conversational models) the model gets the conversation;
    otherwise the Images API — or Pollo, or Venice — gets the prompt plus any reference images."""
    conv_dir = _conv_dir(conv_id)
    refs = [p for p in (_ref_file(conv_id, f) for f in params.get("refs") or []) if p.is_file()]
    if context is None:
        prompt = characters.with_characters(prompt, _param_characters(params))
    credits, sent = None, {}
    if venice_chat.is_venice(model):
        images, cost, sent = venice_chat.generate_image(model, prompt, aspect_ratio=params.get("aspect_ratio"),
                                                        resolution=params.get("resolution"), ref_paths=refs)
    elif pollo_chat.is_pollo(model):
        images, credits, sent = pollo_chat.generate_image(model, prompt, aspect_ratio=params.get("aspect_ratio"),
                                                    resolution=params.get("resolution"), ref_paths=refs)
        cost = None
    elif context is not None:
        images, cost = openrouter.generate_image_chat(model, context, aspect_ratio=params.get("aspect_ratio"),
                                                      session_id=conv_id)
    else:
        images, cost = openrouter.generate_image(
            model, prompt, aspect_ratio=params.get("aspect_ratio"), resolution=params.get("resolution"),
            input_images=[_file_to_data_url(f) for f in refs] or None, session_id=conv_id,
        )
    names = []
    for data, media_type in images:
        name = f"img_{uuid.uuid4().hex[:12]}{IMAGE_EXTS.get(media_type, '.png')}"
        (conv_dir / name).write_bytes(data)
        names.append(name)
    return names, cost, credits, sent


def _submit_video_generation(conv_id: str, model: str, prompt: str, params: dict[str, Any]) -> dict:
    frame = _ref_file(conv_id, params["first_frame"]) if params.get("first_frame") else None
    prompt = characters.with_characters(prompt, _param_characters(params))
    if venice_chat.is_venice(model):
        conv_dir = _conv_dir(conv_id)
        return venice_chat.submit_video(
            model, prompt, duration=params.get("duration"), aspect_ratio=params.get("aspect_ratio"),
            resolution=params.get("resolution"), generate_audio=params.get("generate_audio"),
            first_frame=frame,
            last_frame=_ref_file(conv_id, params["last_frame"]) if params.get("last_frame") else None,
            refs=[_ref_file(conv_id, r) for r in params.get("refs") or []],
            source_video=conv_dir / params["source_video"] if params.get("source_video") else None,
        )
    if pollo_chat.is_pollo(model):
        return pollo_chat.submit_video(
            model, prompt, duration=params.get("duration"), aspect_ratio=params.get("aspect_ratio"),
            resolution=params.get("resolution"), generate_audio=params.get("generate_audio"),
            first_frame=frame,
        )
    return openrouter.submit_video(
        model, prompt, duration=params.get("duration"), aspect_ratio=params.get("aspect_ratio"),
        resolution=params.get("resolution"), generate_audio=params.get("generate_audio"),
        first_frame=_file_to_data_url(frame) if frame else None,
        session_id=conv_id,
    )


def _add_message_cost(message_id: int, cost: float | None) -> None:
    if not cost:
        return
    db = get_db()
    msg = db.get_chat_message(message_id)
    if msg:
        db.update_chat_message(message_id, cost=round((msg.cost or 0) + float(cost), 6))


def _find_media(msg, media_id: str) -> dict | None:
    return next((i for i in msg.media if i.get("id") == media_id), None) if msg else None


class PinMedia(BaseModel):
    pinned: bool


@router.post("/messages/{message_id}/media/{media_id}/pin")
def api_pin_media(message_id: int, media_id: str, data: PinMedia):
    """Pin an image as a reference: it's sent with every image generated
    later on this branch of the chat, until unpinned."""
    db = get_db()
    msg = db.get_chat_message(message_id)
    item = _find_media(msg, media_id)
    if not item or item["kind"] != "image" or not item.get("file") or item.get("status", "done") != "done":
        raise HTTPException(404, "Image not found")
    return _message_out(db.update_chat_media_item(message_id, media_id, pinned=data.pinned))


class RegenerateMedia(BaseModel):
    model: str | None = None           # None = same model as the failed attempt


@router.post("/messages/{message_id}/media/{media_id}/regenerate")
def api_regenerate_media(message_id: int, media_id: str, data: RegenerateMedia):
    """Retry a failed image/video in place, optionally on a different model.
    Runs in the background; the UI polls the message like a rendering video."""
    _require_openrouter()
    db = get_db()
    msg = db.get_chat_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.status == "streaming":
        raise HTTPException(409, "Wait for the reply to finish first")
    item = _find_media(msg, media_id)
    if not item or item.get("source") != "generated":
        raise HTTPException(404, "Media not found")
    if item.get("status") != "error":
        raise HTTPException(400, "Only failed media can be retried")
    if not item.get("prompt"):
        raise HTTPException(400, "This item has no stored prompt to retry")
    model = data.model or item.get("model")
    msg = db.update_chat_media_item(message_id, media_id, status="pending", error=None,
                                    moderated=False, model=model, job_id=None)
    threading.Thread(target=_regenerate_worker, args=(msg.conversation_id, message_id, dict(item), model),
                     daemon=True, name=f"chat-regen-{media_id}").start()
    return _message_out(msg)


def _regenerate_worker(conv_id: str, message_id: int, item: dict, model: str) -> None:
    db = get_db()
    media_id = item["id"]
    params = dict(item.get("params") or {})
    try:
        if item["kind"] == "image":
            context = None
            if _is_conversational(model):
                msg = db.get_chat_message(message_id)
                history = _branch_to(db.get_chat_messages(conv_id), message_id)[:-1]
                direct = params.get("direct", False)
                context = _image_context(conv_id, history, params.get("history_limit"), msg.content if msg else "",
                                         None if direct else item["prompt"], params.get("refs") or [],
                                         _conversation_instructions(conv_id), _param_characters(params),
                                         params.get("image_limit", DEFAULT_IMAGE_LIMIT))
            params["context"] = context is not None
            names, cost, credits, sent = _run_image_generation(conv_id, model, item["prompt"], params, context)
            db.update_chat_media_item(message_id, media_id, status="done", file=names[0], cost=cost,
                                      credits=credits, params={**params, **sent})
            for extra in names[1:]:
                db.append_chat_media_item(message_id, _saved_media("image", "generated", extra,
                                                                   prompt=item["prompt"], model=model))
            _add_message_cost(message_id, cost)
        else:
            # A different model may support different durations/ratios
            params["duration"], params["aspect_ratio"], params["resolution"] = _fit_video_params(
                model, params.get("duration"), params.get("aspect_ratio"), params.get("resolution"))
            job = _submit_video_generation(conv_id, model, item["prompt"], params)
            db.update_chat_media_item(message_id, media_id, job_id=job["id"],
                                      params={**params, **job.get("params", {})})
            start_video_poller(conv_id, message_id, media_id, job["id"])
    except openrouter.OpenRouterError as e:
        db.update_chat_media_item(message_id, media_id, **_failure_fields(e))
    except Exception as e:  # noqa: BLE001 — never leave the card stuck on "pending"
        db.update_chat_media_item(message_id, media_id, status="error", error=f"{type(e).__name__}: {e}",
                                  moderated=False)


# ── Video polling ───────────────────────────────────────────────────

def start_video_poller(conv_id: str, message_id: int, media_id: str, job_id: str) -> None:
    threading.Thread(target=_poll_video, args=(conv_id, message_id, media_id, job_id),
                     daemon=True, name=f"chat-video-{media_id}").start()


def _poll_video(conv_id: str, message_id: int, media_id: str, job_id: str) -> None:
    db = get_db()
    source = (pollo_chat if pollo_chat.is_pollo_job(job_id)
              else venice_chat if venice_chat.is_venice_job(job_id) else openrouter)
    deadline = time.time() + VIDEO_POLL_TIMEOUT
    errors = 0
    while time.time() < deadline:
        time.sleep(VIDEO_POLL_INTERVAL)
        if not db.find_chat_media_item(message_id, media_id):
            return  # conversation deleted (items detached to the library are still updated)
        try:
            job = source.get_video(job_id)
            errors = 0
        except Exception as e:  # noqa: BLE001 — transient network/VPN hiccups
            errors += 1
            print(f"⚠️ chat video {job_id}: poll error {errors}/{VIDEO_MAX_POLL_ERRORS}: {e}")
            if errors >= VIDEO_MAX_POLL_ERRORS:
                db.update_chat_media_item(message_id, media_id, status="error", error=f"Polling failed: {e}")
                return
            continue

        status = job.get("status")
        if status == "completed":
            name = f"vid_{uuid.uuid4().hex[:12]}.mp4"
            try:
                source.download_video(job_id, _conv_dir(conv_id) / name)
            except Exception as e:  # noqa: BLE001
                db.update_chat_media_item(message_id, media_id, status="error", error=f"Download failed: {e}")
                return
            cost = (job.get("usage") or {}).get("cost")
            msg = db.update_chat_media_item(message_id, media_id, status="done", file=name, cost=cost,
                                            credits=job.get("credits"))
            if msg:
                _add_message_cost(message_id, cost)
            print(f"✅ chat video {job_id} saved as {name}")
            return
        if status in ("failed", "cancelled", "expired"):
            error = job.get("error") or f"Video {status}"
            db.update_chat_media_item(message_id, media_id, status="error", error=error,
                                      moderated=bool(_MODERATION.search(error)))
            return
    db.update_chat_media_item(message_id, media_id, status="error", error="Timed out waiting for video")


def startup_resume_chat() -> None:
    """Resume video pollers and fail turns orphaned by a restart."""
    db = get_db()
    resumed = 0
    for msg in db.get_chat_messages_with_pending_media():
        for item in msg.media:
            if item.get("status") != "pending":
                continue
            if item.get("job_id"):
                start_video_poller(msg.conversation_id, msg.id, item["id"], item["job_id"])
                resumed += 1
            else:
                db.update_chat_media_item(msg.id, item["id"], status="error", error="Interrupted by server restart")
    for lib in db.list_chat_library():
        item = lib.item
        if item.get("status") == "pending" and item.get("job_id"):
            # message_id 0 never exists, so updates go straight to the library row
            start_video_poller(lib.conversation_id, 0, item["id"], item["job_id"])
            resumed += 1
    for msg in db.get_chat_messages_by_status("streaming"):
        db.update_chat_message(msg.id, status="error", error="Interrupted by server restart")
    if resumed:
        print(f"🔄 Resumed polling for {resumed} chat video(s)")
