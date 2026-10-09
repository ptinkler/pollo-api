"""
Media library — one place for every upload and creation in the app.

It's an index over files that already live elsewhere, not a store of its own:

  • library  — images uploaded straight to the library (<data>/library/)
  • project  — a Generate project's uploads (src-/ref-/image.* files) and
               creations (generated videos/images), in its assets folder
  • chat     — a chat's uploads and generated images/videos (<data>/chat/<id>/)

Item ids say where a file is: "lib:<file>", "proj:<slug>:<file>",
"chat:<conversation id>:<file>".

Every item has a small cached thumbnail (/api/media/thumb/<id>) for the
grids, so they don't load full-size images or videos.

Using an item (as a character image, a Generate source/ref image or a chat
attachment) copies the file to that destination — the way uploads already
work there — so deleting it from the library never breaks what used it.
"""

import asyncio
import hashlib
import io
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel

from img2vid.common import config
from img2vid.common.metadata import get_db, iso

from . import characters
from .auth import verify_api_key
from .uploads import image_media_type, is_blank_image, read_image_upload, safe_filename

router = APIRouter(prefix="/api/media", dependencies=[Depends(verify_api_key)])

VIDEO_EXTS = {".mp4"}
THUMB_SIZE = 320  # px, the thumbnail's shorter side (grid tiles are square, cropped to fill)
THUMB_WORKERS = 2  # thumbnails made at once — a grid asks for many together, and a NAS CPU is slow
PROJECT_SKIP = {"thumb.jpg"}  # generated project thumbnail, not media


def _web_api():
    # web.api imports this module's router, so import it lazily
    from . import api

    return api


def library_dir() -> Path:
    # Read config at call time so tests can redirect ROOT_DIR
    return config.ROOT_DIR / "library"


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


def _is_project_upload(name: str) -> bool:
    return name.startswith(("src-", "ref-")) or Path(name).stem == "image"


# ── Locating items ──────────────────────────────────────────────────


def resolve(media_id: str) -> tuple[str, Path, dict[str, str]]:
    """(origin, file path, location parts) for an item id; 400/404 if it's
    malformed or gone."""
    origin, _, rest = media_id.partition(":")
    db = get_db()
    if origin == "lib":
        path, parts = library_dir() / safe_filename(rest), {}
    elif origin == "proj":
        slug, _, file = rest.partition(":")
        proj = db.get_project_by_slug(slug)
        if not proj:
            raise HTTPException(404, "Project not found")
        path = _web_api().ASSETS_DIR / proj.assets_folder / safe_filename(file)
        parts = {"project": slug, "file": file, "assets_folder": proj.assets_folder}
    elif origin == "chat":
        conv_id, _, file = rest.partition(":")
        path, parts = (
            _chat_dir(safe_filename(conv_id)) / safe_filename(file),
            {"conversation_id": conv_id, "file": file},
        )
    else:
        raise HTTPException(400, "Unknown media id")
    if not path.is_file():
        raise HTTPException(404, "Media not found")
    return origin, path, parts


# ── Thumbnails ──────────────────────────────────────────────────────


def _thumb_url(media_id: str) -> str:
    return f"/api/media/thumb/{media_id}"


def _thumb_path(path: Path) -> Path:
    """Where a file's thumbnail is cached — keyed by path and mtime, so an
    edited file gets a fresh one."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    return thumb_dir() / f"{hashlib.md5(f'{path}:{mtime}'.encode()).hexdigest()}.jpg"


def make_thumb(path: Path) -> Path | None:
    """A small JPEG of an image, or of a video's first frame (cached). None if
    the file can't be read."""
    out = _thumb_path(path)
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
        scale = min(1.0, THUMB_SIZE / min(w, h))
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


@router.get("/thumb/{media_id:path}")
async def api_media_thumb(media_id: str):
    """Cached thumbnails come straight back; new ones queue for the thumbnail
    pool. Async, so requests waiting in that queue don't tie up the worker
    threads every other (sync) endpoint runs on."""
    _, path, _ = await anyio.to_thread.run_sync(resolve, media_id)
    thumb = _thumb_path(path)
    if not thumb.is_file():
        thumb = await asyncio.wrap_future(_thumb_pool.submit(make_thumb, path))
    if not thumb:
        raise HTTPException(404, "No thumbnail")
    return FileResponse(
        thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )


# ── Listing ─────────────────────────────────────────────────────────


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


def _project_items(db) -> list[dict[str, Any]]:
    api = _web_api()
    items = []
    for proj in db.get_all_projects():
        folder = api.ASSETS_DIR / proj.assets_folder
        if not folder.is_dir():
            continue
        jobs = {}
        for job in db.get_jobs_by_project(proj.slug):
            for name in api._job_files(job):
                jobs.setdefault(name, job)
        for p in folder.iterdir():
            kind = _kind(p) if p.is_file() and p.name not in PROJECT_SKIP else None
            if not kind:
                continue
            job = jobs.get(p.name)
            upload = _is_project_upload(p.name) and not job
            items.append(
                {
                    "id": f"proj:{proj.slug}:{p.name}",
                    "kind": kind,
                    "source": "upload" if upload else "generated",
                    "origin": "project",
                    "name": p.name,
                    "created_at": _mtime_iso(p),
                    "url": f"/video/{proj.slug}/{p.name}"
                    if not upload
                    else f"/api/projects/{proj.slug}/source-image?f={p.name}",
                    "thumb_url": _thumb_url(f"proj:{proj.slug}:{p.name}"),
                    "project": proj.slug,
                    "project_name": proj.name,
                    "prompt": job.prompt if job else None,
                    "model": job.model if job else None,
                }
            )
    return items


