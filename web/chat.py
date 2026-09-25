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
      "prompt", "model", "job_id", "error", "cost": optional
    }

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
from img2vid.common.metadata import get_db

from . import openrouter
from .auth import verify_api_key

router = APIRouter(prefix="/api/chat", dependencies=[Depends(verify_api_key)])

MAX_TOOL_ROUNDS = 4
CONSISTENCY_REFS = 2              # recent images passed to the image model to keep characters consistent
MAX_HISTORY_IMAGES = 4            # most recent images (uploaded or generated) sent to the chat model as pixels
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024   # larger images are downscaled before sending
MODELS_CACHE_TTL = 30 * 60
CHAT_ROUND_SECONDS = 300          # cap on one LLM call (long stories stream for a while)
VIDEO_POLL_INTERVAL = 10
VIDEO_POLL_TIMEOUT = 45 * 60
VIDEO_MAX_POLL_ERRORS = 10
DEFAULT_TITLE = "New chat"

ALLOWED_UPLOAD_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
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
                                                   "image model as reference images. Default false."},
            },
            "required": ["prompt"],
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


class ConversationUpdate(BaseModel):
    title: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None


class TurnOptions(BaseModel):
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | None = None
    generate_audio: bool | None = None


class TurnSettings(BaseModel):
    mode: str = "auto"                 # auto | text | image | video
    history_limit: int | None = Field(default=None, ge=1)   # past messages sent to the chat model; None = all
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    options: TurnOptions = TurnOptions()


class SendMessage(TurnSettings):
    content: str = ""
    attachments: list[str] = []        # filenames returned by the attachments endpoint


class RetryMessage(TurnSettings):
    message_id: int                    # the assistant message to regenerate


class EditMessage(TurnSettings):
    message_id: int                    # the user message to rewrite and resend
    content: str


# ── Paths & media helpers ───────────────────────────────────────────

def _chat_root() -> Path:
    # Read config at call time so tests can redirect ROOT_DIR
    return config.ROOT_DIR / "chat"


def _conv_dir(conv_id: str) -> Path:
    d = _chat_root() / conv_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    safe = Path(name).name
    if not safe or safe != name or safe.startswith("."):
        raise HTTPException(400, "Invalid filename")
    return safe


def _new_media(kind: str, source: str, **fields) -> dict[str, Any]:
    return {"id": uuid.uuid4().hex[:8], "kind": kind, "source": source,
            "status": "pending", "file": None, **fields}


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


def _require_openrouter():
    if not openrouter.is_configured():
        raise HTTPException(503, "OPENROUTER_API_KEY is not set on the server")


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
            try:
                data[kind] = fn()
            except (openrouter.OpenRouterError, Exception) as e:  # noqa: BLE001 — surface any failure per-kind
                data[kind] = []
                data["errors"][kind] = str(e)
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
    return {"configured": openrouter.is_configured()}


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
    conv = get_db().create_conversation(
        title=(data.title or DEFAULT_TITLE).strip()[:255] or DEFAULT_TITLE,
        text_model=data.text_model, image_model=data.image_model, video_model=data.video_model,
    )
    return conv.to_dict()


@router.get("/conversations/{conv_id}")
def api_get_conversation(conv_id: str):
    conv = _require_conv(conv_id)
    return {"conversation": conv.to_dict(),
            "messages": [m.to_dict() for m in get_db().get_chat_messages(conv_id)]}


@router.patch("/conversations/{conv_id}")
def api_update_conversation(conv_id: str, data: ConversationUpdate):
    _require_conv(conv_id)
    fields = data.model_dump(exclude_unset=True)
    if "title" in fields:
        fields["title"] = (fields["title"] or "").strip()[:255] or DEFAULT_TITLE
    return get_db().update_conversation(conv_id, **fields).to_dict()


@router.delete("/conversations/{conv_id}")
def api_delete_conversation(conv_id: str):
    _require_conv(conv_id)
    get_db().delete_conversation(conv_id)
    shutil.rmtree(_chat_root() / conv_id, ignore_errors=True)
    return {"deleted": conv_id}


# ── Routes: media ───────────────────────────────────────────────────

