"""Tests for img2vid.common.metadata — MetadataDB, ORM models, convenience functions."""
import json
import tempfile
from pathlib import Path

import pytest

from img2vid.common.metadata import MetadataDB, Project, Download, Job, Base, get_db, record_download


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path):
    """Return a MetadataDB backed by a fresh in-memory-like temp file."""
    return MetadataDB(db_path=tmp_path / "test.db")


# ── Project CRUD ─────────────────────────────────────────────────────

class TestProjectCRUD:
    def test_create_project_basic(self, db):
        proj = db.create_project(name="My Test Project")
        assert proj.name == "My Test Project"
        assert proj.slug == "my_test_project"
        assert proj.assets_folder  # UUID string
        assert proj.created_at is not None

    def test_create_project_custom_slug(self, db):
        proj = db.create_project(name="Foo", slug="custom-slug")
        assert proj.slug == "custom-slug"

    def test_create_project_unique_slug(self, db):
        p1 = db.create_project(name="Dup")
        p2 = db.create_project(name="Dup")
        assert p1.slug != p2.slug
        assert p2.slug == "dup_1"

    def test_create_project_unique_slug_multiple(self, db):
        db.create_project(name="Dup")
        db.create_project(name="Dup")
        p3 = db.create_project(name="Dup")
        assert p3.slug == "dup_2"

    def test_get_project_by_slug(self, db):
        db.create_project(name="Lookup")
        fetched = db.get_project_by_slug("lookup")
        assert fetched is not None
        assert fetched.name == "Lookup"

    def test_get_project_by_slug_not_found(self, db):
        assert db.get_project_by_slug("nonexistent") is None

    def test_get_project_by_id(self, db):
        proj = db.create_project(name="ById")
        fetched = db.get_project_by_id(proj.id)
        assert fetched is not None
        assert fetched.slug == proj.slug

    def test_get_project_by_id_not_found(self, db):
        assert db.get_project_by_id(999) is None

    def test_get_project_by_assets_folder(self, db):
        proj = db.create_project(name="Asset")
        fetched = db.get_project_by_assets_folder(proj.assets_folder)
        assert fetched is not None
        assert fetched.slug == proj.slug

    def test_get_project_by_assets_folder_not_found(self, db):
        assert db.get_project_by_assets_folder("no-such-folder") is None

    def test_get_all_projects(self, db):
        db.create_project(name="A")
        db.create_project(name="B")
        projects = db.get_all_projects()
        assert len(projects) == 2

    def test_update_project(self, db):
        proj = db.create_project(name="Old")
        updated = db.update_project(proj.slug, name="New", prompt="hello")
        assert updated.name == "New"
        assert updated.prompt == "hello"

    def test_update_project_not_found(self, db):
        assert db.update_project("nope", name="X") is None

    def test_delete_project(self, db):
        proj = db.create_project(name="ToDelete")
        assert db.delete_project(proj.slug) is True
        assert db.get_project_by_slug(proj.slug) is None

    def test_delete_project_not_found(self, db):
        assert db.delete_project("nope") is False


class TestGenerateSlug:
    def test_basic(self, db):
        assert db._generate_slug("Hello World") == "hello_world"

    def test_special_chars(self, db):
        assert db._generate_slug("My Project #1!") == "my_project_1"

    def test_empty_returns_project(self, db):
        assert db._generate_slug("") == "project"

    def test_unicode(self, db):
        slug = db._generate_slug("café ☕")
        assert slug  # should produce something


# ── Download CRUD ────────────────────────────────────────────────────

