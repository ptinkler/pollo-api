"""Background video polling: start a poller thread for a submitted job, poll it.

to completion (downloading the finished file), and resume unfinished jobs +
warm missing thumbnails at startup.
"""

import logging
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from web import media
from web.chat.constants import CHAT_PREVIEW_SIZE, VIDEO_MAX_POLL_ERRORS, VIDEO_POLL_INTERVAL, VIDEO_POLL_TIMEOUT
from web.chat.generation import MODERATION
from web.chat.helpers import add_message_cost, chat_root, conversation_dir
from web.chat.workers import with_owner_keys
from web.core.metadata import get_db
from web.media_types import AUDIO_SUFFIXES, IMAGE_SUFFIXES, VIDEO_SUFFIXES
from web.providers import provider_for_job

log = logging.getLogger(__name__)

_RESULT_EXTS = VIDEO_SUFFIXES | AUDIO_SUFFIXES


def _result_name(kind: str | None, job: dict) -> str:
    """A fresh file name; the extension follows the result's URL (tools return.

    .webm / .mov, speech may be .wav), else .mp3 for audio and .mp4 for video.
    """
    audio = kind == "audio"
    ext = Path(urlsplit((job.get("urls") or [""])[0]).path).suffix.lower()
    if ext not in _RESULT_EXTS:
        ext = ".mp3" if audio else ".mp4"
    return f"{'aud' if audio else 'vid'}_{uuid.uuid4().hex[:12]}{ext}"


def start_video_poller(conv_id: str, message_id: int, media_id: str, job_id: str) -> None:
    """Start a background poller for a submitted media job."""
    threading.Thread(
        target=_poll_video, args=(conv_id, message_id, media_id, job_id), daemon=True, name=f"chat-video-{media_id}"
    ).start()


@with_owner_keys
def _poll_video(conv_id: str, message_id: int, media_id: str, job_id: str) -> None:
    db = get_db()
    source = provider_for_job(job_id)
    deadline = time.time() + VIDEO_POLL_TIMEOUT
    errors = 0
    while time.time() < deadline:
        time.sleep(VIDEO_POLL_INTERVAL)
        item = db.find_chat_media_item(message_id, media_id)
        if not item:
            return  # conversation deleted (items detached to the library are still updated)
        try:
            job = source.get_video(job_id)
            errors = 0
        except Exception as e:  # noqa: BLE001 — provider adapters may raise transport-specific errors
            errors += 1
            log.warning("video %s: poll error %d/%d: %s", job_id, errors, VIDEO_MAX_POLL_ERRORS, e)
            if errors >= VIDEO_MAX_POLL_ERRORS:
                db.update_chat_media_item(message_id, media_id, status="error", error=f"Polling failed: {e}")
                return
            continue

        status = job.get("status")
        if status == "completed":
            name = _result_name(item.get("kind"), job)
            try:
                source.download_video(job_id, conversation_dir(conv_id) / name)
            except Exception as e:  # noqa: BLE001 — convert download failures into a terminal media state
                db.update_chat_media_item(message_id, media_id, status="error", error=f"Download failed: {e}")
                return
            cost = (job.get("usage") or {}).get("cost")
            msg = db.update_chat_media_item(
                message_id, media_id, status="done", file=name, cost=cost, credits=job.get("credits")
            )
            if msg:
                add_message_cost(message_id, cost)
            log.info("video %s saved as %s", job_id, name)
            return
        if status in ("failed", "cancelled", "expired"):
            error = job.get("error") or f"{(item.get('kind') or 'video').title()} {status}"
            # A provider that charges for a failed job says so here; record it so
            # the charge shows up in the usage breakdown like any other. The
            # verdict replaces the submit reply as the stored response, so the
            # request view doesn't still read "accepted".
            extra = {k: job[k] for k in ("credits", "response") if job.get(k) is not None}
            db.update_chat_media_item(
                message_id,
                media_id,
                status="error",
                error=error,
                moderated=bool(MODERATION.search(error)),
                **extra,
            )
            return
    db.update_chat_media_item(message_id, media_id, status="error", error="Timed out waiting for the file")


def startup_resume_chat() -> None:
    """Resume video pollers and fail turns orphaned by a restart."""
    db = get_db()
    resumed = 0
    for msg in db.get_chat_messages_with_pending_media():
        for item in msg.media:
            if item.get("status") != "pending":
                continue
            media_id, job_id = item.get("id"), item.get("job_id")
            if isinstance(media_id, str) and isinstance(job_id, str):
                start_video_poller(msg.conversation_id, msg.id, media_id, job_id)
                resumed += 1
            else:
                if isinstance(media_id, str):
                    db.update_chat_media_item(msg.id, media_id, status="error", error="Interrupted by server restart")
    for lib in db.list_chat_library():
        item = lib.item
        media_id, job_id = item.get("id"), item.get("job_id")
        if item.get("status") == "pending" and isinstance(media_id, str) and isinstance(job_id, str):
            # message_id 0 never exists, so updates go straight to the library row
            start_video_poller(lib.conversation_id, 0, media_id, job_id)
            resumed += 1
    for msg in db.get_chat_messages_by_status("streaming"):
        db.update_chat_message(msg.id, status="error", error="Interrupted by server restart")
    if resumed:
        log.info("resumed polling for %d unfinished generation(s)", resumed)
    threading.Thread(target=_warm_missing_thumbnails, daemon=True).start()


def _warm_missing_thumbnails() -> None:
    """Create missing grid thumbnails and chat previews for stored images.

    Existing thumbnails are skipped; images are processed in the background.
    """
    root = chat_root()
    if not root.is_dir():
        return
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        for path in folder.iterdir():
            if path.suffix.lower() in IMAGE_SUFFIXES - {".svg"}:
                for size in (media.THUMB_SIZE, CHAT_PREVIEW_SIZE):
                    media.make_thumb(path, size)
