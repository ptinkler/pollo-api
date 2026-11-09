"""
Media library — one place for every upload and creation in the app.

It's an index over files that already live elsewhere, not a store of its own:

  • library  — images uploaded straight to the library (<data>/library/)
  • chat     — a chat's uploads and generated images/videos (<data>/chat/<id>/)
  • orphan   — files in a chat's folder that nothing records any more: an
               attachment that was never sent, a file a message dropped, or
               the folder of a chat that's gone

Item ids say where a file is: "lib:<file>", "chat:<conversation id>:<file>".

Every item has a small cached thumbnail (/api/media/thumb/<id>) for the
grids, so they don't load full-size images or videos.

Using an item (as a character image or a chat attachment) copies the file to
that destination — the way uploads already work there — so deleting it from
the library never breaks what used it.
"""

import asyncio
import contextlib
import hashlib
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel

from web.core import config
from web.core.metadata import get_db, iso

from . import characters
from .uploads import (
    image_media_type,
    is_blank_image,
    read_image_upload,
    read_video_upload,
    safe_filename,
    store_deduped,
)
from .users import require_user

router = APIRouter(prefix="/api/media", dependencies=[Depends(require_user)])

VIDEO_EXTS = {".mp4", ".webm", ".mov"}
THUMB_SIZE = 320  # px, the thumbnail's shorter side (grid tiles are square, cropped to fill)
THUMB_WORKERS = 2  # thumbnails made at once — a grid asks for many together, and a NAS CPU is slow
# A new chat file isn't orphaned until it's this old (s): attachments wait in
# the composer, and generations are written before their message records them
ORPHAN_GRACE = 3600
_PARAM_FILES = ("first_frame", "last_frame", "source_video")  # chat media params naming one file


def _web_api():
    # web.api imports this module's router, so import it lazily
    from . import api

    return api


def library_dir() -> Path:
    # Read config at call time so tests can redirect ROOT_DIR. Per-user
    # (<data>/library/<user_id>/) so one user's uploads never show to another;
    # the shared legacy folder is the admin's, migrated by provision_admin.
    from web.core.metadata import current_tenant

    base = config.ROOT_DIR / "library"
    uid = current_tenant()
    return base / uid if uid else base


def thumb_dir() -> Path:
    return config.ROOT_DIR / "cache" / "media-thumbs"


def _chat_dir(conv_id: str) -> Path:
    return config.ROOT_DIR / "chat" / conv_id


def _kind(path: Path | str) -> str | None:
    if Path(path).suffix.lower() in VIDEO_EXTS:
        return "video"
    return "image" if image_media_type(path) else None


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
    except OSError:
        return None


def resolve(media_id: str) -> tuple[str, Path, dict[str, str]]:
    """(origin, file path, location parts) for an item id; 400/404 if it's
    malformed or gone."""
    origin, _, rest = media_id.partition(":")
    if origin == "lib":
        path, parts = library_dir() / safe_filename(rest), {}
    elif origin == "chat":
        conv_id, _, file = rest.partition(":")
        # Multi-tenant guard: chat files live under a global <data>/chat/<id>/,
        # so the id alone must not reach another user's files. Allow it only
        # when the chat is the current user's (get_conversation is tenant-
        # scoped) or no conversation row exists anywhere (a truly orphaned
        # folder — e.g. a deleted chat's leftovers, which anyone may clean up).
        # A row owned by a DIFFERENT user reads as not-mine here → 404.
        db = get_db()
        if not db.get_conversation(conv_id) and db.conversation_exists_any_tenant(conv_id):
            raise HTTPException(404, "Media not found")
        path, parts = (
            _chat_dir(safe_filename(conv_id)) / safe_filename(file),
            {"conversation_id": conv_id, "file": file},
        )
    else:
        raise HTTPException(400, "Unknown media id")
    if not path.is_file():
        raise HTTPException(404, "Media not found")
    return origin, path, parts


def _thumb_url(media_id: str) -> str:
    return f"/api/media/thumb/{media_id}"


