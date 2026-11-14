"""Importing chats from a ChatGPT data export (Settings → Data controls → Export data), to carry them on here.

The same upload and import also take this app's own chat export (see
web/chat_export.py), told apart by what's in the zip.

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
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NotRequired, TypedDict, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from web import chat_export, media
from web.chat import CHAT_PREVIEW_SIZE, ConversationCreate, api_create_conversation, conversation_dir
from web.core import config
from web.core.metadata import current_tenant, get_db
from web.core.metadata.models import ChatConversation, ChatMessage
from web.media_types import IMAGE_EXTS, VIDEO_EXTS
from web.types import JsonValue
from web.uploads import safe_filename
from web.users import require_user

if TYPE_CHECKING:
    from web.core.metadata.imports import ImportedMessage, ImportedMessageUpdate

router = APIRouter(prefix="/api/chat/import", dependencies=[Depends(require_user)])


class _ImportStats(TypedDict):
    total: int
    processed: int
    new: int
    updated: int
    unchanged: int
    deleted: int
    empty: int
    images: int
    missing_images: int
    failed: list[dict[str, JsonValue]]
    space_id: NotRequired[int]


class _UploadMeta(TypedDict):
    name: str
    size: int


SOURCE = "chatgpt"
SPACE_NAME = "ChatGPT"  # the space new imports go in
UPLOAD_CHUNK = 16 * 1024 * 1024  # bytes per upload request, under nginx's 25 MB cap
UPLOAD_STALE_SECONDS = 24 * 60 * 60  # unfinished uploads older than this are deleted
DEFAULT_TITLE = "Imported chat"
_NOT_AN_EXPORT = "Not a chat export: it has neither a ChatGPT conversations.json nor a pollo-chats.json"
MISSING = "Not included in the ChatGPT export"

# Search citations ChatGPT leaves in replies: citeturn0search1
_CITATION = re.compile("[^]*|[-]")
_FILE_ID = re.compile(r"^(file[-_][A-Za-z0-9]+)")
# Its document blocks: :::writing{variant="document" title="…"} … :::
_WRITING_START = re.compile(r"^:::writing(?:\{([^}\n]*)\})?[ \t]*\n?", re.MULTILINE)
_WRITING_END = re.compile(r"^:::[ \t]*(?:\n|$)", re.MULTILINE)
_TITLE_ATTR = re.compile(r'title="([^"]*)"')


def _import_dir() -> Path:
    # Per-tenant (<data>/imports/<uid>/) so one user can't import another user's
    # uploaded export by guessing its filename.
    base = config.ROOT_DIR / "imports"
    uid = current_tenant()
    return base / uid if uid else base


class _GeneratedFile(TypedDict):
    id: str
    name: NotRequired[str | None]
    mime: NotRequired[str | None]


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
    generated: list[_GeneratedFile] = field(default_factory=list)


def _json_object(value: JsonValue) -> Mapping[str, JsonValue]:
    return cast("Mapping[str, JsonValue]", value) if isinstance(value, Mapping) else {}


def _json_array(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def _timestamp(value: JsonValue) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


class _Export:
    def __init__(self, zf: zipfile.ZipFile) -> None:
        self.zf = zf
        self.new_files: list[Path] = []  # images written by this import (their thumbnails are made after)
        self.files: dict[str, str] = {}  # file id → zip entry
        for name in zf.namelist():
            m = _FILE_ID.match(name.rsplit("/", 1)[-1])
            if m and not name.endswith("/"):
                self.files.setdefault(m.group(1), name)
        self.conversations = cast("list[dict[str, JsonValue]]", json.loads(zf.read("conversations.json")))
        self.library: dict[str, list[Mapping[str, JsonValue]]] = {}  # chat id → its files
        if "library_files.json" in zf.namelist():
            for f in cast("list[dict[str, JsonValue]]", json.loads(zf.read("library_files.json"))):
                thread_id = f.get("origination_thread_id")
                if isinstance(thread_id, str) and f.get("file_id"):
                    self.library.setdefault(thread_id, []).append(f)

    def read(self, file_id: str) -> bytes | None:
        name = self.files.get(file_id)
        return self.zf.read(name) if name else None


def _chain(data: Mapping[str, JsonValue]) -> list[Mapping[str, JsonValue]]:
    """The messages on the exported branch, first first."""
    mapping = _json_object(data.get("mapping"))
    current_node = data.get("current_node")
    node_id: str | None = current_node if isinstance(current_node, str) else None
    if node_id not in mapping:  # no shown branch recorded: the newest leaf
        leaves = [
            key
            for key, value in mapping.items()
            if not _json_array(_json_object(value).get("children")) and _json_object(value).get("message")
        ]
        node_id = max(
            leaves,
            key=lambda key: _timestamp(_json_object(_json_object(mapping[key]).get("message")).get("create_time")) or 0,
            default=None,
        )
    out: list[Mapping[str, JsonValue]] = []
    seen: set[str] = set()
    while node_id is not None and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        node = _json_object(mapping[node_id])
        message = node.get("message")
        if message:
            out.append(_json_object(message))
        parent = node.get("parent")
        node_id = parent if isinstance(parent, str) else None
    return out[::-1]


def _parts(msg: Mapping[str, JsonValue]) -> tuple[str, list[str]]:
    """A message's text and the files it shows."""
    texts: list[str] = []
    files: list[str] = []
    for raw_part in _json_array(_json_object(msg.get("content")).get("parts")):
        if isinstance(raw_part, str):
            texts.append(raw_part)
            continue
        part = _json_object(raw_part)
        if part.get("content_type") == "image_asset_pointer":
            pointer = part.get("asset_pointer")
            file_id = pointer.split("://")[-1] if isinstance(pointer, str) else ""
            if file_id:
                files.append(file_id)
    return _plain("\n".join(texts)), files


