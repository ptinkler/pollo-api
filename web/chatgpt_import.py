"""
Importing chats from a ChatGPT data export (Settings → Data controls →
Export data), to carry them on here.

The export's zip goes in <data>/imports/: copied there, or uploaded from
the browser in chunks (it's often gigabytes; nginx takes 25 MB a request).
Inside it:
    conversations.json    every chat: a tree of messages ("mapping") and the
                          one shown ("current_node"). Only the shown branch is
                          exported, and the image tool's messages are left out.
    library_files.json    every file: its chat ("origination_thread_id"), when
                          it was made and its type. Generated images are only
                          linked to their chat here, not to a message.
    file_<id>.dat         the files themselves (older exports: file-<id>-name.ext)

Each ChatGPT turn (a prompt and the replies to it) becomes a prompt and one
reply here. Uploaded images are on their prompt; generated ones go on the
reply to the latest prompt sent before they were made.

New chats go in the "ChatGPT" space (made on the first import), seeded with
the defaults of any chat started there; they can be moved out like any
other. Importing again (a newer export) only adds what's new: chats, messages
and images remember their ids there, chats unchanged since are skipped, and
chats the user deleted here stay deleted. A chat carried on in ChatGPT gets
the new turns; if it was carried on here too, they're a separate branch.
"""

import contextlib
import contextvars
import json
import re
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from img2vid.common import config
from img2vid.common.metadata import get_db

from . import media
from .auth import verify_api_key
from .chat import CHAT_PREVIEW_SIZE, IMAGE_EXTS, ConversationCreate, _conv_dir, api_create_conversation
from .uploads import safe_filename

router = APIRouter(prefix="/api/chat/import", dependencies=[Depends(verify_api_key)])

SOURCE = "chatgpt"
SPACE_NAME = "ChatGPT"  # the space new imports go in
UPLOAD_CHUNK = 16 * 1024 * 1024  # bytes per upload request, under nginx's 25 MB cap
UPLOAD_STALE_SECONDS = 24 * 60 * 60  # unfinished uploads older than this are deleted
DEFAULT_TITLE = "Imported chat"
MISSING = "Not included in the ChatGPT export"
VIDEO_EXTS = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}
# Search citations ChatGPT leaves in replies: citeturn0search1
_CITATION = re.compile("[^]*|[-]")
_FILE_ID = re.compile(r"^(file[-_][A-Za-z0-9]+)")
# Its document blocks: :::writing{variant="document" title="…"} … :::
_WRITING_START = re.compile(r"^:::writing(?:\{([^}\n]*)\})?[ \t]*\n?", re.MULTILINE)
_WRITING_END = re.compile(r"^:::[ \t]*(?:\n|$)", re.MULTILINE)
_TITLE_ATTR = re.compile(r'title="([^"]*)"')


def _import_dir() -> Path:
    return config.ROOT_DIR / "imports"


# ── Reading the export ──────────────────────────────────────────────


@dataclass
class _Turn:
    """A prompt and the replies to it (no prompt: replies before the first one)."""

    prompt_id: str | None
    prompt: str = ""
    time: float = 0.0
    uploads: list[str] = field(default_factory=list)  # file ids
    reply: list[str] = field(default_factory=list)
    reply_time: float | None = None
    model: str | None = None
    generated: list[dict] = field(default_factory=list)  # {"id", "name", "mime"}


class _Export:
    def __init__(self, zf: zipfile.ZipFile):
        self.zf = zf
        self.new_files: list[Path] = []  # images written by this import (their thumbnails are made after)
        self.files: dict[str, str] = {}  # file id → zip entry
        for name in zf.namelist():
            m = _FILE_ID.match(name.rsplit("/", 1)[-1])
            if m and not name.endswith("/"):
                self.files.setdefault(m.group(1), name)
        self.conversations: list[dict] = json.loads(zf.read("conversations.json"))
        self.library: dict[str, list[dict]] = {}  # chat id → its files
        if "library_files.json" in zf.namelist():
            for f in json.loads(zf.read("library_files.json")):
                if f.get("origination_thread_id") and f.get("file_id"):
                    self.library.setdefault(f["origination_thread_id"], []).append(f)

    def read(self, file_id: str) -> bytes | None:
        name = self.files.get(file_id)
        return self.zf.read(name) if name else None


