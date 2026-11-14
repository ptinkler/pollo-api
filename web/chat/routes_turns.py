"""HTTP routes for running turns and managing generated media.

Turn, retry, and edit responses stream events from a worker; the engine lives
in `turn.py` and generation helpers live in `generation.py`.
"""

import json
import queue
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping
from typing import Any, cast

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from web.chat import polling
from web.chat.audio import audio_params, submit_audio_generation
from web.chat.catalogue import fit_video_params, model_info
from web.chat.constants import DEFAULT_IMAGE_LIMIT
from web.chat.deps import router
from web.chat.generation import (
    conversation_instructions,
    enhance_prompt,
    exchange_fields,
    failure_fields,
    image_context,
    is_conversational,
    param_characters,
    run_image_generation,
    submit_video_generation,
    take_log,
)
from web.chat.helpers import (
    add_message_cost,
    branch_to,
    conversation_dir,
    find_media,
    message_out,
    remember_settings,
    require_conv,
    require_idle,
    require_text_provider,
    saved_media,
)
from web.chat.models import EditMessage, EnhancePrompt, EstimateRequest, RetryMessage, SendMessage, TurnSettings
from web.chat.turn import Turn
from web.chat.workers import ctx_thread, with_owner_keys
from web.core.metadata import get_db, iso
from web.core.metadata.models import ChatMessage
from web.media_types import kind_of
from web.providers import openrouter, pollo
from web.types import JsonValue
from web.uploads import safe_filename

# Live turns' cancel flags, keyed by the assistant message id (set by the
# cancel route, checked by the running Turn).
_cancel_events: dict[int, threading.Event] = {}

# Starting a turn checks that the chat is idle and then marks a reply as
# streaming; a media retry checks its card isn't already running and then
# marks it pending. Each is a check-then-act, and FastAPI runs these routes on
# a thread pool — so a double click (or two tabs) could slip both requests
# past the check and pay twice. One lock makes each check-and-mark atomic.
_start_lock = threading.Lock()


@router.post("/enhance-prompt")
def api_enhance_prompt(data: EnhancePrompt) -> dict[str, str | float]:
    """Rewrite a prompt with the chat model.

    Only ever called by the user's
    Enhance button — generations themselves always use the prompt as written.
    """
    try:
        prompt, cost = enhance_prompt(data.model, data.prompt, "video" if data.kind == "video" else "image")
    except (openrouter.OpenRouterError, ValueError) as e:
        raise HTTPException(502, str(e)) from e
    return {"prompt": prompt, "cost": cost}


@router.post("/estimate")
def api_estimate(data: EstimateRequest) -> dict[str, Any]:
    """Estimate a Pollo generation's credit cost for the composer.

    Returns a null estimate for other providers or when Pollo cannot price it.
    """
    if not pollo.is_pollo(data.model):
        return {"estimate": None}
    duration, ratio, resolution = data.duration, data.aspect_ratio, data.resolution
    if data.kind == "video":
        duration, ratio, resolution = fit_video_params(data.model, duration, ratio, resolution)
    return {
        "estimate": pollo.estimate_cost(
            data.model,
            data.kind if data.kind in ("video", "audio") else "image",
            duration,
            ratio,
            resolution,
            data.generate_audio,
            data.n_images,
            data.prompt,
            audio_params(data.audio_options),
        )
    }


@router.get("/audio/voices")
def api_audio_voices(page: int = 1, page_size: int = 50, language: str = "", gender: str = "") -> dict[str, Any]:
    """Pollo's official TTS voices, for the speech models' voice picker."""
    if not pollo.is_configured():
        raise HTTPException(503, "No Pollo API key set — add one in Settings → Keys")
    try:
        return pollo.list_voices(page, min(page_size, 100), language=language, gender=gender)
    except openrouter.OpenRouterError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/messages/{message_id}/cancel")
def api_cancel_message(message_id: int) -> dict[str, bool]:
    """Request cancellation of a running assistant message."""
    ev = _cancel_events.get(message_id)
    if ev:
        ev.set()
    return {"cancelled": bool(ev)}