def _plain(text: str) -> str:
    """ChatGPT's markup out of a reply: citations, and document blocks with their title in bold."""

    def start(m: re.Match[str]) -> str:
        title = _TITLE_ATTR.search(m.group(1) or "")
        return f"**{title.group(1)}**\n\n" if title and title.group(1) else ""

    text = _WRITING_END.sub("", _WRITING_START.sub(start, _CITATION.sub("", text)))
    return text.strip()


def _shown(msg: Mapping[str, JsonValue]) -> bool:
    """A message the ChatGPT page shows, as opposed to tool calls, reasoning and hidden context."""
    meta = _json_object(msg.get("metadata"))
    if meta.get("is_visually_hidden_from_conversation") or meta.get("is_user_system_message"):
        return False
    if msg.get("recipient") not in (None, "all"):
        return False
    return _json_object(msg.get("content")).get("content_type") in ("text", "multimodal_text")


def _current(turns: list[_Turn], time: float) -> _Turn:
    """The turn a reply belongs to, starting one when it comes before any prompt."""
    if not turns:
        turns.append(_Turn(None, time=time))
    return turns[-1]


def _turns(data: Mapping[str, JsonValue], library: list[Mapping[str, JsonValue]]) -> list[_Turn]:
    turns: list[_Turn] = []
    time = _timestamp(data.get("create_time")) or 0.0
    for msg in _chain(data):
        time = _timestamp(msg.get("create_time")) or time
        role = _json_object(msg.get("author")).get("role")
        text, files = _parts(msg)
        if role == "tool" and files:
            # Older exports kept the image tool's results: those are generated images
            _current(turns, time).generated.extend({"id": file_id} for file_id in files)
        elif not _shown(msg):
            continue
        elif role == "user" and (text or files):
            msg_id = msg.get("id")
            if isinstance(msg_id, str):
                turns.append(_Turn(msg_id, text, time, files))
        elif role == "assistant":
            turn = _current(turns, time)
            turn.reply += [text] if text else []
            turn.reply_time = turn.reply_time or _timestamp(msg.get("create_time"))
            model = _json_object(msg.get("metadata")).get("model_slug")
            turn.model = model if isinstance(model, str) else turn.model
    if turns:
        _place_generated(turns, library)
    return turns


def _place_generated(turns: list[_Turn], library: list[Mapping[str, JsonValue]]) -> None:
    """Generated images, which the export doesn't link to a message: each goes.

    on the reply to the latest prompt sent before it was made.
    """
    shown = {f for t in turns for f in t.uploads} | {g["id"] for t in turns for g in t.generated}
    for f in sorted(library, key=lambda file: str(file.get("created_at") or "")):
        file_id = f.get("file_id")
        if not isinstance(file_id, str) or file_id in shown:
            continue
        created_at = f.get("created_at")
        if not isinstance(created_at, str):
            continue
        try:
            made = datetime.fromisoformat(created_at).timestamp()
        except ValueError:
            continue
        turn = next((t for t in reversed(turns) if t.time <= made), turns[0])
        name, mime = f.get("file_name"), f.get("mime_type")
        turn.generated.append(
            {
                "id": file_id,
                "name": name if isinstance(name, str) else None,
                "mime": mime if isinstance(mime, str) else None,
            }
        )


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


