"""Tests for img2vid.common.get_inputs — file reading utilities."""
import pytest
from pathlib import Path

from img2vid.common.get_inputs import (
    get_prompt, get_image_url, get_image_path, get_video_url,
    get_subject_url, get_audio_url, get_from_file,
)


class TestGetFromFile:
    def test_reads_content(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("  hello world  ")
        result = get_from_file(str(f))
        assert result == "hello world"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            get_from_file("/nonexistent/path.txt")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        with pytest.raises(RuntimeError, match="empty"):
            get_from_file(str(f))

    def test_whitespace_only_file(self, tmp_path):
        f = tmp_path / "ws.txt"
        f.write_text("   \n  ")
        with pytest.raises(RuntimeError, match="empty"):
            get_from_file(str(f))


class TestGetPrompt:
    def test_reads_prompt(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "myproj"
        project_dir.mkdir(parents=True)
        (project_dir / "prompt.txt").write_text("Generate a cat video")
        monkeypatch.chdir(tmp_path)
        assert get_prompt("myproj") == "Generate a cat video"

    def test_prompt_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError):
            get_prompt("nonexistent")


class TestGetImageUrl:
    def test_reads_image_url(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "myproj"
        project_dir.mkdir(parents=True)
        (project_dir / "image_url.txt").write_text("https://example.com/img.jpg")
        monkeypatch.chdir(tmp_path)
        assert get_image_url("myproj") == "https://example.com/img.jpg"

    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert get_image_url("nonexistent") is None


class TestGetImagePath:
    def test_finds_jpg(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "myproj"
        project_dir.mkdir(parents=True)
        (project_dir / "image.jpg").write_text("fake")
        monkeypatch.chdir(tmp_path)
        result = get_image_path("myproj")
        assert result is not None
        assert result.name == "image.jpg"

    def test_finds_png(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "myproj"
        project_dir.mkdir(parents=True)
        (project_dir / "image.png").write_text("fake")
        monkeypatch.chdir(tmp_path)
        result = get_image_path("myproj")
        assert result is not None
        assert result.name == "image.png"

    def test_returns_none_when_no_image(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert get_image_path("nonexistent") is None


class TestGetVideoUrl:
    def test_reads_video_url(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "myproj"
        project_dir.mkdir(parents=True)
        (project_dir / "video_url.txt").write_text("https://example.com/video.mp4")
        monkeypatch.chdir(tmp_path)
        assert get_video_url("myproj") == "https://example.com/video.mp4"

    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert get_video_url("nonexistent") is None



class TestGetSubjectUrl:
    def test_reads_subject_url(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "myproj"
        project_dir.mkdir(parents=True)
        (project_dir / "subject_url.txt").write_text("https://example.com/subject.jpg")
        monkeypatch.chdir(tmp_path)
        assert get_subject_url("myproj") == "https://example.com/subject.jpg"

    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert get_subject_url("nonexistent") is None


class TestGetAudioUrl:
    def test_reads_audio_url(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "myproj"
        project_dir.mkdir(parents=True)
        (project_dir / "audio_url.txt").write_text("https://example.com/audio.mp3")
        monkeypatch.chdir(tmp_path)
        assert get_audio_url("myproj") == "https://example.com/audio.mp3"

    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert get_audio_url("nonexistent") is None