def _prompt_optional(settings: TurnSettings) -> bool:
    """Tools take a source file and no prompt (e.g. upscale the chat's latest video)."""
    kind = settings.mode if settings.mode in ("image", "video") else None
    model = {"image": settings.image_model, "video": settings.video_model}.get(kind)
    return bool((model_info(kind, model) or {}).get("no_prompt")) if kind else False


@router.post("/conversations/{conv_id}/messages")
def api_send_message(conv_id: str, data: SendMessage) -> StreamingResponse:
    """Create a user message and stream its assistant turn."""
    require_text_provider(data.mode)
    conv = require_conv(conv_id)
    content = data.content.strip()
    if not content and not data.attachments and not _prompt_optional(data):
        raise HTTPException(400, "Message is empty")

    conv_dir = conversation_dir(conv_id)
    media = []
    for name in data.attachments[:8]:
        if not (conv_dir / safe_filename(name)).is_file():
            raise HTTPException(400, f"Attachment not found: {name}")
        # audio here is a lip-sync track, driven onto a portrait
        media.append(saved_media(kind_of(name) or "image", "upload", name))

    db = get_db()
    lane = "gallery" if data.lane == "gallery" else None
    with _start_lock:
        # One reply at a time in the chat (gallery exchanges run side by side):
        # a second send while one streams would be a double charge, and its
        # reply would be written against a half-finished history.
        require_idle(conv_id, lane)
        user_msg = db.add_chat_message(conv_id, "user", content, media=media, mode=data.mode, lane=lane)
        remember_settings(conv, data)
        return _start_turn(conv_id, data, user_msg, parent_id=user_msg.id, lane=lane)


@router.post("/conversations/{conv_id}/retry")
def api_retry(conv_id: str, data: RetryMessage) -> StreamingResponse:
    """Generate another version of an assistant reply, as a new branch beside it.

    The old reply and everything after it stay on their branch.
    """
    require_text_provider(data.mode)
    conv = require_conv(conv_id)
    msg = get_db().get_chat_message(data.message_id)
    if not msg or msg.conversation_id != conv_id or msg.role != "assistant":
        raise HTTPException(400, "Can only retry an assistant message in this conversation")
    with _start_lock:
        require_idle(conv_id, msg.lane)
        # The retry runs in the mode selected now; the prompt's mode tag follows it
        if msg.parent_id:
            get_db().update_chat_message(msg.parent_id, mode=data.mode)
        remember_settings(conv, data)
        return _start_turn(conv_id, data, None, parent_id=msg.parent_id, lane=msg.lane)


@router.post("/conversations/{conv_id}/edit")
def api_edit(conv_id: str, data: EditMessage) -> StreamingResponse:
    """Resend a user message with new text, as a new branch beside it (same attachments), and stream a fresh reply.

    The original prompt and
    everything after it stay on their branch.
    """
    require_text_provider(data.mode)
    conv = require_conv(conv_id)
    db = get_db()
    msg = db.get_chat_message(data.message_id)
    if not msg or msg.conversation_id != conv_id or msg.role != "user":
        raise HTTPException(400, "Can only edit a user message in this conversation")
    content = data.content.strip()
    if not content and not msg.media:
        raise HTTPException(400, "Message is empty")
    media = [{**item, "id": uuid.uuid4().hex[:8]} for item in msg.media]
    with _start_lock:
        require_idle(conv_id, msg.lane)
        user_msg = db.add_chat_message(
            conv_id, "user", content, media=media, parent_id=msg.parent_id, mode=data.mode, lane=msg.lane
        )
        remember_settings(conv, data)
        return _start_turn(conv_id, data, user_msg, parent_id=user_msg.id, lane=msg.lane)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _start_turn(
    conv_id: str, settings: TurnSettings, user_msg: ChatMessage | None, parent_id: int | None, lane: str | None = None
) -> StreamingResponse:
    model = {"image": settings.image_model, "video": settings.video_model, "audio": settings.audio_model}.get(
        settings.mode, settings.text_model
    )
    assistant = get_db().add_chat_message(
        conv_id, "assistant", "", model=model, status="streaming", parent_id=parent_id, mode=settings.mode, lane=lane
    )
    start = {
        "type": "start",
        "user_message": message_out(user_msg) if user_msg else None,
        "assistant_message": message_out(assistant),
    }
    return _stream_turn(conv_id, settings, assistant.id, start)


