"""
Metadata database for tracking projects, downloads, and generation jobs.
Uses SQLAlchemy ORM.
"""
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
import json
from sqlalchemy import create_engine, event, String, Integer, Float, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship
from sqlalchemy.pool import StaticPool

from .config import DB_PATH


# ═══════════════════════════════════════════════════════════════════
#  ORM Models
# ═══════════════════════════════════════════════════════════════════

class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    assets_folder: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    # Relationships
    jobs: Mapped[list["Job"]] = relationship(back_populates="project_rel", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "assets_folder": self.assets_folder,
            "prompt": self.prompt,
            "image_url": self.image_url,
            "video_url": self.video_url,
            "subject_url": self.subject_url,
            "audio_url": self.audio_url,
            "archived": self.archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Download(Base):
    __tablename__ = "downloads"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    local_path: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(50))  # 'video', 'image', 'audio'
    project: Mapped[str] = mapped_column(String(255), index=True)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "url": self.url,
            "local_path": self.local_path,
            "file_type": self.file_type,
            "project": self.project,
            "task_id": self.task_id,
            "model": self.model,
            "prompt": self.prompt,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if self.metadata_json:
            try:
                result["metadata"] = json.loads(self.metadata_json)
            except json.JSONDecodeError:
                result["metadata"] = None
        return result


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    project: Mapped[str] = mapped_column(String(255), ForeignKey("projects.slug"), index=True)
    model: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generate_audio: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    job_type: Mapped[str] = mapped_column(String(20), default="video", index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    credits_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    # Relationship
    project_rel: Mapped["Project | None"] = relationship(back_populates="jobs")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "job_id": self.job_id,
            "project": self.project,
            "model": self.model,
            "prompt": self.prompt,
            "status": self.status,
            "message": self.message,
            "task_id": self.task_id,
            "video_path": self.video_path,
            "video_url": self.video_url,
            "image_url": self.image_url,
            "source_video_url": self.source_video_url,
            "subject_url": self.subject_url,
            "audio_url": self.audio_url,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "length": self.length,
            "generate_audio": self.generate_audio,
            "job_type": self.job_type,
            "archived": self.archived,
            "credits_used": self.credits_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.params_json:
            try:
                result["params"] = json.loads(self.params_json)
            except json.JSONDecodeError:
                result["params"] = None
        return result


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    text_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.id",
    )
    library_items: Mapped[list["ChatLibraryItem"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "text_model": self.text_model,
            "image_model": self.image_model,
            "video_model": self.video_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatMessage(Base):
    """One chat turn. `media_json` is a list of media items (images/videos,
    uploaded or generated) — see web/chat.py for the item shape."""
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True,
    )
    role: Mapped[str] = mapped_column(String(20))  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, default="")
    media_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="done")  # 'streaming' | 'done' | 'error'
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    conversation: Mapped["ChatConversation"] = relationship(back_populates="messages")

    @property
    def media(self) -> list[dict[str, Any]]:
        if not self.media_json:
            return []
        try:
            return json.loads(self.media_json)
        except json.JSONDecodeError:
            return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "media": self.media,
            "model": self.model,
            "status": self.status,
            "error": self.error,
            "cost": self.cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ChatLibraryItem(Base):
    """Chat media detached from its message (the message was removed by an
    edit or retry). Media still attached to messages lives in
    ChatMessage.media_json; the library view shows both."""
    __tablename__ = "chat_library_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    conversation_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True,
    )
    item_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    detached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    conversation: Mapped["ChatConversation"] = relationship(back_populates="library_items")

    @property
    def item(self) -> dict[str, Any]:
        try:
            return json.loads(self.item_json)
        except json.JSONDecodeError:
            return {}


# ═══════════════════════════════════════════════════════════════════
#  Database Manager
# ═══════════════════════════════════════════════════════════════════

