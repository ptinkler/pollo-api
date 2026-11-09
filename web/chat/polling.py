"""Background video polling: start a poller thread for a submitted job, poll it
to completion (downloading the finished file), and resume unfinished jobs +
warm missing thumbnails at startup."""

import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from web.core.metadata import get_db

from .. import media
from ..providers import openrouter, pollo, venice
from .constants import CHAT_PREVIEW_SIZE, IMAGE_EXTS, VIDEO_MAX_POLL_ERRORS, VIDEO_POLL_INTERVAL, VIDEO_POLL_TIMEOUT
from .generation import _MODERATION
from .helpers import _add_message_cost, _chat_root, _conv_dir
from .workers import _with_owner_keys

_RESULT_EXTS = {".mp4", ".webm", ".mov", ".mp3", ".wav", ".m4a", ".ogg"}


def _result_name(kind: str | None, job: dict) -> str:
    """A fresh file name; the extension follows the result's URL (tools return
    .webm / .mov, speech may be .wav), else .mp3 for audio and .mp4 for video."""
    audio = kind == "audio"
    ext = Path(urlsplit((job.get("urls") or [""])[0]).path).suffix.lower()
    if ext not in _RESULT_EXTS:
        ext = ".mp3" if audio else ".mp4"
    return f"{'aud' if audio else 'vid'}_{uuid.uuid4().hex[:12]}{ext}"


def start_video_poller(conv_id: str, message_id: int, media_id: str, job_id: str) -> None:
    threading.Thread(
        target=_poll_video, args=(conv_id, message_id, media_id, job_id), daemon=True, name=f"chat-video-{media_id}"
    ).start()


@_with_owner_keys
def _poll_video(conv_id: str, message_id: int, media_id: str, job_id: str) -> None:
    db = get_db()
    source = pollo if pollo.is_pollo_job(job_id) else venice if venice.is_venice_job(job_id) else openrouter
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
        except Exception as e:  # noqa: BLE001 — transient network/VPN hiccups
            errors += 1
            print(f"⚠️ chat video {job_id}: poll error {errors}/{VIDEO_MAX_POLL_ERRORS}: {e}")
            if errors >= VIDEO_MAX_POLL_ERRORS:
                db.update_chat_media_item(message_id, media_id, status="error", error=f"Polling failed: {e}")
                return
            continue

        status = job.get("status")
        if status == "completed":
            name = _result_name(item.get("kind"), job)
            try:
                source.download_video(job_id, _conv_dir(conv_id) / name)
            except Exception as e:  # noqa: BLE001
                db.update_chat_media_item(message_id, media_id, status="error", error=f"Download failed: {e}")
                return
            cost = (job.get("usage") or {}).get("cost")
            msg = db.update_chat_media_item(
                message_id, media_id, status="done", file=name, cost=cost, credits=job.get("credits")
            )
            if msg:
                _add_message_cost(message_id, cost)
            print(f"✅ chat video {job_id} saved as {name}")
            return
        if status in ("failed", "cancelled", "expired"):
            error = job.get("error") or f"{(item.get('kind') or 'video').title()} {status}"
            db.update_chat_media_item(
                message_id, media_id, status="error", error=error, moderated=bool(_MODERATION.search(error))
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
    threading.Thread(target=_warm_missing_thumbnails, daemon=True).start()


def _warm_missing_thumbnails() -> None:
    """Make any missing grid thumbnails and chat previews for chat images, one
    at a time in the background, so the Media page and big chats (imports)
    don't wait for them on first view. Ones already made are skipped quickly."""
    root = _chat_root()
    if not root.is_dir():
        return
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        for path in folder.iterdir():
            if path.suffix.lower() in IMAGE_EXTS.values() and path.suffix.lower() != ".svg":
                for size in (media.THUMB_SIZE, CHAT_PREVIEW_SIZE):
                    media.make_thumb(path, size)
