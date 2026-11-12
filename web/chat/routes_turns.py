"""HTTP routes for running turns and managing generated media.

Turn, retry, and edit responses stream events from a worker; the engine lives
in `turn.py` and generation helpers live in `generation.py`.
"""

import json
import queue
import threading
import uuid
from collections.abc import Iterator
from typing import Any

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
from web.uploads import safe_filename

# Live turns' cancel flags, keyed by the assistant message id (set by the
# cancel route, checked by the running Turn).
_cancel_events: dict[int, threading.Event] = {}


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
    require_idle(conv_id, msg.lane)
    content = data.content.strip()
    if not content and not msg.media:
        raise HTTPException(400, "Message is empty")
    media = [{**item, "id": uuid.uuid4().hex[:8]} for item in msg.media]
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
    restore: str | None = None,
) -> StreamingResponse:
    """Run a Turn against `assistant_id` and stream its events as SSE.

    Used
    both for a brand-new reply and for generating an existing one again.

    `restore` is the text the message had before: if the run comes back with
    nothing (it failed, or was stopped before a word arrived), it is put back,
    so regenerating a reply's words can't lose the ones it had.
    """
    events: queue.Queue = queue.Queue()
    cancel = threading.Event()
    _cancel_events[assistant_id] = cancel

    def worker() -> None:
        try:
            Turn(conv_id, settings, assistant_id, events.put, cancel, initial_cost=initial_cost).run()
            if restore:
                msg = get_db().get_chat_message(assistant_id)
                if msg and not (msg.content or "").strip():
                    events.put(
                        {
                            "type": "done",
                            "message": message_out(get_db().update_chat_message(assistant_id, content=restore)),
                        }
                    )
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
    require_idle(conv_id, msg.lane)
    if any(i.get("status") == "pending" for i in msg.media):
        raise HTTPException(409, "Wait for this reply's media to finish first")
    remember_settings(conv, data)
    # Only the words are generated again, whatever mode the composer is in.
    settings = data.model_copy(update={"mode": "text"})
    # Its pictures keep their cost; the words it had are replaced by new ones.
    media_cost = sum(float(cost) for item in msg.media if isinstance((cost := item.get("cost")), (int, float, str)))
    previous = msg.content
    db.update_chat_message(data.message_id, content="", status="streaming", error=None)
    start = {"type": "start", "user_message": None, "assistant_message": message_out(msg), "replaces": msg.id}
    start["assistant_message"] = {**start["assistant_message"], "content": "", "status": "streaming"}
    return _stream_turn(conv_id, settings, msg.id, start, initial_cost=media_cost, restore=previous)


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


def _as_version(item: dict) -> dict:
    """What a card keeps about a picture it has replaced."""
    keep = ("file", "prompt", "model", "cost", "credits", "params", "request", "response")
    return {k: item[k] for k in keep if item.get(k) is not None}


@router.post("/messages/{message_id}/media/{media_id}/regenerate")
def api_regenerate_media(message_id: int, media_id: str, data: RegenerateMedia) -> dict[str, Any]:
    """Retry or re-roll a generated image or video.

    The retry runs in the background while the UI polls the message.
    """
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
        old_versions = list(item.get("versions") or [])
        versions = [*old_versions, _as_version(item)] if item.get("file") else old_versions
        blank = dict.fromkeys(("file", "cost", "credits", "error", "job_id", "request", "response"))
        item = {**item, **blank, "status": "pending", "model": model, "prompt": prompt, "params": params}
        item["versions"] = versions
        msg = db.update_chat_media_item(
            message_id,
            media_id,
            **{k: item[k] for k in (*blank, "status", "model", "prompt", "params", "versions")},
            moderated=False,
        )
    elif item["status"] == "done":
        # Re-roll just this image/video: the original stays, a new one joins the reply
        gone = ("file", "cost", "credits", "error", "job_id", "favourite", "pinned", "log", "versions")
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
def _regenerate_worker(conv_id: str, message_id: int, item: dict, model: str) -> None:
    db = get_db()
    media_id = item["id"]
    params = dict(item.get("params") or {})
    try:
        if item["kind"] == "image":
            context = None
            if is_conversational(model):
                msg = db.get_chat_message(message_id)
                history = branch_to(db.get_chat_messages(conv_id), message_id)[:-1]
                direct = params.get("direct", False)
                context = image_context(
                    conv_id,
                    history,
                    params.get("history_limit"),
                    msg.content if msg else "",
                    None if direct else item["prompt"],
                    params.get("refs") or [],
                    conversation_instructions(conv_id),
                    param_characters(params),
                    params.get("image_limit", DEFAULT_IMAGE_LIMIT),
                )
            params["context"] = context is not None
            names, cost, credits, sent = run_image_generation(conv_id, model, item["prompt"], params, context)
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
                    message_id, saved_media("image", "generated", extra, prompt=item["prompt"], model=model)
                )
            add_message_cost(message_id, cost)
        elif item["kind"] == "audio":
            job = submit_audio_generation(conv_id, model, item["prompt"], params)
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
            params["duration"], params["aspect_ratio"], params["resolution"] = fit_video_params(
                model, params.get("duration"), params.get("aspect_ratio"), params.get("resolution")
            )
            job = submit_video_generation(conv_id, model, item["prompt"], params)
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