class _ChatMedia:
    """Media items for one chat, writing each export file into its folder once."""

    def __init__(self, export: _Export, conv_id: str, known: list[dict[str, JsonValue]], stats: _ImportStats) -> None:
        self.export, self.conv_id, self.stats = export, conv_id, stats
        self.saved: dict[str, dict[str, JsonValue]] = {}
        for item in known:
            import_file, file = item.get("import_file"), item.get("file")
            if isinstance(import_file, str) and isinstance(file, str):
                self.saved[import_file] = item

    def item(
        self, file_id: str, source: str, mime: str | None = None, name: str | None = None
    ) -> dict[str, JsonValue] | None:
        """None for a generated file that isn't in the export (one that never finished)."""
        fields: dict[str, JsonValue] = {"id": uuid.uuid4().hex[:8], "source": source, "import_file": file_id}
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
        (conversation_dir(self.conv_id) / file).write_bytes(raw)
        self.export.new_files.append(conversation_dir(self.conv_id) / file)
        self.stats["images"] += 1
        item = {**fields, "kind": kind, "status": "done", "file": file}
        self.saved[file_id] = item
        return item


def _when(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts).astimezone().replace(tzinfo=None) if ts else None


class _Merge:
    """What one chat's import adds to it: new messages (`rows`, each after.

    the one before on the exported branch) and changes to replies imported
    before (`updates`).
    """

    def __init__(self, export: _Export, conv_id: str, known: dict[str, ChatMessage], stats: _ImportStats) -> None:
        self.known = known
        self.media = _ChatMedia(export, conv_id, [i for m in known.values() for i in m.media], stats)
        self.rows: list[ImportedMessage] = []
        self.updates: dict[int, ImportedMessageUpdate] = {}
        self.parent: dict[str, str | int | None] = {"parent_id": None}

    def _add(self, import_id: str, **row: JsonValue | datetime) -> None:
        self.rows.append(cast("ImportedMessage", {**self.parent, "import_id": import_id, **row}))
        self.parent = {"parent_import_id": import_id}

    def prompt(self, turn: _Turn) -> None:
        if turn.prompt_id is None:
            return
        if turn.prompt_id in self.known:
            self.parent = {"parent_id": self.known[turn.prompt_id].id}
            return
        self._add(
            turn.prompt_id,
            role="user",
            content=turn.prompt,
            media=[self.media.item(f, "upload") for f in turn.uploads],
            created_at=_when(turn.time) or datetime.now().astimezone().replace(tzinfo=None),
        )

    def reply(self, turn: _Turn) -> None:
        reply_id = f"reply:{turn.prompt_id or ''}"
        content = "\n\n".join(turn.reply)
        prev = self.known.get(reply_id)
        have: set[str] = (
            {import_file for item in prev.media if isinstance(import_file := item.get("import_file"), str)}
            if prev
            else set()
        )
        items = [
            i
            for g in turn.generated
            if g["id"] not in have and (i := self.media.item(g["id"], "generated", g.get("mime"), g.get("name")))
        ]
        if prev:
            # A reply still being written when the last export was made
            fields: ImportedMessageUpdate = {"content": content} if content and content != prev.content else {}
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
                created_at=_when(turn.reply_time or turn.time) or datetime.now().astimezone().replace(tzinfo=None),
            )


def _import_space_id() -> int:
    """The "ChatGPT" space, made the first time it's needed (or again, if renamed or deleted)."""
    db = get_db()
    space = next((s for s in db.list_spaces() if s.name.strip().lower() == SPACE_NAME.lower()), None)
    if space is None:
        space = db.save_space(name=SPACE_NAME)
    if space is None:
        raise LookupError("Could not create the ChatGPT import space")  # noqa: TRY003
    return space.id


def _new_imported_conversation(data: Mapping[str, JsonValue], stats: _ImportStats) -> ChatConversation:
    """Create a chat for a new ChatGPT import."""
    db = get_db()
    # Made like a chat started in the space, so it gets the same defaults.
    space_id = stats.get("space_id")
    if space_id is None:
        space_id = stats["space_id"] = _import_space_id()
    import_id = data.get("id")
    if not isinstance(import_id, str):
        raise TypeError(import_id)
    title_value = data.get("title")
    title = (title_value if isinstance(title_value, str) else DEFAULT_TITLE).strip()[:255] or DEFAULT_TITLE
    made = api_create_conversation(ConversationCreate(title=title, space_id=space_id))
    made_id = cast("Mapping[str, JsonValue]", made).get("id")
    if not isinstance(made_id, str):
        raise TypeError(made_id)
    create_time = data.get("create_time")
    timestamp = (
        float(create_time) if isinstance(create_time, int | float) and not isinstance(create_time, bool) else None
    )
    conv = db.update_conversation(
        made_id,
        import_source=SOURCE,
        import_id=import_id,
        created_at=_when(timestamp) or datetime.now().astimezone().replace(tzinfo=None),
    )
    if conv is None:
        raise LookupError(made_id)
    return conv