def _stream_turn(
    conv_id: str,
    settings: TurnSettings,
    assistant_id: int,
    start: dict[str, Any],
    initial_cost: float = 0.0,
    rewrite: tuple[str, str] | None = None,
    after: Callable[[], ChatMessage | None] | None = None,
) -> StreamingResponse:
    """Run a Turn against `assistant_id` and stream its events as SSE.

    Used
    both for a brand-new reply and for generating an existing one again.

    `after` runs once the Turn has finished and saved; if it returns a message
    that goes out as a final "done", so the UI ends on its state.
    """
    events: queue.Queue = queue.Queue()
    cancel = threading.Event()
    _cancel_events[assistant_id] = cancel

    def worker() -> None:
        try:
            Turn(conv_id, settings, assistant_id, events.put, cancel, initial_cost=initial_cost, rewrite=rewrite).run()
            if after and (msg := after()):
                events.put({"type": "done", "message": message_out(msg)})
        finally:
            _cancel_events.pop(assistant_id, None)
            events.put(None)

    # Run in a copy of the current context so the turn's DB writes/reads are
    # scoped to the signed-in user (tenant) and use their keys — a plain thread
    # would not inherit those contextvars.
    ctx_thread(worker, name=f"chat-turn-{assistant_id}").start()

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

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


class RewordMessage(TurnSettings):
    """Turn settings and assistant message ID for regenerating only its text."""

    message_id: int  # the assistant reply whose words to generate again
    # Edit text: how to change the words ("shorter", "make it rhyme"). Empty =
    # Redo text: write them again from the conversation alone.
    instruction: str = ""


def _text_versions_json(items: list[dict[str, JsonValue]], shown: int) -> str:
    return json.dumps({"items": items, "shown": shown})


@router.post("/conversations/{conv_id}/reword")
def api_reword(conv_id: str, data: RewordMessage) -> StreamingResponse:
    """Write this reply's words again, keeping the pictures it already made.

    Unlike Retry, which starts a whole new turn on a new branch (new words AND
    new media), this re-runs only the chat model, with its tools withheld, and
    overwrites the text on the same message. The media items are left exactly
    as they are, so a reply whose picture is right but whose words aren't can
    be fixed without paying for the picture again.
    """
    require_text_provider("text")
    conv = require_conv(conv_id)
    db = get_db()
    msg = db.get_chat_message(data.message_id)
    if not msg or msg.conversation_id != conv_id or msg.role != "assistant":
        raise HTTPException(400, "Can only reword an assistant message in this conversation")
    if msg.status == "streaming":
        raise HTTPException(409, "Wait for the reply to finish first")
    if any(i.get("status") == "pending" for i in msg.media):
        raise HTTPException(409, "Wait for this reply's media to finish first")
    instruction = data.instruction.strip()
    previous = msg.content or ""
    if instruction and not previous.strip():
        raise HTTPException(400, "This reply has no words to edit yet")
    # Only the words are generated again, whatever mode the composer is in.
    settings = data.model_copy(update={"mode": "text"})
    # The words being replaced were paid for too (and stay as a version you
    # can switch back to), so the reply's cost keeps everything spent on it.
    spent = msg.cost or 0.0
    items: list[dict[str, JsonValue]] = msg.text_versions[0]
    if not items:  # first rewrite: the words it has become version 1
        items = [{"content": previous, "model": msg.model}]
    message_id = msg.id

    def after() -> ChatMessage | None:
        """File the new words as the latest version — or, if none came, put the old ones back."""
        done = db.get_chat_message(message_id)
        if not done:
            return None
        if not (done.content or "").strip():
            return db.update_chat_message(message_id, content=previous)
        versions: list[dict[str, JsonValue]] = [*items, {"content": done.content, "model": settings.text_model}]
        return db.update_chat_message(message_id, text_versions_json=_text_versions_json(versions, len(versions) - 1))

    with _start_lock:
        require_idle(conv_id, msg.lane)
        if (db.get_chat_message(message_id) or msg).status == "streaming":
            raise HTTPException(409, "Wait for the reply to finish first")
        remember_settings(conv, data)
        db.update_chat_message(message_id, content="", status="streaming", error=None)
        start = {"type": "start", "user_message": None, "assistant_message": message_out(msg), "replaces": msg.id}
        start["assistant_message"] = {**start["assistant_message"], "content": "", "status": "streaming"}
        return _stream_turn(
            conv_id,
            settings,
            message_id,
            start,
            initial_cost=spent,
            rewrite=(previous, instruction) if instruction else None,
            after=after,
        )


