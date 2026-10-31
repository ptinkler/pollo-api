"""backfill Generate projects into the unified thread model

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28

One-time data migration (no schema change): folds each Generate-page project +
its successful jobs into the thread model (chat_conversations + chat_messages),
then unifies favourites.

Non-destructive and idempotent:
  • Adds a conversation per project and one assistant "generation" message per
    successful job; the projects/jobs/downloads tables are left intact.
  • Output files are HARD-LINKED into each thread's chat dir (same inode, no
    extra disk, originals untouched); falls back to a copy across filesystems.
    Filenames are kept so generation_favourites still match.
  • Skips projects already migrated (import_source='migrated-project'), so a
    re-run or fresh deploy is safe. Archived projects are skipped.

Favourites are then normalized: every generation_favourites filename is
reflected as "pinned": true on its media item, and a thread holding any
favourited generation is itself pinned (so it surfaces in the Favourites
filter).

Downgrade removes the migrated threads and their messages; it leaves the
hard-linked files (they cost no extra space) — delete orphaned chat/<id> dirs
by hand if wanted.
"""

import json
import os
import shutil
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy import select
from sqlalchemy.orm import Session

from img2vid.common import config
from img2vid.common.metadata import (
    ChatConversation,
    ChatMessage,
    Download,
    GenerationFavourite,
    Job,
    Project,
)

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHAT_ROOT = config.ROOT_DIR / "chat"
ASSETS_DIR = config.ASSETS_DIR
IMPORT_SOURCE = "migrated-project"
DONE_STATUSES = {"done", "completed", "success", "succeeded"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _resolve(path_str, assets_folder):
    """An existing local file for a stored path: the path as-is, else the same
    basename inside the project's assets folder."""
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_file():
        return p
    candidate = ASSETS_DIR / assets_folder / Path(path_str).name
    return candidate if candidate.is_file() else None


def _job_outputs(job, assets_folder, downloads_by_task):
    """(file, kind) for a job's outputs — from its Download rows, else its own
    video_path / image_url."""
    outs = []
    seen = set()
    for d in downloads_by_task.get(job.task_id or "", []):
        path = _resolve(d.local_path, assets_folder)
        if path and path not in seen:
            seen.add(path)
            outs.append((path, "image" if (d.file_type or "").startswith("image") else "video"))
    if not outs:
        fallback = _resolve(job.video_path, assets_folder) or _resolve(job.image_url, assets_folder)
        if fallback:
            is_image = job.job_type == "image" or fallback.suffix.lower() in IMAGE_EXTS
            outs.append((fallback, "image" if is_image else "video"))
    return outs


def _link_or_copy(src, dst):
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)  # hard link: no extra disk, original untouched
    except OSError:
        shutil.copy2(src, dst)  # across filesystems: fall back to a copy


def _media_item(filename, kind, job, fav_files):
    """A chat media item, matching web/chat.py's _saved_media shape."""
    params = {
        k: v
        for k, v in {
            "aspect_ratio": job.aspect_ratio,
            "resolution": job.resolution,
            "length": job.length,
            "generate_audio": job.generate_audio,
        }.items()
        if v is not None
    }
    item = {
        "id": uuid.uuid4().hex[:8],
        "kind": kind,
        "source": "generated",
        "status": "done",
        "file": filename,
        "prompt": job.prompt or "",
        "model": job.model,
        "params": params,
    }
    if job.credits_used is not None:
        item["credits"] = job.credits_used
    if filename in fav_files:
        item["pinned"] = True
    return item