@router.post("/conversations/{conv_id}/attachments")
async def api_upload_attachment(conv_id: str, file: UploadFile = File(...)):
    _require_conv(conv_id)
    ext = ALLOWED_UPLOAD_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Use PNG, JPEG, WebP or GIF.")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 20 MB)")
    try:
        Image.open(io.BytesIO(content)).verify()
    except Exception:
        raise HTTPException(400, "File is not a valid image")
    name = f"up_{uuid.uuid4().hex[:12]}{ext}"
    (_conv_dir(conv_id) / name).write_bytes(content)
    return {"file": name}


@router.get("/media/{conv_id}/{filename}")
def api_chat_media(conv_id: str, filename: str):
    path = _chat_root() / _safe_name(conv_id) / _safe_name(filename)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/library")
def api_chat_library():
    """Every generated image/video across chats, newest first. `attached`
    items are still in their chat; the rest were detached by an edit/retry."""
    db = get_db()
    titles = {c.id: c.title for c in db.list_conversations(limit=100000)}
    items = []
    for msg in db.get_chat_messages_with_media():
        for item in msg.media:
            if item.get("source") != "upload":
                items.append({**item, "conversation_id": msg.conversation_id, "message_id": msg.id,
                              "attached": True, "created_at": msg.created_at.isoformat()})
    for lib in db.list_chat_library():
        items.append({**lib.item, "conversation_id": lib.conversation_id, "message_id": None,
                      "attached": False, "created_at": lib.created_at.isoformat()})
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
        (_chat_root() / lib.conversation_id / _safe_name(lib.item["file"])).unlink(missing_ok=True)
    return {"deleted": media_id}


@router.get("/messages/{message_id}")
def api_get_message(message_id: int):
    msg = get_db().get_chat_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    return msg.to_dict()


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
        if not (conv_dir / _safe_name(name)).is_file():
            raise HTTPException(400, f"Attachment not found: {name}")
        media.append({**_new_media("image", "upload"), "status": "done", "file": name})

    db = get_db()
    user_msg = db.add_chat_message(conv_id, "user", content, media=media)
    _remember_models(conv, data)
    return _start_turn(conv_id, data, user_msg.to_dict())


@router.post("/conversations/{conv_id}/retry")
def api_retry(conv_id: str, data: RetryMessage):
    """Drop an assistant reply (and anything after it) and generate it again.
    Generated media from the dropped messages moves to the library."""
    _require_openrouter()
    conv = _require_conv(conv_id)
    _require_idle(conv_id)
    msg = get_db().get_chat_message(data.message_id)
    if not msg or msg.conversation_id != conv_id or msg.role != "assistant":
        raise HTTPException(400, "Can only retry an assistant message in this conversation")
    get_db().truncate_chat(conv_id, after_id=data.message_id - 1)
    _remember_models(conv, data)
    return _start_turn(conv_id, data, None)


@router.post("/conversations/{conv_id}/edit")
def api_edit(conv_id: str, data: EditMessage):
    """Rewrite a user message and resend it. Every later message is removed
    (its generated media moves to the library) and a fresh reply streams."""
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
    db.truncate_chat(conv_id, after_id=msg.id)
    user_msg = db.update_chat_message(msg.id, content=content)
    _remember_models(conv, data)
    return _start_turn(conv_id, data, user_msg.to_dict())


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