class ShowTextVersion(BaseModel):
    """Which of a reply's wordings to show (0 = the first)."""

    index: int


@router.post("/messages/{message_id}/text-version")
def api_show_text_version(message_id: int, data: ShowTextVersion) -> dict[str, Any]:
    """Switch a reply to one of its earlier (or later) wordings.

    The chosen words become the reply's text — what's shown and what the chat
    model sees from then on. Its pictures are untouched; nothing is generated.
    """
    db = get_db()
    msg = db.get_chat_message(message_id)
    if not msg or msg.role != "assistant":
        raise HTTPException(404, "Message not found")
    if msg.status == "streaming":
        raise HTTPException(409, "Wait for the reply to finish first")
    items, _ = msg.text_versions
    if not 0 <= data.index < len(items):
        raise HTTPException(400, "No such version")
    content = items[data.index]["content"]
    updated = db.update_chat_message(
        message_id,
        content=content if isinstance(content, str) else "",
        text_versions_json=_text_versions_json(items, data.index),
    )
    if not updated:
        raise HTTPException(404, "Message not found")
    return message_out(updated)


class PinMedia(BaseModel):
    """Requested pin state for an image."""

    pinned: bool


@router.post("/messages/{message_id}/media/{media_id}/pin")
def api_pin_media(message_id: int, media_id: str, data: PinMedia) -> dict[str, Any]:
    """Pin an image as a reference: it's sent with every image generated.

    later on this branch of the chat, until unpinned.
    """
    db = get_db()
    msg = db.get_chat_message(message_id)
    item = find_media(msg, media_id)
    if not item or item["kind"] != "image" or not item.get("file") or item.get("status", "done") != "done":
        raise HTTPException(404, "Image not found")
    return message_out(db.update_chat_media_item(message_id, media_id, pinned=data.pinned))


class FavouriteMedia(BaseModel):
    """Requested favourite state for a media item."""

    favourite: bool


@router.post("/messages/{message_id}/media/{media_id}/favourite")
def api_favourite_media(message_id: int, media_id: str, data: FavouriteMedia) -> dict[str, Any]:
    """Star/un-star a generation.

    Unlike pinning (which re-sends an image as a
    reference with every new generation), a favourite is just a bookmark: it
    surfaces the item in the cross-thread Favourites gallery. Works for images
    and videos.
    """
    db = get_db()
    msg = db.get_chat_message(message_id)
    item = find_media(msg, media_id)
    if not item or not item.get("file") or item.get("status", "done") != "done":
        raise HTTPException(404, "Generation not found")
    return message_out(db.update_chat_media_item(message_id, media_id, favourite=data.favourite))


class RegenerateMedia(BaseModel):
    """Optional model, prompt, and replacement behavior for a media retry."""

    model: str | None = None  # None = same model as the failed attempt
    prompt: str | None = None  # None = the prompt it was made with
    # Edit: send the image itself back as the reference, so the model changes
    # this picture instead of making a new one from the prompt alone.
    edit: bool = False
    # Replace the item rather than adding a new one beside it: the picture it
    # had moves into `versions`, so nothing is lost and the card can flip back.
    replace: bool = False