def _thumb_path(path: Path, size: int = THUMB_SIZE) -> Path:
    """Where a file's thumbnail is cached — keyed by path, mtime and size, so
    an edited file gets a fresh one."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    key = f"{path}:{mtime}" + (f":{size}" if size != THUMB_SIZE else "")
    return thumb_dir() / f"{hashlib.md5(key.encode()).hexdigest()}.jpg"


def make_thumb(path: Path, size: int = THUMB_SIZE) -> Path | None:
    """A small JPEG of an image, or of a video's first frame (cached), `size`
    px on its shorter side. None if the file can't be read."""
    out = _thumb_path(path, size)
    if out.is_file():
        return out
    try:
        if _kind(path) == "video":
            frame = _web_api()._extract_first_frame_uncached(path)
            if not frame:
                return None
            img = Image.open(io.BytesIO(frame))
        else:
            img = Image.open(path)
        w, h = img.size
        scale = min(1.0, size / min(w, h))
        target = (max(1, round(w * scale)), max(1, round(h * scale)))
        img.draft("RGB", target)  # JPEGs decode straight at a reduced size — much faster
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail(target, Image.LANCZOS, reducing_gap=2.0)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".part")
        img.save(tmp, "JPEG", quality=80)
        tmp.replace(out)
        return out
    except Exception:  # noqa: BLE001 — a broken file just has no thumbnail
        return None


# New thumbnails are made on their own small pool, THUMB_WORKERS at a time
_thumb_pool = ThreadPoolExecutor(max_workers=THUMB_WORKERS, thread_name_prefix="media-thumb")


async def thumb_response(path: Path, size: int = THUMB_SIZE) -> FileResponse:
    """A file's thumbnail: cached ones straight back, new ones queued for the
    thumbnail pool (awaited, so queued requests don't tie up the worker
    threads every other, sync, endpoint runs on)."""
    thumb = _thumb_path(path, size)
    if not thumb.is_file():
        thumb = await asyncio.wrap_future(_thumb_pool.submit(make_thumb, path, size))
    if not thumb:
        raise HTTPException(404, "No thumbnail")
    return FileResponse(
        thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )


@router.get("/thumb/{media_id:path}")
async def api_media_thumb(media_id: str):
    """A library item's thumbnail (see thumb_response)."""
    _, path, _ = await anyio.to_thread.run_sync(resolve, media_id)
    return await thumb_response(path)


def _library_items() -> list[dict[str, Any]]:
    d = library_dir()
    if not d.is_dir():
        return []
    return [
        {
            "id": f"lib:{p.name}",
            "kind": _kind(p),
            "source": "upload",
            "origin": "library",
            "name": p.name,
            "url": f"/api/media/library/{p.name}",
            "thumb_url": _thumb_url(f"lib:{p.name}"),
            "created_at": _mtime_iso(p),
        }
        for p in d.iterdir()
        if p.is_file() and _kind(p)
    ]


def _chat_records(msgs, lib_items, titles: dict[str, str]) -> list[dict[str, Any]]:
    # Keyed by file name alone: a branched chat links its media in under the
    # same names (web/chat.py api_fork_conversation), so each shows once —
    # in the oldest chat that still has it
    items: dict[str, dict[str, Any]] = {}

    def add(conv_id: str, item: dict, created_at, replace: bool = False) -> None:
        file = item.get("file")
        if not file or item.get("status", "done") != "done" or (file in items and not replace):
            return
        if not (_chat_dir(conv_id) / file).is_file():
            return
        items[file] = {
            "id": f"chat:{conv_id}:{file}",
            "kind": item.get("kind") or _kind(file),
            "source": "upload" if item.get("source") == "upload" else "generated",
            "origin": "chat",
            "name": file,
            "url": f"/api/chat/media/{conv_id}/{file}",
            "thumb_url": _thumb_url(f"chat:{conv_id}:{file}"),
            "created_at": iso(created_at),
            "conversation_id": conv_id,
            "conversation_title": titles.get(conv_id),
            "prompt": item.get("prompt"),
            "model": item.get("model"),
            "cost": item.get("cost"),
        }

    for msg in msgs:  # newest first, so older copies win
        for item in msg.media:
            add(msg.conversation_id, item, msg.created_at, replace=True)
    for lib in lib_items:  # media detached from its message by older edits/retries
        add(lib.conversation_id, lib.item, lib.created_at)
    return list(items.values())