def _start_turn(conv_id: str, settings: TurnSettings, user_msg: dict | None) -> StreamingResponse:
    model = {"image": settings.image_model, "video": settings.video_model}.get(settings.mode, settings.text_model)
    assistant = get_db().add_chat_message(conv_id, "assistant", "", model=model, status="streaming")
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
        yield _sse({"type": "start", "user_message": user_msg, "assistant_message": assistant.to_dict()})
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
        self.history = [m for m in self.db.get_chat_messages(conv_id) if m.id != message_id]
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
        self.emit({"type": "done", "message": msg.to_dict() if msg else None})

    # ― explicit modes ―
    def _last_user(self):
        return next((m for m in reversed(self.history) if m.role == "user"), None)

    def _direct_image(self) -> None:
        user = self._last_user()
        prompt = (user.content if user else "").strip()
        if not prompt:
            raise openrouter.OpenRouterError("Image mode needs a text prompt")
        refs = [m["file"] for m in (user.media if user else []) if m["kind"] == "image" and m.get("file")]
        self._generate_image(prompt, self.s.options.aspect_ratio, refs)

    def _direct_video(self) -> None:
        user = self._last_user()
        prompt = (user.content if user else "").strip()
        frames = [m["file"] for m in (user.media if user else []) if m["kind"] == "image" and m.get("file")]
        if not prompt and not frames:
            raise openrouter.OpenRouterError("Video mode needs a prompt or an image")
        self._generate_video(prompt, self.s.options.duration, self.s.options.aspect_ratio,
                             frames[0] if frames else None)

    # ― chat with tools ―
    def _chat(self, tools_enabled: bool) -> None:
        if not self.s.text_model:
            raise openrouter.OpenRouterError("No text model selected")
        tools = []
        info = _model_info("text", self.s.text_model)
        if tools_enabled and (info is None or info.get("supports_tools")):
            if self.s.image_model:
                tools.append(TOOLS_IMAGE)
            if self.s.video_model:
                tools.append(TOOLS_VIDEO)
        vision = info is None or "image" in (info.get("input_modalities") or [])
        messages = self._build_llm_messages(vision, as_tool_calls=bool(tools))

        for round_no in range(MAX_TOOL_ROUNDS):
            # Last round: withhold tools so the loop can't run forever
            round_tools = (tools or None) if round_no < MAX_TOOL_ROUNDS - 1 else None
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
            # Otherwise the model gets the tool results and continues as it sees fit

    def _stream_round(self, messages: list[dict], tools: list[dict] | None) -> tuple[str, list[dict]]:
        """One chat completion, streamed to the UI."""
        text = ""
        calls: dict[int, dict] = {}
        finish = None
        if self.content and not self.content.endswith("\n\n"):
            self._append("\n\n")
        for chunk in openrouter.stream_chat(self.s.text_model, messages, tools, session_id=self.conv_id,
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
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return {"ok": False, "error": "prompt is required"}
        source = self._latest_image() if args.get("source_image") == "latest" else None
        if args.get("source_image") == "latest" and not source:
            return {"ok": False, "error": "There is no earlier image in the conversation to use"}
        # An explicit ratio picked in the composer beats the model's guess
        ratio = self.s.options.aspect_ratio or args.get("aspect_ratio")
        try:
            if name == "generate_image":
                self._generate_image(prompt, ratio, self._image_refs(args, source))
                return {"ok": True, "result": IMAGE_TOOL_RESULT}
            if name == "generate_video":
                duration = self.s.options.duration or args.get("duration")
                self._generate_video(prompt, duration, ratio, source)
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

    def _image_refs(self, args: dict, source: str | None) -> list[str]:
        """Reference images for generate_image, as the model asked for: the
        edit source (source_image) and/or the most recent images
        (keep_consistent). The app never adds references on its own."""
        refs = [source] if source else []
        info = _model_info("image", self.s.image_model)
        if info and "image" not in (info.get("input_modalities") or []):
            return []  # this image model can't take references
        keep = args.get("keep_consistent") is True

        if keep:
            for f in self._latest_images(CONSISTENCY_REFS):
                if f not in refs:
                    refs.append(f)
        return refs[:max(CONSISTENCY_REFS, 1)]

    # ― generation ―
    def _add_media(self, item: dict) -> None:
        self.media.append(item)
        self.db.append_chat_media_item(self.message_id, item)
        self.emit({"type": "media", "message_id": self.message_id, "item": dict(item)})

    def _update_media(self, item: dict, **fields) -> None:
        item.update(fields)
        self.db.update_chat_media_item(self.message_id, item["id"], **fields)
        self.emit({"type": "media", "message_id": self.message_id, "item": dict(item)})

    def _generate_image(self, prompt: str, aspect_ratio: str | None, ref_files: list[str]) -> None:
        if not self.s.image_model:
            raise openrouter.OpenRouterError("No image model selected")
        # Params are stored on the item so a failed image can be retried as-is
        params = {"aspect_ratio": aspect_ratio,
                  "resolution": self.s.options.resolution if self.s.mode == "image" else None,
                  "refs": ref_files}
        context = None
        if _is_conversational(self.s.image_model):
            # Like the Gemini app: the image model gets the conversation
            direct = self.s.mode == "image"
            params.update(context=True, direct=direct, history_limit=self.s.history_limit)
            context = _image_context(self.conv_id, self.history, self.s.history_limit, self.content,
                                     None if direct else prompt, ref_files)
        item = _new_media("image", "generated", prompt=prompt, model=self.s.image_model, params=params)
        self._add_media(item)
        try:
            names, cost = _run_image_generation(self.conv_id, self.s.image_model, prompt, params, context)
        except openrouter.OpenRouterError as e:
            self._update_media(item, **_failure_fields(e))
            raise
        if cost:
            self.cost += float(cost)
        for i, name in enumerate(names):
            if i == 0:
                self._update_media(item, status="done", file=name, cost=cost)
            else:
                self._add_media({**_new_media("image", "generated", prompt=prompt, model=self.s.image_model),
                                 "status": "done", "file": name})

    def _generate_video(self, prompt: str, duration: int | None, aspect_ratio: str | None,
                        first_frame: str | None) -> None:
        if not self.s.video_model:
            raise openrouter.OpenRouterError("No video model selected")
        duration, aspect_ratio, resolution = _fit_video_params(
            self.s.video_model, duration, aspect_ratio, self.s.options.resolution if self.s.mode == "video" else None)
        params = {"duration": duration, "aspect_ratio": aspect_ratio, "resolution": resolution,
                  "first_frame": first_frame, "generate_audio": self.s.options.generate_audio}
        item = _new_media("video", "generated", prompt=prompt, model=self.s.video_model, params=params)
        self._add_media(item)
        try:
            job = _submit_video_generation(self.conv_id, self.s.video_model, prompt, params)
        except openrouter.OpenRouterError as e:
            self._update_media(item, **_failure_fields(e))
            raise
        self._update_media(item, job_id=job["id"])
        start_video_poller(self.conv_id, self.message_id, item["id"], job["id"])

    # ― history → OpenRouter messages ―
    def _build_llm_messages(self, vision: bool, as_tool_calls: bool = False) -> list[dict]:
        return [{"role": "system", "content": SYSTEM_PROMPT.format(today=datetime.now().strftime("%A %d %B %Y"))},
                *_conversation(self.conv_id, self.history, self.s.history_limit, vision, as_tool_calls)]

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
                  as_tool_calls: bool = False) -> list[dict]:
    """The chat history as OpenRouter messages (no system prompt): the last
    `history_limit` messages, with the most recent images as pixels.
    Shared by the chat model and conversational image models.

    `as_tool_calls` (only when tools are offered — providers reject tool
    calls otherwise) records generated media as the tool calls and results
    that produced it; without it, media is summarised in bracketed notes."""
    messages: list[dict] = []

    history = _history_window(history, history_limit)

    # The most recent few images — uploaded or generated — go over as
    # pixels so the model can see what's actually in them; older ones
    # are described by a note instead.
    image_budget = MAX_HISTORY_IMAGES if vision else 0
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
                   prompt: str | None, refs: list[str]) -> list[dict]:
    """What a conversational image model is sent: the conversation, then —
    when the chat model called the tool — its reply so far and its prompt,
    verbatim, with any reference images it asked for. In Image mode
    (prompt=None) the user's own message is already the last one."""
    messages = _conversation(conv_id, history, history_limit, vision=True)
    if prompt is not None:
        if reply_text.strip():
            messages.append({"role": "assistant", "content": reply_text.strip()})
        conv_dir = _conv_dir(conv_id)
        parts: list[dict] = [{"type": "text", "text": prompt}]
        parts += [{"type": "image_url", "image_url": {"url": _file_to_data_url(conv_dir / f)}}
                  for f in refs if (conv_dir / f).is_file()]
        messages.append({"role": "user", "content": parts})
    return messages