# A card's pictures: the live one is the item's own fields; the others are in
# `versions`, and `version_shown` is where the live one sits among them all
# (missing = last). Whichever is showing is the real one — what the chat sends
# as context and references, pins, downloads — so the arrows swap it in.
VERSION_FIELDS = ("file", "prompt", "model", "cost", "credits", "params", "request", "response")


def _all_versions(item: Mapping[str, JsonValue]) -> tuple[list[dict[str, JsonValue]], int]:
    """Every picture the card has had, in order, and which is live (None-file live ones left out)."""
    raw = item.get("versions")
    versions = [v for v in (raw if isinstance(raw, list) else []) if isinstance(v, dict)]
    shown = item.get("version_shown")
    at = (
        shown
        if isinstance(shown, int) and not isinstance(shown, bool) and 0 <= shown <= len(versions)
        else len(versions)
    )
    live = [_as_version(item)] if item.get("file") else []
    return [*versions[:at], *live, *versions[at:]], at


def _spent(item: Mapping[str, JsonValue]) -> list[JsonValue]:
    """Charges of failed attempts the card no longer shows (Pollo bills those too), so spend keeps them."""
    raw = item.get("spent")
    spent: list[JsonValue] = list(raw) if isinstance(raw, list) else []
    if not item.get("file") and (item.get("cost") or item.get("credits")):
        spent.append({"cost": item.get("cost"), "credits": item.get("credits")})
    return spent