def _referenced_files(item: dict) -> list[str]:
    """Files a chat media item uses: its own, and the references it was made
    from (kept so it can be retried)."""
    params = item.get("params") or {}
    refs = [*(params.get("refs") or []), *(params.get(k) for k in _PARAM_FILES)]
    return [f for f in [item.get("file"), *refs] if isinstance(f, str) and f]


def _chat_orphans(msgs, lib_items, titles: dict[str, str]) -> list[dict[str, Any]]:
    """Files in chat folders that no message or library entry records."""
    root = config.ROOT_DIR / "chat"
    if not root.is_dir():
        return []
    used: set[tuple[str, str]] = set()
    for msg in msgs:
        used.update((msg.conversation_id, f) for i in msg.media for f in _referenced_files(i))
    for lib in lib_items:
        used.update((lib.conversation_id, f) for f in _referenced_files(lib.item))
    cutoff = time.time() - ORPHAN_GRACE
    items = []
    # Only the current user's conversation folders (titles is tenant-scoped), so
    # one user's orphan scan never lists another user's files.
    for conv_id in titles:
        d = root / conv_id
        if not d.is_dir() or d.name.startswith("."):  # .deleting-<id>: a deleted chat's files, going
            continue
        for p in d.iterdir():
            kind = _kind(p) if p.is_file() and (d.name, p.name) not in used else None
            if not kind or p.stat().st_mtime > cutoff:
                continue
            media_id = f"chat:{d.name}:{p.name}"
            items.append(
                {
                    "id": media_id,
                    "kind": kind,
                    "source": "upload" if p.name.startswith("up_") else "generated",
                    "origin": "orphan",
                    "name": p.name,
                    "url": f"/api/chat/media/{d.name}/{p.name}",
                    "thumb_url": _thumb_url(media_id),
                    "created_at": _mtime_iso(p),
                    "conversation_id": d.name if d.name in titles else None,
                    "conversation_title": titles.get(d.name),
                }
            )
    return items


def _build_items(db) -> list[dict[str, Any]]:
    """The whole library, newest first. The two chat queries (every message
    with media, and the detached library) are each run once and shared by the
    records and orphans passes — they were the list's main cost."""
    msgs = db.get_chat_messages_with_media()  # newest first (id desc)
    lib_items = db.list_chat_library()
    titles = {c.id: c.title for c in db.list_conversations(limit=100000)}
    items = _library_items() + _chat_records(msgs, lib_items, titles) + _chat_orphans(msgs, lib_items, titles)
    items.sort(key=lambda i: i["created_at"] or "", reverse=True)
    return items


# The built list, cached so paging through it doesn't rebuild it each request
# (scanning the user's chat folders and the chat DB is slow on a NAS). Keyed on
# (ROOT_DIR, tenant) so one user never sees another's list, and tests (each with
# their own ROOT_DIR) stay isolated. Writes invalidate it; a short TTL catches
# creations made elsewhere.
_LIST_TTL = 30.0
_list_cache: dict[tuple, dict] = {}


def _all_items() -> list[dict[str, Any]]:
    from web.core.metadata import current_tenant

    key = (config.ROOT_DIR, current_tenant())
    now = time.monotonic()
    entry = _list_cache.get(key)
    if entry is None or now - entry["at"] > _LIST_TTL:
        entry = {"at": now, "items": _build_items(get_db())}
        _list_cache[key] = entry
    return entry["items"]


def _invalidate_list() -> None:
    _list_cache.clear()