def _import_conversation(
    export: _Export, data: dict[str, JsonValue], conv: ChatConversation | None, stats: _ImportStats
) -> str:
    """Import one chat, or what's new in it: "new", "updated", "unchanged" or "empty"."""
    db = get_db()
    conv_id = data.get("id")
    if not isinstance(conv_id, str):
        raise TypeError(conv_id)
    turns = _turns(data, export.library.get(conv_id, []))
    fresh = conv is None
    if fresh and not turns:
        return "empty"
    imported_conv = _new_imported_conversation(cast("Mapping[str, JsonValue]", data), stats) if conv is None else conv
    known: dict[str, ChatMessage] = {} if fresh else db.get_chat_import_ids(imported_conv.id)
    leaf = None if fresh else db.get_chat_leaf_id(imported_conv.id)
    # Carried on here since: keep showing that, the new turns are a branch
    show = leaf is None or any(m.id == leaf for m in known.values())

    merge = _Merge(export, imported_conv.id, known, stats)
    for turn in turns:
        if turn.prompt_id:
            merge.prompt(turn)
        merge.reply(turn)
    changed = bool(merge.rows or merge.updates)
    changed_at = _when(_timestamp(data.get("update_time")))
    if fresh:
        updated_at = changed_at
    else:
        updated_at = max(filter(None, [changed_at, conv.updated_at])) if changed else conv.updated_at
    db.add_imported_messages(
        imported_conv.id, merge.rows, merge.updates, _timestamp(data.get("update_time")), updated_at, show
    )
    if fresh:
        return "new"
    return "updated" if changed else "unchanged"


def run_import(path: Path, progress: dict[str, JsonValue] | None = None) -> _ImportStats:
    """Import the export at `path`.

    Returns (and keeps `progress` up to
    date with) how many chats were new, updated, unchanged or skipped.
    """
    stats: _ImportStats = cast("_ImportStats", progress) if progress is not None else cast("_ImportStats", {})
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
        if chat_export.is_native_export(zf):
            return _run_native(zf, stats)
        if "conversations.json" not in zf.namelist():
            raise ValueError(_NOT_AN_EXPORT)
        export = _Export(zf)
        stats["total"] = len(export.conversations)
        imported = db.get_imported_conversations(SOURCE)
        skips = db.get_import_skips(SOURCE)
        for data in export.conversations:
            conv_id = data.get("id") or data.get("conversation_id")
            if not isinstance(conv_id, str):
                outcome = "empty"
            else:
                data["id"] = conv_id
                conv = imported.get(conv_id)
                if conv_id in skips:
                    outcome = "deleted"
                elif conv and conv.import_updated_at == _timestamp(data.get("update_time")):
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


def _run_native(zf: zipfile.ZipFile, stats: _ImportStats) -> _ImportStats:
    """This app's own export (from here or another server)."""
    written = chat_export.import_native(zf, cast("dict[str, JsonValue]", stats))
    if written:
        threading.Thread(target=_warm_thumbnails, args=(written,), daemon=True).start()
    return stats


def _warm_thumbnails(paths: list[Path]) -> None:
    """Make the new images' grid thumbnails and chat previews now, one at a.

    time in the background, so opening the chats and Media page later
    doesn't wait for hundreds of them to be made.
    """
    for path in paths:
        for size in (media.THUMB_SIZE, CHAT_PREVIEW_SIZE):
            media.make_thumb(path, size)


# Per-tenant import progress, keyed by user id (so one user's import status and
# single-flight don't leak into or block another's).
_jobs: dict[str, dict[str, JsonValue]] = {}
_job_lock = threading.Lock()


def _job_key() -> str:
    return current_tenant() or ""


def _current_job() -> dict[str, JsonValue]:
    return _jobs.get(_job_key(), {"state": "idle"})


class StartImport(BaseModel):
    """Name of an export zip already stored in the imports folder."""

    file: str  # a zip in the imports folder


