"""HTTP routes for running turns and acting on generated media: the SSE
message/retry/edit endpoints (streamed from a Turn worker), the cancel hook,
and the pin / favourite / regenerate media endpoints. They register on the
shared router; the turn engine itself lives in turn.py / generation.py."""

import json
import queue
import threading
import uuid
from collections.abc import Iterator

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from web.core.metadata import get_db

from ..providers import openrouter
from ..uploads import safe_filename
from . import polling
from .catalogue import _fit_video_params
from .constants import DEFAULT_IMAGE_LIMIT
from .deps import router
from .generation import (
    _conversation_instructions,
    _exchange,
    _failure_fields,
    _image_context,
    _is_conversational,
    _param_characters,
    _run_image_generation,
    _submit_video_generation,
    _take_log,
)
from .helpers import (
    _add_message_cost,
    _branch_to,
    _conv_dir,
    _find_media,
    _message_out,
    _remember_settings,
    _require_conv,
    _require_idle,
    _require_openrouter,
    _saved_media,
)
from .models import EditMessage, RetryMessage, SendMessage, TurnSettings
from .turn import Turn
from .workers import _ctx_thread, _with_owner_keys

# Live turns' cancel flags, keyed by the assistant message id (set by the
# cancel route, checked by the running Turn).
_cancel_events: dict[int, threading.Event] = {}


@router.post("/messages/{message_id}/cancel")
def api_cancel_message(message_id: int):
    ev = _cancel_events.get(message_id)
    if ev:
        ev.set()
    return {"cancelled": bool(ev)}


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
        kind = "video" if name.lower().endswith(".mp4") else "image"
        media.append(_saved_media(kind, "upload", name))

    db = get_db()
    user_msg = db.add_chat_message(conv_id, "user", content, media=media, mode=data.mode)
    _remember_settings(conv, data)
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
    # The retry runs in the mode selected now; the prompt's mode tag follows it
    if msg.parent_id:
        get_db().update_chat_message(msg.parent_id, mode=data.mode)
    _remember_settings(conv, data)
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
    user_msg = db.add_chat_message(conv_id, "user", content, media=media, parent_id=msg.parent_id, mode=data.mode)
    _remember_settings(conv, data)
    return _start_turn(conv_id, data, user_msg, parent_id=user_msg.id)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _start_turn(conv_id: str, settings: TurnSettings, user_msg, parent_id: int | None) -> StreamingResponse:
    model = {"image": settings.image_model, "video": settings.video_model}.get(settings.mode, settings.text_model)
    assistant = get_db().add_chat_message(
        conv_id, "assistant", "", model=model, status="streaming", parent_id=parent_id, mode=settings.mode
    )
    start = {
        "type": "start",
        "user_message": _message_out(user_msg) if user_msg else None,
        "assistant_message": _message_out(assistant),
    }
    events: queue.Queue = queue.Queue()
    cancel = threading.Event()
    _cancel_events[assistant.id] = cancel

    def worker():
        try:
            Turn(conv_id, settings, assistant.id, events.put, cancel).run()
        finally:
            _cancel_events.pop(assistant.id, None)
            events.put(None)

    # Run in a copy of the current context so the turn's DB writes/reads are
    # scoped to the signed-in user (tenant) and use their keys — a plain thread
    # would not inherit those contextvars.
    _ctx_thread(worker, name=f"chat-turn-{assistant.id}").start()

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


class FavouriteMedia(BaseModel):
    favourite: bool


@router.post("/messages/{message_id}/media/{media_id}/favourite")
def api_favourite_media(message_id: int, media_id: str, data: FavouriteMedia):
    """Star/un-star a generation. Unlike pinning (which re-sends an image as a
    reference with every new generation), a favourite is just a bookmark: it
    surfaces the item in the cross-thread Favourites gallery. Works for images
    and videos."""
    db = get_db()
    msg = db.get_chat_message(message_id)
    item = _find_media(msg, media_id)
    if not item or not item.get("file") or item.get("status", "done") != "done":
        raise HTTPException(404, "Generation not found")
    return _message_out(db.update_chat_media_item(message_id, media_id, favourite=data.favourite))


class RegenerateMedia(BaseModel):
    model: str | None = None  # None = same model as the failed attempt


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
    msg = db.update_chat_media_item(
        message_id, media_id, status="pending", error=None, moderated=False, model=model, job_id=None
    )
    threading.Thread(
        target=_regenerate_worker,
        args=(msg.conversation_id, message_id, dict(item), model),
        daemon=True,
        name=f"chat-regen-{media_id}",
    ).start()
    return _message_out(msg)


@_with_owner_keys
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
                context = _image_context(
                    conv_id,
                    history,
                    params.get("history_limit"),
                    msg.content if msg else "",
                    None if direct else item["prompt"],
                    params.get("refs") or [],
                    _conversation_instructions(conv_id),
                    _param_characters(params),
                    params.get("image_limit", DEFAULT_IMAGE_LIMIT),
                )
            params["context"] = context is not None
            names, cost, credits, sent = _run_image_generation(conv_id, model, item["prompt"], params, context)
            sent, exchange = _take_log(sent)
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
                    message_id, _saved_media("image", "generated", extra, prompt=item["prompt"], model=model)
                )
            _add_message_cost(message_id, cost)
        else:
            # A different model may support different durations/ratios
            params["duration"], params["aspect_ratio"], params["resolution"] = _fit_video_params(
                model, params.get("duration"), params.get("aspect_ratio"), params.get("resolution")
            )
            job = _submit_video_generation(conv_id, model, item["prompt"], params)
            db.update_chat_media_item(
                message_id,
                media_id,
                job_id=job["id"],
                params={**params, **job.get("params", {})},
                **_exchange(job.get("log")),
            )
            polling.start_video_poller(conv_id, message_id, media_id, job["id"])
    except openrouter.OpenRouterError as e:
        db.update_chat_media_item(message_id, media_id, **_failure_fields(e))
    except Exception as e:  # noqa: BLE001 — never leave the card stuck on "pending"
        db.update_chat_media_item(
            message_id, media_id, status="error", error=f"{type(e).__name__}: {e}", moderated=False
        )