def _origin_label(item: dict[str, Any]) -> str:
    """Where an item is from, for search — mirrors mediaOrigin in the frontend."""
    origin = item.get("origin")
    if origin == "chat":
        return item.get("conversation_title") or "Chat"
    if origin == "orphan":
        title = item.get("conversation_title")
        return f"{title} (orphaned)" if title else "Orphaned"
    return "Library"


def _matches(item: dict[str, Any], kind: str, source: str, origin: str, q: str) -> bool:
    if kind != "all" and item.get("kind") != kind:
        return False
    if source != "all" and item.get("source") != source:
        return False
    if origin != "all" and item.get("origin") != origin:
        return False
    if not q:
        return True
    return any(s and q in s.lower() for s in (item.get("prompt"), item.get("name"), _origin_label(item)))


@router.get("")
def api_list_media(
    offset: int = 0,
    limit: int = 0,  # 0 = everything from `offset` on (the default — the whole library)
    kind: str = "all",
    source: str = "all",
    origin: str = "all",
    q: str = "",
):
    """A page of the library, newest first, narrowed by the same filters as the
    Media page. `total` is how many match before paging, for infinite scroll."""
    items = _all_items()
    ql = q.strip().lower()
    if kind != "all" or source != "all" or origin != "all" or ql:
        items = [i for i in items if _matches(i, kind, source, origin, ql)]
    total = len(items)
    items = items[offset : offset + limit] if limit else items[offset:]
    return {"items": items, "total": total, "offset": offset}


@router.get("/library/{filename}")
def api_library_file(filename: str):
    path = library_dir() / safe_filename(filename)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.post("/upload")
async def api_upload_media(file: UploadFile = File(...)):
    """Upload an image or video straight to the library (so it can be picked as
    a reference). Audio stays a chat-only upload."""
    ct = file.content_type or ""
    content, ext = await (read_video_upload(file) if ct.startswith("video/") else read_image_upload(file))
    name = store_deduped(library_dir(), "up_", content, ext)
    _invalidate_list()
    return next(i for i in _library_items() if i["name"] == name)


@router.delete("/{media_id:path}")
def api_delete_media(media_id: str):
    """Delete an item's file — and what records it: a generation's job, or
    the chat message's media item. Copies already made from it (character
    images, attachments, Generate sources) are separate files and stay."""
    origin, path, parts = resolve(media_id)
    _thumb_path(path).unlink(missing_ok=True)
    db = get_db()
    if origin == "lib":
        path.unlink()
    else:
        conv_id, file = parts["conversation_id"], parts["file"]
        for msg in db.get_chat_messages(conv_id):
            if any(i.get("file") == file for i in msg.media):
                db.update_chat_message(msg.id, media=[i for i in msg.media if i.get("file") != file])
        for lib in db.list_chat_library():
            if lib.conversation_id == conv_id and lib.item.get("file") == file:
                db.delete_chat_library_item(lib.media_id)
        path.unlink()
    _invalidate_list()
    return {"deleted": media_id}


# Which saved images are solid black, per file version, kept on disk: the
# Media page asks on every load, and decoding every chat image again after
# each restart takes minutes on a NAS
_blank_cache: dict[str, bool] | None = None
_blank_lock = threading.Lock()


def _blank_cache_path() -> Path:
    return config.ROOT_DIR / "cache" / "blank-images.json"


def _blank_checks() -> dict[str, bool]:
    global _blank_cache
    if _blank_cache is None:
        try:
            _blank_cache = json.loads(_blank_cache_path().read_text())
        except (OSError, ValueError):
            _blank_cache = {}
    return _blank_cache


def _save_blank_checks() -> None:
    path = _blank_cache_path()
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_text(json.dumps(_blank_checks()))
        tmp.replace(path)