def _project_to_thread(session, project, downloads_by_task, fav_files):
    """Build (conversation, messages) for a project's successful jobs, linking
    their files. None if nothing to bring."""
    jobs = session.scalars(select(Job).where(Job.project == project.slug).order_by(Job.created_at)).all()
    jobs = [j for j in jobs if j.status in DONE_STATUSES]
    conv_id = uuid.uuid4().hex
    conv_dir = CHAT_ROOT / conv_id
    messages = []
    for job in jobs:
        outputs = _job_outputs(job, project.assets_folder, downloads_by_task)
        if not outputs:
            continue
        media = []
        for src, kind in outputs:
            _link_or_copy(src, conv_dir / src.name)
            media.append(_media_item(src.name, kind, job, fav_files))
        messages.append(
            ChatMessage(
                conversation_id=conv_id,
                parent_id=None,
                role="assistant",
                content="",
                media_json=json.dumps(media),
                model=job.model,
                mode="image" if job.job_type == "image" else "video",
                status="done",
                created_at=job.created_at or datetime.now(),
            )
        )
    if not messages:
        return None
    conv = ChatConversation(
        id=conv_id,
        title=project.name,
        space_id=None,
        import_source=IMPORT_SOURCE,
        import_id=project.slug,
        created_at=project.created_at or datetime.now(),
        updated_at=project.updated_at or datetime.now(),
    )
    return conv, messages


def _backfill(session, fav_files):
    downloads_by_task = {}
    for d in session.scalars(select(Download)).all():
        downloads_by_task.setdefault(d.task_id or "", []).append(d)
    done = select(ChatConversation).where(ChatConversation.import_source == IMPORT_SOURCE)
    already = {c.import_id for c in session.scalars(done)}
    for project in session.scalars(select(Project).order_by(Project.created_at)):
        if project.archived or project.slug in already:
            continue
        result = _project_to_thread(session, project, downloads_by_task, fav_files)
        if not result:
            continue
        conv, messages = result
        session.add(conv)
        session.add_all(messages)
        session.flush()
        prev = None
        for m in messages:  # chain the generations so the thread shows them all
            m.parent_id = prev
            prev = m.id
        conv.current_leaf_id = messages[-1].id
        print(f"  project -> thread: {project.name!r}  ({len(messages)} generations)")


def _normalize_favourites(session, fav_files):
    """Reflect generation_favourites onto media items, and pin threads that
    hold a favourited generation."""
    for conv in session.scalars(select(ChatConversation)):
        has_fav = conv.pinned
        for msg in session.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv.id)):
            if not msg.media_json:
                continue
            items = json.loads(msg.media_json)
            changed = False
            for item in items:
                if item.get("pinned"):
                    has_fav = True
                elif item.get("file") in fav_files:
                    item["pinned"] = True
                    has_fav = True
                    changed = True
            if changed:
                msg.media_json = json.dumps(items)
        if has_fav and not conv.pinned:
            conv.pinned = True


def upgrade() -> None:
    bind = op.get_bind()
    # The ORM models carry a user_id column (added for multi-tenancy in 0020,
    # which runs AFTER this). On a fresh DB this migration would otherwise query
    # those models before the column exists, so ensure it's present on the
    # tables this migration touches. 0020's add is guarded and will skip these.
    insp = sa.inspect(bind)
    for table in ("projects", "jobs", "downloads", "generation_favourites", "chat_conversations", "chat_messages"):
        if "user_id" not in {c["name"] for c in insp.get_columns(table)}:
            op.execute(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(50)")
    # Likewise chat_conversations.kind, added in 0022 (after this). 0022's add is
    # guarded and skips it when already present.
    if "kind" not in {c["name"] for c in sa.inspect(bind).get_columns("chat_conversations")}:
        op.execute("ALTER TABLE chat_conversations ADD COLUMN kind VARCHAR(10) NOT NULL DEFAULT 'chat'")

    session = Session(bind=bind)
    fav_files = {f.filename for f in session.scalars(select(GenerationFavourite)).all()}
    _backfill(session, fav_files)
    _normalize_favourites(session, fav_files)
    session.flush()  # Alembic owns the commit for the migration's transaction


def downgrade() -> None:
    session = Session(bind=op.get_bind())
    convs = session.scalars(select(ChatConversation).where(ChatConversation.import_source == IMPORT_SOURCE)).all()
    for conv in convs:
        session.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).delete()
        session.delete(conv)
    session.flush()