@router.get("/chatgpt")
def api_import_status() -> dict[str, JsonValue]:
    """The exports in the imports folder (newest first) and this user's last import's progress."""
    folder = _import_dir()
    files = sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.is_dir() else []
    return {
        "folder": str(folder),
        "files": [
            {
                "name": p.name,
                "size": p.stat().st_size,
                "modified": datetime.fromtimestamp(p.stat().st_mtime).astimezone().replace(tzinfo=None).isoformat(),
            }
            for p in files
        ],
        "job": dict(_current_job()),
    }


@router.post("/chatgpt")
def api_start_import(data: StartImport) -> dict[str, JsonValue]:
    """Start importing an export in the background; progress is in GET."""
    path = _import_dir() / safe_filename(data.file)
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise HTTPException(404, "That export isn't in the imports folder")
    key = _job_key()
    with _job_lock:
        if _jobs.get(key, {}).get("state") == "running":
            raise HTTPException(409, "An import is already running")
        job: dict[str, JsonValue] = {
            "state": "running",
            "file": path.name,
            "started_at": datetime.now().astimezone().replace(tzinfo=None).isoformat(),
        }
        _jobs[key] = job
    # Copy the request context so imported rows belong to the signed-in user
    ctx = contextvars.copy_context()
    threading.Thread(target=lambda: ctx.run(_run_job, path, job), daemon=True).start()
    return dict(job)


def _run_job(path: Path, job: dict[str, JsonValue]) -> None:
    try:
        run_import(path, job)
        job["state"] = "done"
    except Exception as e:  # noqa: BLE001 — report unexpected worker failures to the UI
        job.update(state="error", error=str(e))


# In chunks: start an upload, send each chunk with its offset (resending one
# replaces what was there from that offset), and the last one turns the
# upload into <name>.zip in the imports folder.


class StartUpload(BaseModel):
    """Original filename and total byte size for a chunked export upload."""

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
def api_start_upload(data: StartUpload) -> dict[str, int | str]:
    """Start a chunked upload and return its ID and chunk size."""
    name = Path(data.name.replace("\\", "/")).name
    if not name.lower().endswith(".zip") or name.startswith("."):
        raise HTTPException(400, "Choose a .zip: a chat export from here, or the one ChatGPT's export email links to")
    folder = _import_dir()
    folder.mkdir(parents=True, exist_ok=True)
    _clear_stale_uploads(folder)
    upload_id = uuid.uuid4().hex
    part, meta = _upload_paths(upload_id)
    part.touch()
    meta.write_text(json.dumps({"name": name, "size": data.size}))
    return {"id": upload_id, "received": 0, "chunk_size": UPLOAD_CHUNK}


@router.post("/chatgpt/uploads/{upload_id}")
async def api_upload_chunk(
    upload_id: str,
    offset: Annotated[int, Form(..., ge=0)],
    chunk: Annotated[UploadFile, File(...)],
) -> dict[str, int | str]:
    """Write one chunk at `offset`.

    Returns how much has arrived, and once
    it's all there, the export's `file` name in the imports folder.
    """
    part, meta = _upload_paths(upload_id)
    if not part.is_file() or not meta.is_file():
        raise HTTPException(404, "Upload not found (unfinished uploads are cleared after a day)")
    info = cast("_UploadMeta", json.loads(meta.read_text()))
    raw = await chunk.read(UPLOAD_CHUNK + 1)
    if len(raw) > UPLOAD_CHUNK or offset + len(raw) > info["size"]:
        raise HTTPException(400, "Chunk too large")
    return await run_in_threadpool(_write_chunk, part, meta, info, offset, raw)


def _write_chunk(part: Path, meta: Path, info: _UploadMeta, offset: int, raw: bytes) -> dict[str, int | str]:
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
        if "conversations.json" not in zf.namelist() and not chat_export.is_native_export(zf):
            part.unlink()
            meta.unlink()
            raise HTTPException(400, _NOT_AN_EXPORT)
    target = part.parent / info["name"]
    n = 1
    while target.exists():
        n += 1
        target = part.parent / f"{Path(info['name']).stem} ({n}).zip"
    part.rename(target)
    meta.unlink()
    return {"received": received, "file": target.name}


@router.delete("/chatgpt/uploads/{upload_id}")
def api_cancel_upload(upload_id: str) -> dict[str, str]:
    """Cancel an unfinished upload and remove its temporary files."""
    for p in _upload_paths(upload_id):
        p.unlink(missing_ok=True)
    return {"cancelled": upload_id}