class TestDownloadCRUD:
    def test_add_download(self, db):
        # Need a project first
        db.create_project(name="dlproj", slug="dlproj")
        dl_id = db.add_download(
            url="https://example.com/video.mp4",
            local_path="/tmp/video.mp4",
            file_type="video",
            project="dlproj",
            task_id="task123",
            model="pollodance20",
            prompt="test",
            metadata={"key": "value"},
        )
        assert isinstance(dl_id, int)

    def test_get_download_by_id(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        dl_id = db.add_download("https://ex.com/v.mp4", "/tmp/v.mp4", "video", "dlproj")
        dl = db.get_download_by_id(dl_id)
        assert dl is not None
        assert dl.url == "https://ex.com/v.mp4"

    def test_get_download_by_id_not_found(self, db):
        assert db.get_download_by_id(999) is None

    def test_get_downloads_by_task_id(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        db.add_download("https://ex.com/v1.mp4", "/tmp/v1.mp4", "video", "dlproj", task_id="t1")
        db.add_download("https://ex.com/v2.mp4", "/tmp/v2.mp4", "video", "dlproj", task_id="t1")
        results = db.get_downloads_by_task_id("t1")
        assert len(results) == 2

    def test_get_downloads_by_project(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        db.add_download("https://ex.com/v1.mp4", "/tmp/v1.mp4", "video", "dlproj")
        results = db.get_downloads_by_project("dlproj")
        assert len(results) == 1

    def test_get_download_by_url(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        db.add_download("https://ex.com/unique.mp4", "/tmp/u.mp4", "video", "dlproj")
        dl = db.get_download_by_url("https://ex.com/unique.mp4")
        assert dl is not None

    def test_get_download_by_url_not_found(self, db):
        assert db.get_download_by_url("https://noexist.com/x.mp4") is None

    def test_get_videos_by_project(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        db.add_download("https://ex.com/v.mp4", "/tmp/v.mp4", "video", "dlproj")
        db.add_download("https://ex.com/i.jpg", "/tmp/i.jpg", "image", "dlproj")
        videos = db.get_videos_by_project("dlproj")
        assert len(videos) == 1
        assert videos[0].file_type == "video"

    def test_get_latest_video(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        db.add_download("https://ex.com/v1.mp4", "/tmp/v1.mp4", "video", "dlproj")
        db.add_download("https://ex.com/v2.mp4", "/tmp/v2.mp4", "video", "dlproj")
        latest = db.get_latest_video("dlproj")
        assert latest is not None

    def test_get_latest_video_none(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        assert db.get_latest_video("dlproj") is None

    def test_get_all_downloads(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        for i in range(5):
            db.add_download(f"https://ex.com/v{i}.mp4", f"/tmp/v{i}.mp4", "video", "dlproj")
        results = db.get_all_downloads(limit=3)
        assert len(results) == 3

    def test_delete_download(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        dl_id = db.add_download("https://ex.com/v.mp4", "/tmp/v.mp4", "video", "dlproj")
        assert db.delete_download(dl_id) is True
        assert db.get_download_by_id(dl_id) is None

    def test_delete_download_not_found(self, db):
        assert db.delete_download(999) is False

    def test_delete_download_by_path(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        db.add_download("https://ex.com/v.mp4", "/tmp/video.mp4", "video", "dlproj")
        assert db.delete_download_by_path("video.mp4") is True

    def test_delete_download_by_path_not_found(self, db):
        assert db.delete_download_by_path("no_such.mp4") is False


# ── Job CRUD ─────────────────────────────────────────────────────────

class TestJobCRUD:
    def test_create_job(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        job_id_int = db.create_job(
            job_id="abc123",
            project="jobproj",
            model="pollodance20",
            prompt="hello",
        )
        assert isinstance(job_id_int, int)

    def test_get_job(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="j1", project="jobproj", model="pollodance20", prompt="test")
        job = db.get_job("j1")
        assert job is not None
        assert job.model == "pollodance20"

    def test_get_job_not_found(self, db):
        assert db.get_job("nope") is None

    def test_update_job(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="j2", project="jobproj", model="pollodance20", prompt="test")
        assert db.update_job("j2", status="done", message="All good") is True
        job = db.get_job("j2")
        assert job.status == "done"
        assert job.message == "All good"

    def test_update_job_not_found(self, db):
        assert db.update_job("nope", status="done") is False

    def test_get_jobs_by_project(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="j3", project="jobproj", model="pollodance20", prompt="a")
        db.create_job(job_id="j4", project="jobproj", model="pollo20", prompt="b")
        jobs = db.get_jobs_by_project("jobproj")
        assert len(jobs) == 2

    def test_get_active_jobs(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="active1", project="jobproj", model="pollodance20", prompt="a")
        db.create_job(job_id="done1", project="jobproj", model="pollodance20", prompt="b")
        db.update_job("done1", status="done")
        active = db.get_active_jobs()
        assert len(active) == 1
        assert active[0].job_id == "active1"

    def test_get_all_jobs(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        for i in range(5):
            db.create_job(job_id=f"jall{i}", project="jobproj", model="pollodance20", prompt="x")
        jobs = db.get_all_jobs(limit=3)
        assert len(jobs) == 3

    def test_get_jobs_by_status(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="s1", project="jobproj", model="pollodance20", prompt="x")
        db.update_job("s1", status="error")
        db.create_job(job_id="s2", project="jobproj", model="pollodance20", prompt="y")
        errors = db.get_jobs_by_status("error")
        assert len(errors) == 1

    def test_delete_job(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="del1", project="jobproj", model="pollodance20", prompt="x")
        assert db.delete_job("del1") is True
        assert db.get_job("del1") is None

    def test_delete_job_not_found(self, db):
        assert db.delete_job("nope") is False

    def test_delete_job_by_video_path(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="delvp", project="jobproj", model="pollodance20", prompt="x")
        db.update_job("delvp", video_path="/assets/jobproj/video123.mp4")
        assert db.delete_job_by_video_path("video123.mp4") is True

    def test_delete_job_by_video_path_not_found(self, db):
        assert db.delete_job_by_video_path("no_such.mp4") is False

    def test_create_job_with_params(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(
            job_id="p1", project="jobproj", model="pollodance20", prompt="x",
            image_url="https://img.com/i.jpg",
            aspect_ratio="16:9",
            resolution="720p",
            length=10,
            generate_audio=True,
            params={"web_search": True},
        )
        job = db.get_job("p1")
        assert job.image_url == "https://img.com/i.jpg"
        assert job.aspect_ratio == "16:9"
        assert job.length == 10
        assert job.generate_audio is True

    def test_job_archived_default_false(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="arc1", project="jobproj", model="pollodance20", prompt="x")
        job = db.get_job("arc1")
        assert job.archived is False

    def test_update_job_archived(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="arc2", project="jobproj", model="pollodance20", prompt="x")
        db.update_job("arc2", archived=True)
        job = db.get_job("arc2")
        assert job.archived is True


# ── to_dict methods ──────────────────────────────────────────────────

class TestToDict:
    def test_project_to_dict(self, db):
        proj = db.create_project(name="Dict Test")
        d = proj.to_dict()
        assert d["name"] == "Dict Test"
        assert "slug" in d
        assert "created_at" in d

    def test_download_to_dict(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        dl_id = db.add_download(
            "https://ex.com/v.mp4", "/tmp/v.mp4", "video", "dlproj",
            metadata={"key": "val"},
        )
        dl = db.get_download_by_id(dl_id)
        d = dl.to_dict()
        assert d["url"] == "https://ex.com/v.mp4"
        assert d["metadata"] == {"key": "val"}

    def test_download_to_dict_invalid_json(self, db):
        db.create_project(name="dlproj", slug="dlproj")
        dl_id = db.add_download("https://ex.com/v.mp4", "/tmp/v.mp4", "video", "dlproj")
        # Manually set bad JSON
        with db._session() as session:
            dl = session.get(Download, dl_id)
            dl.metadata_json = "not valid json"
            session.commit()
        dl = db.get_download_by_id(dl_id)
        d = dl.to_dict()
        assert d.get("metadata") is None

    def test_job_to_dict(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(
            job_id="jd1", project="jobproj", model="pollodance20", prompt="x",
            params={"web_search": True},
        )
        job = db.get_job("jd1")
        d = job.to_dict()
        assert d["job_id"] == "jd1"
        assert d["params"] == {"web_search": True}

    def test_job_to_dict_invalid_params(self, db):
        db.create_project(name="jobproj", slug="jobproj")
        db.create_job(job_id="jd2", project="jobproj", model="pollodance20", prompt="x")
        with db._session() as session:
            job = session.query(Job).filter(Job.job_id == "jd2").first()
            job.params_json = "not valid"
            session.commit()
        job = db.get_job("jd2")
        d = job.to_dict()
        assert d.get("params") is None


# ── Global instance / convenience ────────────────────────────────────

class TestGlobalDB:
    def test_get_db_returns_singleton(self, tmp_path, monkeypatch):
        import img2vid.common.metadata as meta_mod
        import img2vid.common.config as config_mod
        old = meta_mod._db_instance
        # Point DB_PATH to tmp so we never touch the real filesystem
        monkeypatch.setattr(config_mod, "DB_PATH", tmp_path / "data" / "singleton.db")
        monkeypatch.setattr(meta_mod, "DB_PATH", tmp_path / "data" / "singleton.db")
        try:
            meta_mod._db_instance = None
            db1 = get_db()
            db2 = get_db()
            assert db1 is db2
        finally:
            meta_mod._db_instance = old

    def test_record_download_convenience(self, db, monkeypatch):
        import img2vid.common.metadata as meta_mod
        monkeypatch.setattr(meta_mod, "_db_instance", db)
        db.create_project(name="conv", slug="conv")
        dl_id = record_download(
            url="https://ex.com/v.mp4",
            local_path="/tmp/v.mp4",
            file_type="video",
            project="conv",
        )
        assert isinstance(dl_id, int)


# ── Cascade delete ───────────────────────────────────────────────────

class TestCascadeDelete:
    def test_delete_project_cascades_jobs(self, db):
        db.create_project(name="casc", slug="casc")
        db.create_job(job_id="cj1", project="casc", model="pollodance20", prompt="x")
        db.delete_project("casc")
        assert db.get_job("cj1") is None