def _chat_items(db) -> list[dict[str, Any]]:
    titles = {c.id: c.title for c in db.list_conversations(limit=100000)}
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

    for msg in db.get_chat_messages_with_media():  # newest first, so older copies win
        for item in msg.media:
            add(msg.conversation_id, item, msg.created_at, replace=True)
    for lib in db.list_chat_library():  # media detached from its message by older edits/retries
        add(lib.conversation_id, lib.item, lib.created_at)
    return list(items.values())


@router.get("")
def api_list_media():
    """Every upload and creation, newest first."""
    db = get_db()
    items = _library_items() + _project_items(db) + _chat_items(db)
    items.sort(key=lambda i: i["created_at"] or "", reverse=True)
    return {"items": items}


@router.get("/library/{filename}")
def api_library_file(filename: str):
    path = library_dir() / safe_filename(filename)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.post("/upload")
async def api_upload_media(file: UploadFile = File(...)):
    """Upload an image straight to the library."""
    content, ext = await read_image_upload(file)
    d = library_dir()
    d.mkdir(parents=True, exist_ok=True)
    name = f"up_{uuid.uuid4().hex[:12]}{ext}"
    (d / name).write_bytes(content)
    return next(i for i in _library_items() if i["name"] == name)


# ── Deleting ────────────────────────────────────────────────────────


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
    elif origin == "proj":
        api = _web_api()
        if _is_project_upload(path.name) and not any(
            path.name in api._job_files(j) for j in db.get_jobs_by_project(parts["project"])
        ):
            path.unlink()
            proj = db.get_project_by_slug(parts["project"])
            if proj.image_url == f"local:{path.name}":
                db.update_project(parts["project"], image_url=None)
            api._invalidate_project_caches()
        else:
            api.api_delete_video(parts["project"], path.name)  # also its job, favourite and the thumbnail
    else:
        conv_id, file = parts["conversation_id"], parts["file"]
        for msg in db.get_chat_messages(conv_id):
            if any(i.get("file") == file for i in msg.media):
                db.update_chat_message(msg.id, media=[i for i in msg.media if i.get("file") != file])
        for lib in db.list_chat_library():
            if lib.conversation_id == conv_id and lib.item.get("file") == file:
                db.delete_chat_library_item(lib.media_id)
        path.unlink()
    return {"deleted": media_id}


# ── Clearing blocked generations ────────────────────────────────────

_blank_cache: dict[tuple[str, float], bool] = {}


def _is_blank_file(path: Path) -> bool:
    """is_blank_image for a saved file, remembered per file version (the
    Media page asks on every load, and a NAS reads slowly)."""
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return False
    if key not in _blank_cache:
        _blank_cache[key] = is_blank_image(path.read_bytes())
    return _blank_cache[key]


def _blocked_reason(conv_id: str, item: dict) -> str | None:
    """Why a chat media item counts as a blocked generation: "moderated" (a
    content filter refused it) or "black" (a black image saved before the
    app caught those); None otherwise."""
    if item.get("source") == "upload":
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
    out = []
    for msg in db.get_chat_messages_with_media():
        out += [(msg, i, r) for i in msg.media if (r := _blocked_reason(msg.conversation_id, i))]
    for lib in db.list_chat_library():
        if r := _blocked_reason(lib.conversation_id, lib.item):
            out.append((lib, lib.item, r))
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
    return {"cleared": len(found)}


# ── Using an item elsewhere ─────────────────────────────────────────


class ImportMedia(BaseModel):
    media_id: str
    target: Literal["project", "chat", "character"]
    project: str | None = None  # target "project": its slug
    prefix: Literal["src", "ref"] = "ref"  # …as a source image (src) or a reference (ref)
    conversation_id: str | None = None  # target "chat"
    character_id: int | None = None  # target "character"


@router.post("/import")
def api_import_media(data: ImportMedia):
    """Copy an image from the library to where it's being used:
    project   → {"image_url": "local:<file>"} for a Generate source/ref image
    chat      → {"file": "<file>"} to attach to the next message
    character → the character, with the image added"""
    origin, path, parts = resolve(data.media_id)
    if _kind(path) != "image":
        raise HTTPException(400, "Only images can be used here")
    db = get_db()
    ext = path.suffix.lower()

    if data.target == "project":
        proj = db.get_project_by_slug(data.project or "")
        if not proj:
            raise HTTPException(404, "Project not found")
        if origin == "proj" and parts["project"] == proj.slug and _is_project_upload(path.name):
            return {"image_url": f"local:{path.name}"}  # already one of this project's uploads
        folder = _web_api().ASSETS_DIR / proj.assets_folder
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{data.prefix}-{uuid.uuid4().hex[:12]}{ext}"
        shutil.copyfile(path, folder / name)
        return {"image_url": f"local:{name}"}

    if data.target == "chat":
        conv_id = data.conversation_id or ""
        if not db.get_conversation(conv_id):
            raise HTTPException(404, "Conversation not found")
        if origin == "chat" and parts["conversation_id"] == conv_id:
            return {"file": path.name}  # already in this chat
        d = _chat_dir(conv_id)
        d.mkdir(parents=True, exist_ok=True)
        name = f"up_{uuid.uuid4().hex[:12]}{ext}"
        shutil.copyfile(path, d / name)
        return {"file": name}

    char = db.get_character(data.character_id or 0)
    if not char:
        raise HTTPException(404, "Character not found")
    return characters.add_image_from_file(char, path)