def _as_version(item: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """What a card keeps about a picture it has replaced."""
    return {k: item[k] for k in VERSION_FIELDS if item.get(k) is not None}


@router.post("/messages/{message_id}/media/{media_id}/regenerate")
def api_regenerate_media(message_id: int, media_id: str, data: RegenerateMedia) -> dict[str, Any]:
    """Retry or re-roll a generated image or video.

    The retry runs in the background while the UI polls the message.
    """
    with _start_lock:
        return _regenerate_media(message_id, media_id, data)


def _regenerate_media(message_id: int, media_id: str, data: RegenerateMedia) -> dict[str, Any]:
    db = get_db()
    msg = db.get_chat_message(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.status == "streaming":
        raise HTTPException(409, "Wait for the reply to finish first")
    item = find_media(msg, media_id)
    if not item or item.get("source") != "generated":
        raise HTTPException(404, "Media not found")
    if item.get("status") not in ("error", "done"):
        raise HTTPException(400, "Wait for the generation to finish first")
    prompt = (data.prompt or "").strip() or item.get("prompt")
    if not prompt:
        raise HTTPException(400, "This item has no stored prompt to retry")
    if data.edit and not item.get("file"):
        raise HTTPException(400, "There is no picture here to edit yet")
    model = data.model or item.get("model")
    params = dict(item.get("params") or {})
    if data.edit:
        # The picture being edited leads the reference list; the references it
        # was itself made from are dropped, so the model edits this one image.
        params["refs"] = [item["file"], *(r for r in params.get("refs") or [] if str(r).startswith("char:"))]
    if data.replace:
        # Keep what it looked like before, then clear the result fields so the
        # worker fills them in on the same item. A failed attempt has no
        # picture to keep, so retrying one adds no version to flip back to.
        # The new picture goes last, whichever one was showing.
        versions, _ = _all_versions(item)
        spent = _spent(item)
        blank = dict.fromkeys(("file", "cost", "credits", "error", "job_id", "request", "response"))
        item = {**item, **blank, "status": "pending", "model": model, "prompt": prompt, "params": params}
        item.update(versions=versions, version_shown=len(versions), spent=spent)
        msg = db.update_chat_media_item(
            message_id,
            media_id,
            **{
                k: item[k]
                for k in (*blank, "status", "model", "prompt", "params", "versions", "version_shown", "spent")
            },
            moderated=False,
        )
    elif item["status"] == "done":
        # Re-roll just this image/video: the original stays, a new one joins the reply
        gone = (
            "file",
            "cost",
            "credits",
            "error",
            "job_id",
            "favourite",
            "pinned",
            "log",
            "versions",
            "version_shown",
            "spent",
        )
        item = {k: v for k, v in item.items() if k not in gone}
        item = {
            **item,
            "id": uuid.uuid4().hex[:8],
            "status": "pending",
            "model": model,
            "prompt": prompt,
            "params": params,
        }
        media_id = item["id"]
        msg = db.append_chat_media_item(message_id, item)
    else:
        item = {**item, "prompt": prompt, "params": params, "model": model}
        msg = db.update_chat_media_item(
            message_id,
            media_id,
            status="pending",
            error=None,
            moderated=False,
            model=model,
            job_id=None,
            prompt=prompt,
            params=params,
        )
    threading.Thread(
        target=_regenerate_worker,
        args=(msg.conversation_id, message_id, dict(item), model),
        daemon=True,
        name=f"chat-regen-{media_id}",
    ).start()
    return message_out(msg)


class ShowMediaVersion(BaseModel):
    """Which of a card's pictures to make the live one (0 = the first)."""

    index: int


@router.post("/messages/{message_id}/media/{media_id}/version")
def api_show_media_version(message_id: int, media_id: str, data: ShowMediaVersion) -> dict[str, JsonValue]:
    """Make one of a card's pictures the real one.

    It becomes the item's file, prompt, model and settings — what the chat
    sends from then on — and the one that was live becomes a version. Nothing
    is generated; what each cost stays counted.
    """
    with _start_lock:
        db = get_db()
        msg = db.get_chat_message(message_id)
        if not msg:
            raise HTTPException(404, "Message not found")
        if msg.status == "streaming":
            raise HTTPException(409, "Wait for the reply to finish first")
        item = find_media(msg, media_id)
        if not item:
            raise HTTPException(404, "Media not found")
        if item.get("status") == "pending":
            raise HTTPException(409, "Wait for the generation to finish first")
        versions, _ = _all_versions(item)
        if not 0 <= data.index < len(versions):
            raise HTTPException(400, "No such version")
        chosen = versions.pop(data.index)
        fields: dict[str, JsonValue] = {k: chosen.get(k) for k in VERSION_FIELDS}
        updated = db.update_chat_media_item(
            message_id,
            media_id,
            **fields,
            status="done",
            error=None,
            moderated=False,
            versions=cast("JsonValue", versions),
            version_shown=data.index,
            spent=_spent(item),
        )
        if not updated:
            raise HTTPException(404, "Message not found")
        return message_out(updated)


class ActiveQuery(BaseModel):
    """Message IDs whose generation state the client still tracks."""

    # Message ids the client is already tracking, so finished/failed ones get
    # their final status back even though they've dropped out of the pending set.
    known: list[int] = []


def _gen_descriptor(msg: ChatMessage, item: dict[str, Any], title: str) -> dict[str, Any]:
    return {
        "media_id": item["id"],
        "message_id": msg.id,
        "conversation_id": msg.conversation_id,
        "conversation_title": title,
        "kind": item.get("kind"),
        "prompt": item.get("prompt"),
        "model": item.get("model") or msg.model,
        "status": item.get("status"),
        "file": item.get("file"),
        "error": item.get("error"),
        "moderated": bool(item.get("moderated")),
        "created_at": iso(msg.created_at),
    }


@router.post("/generations/active")
def api_active_generations(data: ActiveQuery) -> dict[str, list[dict[str, Any]]]:
    """List pending generations and the final states of tracked messages.

    Results cover all of the signed-in user's conversations. `known` IDs let
    the client resolve completions that have left the pending set.
    """
    db = get_db()
    msgs: dict[int, object] = {m.id: m for m in db.get_chat_messages_with_pending_media()}
    for m in db.get_chat_messages_by_ids([i for i in data.known if i not in msgs]):
        msgs.setdefault(m.id, m)
    titles: dict[str, str] = {}
    items: list[dict] = []
    seen: set[str] = set()
    for m in msgs.values():
        for item in m.media:
            if item.get("source") != "generated" or item.get("kind") not in ("image", "video", "audio"):
                continue
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            cid = m.conversation_id
            if cid not in titles:
                conv = db.get_conversation(cid)
                titles[cid] = conv.title if conv else ""
            items.append(_gen_descriptor(m, item, titles[cid]))
    return {"items": items}


@with_owner_keys
def _regenerate_worker(conv_id: str, message_id: int, item: Mapping[str, JsonValue], model: str) -> None:
    db = get_db()
    media_id = item.get("id")
    prompt = item.get("prompt")
    kind = item.get("kind")
    if not isinstance(media_id, str) or not isinstance(prompt, str) or not isinstance(kind, str):
        raise TypeError("Invalid media item for regeneration")  # noqa: TRY003
    raw_params = item.get("params")
    params: dict[str, JsonValue] = dict(raw_params) if isinstance(raw_params, Mapping) else {}
    try:
        if kind == "image":
            context = None
            if is_conversational(model):
                msg = db.get_chat_message(message_id)
                history = branch_to(db.get_chat_messages(conv_id), message_id)[:-1]
                direct = params.get("direct") is True
                history_limit = params.get("history_limit")
                refs = params.get("refs")
                image_limit = params.get("image_limit")
                context = image_context(
                    conv_id,
                    history,
                    history_limit if isinstance(history_limit, int) and not isinstance(history_limit, bool) else None,
                    msg.content if msg else "",
                    None if direct else prompt,
                    [ref for ref in refs if isinstance(ref, str)] if isinstance(refs, list) else [],
                    conversation_instructions(conv_id),
                    param_characters(params),
                    image_limit
                    if isinstance(image_limit, int) and not isinstance(image_limit, bool)
                    else DEFAULT_IMAGE_LIMIT,
                )
            params["context"] = context is not None
            names, cost, credits, sent = run_image_generation(conv_id, model, prompt, params, context)
            sent, exchange = take_log(sent)
            db.update_chat_media_item(
                message_id,
                media_id,
                status="done",
                file=names[0],
                cost=cost,
                credits=credits,
                params={**params, **sent},
                **exchange,
            )
            for extra in names[1:]:
                db.append_chat_media_item(
                    message_id, saved_media("image", "generated", extra, prompt=prompt, model=model)
                )
            add_message_cost(message_id, cost)
        elif kind == "audio":
            job = submit_audio_generation(conv_id, model, prompt, params)
            db.update_chat_media_item(
                message_id,
                media_id,
                job_id=job["id"],
                params={**params, **job.get("params", {})},
                **exchange_fields(job.get("log")),
            )
            polling.start_video_poller(conv_id, message_id, media_id, job["id"])
        else:
            # A different model may support different durations/ratios
            duration = params.get("duration")
            aspect_ratio = params.get("aspect_ratio")
            resolution = params.get("resolution")
            params["duration"], params["aspect_ratio"], params["resolution"] = fit_video_params(
                model,
                duration if isinstance(duration, int) and not isinstance(duration, bool) else None,
                aspect_ratio if isinstance(aspect_ratio, str) else None,
                resolution if isinstance(resolution, str) else None,
            )
            job = submit_video_generation(conv_id, model, prompt, params)
            db.update_chat_media_item(
                message_id,
                media_id,
                job_id=job["id"],
                params={**params, **job.get("params", {})},
                **exchange_fields(job.get("log")),
            )
            polling.start_video_poller(conv_id, message_id, media_id, job["id"])
    except openrouter.OpenRouterError as e:
        db.update_chat_media_item(message_id, media_id, **failure_fields(e))
    except Exception as e:  # noqa: BLE001 — never leave the card stuck on "pending"
        db.update_chat_media_item(
            message_id, media_id, status="error", error=f"{type(e).__name__}: {e}", moderated=False
        )