def _is_conversational(image_model: str | None) -> bool:
    info = _model_info("image", image_model)
    return bool(info and info.get("conversational"))


def _history_tool_call(item: dict) -> dict:
    args: dict[str, Any] = {"prompt": item["prompt"]}
    ratio = (item.get("params") or {}).get("aspect_ratio")
    if ratio:
        args["aspect_ratio"] = ratio
    return {"id": f"call_{item['id']}", "type": "function",
            "function": {"name": "generate_image" if item["kind"] == "image" else "generate_video",
                         "arguments": json.dumps(args)}}


def _history_tool_result(item: dict) -> dict:
    if item.get("status") == "error":
        return {"ok": False, "error": item.get("error") or "failed"}
    return {"ok": True, "result": IMAGE_TOOL_RESULT if item["kind"] == "image" else VIDEO_TOOL_RESULT}


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
    content-policy refusals in many ways, so also match on the message."""
    return e.status == 403 or bool(_MODERATION.search(str(e)))


def _failure_fields(e: openrouter.OpenRouterError) -> dict[str, Any]:
    return {"status": "error", "error": str(e), "moderated": _is_moderation_error(e)}


def _run_image_generation(conv_id: str, model: str, prompt: str, params: dict[str, Any],
                          context: list[dict] | None = None) -> tuple[list[str], float | None]:
    """Generate and save images; returns (filenames, cost). With `context`
    (conversational models) the model gets the conversation; otherwise the
    Images API gets the prompt plus any reference images."""
    conv_dir = _conv_dir(conv_id)
    if context is not None:
        images, cost = openrouter.generate_image_chat(model, context, aspect_ratio=params.get("aspect_ratio"),
                                                      session_id=conv_id)
    else:
        refs = [conv_dir / f for f in params.get("refs") or [] if (conv_dir / f).is_file()]
        images, cost = openrouter.generate_image(
            model, prompt, aspect_ratio=params.get("aspect_ratio"), resolution=params.get("resolution"),
            input_images=[_file_to_data_url(f) for f in refs] or None, session_id=conv_id,
        )
    names = []
    for data, media_type in images:
        name = f"img_{uuid.uuid4().hex[:12]}{IMAGE_EXTS.get(media_type, '.png')}"
        (conv_dir / name).write_bytes(data)
        names.append(name)
    return names, cost


def _submit_video_generation(conv_id: str, model: str, prompt: str, params: dict[str, Any]) -> dict:
    first_frame = params.get("first_frame")
    return openrouter.submit_video(
        model, prompt, duration=params.get("duration"), aspect_ratio=params.get("aspect_ratio"),
        resolution=params.get("resolution"), generate_audio=params.get("generate_audio"),
        first_frame=_file_to_data_url(_conv_dir(conv_id) / first_frame) if first_frame else None,
        session_id=conv_id,
    )


def _add_message_cost(message_id: int, cost: float | None) -> None:
    if not cost:
        return
    db = get_db()
    msg = db.get_chat_message(message_id)
    if msg:
        db.update_chat_message(message_id, cost=round((msg.cost or 0) + float(cost), 6))


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
    item = next((i for i in msg.media if i.get("id") == media_id), None)
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
    return msg.to_dict()


def _regenerate_worker(conv_id: str, message_id: int, item: dict, model: str) -> None:
    db = get_db()
    media_id = item["id"]
    params = dict(item.get("params") or {})
    try:
        if item["kind"] == "image":
            context = None
            if _is_conversational(model):
                msg = db.get_chat_message(message_id)
                history = [m for m in db.get_chat_messages(conv_id) if m.id < message_id]
                direct = params.get("direct", False)
                context = _image_context(conv_id, history, params.get("history_limit"), msg.content if msg else "",
                                         None if direct else item["prompt"], params.get("refs") or [])
            params["context"] = context is not None
            names, cost = _run_image_generation(conv_id, model, item["prompt"], params, context)
            db.update_chat_media_item(message_id, media_id, status="done", file=names[0], cost=cost,
                                      params=params)
            for extra in names[1:]:
                db.append_chat_media_item(message_id, {**_new_media("image", "generated", prompt=item["prompt"],
                                                                    model=model), "status": "done", "file": extra})
            _add_message_cost(message_id, cost)
        else:
            # A different model may support different durations/ratios
            params["duration"], params["aspect_ratio"], params["resolution"] = _fit_video_params(
                model, params.get("duration"), params.get("aspect_ratio"), params.get("resolution"))
            job = _submit_video_generation(conv_id, model, item["prompt"], params)
            db.update_chat_media_item(message_id, media_id, job_id=job["id"], params=params)
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
    deadline = time.time() + VIDEO_POLL_TIMEOUT
    errors = 0
    while time.time() < deadline:
        time.sleep(VIDEO_POLL_INTERVAL)
        if not db.find_chat_media_item(message_id, media_id):
            return  # conversation deleted (edit/retry moves the item to the library, which we still update)
        try:
            job = openrouter.get_video(job_id)
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
                openrouter.download_video(job_id, _conv_dir(conv_id) / name)
            except Exception as e:  # noqa: BLE001
                db.update_chat_media_item(message_id, media_id, status="error", error=f"Download failed: {e}")
                return
            cost = (job.get("usage") or {}).get("cost")
            msg = db.update_chat_media_item(message_id, media_id, status="done", file=name, cost=cost)
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