def _is_blank_file(path: Path) -> bool:
    """is_blank_image for a saved file, remembered per file version. Reads its
    small thumbnail when there is one rather than the full image."""
    try:
        key = f"{path}:{path.stat().st_mtime}"
    except OSError:
        return False
    checks = _blank_checks()
    if key not in checks:
        thumb = _thumb_path(path)
        data = thumb.read_bytes() if thumb.is_file() else path.read_bytes()
        with _blank_lock:
            checks[key] = is_blank_image(data)
    return checks[key]


def _blocked_reason(conv_id: str, item: dict) -> str | None:
    """Why a chat media item counts as a blocked generation: "moderated" (a
    content filter refused it) or "black" (a black image saved before the
    app caught those); None otherwise."""
    if item.get("source") == "upload" or item.get("import_file"):  # imports weren't made by this app's providers
        return None
    if item.get("status") == "error":
        return "moderated" if item.get("moderated") else None
    if item.get("kind") == "image" and item.get("status", "done") == "done" and item.get("file"):
        path = _chat_dir(conv_id) / item["file"]
        if path.is_file() and _is_blank_file(path):
            return "black"
    return None


def _blocked(db) -> list[tuple[Any, dict, str]]:
    """(chat message or library entry, media item, reason) for each blocked generation."""
    checked = len(_blank_checks())
    out = []
    for msg in db.get_chat_messages_with_media():
        out += [(msg, i, r) for i in msg.media if (r := _blocked_reason(msg.conversation_id, i))]
    for lib in db.list_chat_library():
        if r := _blocked_reason(lib.conversation_id, lib.item):
            out.append((lib, lib.item, r))
    if len(_blank_checks()) != checked:
        _save_blank_checks()
    return out


@router.get("/blocked")
def api_blocked_count():
    """How many chat generations a content filter blocked: failed ones
    (moderated) and black images saved before those were caught."""
    found = _blocked(get_db())
    return {"moderated": sum(r == "moderated" for *_, r in found), "black": sum(r == "black" for *_, r in found)}


@router.post("/blocked/clear")
def api_clear_blocked():
    """Remove every blocked chat generation: the failed cards from their chats
    (and detached ones from the library) and the black images' files."""
    db = get_db()
    found = _blocked(db)
    by_message: dict[int, list[str]] = {}
    for owner, item, _ in found:
        if hasattr(owner, "media_id"):  # a detached library entry
            db.delete_chat_library_item(owner.media_id)
        else:
            by_message.setdefault(owner.id, []).append(item.get("id"))
        if item.get("file") and item.get("status", "done") == "done":
            path = _chat_dir(owner.conversation_id) / safe_filename(item["file"])
            _thumb_path(path).unlink(missing_ok=True)
            path.unlink(missing_ok=True)
    for msg_id, ids in by_message.items():
        msg = db.get_chat_message(msg_id)
        if msg:
            db.update_chat_message(msg_id, media=[i for i in msg.media if i.get("id") not in ids])
    _invalidate_list()
    return {"cleared": len(found)}


class ImportMedia(BaseModel):
    media_id: str
    target: Literal["chat", "character"]
    conversation_id: str | None = None  # target "chat"
    character_id: int | None = None  # target "character"


@router.post("/import")
def api_import_media(data: ImportMedia):
    """Copy an image from the library to where it's being used:
    chat      → {"file": "<file>"} to attach to the next message
    character → the character, with the image added"""
    origin, path, parts = resolve(data.media_id)
    if _kind(path) != "image":
        raise HTTPException(400, "Only images can be used here")
    db = get_db()
    ext = path.suffix.lower()

    if data.target == "chat":
        conv_id = data.conversation_id or ""
        if not db.get_conversation(conv_id):
            raise HTTPException(404, "Conversation not found")
        if origin == "chat" and parts["conversation_id"] == conv_id:
            return {"file": path.name}  # already in this chat
        name = store_deduped(_chat_dir(conv_id), "up_", path.read_bytes(), ext)
        _invalidate_list()
        return {"file": name}

    char = db.get_character(data.character_id or 0)
    if not char:
        raise HTTPException(404, "Character not found")
    return characters.add_image_from_file(char, path)