class MetadataDB:
    """SQLAlchemy-based database manager for tracking projects, downloads, and jobs."""
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # StaticPool keeps a single connection open for the process lifetime.
        # This avoids repeated file-lock acquire/release cycles, which is
        # critical when the DB file lives on a NAS (NFS/SMB) where POSIX
        # locking may be unreliable.
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=DELETE")
            cursor.execute("PRAGMA synchronous=NORMAL")
            # Hold an exclusive lock for the lifetime of the connection so
            # SQLite never re-negotiates locks against the filesystem.
            cursor.execute("PRAGMA locking_mode=EXCLUSIVE")
            cursor.close()

        Base.metadata.create_all(self.engine)

    @contextmanager
    def _session(self):
        """Yield a Session while holding the thread lock.

        Because StaticPool shares one raw connection across threads, we
        serialise all database work through a threading.Lock so two
        threads never interleave SQL on the same connection.
        """
        with self._lock:
            with Session(self.engine) as session:
                yield session

    # ── Project methods ──────────────────────────────────────────────

    def create_project(self, name: str, slug: str | None = None) -> Project:
        """Create a new project with a unique assets folder."""
        with self._session() as session:
            if not slug:
                slug = self._generate_slug(name)
            slug = self._ensure_unique_slug(session, slug)
            project = Project(
                slug=slug,
                name=name,
                assets_folder=str(uuid.uuid4()),
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            session.expunge(project)
            return project

    def _generate_slug(self, name: str) -> str:
        """Generate a URL-friendly slug from a name."""
        slug = name.lower().strip()
        slug = re.sub(r'[^a-z0-9]+', '_', slug)
        slug = re.sub(r'_+', '_', slug).strip('_')
        return slug or 'project'

    def _ensure_unique_slug(self, session: Session, slug: str) -> str:
        """Ensure slug is unique by adding a number suffix if needed."""
        base_slug = slug
        counter = 1
        while session.query(Project).filter(Project.slug == slug).first():
            slug = f"{base_slug}_{counter}"
            counter += 1
        return slug

    def get_project_by_id(self, project_id: int) -> Project | None:
        with self._session() as session:
            project = session.get(Project, project_id)
            if project:
                session.expunge(project)
            return project

    def get_project_by_slug(self, slug: str) -> Project | None:
        with self._session() as session:
            project = session.query(Project).filter(Project.slug == slug).first()
            if project:
                session.expunge(project)
            return project

    def get_project_by_assets_folder(self, assets_folder: str) -> Project | None:
        with self._session() as session:
            project = session.query(Project).filter(Project.assets_folder == assets_folder).first()
            if project:
                session.expunge(project)
            return project

    def get_all_projects(self, archived: bool | None = None) -> list[Project]:
        with self._session() as session:
            query = session.query(Project)
            if archived is not None:
                query = query.filter(Project.archived == archived)
            projects = query.order_by(Project.updated_at.desc()).all()
            for p in projects:
                session.expunge(p)
            return projects

    def update_project(self, slug: str, **fields) -> Project | None:
        """Update project fields."""
        with self._session() as session:
            project = session.query(Project).filter(Project.slug == slug).first()
            if not project:
                return None
            for key, value in fields.items():
                if hasattr(project, key):
                    setattr(project, key, value)
            project.updated_at = datetime.now()
            session.commit()
            session.refresh(project)
            session.expunge(project)
            return project

    def delete_project(self, slug: str) -> bool:
        with self._session() as session:
            project = session.query(Project).filter(Project.slug == slug).first()
            if project:
                session.delete(project)
                session.commit()
                return True
            return False

    # ── Download methods ─────────────────────────────────────────────

    def add_download(
        self,
        url: str,
        local_path: str,
        file_type: str,
        project: str,
        task_id: str | None = None,
        model: str | None = None,
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Add a download record and return its ID."""
        with self._session() as session:
            download = Download(
                url=url,
                local_path=local_path,
                file_type=file_type,
                project=project,
                task_id=task_id,
                model=model,
                prompt=prompt,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            session.add(download)
            session.commit()
            return download.id

    def get_download_by_id(self, record_id: int) -> Download | None:
        with self._session() as session:
            download = session.get(Download, record_id)
            if download:
                session.expunge(download)
            return download

    def get_downloads_by_task_id(self, task_id: str) -> list[Download]:
        with self._session() as session:
            downloads = session.query(Download).filter(Download.task_id == task_id).all()
            for d in downloads:
                session.expunge(d)
            return downloads

    def get_downloads_by_project(self, project: str) -> list[Download]:
        with self._session() as session:
            downloads = session.query(Download).filter(Download.project == project)\
                .order_by(Download.created_at.desc()).all()
            for d in downloads:
                session.expunge(d)
            return downloads

    def get_download_by_url(self, url: str) -> Download | None:
        with self._session() as session:
            download = session.query(Download).filter(Download.url == url)\
                .order_by(Download.created_at.desc()).first()
            if download:
                session.expunge(download)
            return download

    def get_videos_by_project(self, project: str) -> list[Download]:
        with self._session() as session:
            downloads = session.query(Download).filter(
                Download.project == project,
                Download.file_type == 'video'
            ).order_by(Download.created_at.desc()).all()
            for d in downloads:
                session.expunge(d)
            return downloads

    def get_latest_video(self, project: str) -> Download | None:
        with self._session() as session:
            download = session.query(Download).filter(
                Download.project == project,
                Download.file_type == 'video'
            ).order_by(Download.created_at.desc()).first()
            if download:
                session.expunge(download)
            return download

    def get_all_downloads(self, limit: int = 100) -> list[Download]:
        with self._session() as session:
            downloads = session.query(Download).order_by(Download.created_at.desc()).limit(limit).all()
            for d in downloads:
                session.expunge(d)
            return downloads

    def delete_download(self, record_id: int) -> bool:
        with self._session() as session:
            download = session.get(Download, record_id)
            if download:
                session.delete(download)
                session.commit()
                return True
            return False

    # ── Job methods ──────────────────────────────────────────────────

    def create_job(
        self,
        job_id: str,
        project: str,
        model: str,
        prompt: str,
        image_url: str | None = None,
        source_video_url: str | None = None,
        subject_url: str | None = None,
        audio_url: str | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        length: int | None = None,
        generate_audio: bool | None = None,
        params: dict[str, Any] | None = None,
        job_type: str = "video",
    ) -> int:
        """Create a new job record."""
        with self._session() as session:
            job = Job(
                job_id=job_id,
                project=project,
                model=model,
                prompt=prompt,
                image_url=image_url,
                source_video_url=source_video_url,
                subject_url=subject_url,
                audio_url=audio_url,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                length=length,
                generate_audio=generate_audio,
                params_json=json.dumps(params) if params else None,
                job_type=job_type,
            )
            session.add(job)
            session.commit()
            return job.id

    def update_job(self, job_id: str, **fields) -> bool:
        """Update fields on a job record."""
        with self._session() as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return False
            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = datetime.now()
            session.commit()
            return True

    def get_job(self, job_id: str) -> Job | None:
        with self._session() as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if job:
                session.expunge(job)
            return job

    def get_jobs_by_project(self, project: str) -> list[Job]:
        with self._session() as session:
            jobs = session.query(Job).filter(Job.project == project)\
                .order_by(Job.created_at.desc()).all()
            for j in jobs:
                session.expunge(j)
            return jobs

    def get_all_jobs_with_video_in_folder(self, folder: str) -> list[Job]:
        """Return jobs whose video_path starts with the given folder path."""
        with self._session() as session:
            jobs = session.query(Job).filter(Job.video_path.startswith(folder)).all()
            for j in jobs:
                session.expunge(j)
            return jobs

    def get_active_jobs(self) -> list[Job]:
        with self._session() as session:
            jobs = session.query(Job).filter(
                ~Job.status.in_(['done', 'error'])
            ).order_by(Job.created_at.desc()).all()
            for j in jobs:
                session.expunge(j)
            return jobs

    def get_all_jobs(self, limit: int = 100) -> list[Job]:
        with self._session() as session:
            jobs = session.query(Job).order_by(Job.created_at.desc()).limit(limit).all()
            for j in jobs:
                session.expunge(j)
            return jobs

    def get_jobs_by_status(self, status: str, limit: int = 50) -> list[Job]:
        with self._session() as session:
            jobs = session.query(Job).filter(Job.status == status)\
                .order_by(Job.created_at.desc()).limit(limit).all()
            for j in jobs:
                session.expunge(j)
            return jobs

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by job_id."""
        with self._session() as session:
            job = session.query(Job).filter(Job.job_id == job_id).first()
            if job:
                session.delete(job)
                session.commit()
                return True
            return False

    def delete_job_by_video_path(self, video_path: str) -> bool:
        """Delete a job by its video_path (filename match)."""
        with self._session() as session:
            # Match by filename in video_path
            job = session.query(Job).filter(Job.video_path.contains(video_path)).first()
            if job:
                session.delete(job)
                session.commit()
                return True
            return False

    def update_download_by_local_path(self, old_path: str, **fields) -> bool:
        """Update fields on a download record matched by local_path filename."""
        with self._session() as session:
            download = session.query(Download).filter(Download.local_path.contains(old_path)).first()
            if not download:
                return False
            for key, value in fields.items():
                if hasattr(download, key):
                    setattr(download, key, value)
            session.commit()
            return True

    def delete_download_by_path(self, local_path: str) -> bool:
        """Delete a download record by local_path (filename match)."""
        with self._session() as session:
            download = session.query(Download).filter(Download.local_path.contains(local_path)).first()
            if download:
                session.delete(download)
                session.commit()
                return True
            return False

    # ── Chat methods ─────────────────────────────────────────────────

    def create_conversation(self, title: str = "New chat", **fields) -> ChatConversation:
        with self._session() as session:
            conv = ChatConversation(id=uuid.uuid4().hex, title=title, **fields)
            session.add(conv)
            session.commit()
            session.refresh(conv)
            session.expunge(conv)
            return conv

    def get_conversation(self, conv_id: str) -> ChatConversation | None:
        with self._session() as session:
            conv = session.get(ChatConversation, conv_id)
            if conv:
                session.expunge(conv)
            return conv

    def list_conversations(self, limit: int = 200) -> list[ChatConversation]:
        with self._session() as session:
            convs = session.query(ChatConversation)\
                .order_by(ChatConversation.updated_at.desc()).limit(limit).all()
            for c in convs:
                session.expunge(c)
            return convs

    def update_conversation(self, conv_id: str, **fields) -> ChatConversation | None:
        with self._session() as session:
            conv = session.get(ChatConversation, conv_id)
            if not conv:
                return None
            for key, value in fields.items():
                if hasattr(conv, key):
                    setattr(conv, key, value)
            conv.updated_at = datetime.now()
            session.commit()
            session.refresh(conv)
            session.expunge(conv)
            return conv

    def delete_conversation(self, conv_id: str) -> bool:
        with self._session() as session:
            conv = session.get(ChatConversation, conv_id)
            if not conv:
                return False
            session.delete(conv)
            session.commit()
            return True

    def add_chat_message(
        self,
        conversation_id: str,
        role: str,
        content: str = "",
        media: list[dict[str, Any]] | None = None,
        model: str | None = None,
        status: str = "done",
    ) -> ChatMessage:
        with self._session() as session:
            msg = ChatMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                media_json=json.dumps(media) if media else None,
                model=model,
                status=status,
            )
            session.add(msg)
            conv = session.get(ChatConversation, conversation_id)
            if conv:
                conv.updated_at = datetime.now()
            session.commit()
            session.refresh(msg)
            session.expunge(msg)
            return msg

    def update_chat_message(self, message_id: int, media: list[dict[str, Any]] | None = None, **fields) -> ChatMessage | None:
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if not msg:
                return None
            for key, value in fields.items():
                if hasattr(msg, key):
                    setattr(msg, key, value)
            if media is not None:
                msg.media_json = json.dumps(media) if media else None
            session.commit()
            session.refresh(msg)
            session.expunge(msg)
            return msg

    def update_chat_media_item(self, message_id: int, media_id: str, **fields) -> ChatMessage | None:
        """Atomically merge `fields` into one media item.

        Looks in the message first, then the library (the message may have
        been removed by an edit/retry while a video was still rendering).
        Returns the message if the item was updated there, else None.
        Background video pollers update items while the chat stream may be
        appending others, so the read-modify-write must happen under one lock.
        """
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if msg:
                media = msg.media
                for item in media:
                    if item.get("id") == media_id:
                        item.update(fields)
                        msg.media_json = json.dumps(media)
                        session.commit()
                        session.refresh(msg)
                        session.expunge(msg)
                        return msg
            lib = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            if lib:
                lib.item_json = json.dumps({**lib.item, **fields})
                session.commit()
            return None

    def find_chat_media_item(self, message_id: int, media_id: str) -> dict[str, Any] | None:
        """The media item's current state, wherever it lives (message or library)."""
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if msg:
                item = next((i for i in msg.media if i.get("id") == media_id), None)
                if item:
                    return item
            lib = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            return lib.item if lib else None

    def append_chat_media_item(self, message_id: int, item: dict[str, Any]) -> ChatMessage | None:
        """Atomically append one media item to a message."""
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if not msg:
                return None
            msg.media_json = json.dumps(msg.media + [item])
            session.commit()
            session.refresh(msg)
            session.expunge(msg)
            return msg

    def get_chat_messages_by_status(self, status: str) -> list[ChatMessage]:
        with self._session() as session:
            msgs = session.query(ChatMessage).filter(ChatMessage.status == status).all()
            for m in msgs:
                session.expunge(m)
            return msgs

    def get_chat_message(self, message_id: int) -> ChatMessage | None:
        with self._session() as session:
            msg = session.get(ChatMessage, message_id)
            if msg:
                session.expunge(msg)
            return msg

    def get_chat_messages(self, conversation_id: str) -> list[ChatMessage]:
        with self._session() as session:
            msgs = session.query(ChatMessage)\
                .filter(ChatMessage.conversation_id == conversation_id)\
                .order_by(ChatMessage.id).all()
            for m in msgs:
                session.expunge(m)
            return msgs

    def truncate_chat(self, conversation_id: str, after_id: int) -> list[dict[str, Any]]:
        """Delete every message with id > after_id (used by edit/retry),
        moving their generated media into the library first. Uploaded
        attachments are the user's own inputs and aren't kept.

        Returns the detached media items.
        """
        with self._session() as session:
            msgs = session.query(ChatMessage).filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.id > after_id,
            ).all()
            detached = []
            for msg in msgs:
                for item in msg.media:
                    if item.get("source") == "upload" or not (item.get("file") or item.get("job_id")):
                        continue
                    session.add(ChatLibraryItem(
                        media_id=item["id"], conversation_id=conversation_id,
                        item_json=json.dumps(item), created_at=msg.created_at,
                    ))
                    detached.append(item)
                session.delete(msg)
            session.commit()
            return detached

    def list_chat_library(self) -> list[ChatLibraryItem]:
        with self._session() as session:
            items = session.query(ChatLibraryItem).order_by(ChatLibraryItem.created_at.desc()).all()
            for i in items:
                session.expunge(i)
            return items

    def get_chat_library_item(self, media_id: str) -> ChatLibraryItem | None:
        with self._session() as session:
            item = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            if item:
                session.expunge(item)
            return item

    def delete_chat_library_item(self, media_id: str) -> bool:
        with self._session() as session:
            item = session.query(ChatLibraryItem).filter(ChatLibraryItem.media_id == media_id).first()
            if not item:
                return False
            session.delete(item)
            session.commit()
            return True

    def get_chat_messages_with_media(self) -> list[ChatMessage]:
        with self._session() as session:
            msgs = session.query(ChatMessage).filter(ChatMessage.media_json.isnot(None))\
                .order_by(ChatMessage.id.desc()).all()
            for m in msgs:
                session.expunge(m)
            return msgs

    def get_chat_messages_with_pending_media(self) -> list[ChatMessage]:
        with self._session() as session:
            msgs = session.query(ChatMessage)\
                .filter(ChatMessage.media_json.contains('"status": "pending"')).all()
            for m in msgs:
                session.expunge(m)
            return msgs


# ═══════════════════════════════════════════════════════════════════
#  Global Instance & Convenience Functions
# ═══════════════════════════════════════════════════════════════════

_db_instance: MetadataDB | None = None
_db_init_lock = threading.Lock()


def get_db() -> MetadataDB:
    """Get the global metadata database instance."""
    global _db_instance
    if _db_instance is None:
        with _db_init_lock:
            if _db_instance is None:
                _db_instance = MetadataDB()
    return _db_instance


def record_download(
    url: str,
    local_path: str,
    file_type: str,
    project: str,
    task_id: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Convenience function to record a download."""
    return get_db().add_download(
        url=url,
        local_path=local_path,
        file_type=file_type,
        project=project,
        task_id=task_id,
        model=model,
        prompt=prompt,
        metadata=metadata,
    )