def _chain(data: dict) -> list[dict]:
    """The messages on the exported branch, first first."""
    mapping = data.get("mapping") or {}
    node_id = data.get("current_node")
    if node_id not in mapping:  # no shown branch recorded: the newest leaf
        leaves = [k for k, n in mapping.items() if not n.get("children") and n.get("message")]
        node_id = max(leaves, key=lambda k: mapping[k]["message"].get("create_time") or 0, default=None)
    out, seen = [], set()
    while node_id in mapping and node_id not in seen:
        seen.add(node_id)
        node = mapping[node_id]
        if node.get("message"):
            out.append(node["message"])
        node_id = node.get("parent")
    return out[::-1]


def _parts(msg: dict) -> tuple[str, list[str]]:
    """A message's text and the files it shows."""
    texts, files = [], []
    for p in (msg.get("content") or {}).get("parts") or []:
        if isinstance(p, str):
            texts.append(p)
        elif isinstance(p, dict) and p.get("content_type") == "image_asset_pointer":
            file_id = (p.get("asset_pointer") or "").split("://")[-1]
            if file_id:
                files.append(file_id)
    return _plain("\n".join(texts)), files


def _plain(text: str) -> str:
    """ChatGPT's markup out of a reply: citations, and document blocks with their title in bold."""

    def start(m: re.Match) -> str:
        title = _TITLE_ATTR.search(m.group(1) or "")
        return f"**{title.group(1)}**\n\n" if title and title.group(1) else ""

    text = _WRITING_END.sub("", _WRITING_START.sub(start, _CITATION.sub("", text)))
    return text.strip()


def _shown(msg: dict) -> bool:
    """A message the ChatGPT page shows, as opposed to tool calls, reasoning and hidden context."""
    meta = msg.get("metadata") or {}
    if meta.get("is_visually_hidden_from_conversation") or meta.get("is_user_system_message"):
        return False
    if msg.get("recipient") not in (None, "all"):
        return False
    return (msg.get("content") or {}).get("content_type") in ("text", "multimodal_text")


def _current(turns: list[_Turn], time: float) -> _Turn:
    """The turn a reply belongs to, starting one when it comes before any prompt."""
    if not turns:
        turns.append(_Turn(None, time=time))
    return turns[-1]


def _turns(data: dict, library: list[dict]) -> list[_Turn]:
    turns: list[_Turn] = []
    time = data.get("create_time") or 0.0
    for msg in _chain(data):
        time = msg.get("create_time") or time
        role = (msg.get("author") or {}).get("role")
        text, files = _parts(msg)
        if role == "tool" and files:
            # Older exports kept the image tool's results: those are generated images
            _current(turns, time).generated += [{"id": f} for f in files]
        elif not _shown(msg):
            continue
        elif role == "user" and (text or files):
            turns.append(_Turn(msg["id"], text, time, files))
        elif role == "assistant":
            turn = _current(turns, time)
            turn.reply += [text] if text else []
            turn.reply_time = turn.reply_time or msg.get("create_time")
            turn.model = (msg.get("metadata") or {}).get("model_slug") or turn.model
    if turns:
        _place_generated(turns, library)
    return turns


def _place_generated(turns: list[_Turn], library: list[dict]) -> None:
    """Generated images, which the export doesn't link to a message: each goes
    on the reply to the latest prompt sent before it was made."""
    shown = {f for t in turns for f in t.uploads} | {g["id"] for t in turns for g in t.generated}
    for f in sorted(library, key=lambda f: f.get("created_at") or ""):
        if f["file_id"] in shown:
            continue
        try:
            made = datetime.fromisoformat(f["created_at"]).timestamp()
        except (KeyError, TypeError, ValueError):
            continue
        turn = next((t for t in reversed(turns) if t.time <= made), turns[0])
        turn.generated.append({"id": f["file_id"], "name": f.get("file_name"), "mime": f.get("mime_type")})


def _ext(raw: bytes, mime: str | None) -> str:
    if mime in IMAGE_EXTS or mime in VIDEO_EXTS:
        return IMAGE_EXTS.get(mime) or VIDEO_EXTS[mime]
    if raw.startswith(b"\x89PNG"):
        return ".png"
    if raw.startswith(b"\xff\xd8"):
        return ".jpg"
    if raw.startswith(b"GIF8"):
        return ".gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    if raw[4:8] == b"ftyp":
        return ".mp4"
    return ".png"


