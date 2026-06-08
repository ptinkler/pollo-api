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
from sqlalchemy import create_engine, event, String, Integer, Text, Boolean, DateTime, ForeignKey
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