# ── Importing ───────────────────────────────────────────────────────


class _ChatMedia:
    """Media items for one chat, writing each export file into its folder once."""

    def __init__(self, export: _Export, conv_id: str, known: list[dict], stats: dict):
        self.export, self.conv_id, self.stats = export, conv_id, stats
        self.saved = {i["import_file"]: i for i in known if i.get("import_file") and i.get("file")}

    def item(self, file_id: str, source: str, mime: str | None = None, name: str | None = None) -> dict | None:
        """None for a generated file that isn't in the export (one that never finished)."""
        fields: dict[str, Any] = {"id": uuid.uuid4().hex[:8], "source": source, "import_file": file_id}
        if source == "generated":
            stem = Path(name or "").stem
            fields.update(model=SOURCE, prompt=stem if stem and stem.lower() != "image" else None)
        if file_id in self.saved:
            prev = self.saved[file_id]
            return {**fields, "kind": prev["kind"], "status": "done", "file": prev["file"]}
        raw = self.export.read(file_id)
        if raw is None:
            self.stats["missing_images"] += 1
            if source == "generated":
                return None
            return {**fields, "kind": "image", "status": "error", "file": None, "error": MISSING}
        ext = _ext(raw, mime)
        kind = "video" if ext in VIDEO_EXTS.values() else "image"
        file = f"{'up' if source == 'upload' else 'img'}_{uuid.uuid4().hex[:12]}{ext}"
        (_conv_dir(self.conv_id) / file).write_bytes(raw)
        self.export.new_files.append(_conv_dir(self.conv_id) / file)
        self.stats["images"] += 1
        item = {**fields, "kind": kind, "status": "done", "file": file}
        self.saved[file_id] = item
        return item


def _when(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts) if ts else None


class _Merge:
    """What one chat's import adds to it: new messages (`rows`, each after
    the one before on the exported branch) and changes to replies imported
    before (`updates`)."""

    def __init__(self, export: _Export, conv_id: str, known: dict, stats: dict):
        self.known = known
        self.media = _ChatMedia(export, conv_id, [i for m in known.values() for i in m.media], stats)
        self.rows: list[dict] = []
        self.updates: dict[int, dict] = {}
        self.parent: dict[str, Any] = {"parent_id": None}

    def _add(self, import_id: str, **row) -> None:
        self.rows.append({**self.parent, "import_id": import_id, **row})
        self.parent = {"parent_import_id": import_id}

    def prompt(self, turn: _Turn) -> None:
        if turn.prompt_id in self.known:
            self.parent = {"parent_id": self.known[turn.prompt_id].id}
            return
        self._add(
            turn.prompt_id,
            role="user",
            content=turn.prompt,
            media=[self.media.item(f, "upload") for f in turn.uploads],
            created_at=_when(turn.time) or datetime.now(),
        )

    def reply(self, turn: _Turn) -> None:
        reply_id = f"reply:{turn.prompt_id or ''}"
        content = "\n\n".join(turn.reply)
        prev = self.known.get(reply_id)
        have = {i.get("import_file") for i in prev.media} if prev else set()
        items = [
            i
            for g in turn.generated
            if g["id"] not in have and (i := self.media.item(g["id"], "generated", g.get("mime"), g.get("name")))
        ]
        if prev:
            # A reply still being written when the last export was made
            fields: dict[str, Any] = {"content": content} if content and content != prev.content else {}
            if items:
                fields["media"] = prev.media + items
            if fields:
                self.updates[prev.id] = fields
            self.parent = {"parent_id": prev.id}
        elif content or items:
            self._add(
                reply_id,
                role="assistant",
                content=content,
                media=items,
                model=f"{SOURCE}/{turn.model}" if turn.model else None,
                created_at=_when(turn.reply_time or turn.time) or datetime.now(),
            )


def _import_space_id() -> int:
    """The "ChatGPT" space, made the first time it's needed (or again, if renamed or deleted)."""
    db = get_db()
    space = next((s for s in db.list_spaces() if s.name.strip().lower() == SPACE_NAME.lower()), None)
    return (space or db.save_space(name=SPACE_NAME)).id


def _import_conversation(export: _Export, data: dict, conv, stats: dict) -> str:
    """Import one chat, or what's new in it: "new", "updated", "unchanged" or "empty"."""
    db = get_db()
    turns = _turns(data, export.library.get(data["id"], []))
    fresh = conv is None
    if fresh and not turns:
        return "empty"
    if fresh:
        # Made like a chat started in the space, so it gets the same defaults
        if "space_id" not in stats:
            stats["space_id"] = _import_space_id()
        title = (data.get("title") or DEFAULT_TITLE).strip()[:255] or DEFAULT_TITLE
        made = api_create_conversation(ConversationCreate(title=title, space_id=stats["space_id"]))
        conv = db.update_conversation(
            made["id"],
            import_source=SOURCE,
            import_id=data["id"],
            created_at=_when(data.get("create_time")) or datetime.now(),
        )
    known = {} if fresh else db.get_chat_import_ids(conv.id)
    leaf = None if fresh else db.get_chat_leaf_id(conv.id)
    # Carried on here since: keep showing that, the new turns are a branch
    show = leaf is None or any(m.id == leaf for m in known.values())

    merge = _Merge(export, conv.id, known, stats)
    for turn in turns:
        if turn.prompt_id:
            merge.prompt(turn)
        merge.reply(turn)
    changed = bool(merge.rows or merge.updates)
    changed_at = _when(data.get("update_time"))
    if fresh:
        updated_at = changed_at
    else:
        updated_at = max(filter(None, [changed_at, conv.updated_at])) if changed else conv.updated_at
    db.add_imported_messages(conv.id, merge.rows, merge.updates, data.get("update_time"), updated_at, show)
    if fresh:
        return "new"
    return "updated" if changed else "unchanged"


def run_import(path: Path, progress: dict | None = None) -> dict:
    """Import the export at `path`. Returns (and keeps `progress` up to
    date with) how many chats were new, updated, unchanged or skipped."""
    stats = progress if progress is not None else {}
    stats.update(
        total=0,
        processed=0,
        new=0,
        updated=0,
        unchanged=0,
        deleted=0,
        empty=0,
        images=0,
        missing_images=0,
        failed=[],
    )
    stats.pop("space_id", None)  # the space new chats went in, once there are some
    db = get_db()
    with zipfile.ZipFile(path) as zf:
        if "conversations.json" not in zf.namelist():
            raise ValueError("Not a ChatGPT export: there's no conversations.json in it")
        export = _Export(zf)
        stats["total"] = len(export.conversations)
        imported = db.get_imported_conversations(SOURCE)
        skips = db.get_import_skips(SOURCE)
        for data in export.conversations:
            conv_id = data.get("id") or data.get("conversation_id")
            data["id"] = conv_id
            conv = imported.get(conv_id)
            if not conv_id:
                outcome = "empty"
            elif conv_id in skips:
                outcome = "deleted"
            elif conv and conv.import_updated_at == data.get("update_time"):
                outcome = "unchanged"
            else:
                try:
                    outcome = _import_conversation(export, data, conv, stats)
                except Exception as e:  # noqa: BLE001 — one bad chat shouldn't stop the rest
                    outcome = None
                    stats["failed"].append({"title": data.get("title"), "error": str(e)})
            if outcome:
                stats[outcome] += 1
            stats["processed"] += 1
    if export.new_files:
        threading.Thread(target=_warm_thumbnails, args=(export.new_files,), daemon=True).start()
    return stats


def _warm_thumbnails(paths: list[Path]) -> None:
    """Make the new images' grid thumbnails and chat previews now, one at a
    time in the background, so opening the chats and Media page later
    doesn't wait for hundreds of them to be made."""
    for path in paths:
        for size in (media.THUMB_SIZE, CHAT_PREVIEW_SIZE):
            media.make_thumb(path, size)


# ── Routes ──────────────────────────────────────────────────────────

_job: dict[str, Any] = {"state": "idle"}
_job_lock = threading.Lock()


class StartImport(BaseModel):
    file: str  # a zip in the imports folder


@router.get("/chatgpt")
def api_import_status():
    """The exports in the imports folder (newest first) and the last import's progress."""
    folder = _import_dir()
    files = sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.is_dir() else []
    return {
        "folder": str(folder),
        "files": [
            {
                "name": p.name,
                "size": p.stat().st_size,
                "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            }
            for p in files
        ],
        "job": dict(_job),
    }


@router.post("/chatgpt")
def api_start_import(data: StartImport):
    """Start importing an export in the background; progress is in GET."""
    path = _import_dir() / safe_filename(data.file)
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise HTTPException(404, "That export isn't in the imports folder")
    with _job_lock:
        if _job.get("state") == "running":
            raise HTTPException(409, "An import is already running")
        _job.clear()
        _job.update(state="running", file=path.name, started_at=datetime.now().isoformat())
    # Copy the request context so imported rows belong to the signed-in user
    ctx = contextvars.copy_context()
    threading.Thread(target=lambda: ctx.run(_run_job, path), daemon=True).start()
    return dict(_job)


def _run_job(path: Path) -> None:
    try:
        run_import(path, _job)
        _job["state"] = "done"
    except Exception as e:  # noqa: BLE001 — reported to the UI
        _job.update(state="error", error=str(e))


# ── Uploading an export ─────────────────────────────────────────────
# In chunks: start an upload, send each chunk with its offset (resending one
# replaces what was there from that offset), and the last one turns the
# upload into <name>.zip in the imports folder.


class StartUpload(BaseModel):
    name: str
    size: int = Field(gt=0)


def _upload_paths(upload_id: str) -> tuple[Path, Path]:
    if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
        raise HTTPException(404, "Upload not found")
    folder = _import_dir()
    return folder / f".upload-{upload_id}.part", folder / f".upload-{upload_id}.json"


def _clear_stale_uploads(folder: Path) -> None:
    for p in folder.glob(".upload-*"):
        with contextlib.suppress(OSError):
            if time.time() - p.stat().st_mtime > UPLOAD_STALE_SECONDS:
                p.unlink()


@router.post("/chatgpt/uploads")
def api_start_upload(data: StartUpload):
    name = Path(data.name.replace("\\", "/")).name
    if not name.lower().endswith(".zip") or name.startswith("."):
        raise HTTPException(400, "Choose the .zip that ChatGPT's export email links to")
    folder = _import_dir()
    folder.mkdir(parents=True, exist_ok=True)
    _clear_stale_uploads(folder)
    upload_id = uuid.uuid4().hex
    part, meta = _upload_paths(upload_id)
    part.touch()
    meta.write_text(json.dumps({"name": name, "size": data.size}))
    return {"id": upload_id, "received": 0, "chunk_size": UPLOAD_CHUNK}


@router.post("/chatgpt/uploads/{upload_id}")
async def api_upload_chunk(upload_id: str, offset: int = Form(..., ge=0), chunk: UploadFile = File(...)):
    """Write one chunk at `offset`. Returns how much has arrived, and once
    it's all there, the export's `file` name in the imports folder."""
    part, meta = _upload_paths(upload_id)
    if not part.is_file() or not meta.is_file():
        raise HTTPException(404, "Upload not found (unfinished uploads are cleared after a day)")
    info = json.loads(meta.read_text())
    raw = await chunk.read(UPLOAD_CHUNK + 1)
    if len(raw) > UPLOAD_CHUNK or offset + len(raw) > info["size"]:
        raise HTTPException(400, "Chunk too large")
    return await run_in_threadpool(_write_chunk, part, meta, info, offset, raw)


def _write_chunk(part: Path, meta: Path, info: dict, offset: int, raw: bytes) -> dict:
    received = part.stat().st_size
    if offset > received:
        raise HTTPException(409, f"Expected the chunk at {received}")
    with part.open("r+b") as f:
        f.truncate(offset)  # a resent chunk replaces what was there
        f.seek(offset)
        f.write(raw)
    received = offset + len(raw)
    if received < info["size"]:
        return {"received": received}
    if not zipfile.is_zipfile(part):
        part.unlink()
        meta.unlink()
        raise HTTPException(400, "That isn't a zip file")
    with zipfile.ZipFile(part) as zf:
        if "conversations.json" not in zf.namelist():
            part.unlink()
            meta.unlink()
            raise HTTPException(400, "Not a ChatGPT export: there's no conversations.json in it")
    target = part.parent / info["name"]
    n = 1
    while target.exists():
        n += 1
        target = part.parent / f"{Path(info['name']).stem} ({n}).zip"
    part.rename(target)
    meta.unlink()
    return {"received": received, "file": target.name}


@router.delete("/chatgpt/uploads/{upload_id}")
def api_cancel_upload(upload_id: str):
    for p in _upload_paths(upload_id):
        p.unlink(missing_ok=True)
    return {"cancelled": upload_id}
