"""Tests for img2vid.common.download — download, validation, filename utilities."""
import os
import struct
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from img2vid.common.download import (
    get_filename, get_filename_from_url, get_unique_filepath,
    download_file, download_image, download_video,
    validate_video, _has_moov_atom,
)


# ── Filename utilities ───────────────────────────────────────────────

class TestGetFilename:
    def test_returns_uuid_mp4(self):
        fn = get_filename()
        assert fn.endswith(".mp4")
        assert len(fn) > 5  # UUID + .mp4


class TestGetFilenameFromUrl:
    def test_simple_url(self):
        assert get_filename_from_url("https://cdn.example.com/path/video.mp4") == "video.mp4"

    def test_url_with_query(self):
        result = get_filename_from_url("https://cdn.example.com/path/video.mp4?token=abc")
        assert result == "video.mp4"

    def test_url_with_special_chars(self):
        result = get_filename_from_url("https://cdn.example.com/path/my video (1).mp4")
        assert result is not None
        assert result.endswith(".mp4")
        # Special chars should be sanitized
        assert " " not in result

    def test_non_mp4_url(self):
        assert get_filename_from_url("https://cdn.example.com/path/file.txt") is None

    def test_no_path(self):
        assert get_filename_from_url("https://example.com/") is None

    def test_empty_url(self):
        assert get_filename_from_url("") is None

    def test_encoded_url(self):
        result = get_filename_from_url("https://cdn.example.com/path/my%20video.mp4")
        assert result is not None
        assert result.endswith(".mp4")


class TestGetUniqueFilepath:
    def test_no_collision(self, tmp_path):
        result = get_unique_filepath(str(tmp_path), "video.mp4")
        assert result == f"{tmp_path}/video.mp4"

    def test_collision(self, tmp_path):
        (tmp_path / "video.mp4").write_text("existing")
        result = get_unique_filepath(str(tmp_path), "video.mp4")
        assert result == f"{tmp_path}/video(1).mp4"

    def test_multiple_collisions(self, tmp_path):
        (tmp_path / "video.mp4").write_text("existing")
        (tmp_path / "video(1).mp4").write_text("existing")
        result = get_unique_filepath(str(tmp_path), "video.mp4")
        assert result == f"{tmp_path}/video(2).mp4"


# ── Moov atom / validation ──────────────────────────────────────────

def _make_mp4_with_moov(filepath: str):
    """Create a minimal valid MP4 with ftyp + moov boxes."""
    with open(filepath, 'wb') as f:
        # ftyp box
        ftyp_data = b'isom'
        ftyp_size = 8 + len(ftyp_data)
        f.write(struct.pack('>I', ftyp_size))
        f.write(b'ftyp')
        f.write(ftyp_data)
        # moov box (empty body, just the header counts)
        moov_data = b'\x00' * 100
        moov_size = 8 + len(moov_data)
        f.write(struct.pack('>I', moov_size))
        f.write(b'moov')
        f.write(moov_data)
    # Pad to > 1024 bytes
    with open(filepath, 'ab') as f:
        f.write(b'\x00' * 1024)


def _make_mp4_without_moov(filepath: str):
    """Create an MP4-like file without a moov atom."""
    with open(filepath, 'wb') as f:
        data = b'\x00' * 100
        f.write(struct.pack('>I', 8 + len(data)))
        f.write(b'ftyp')
        f.write(data)
        f.write(struct.pack('>I', 8 + len(data)))
        f.write(b'mdat')
        f.write(data)
    # Pad to > 1024 bytes
    with open(filepath, 'ab') as f:
        f.write(b'\x00' * 1024)


class TestHasMoovAtom:
    def test_valid_mp4(self, tmp_path):
        fp = str(tmp_path / "valid.mp4")
        _make_mp4_with_moov(fp)
        assert _has_moov_atom(fp) is True

    def test_missing_moov(self, tmp_path):
        fp = str(tmp_path / "nomoov.mp4")
        _make_mp4_without_moov(fp)
        assert _has_moov_atom(fp) is False

    def test_too_small(self, tmp_path):
        fp = str(tmp_path / "tiny.mp4")
        with open(fp, 'wb') as f:
            f.write(b'\x00\x00')
        assert _has_moov_atom(fp) is False

    def test_nonexistent_file(self):
        assert _has_moov_atom("/nonexistent/file.mp4") is False


class TestValidateVideo:
    def test_valid_video(self, tmp_path):
        fp = str(tmp_path / "valid.mp4")
        _make_mp4_with_moov(fp)
        # Should not raise
        validate_video(fp)

    def test_too_small(self, tmp_path):
        fp = str(tmp_path / "tiny.mp4")
        with open(fp, 'wb') as f:
            f.write(b'\x00' * 100)
        with pytest.raises(ValueError, match="too small"):
            validate_video(fp)

    def test_no_moov(self, tmp_path):
        fp = str(tmp_path / "nomoov.mp4")
        _make_mp4_without_moov(fp)
        with pytest.raises(ValueError, match="moov atom"):
            validate_video(fp)

    def test_non_mp4_skips_moov_check(self, tmp_path):
        fp = str(tmp_path / "video.webm")
        with open(fp, 'wb') as f:
            f.write(b'\x00' * 2048)
        # Should not raise — moov check only for .mp4
        validate_video(fp)


# ── Download functions ───────────────────────────────────────────────

class TestDownloadFile:
    def test_downloads_content(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_resp.raise_for_status = MagicMock()
        dest = str(tmp_path / "out.mp4")
        with patch("img2vid.common.download.requests.get", return_value=mock_resp):
            download_file("https://example.com/video.mp4", dest)
        assert (tmp_path / "out.mp4").read_bytes() == b"chunk1chunk2"


class TestDownloadImage:
    def test_downloads_new_image(self, tmp_path, monkeypatch):
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"imgdata"]
        mock_resp.raise_for_status = MagicMock()

        with patch("img2vid.common.download.requests.get", return_value=mock_resp), \
             patch("img2vid.common.download.record_download"):
            result = download_image("https://example.com/img.jpg", "testproj")
        assert "image.jpg" in result

    def test_skips_existing_image(self, tmp_path, monkeypatch):
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        proj_dir = tmp_path / "testproj"
        proj_dir.mkdir()
        (proj_dir / "image.jpg").write_text("existing")

        result = download_image("https://example.com/img.jpg", "testproj")
        assert "image.jpg" in result


class TestDownloadVideo:
    def test_downloads_and_validates(self, tmp_path, monkeypatch):
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()

        def fake_download(url, dest):
            _make_mp4_with_moov(dest)

        mock_db = MagicMock()
        mock_db.get_downloads_by_task_id.return_value = []

        with patch("img2vid.common.download.download_file", side_effect=fake_download), \
             patch("img2vid.common.download.record_download"), \
             patch("img2vid.common.download.get_db", return_value=mock_db):
            result = download_video("https://cdn.example.com/video.mp4", "proj", task_id="t1", model="pollodance20")
        assert result.endswith(".mp4")

    def test_removes_corrupt_file(self, tmp_path, monkeypatch):
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()

        def fake_download(url, dest):
            with open(dest, 'wb') as f:
                f.write(b'\x00' * 100)  # Too small

        with patch("img2vid.common.download.download_file", side_effect=fake_download):
            with pytest.raises(ValueError, match="too small"):
                download_video("https://cdn.example.com/video.mp4", "proj")

    def test_no_record_when_disabled(self, tmp_path, monkeypatch):
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()

        def fake_download(url, dest):
            _make_mp4_with_moov(dest)

        with patch("img2vid.common.download.download_file", side_effect=fake_download), \
             patch("img2vid.common.download.record_download") as mock_record:
            download_video("https://cdn.example.com/video.mp4", "proj", record=False)
        mock_record.assert_not_called()

    def test_fallback_to_uuid_filename(self, tmp_path, monkeypatch):
        """When URL doesn't yield an mp4 filename, fall back to UUID."""
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()

        def fake_download(url, dest):
            _make_mp4_with_moov(dest)

        with patch("img2vid.common.download.download_file", side_effect=fake_download), \
             patch("img2vid.common.download.record_download"):
            result = download_video("https://cdn.example.com/path/noext", "proj")
        # Should have used UUID filename
        assert result.endswith(".mp4")

    def test_corrupt_file_remove_oserror(self, tmp_path, monkeypatch):
        """When validate_video fails and os.remove also fails, still raises ValueError."""
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()

        def fake_download(url, dest):
            with open(dest, 'wb') as f:
                f.write(b'\x00' * 100)  # Too small

        with patch("img2vid.common.download.download_file", side_effect=fake_download), \
             patch("os.remove", side_effect=OSError("perm denied")):
            with pytest.raises(ValueError, match="too small"):
                download_video("https://cdn.example.com/video.mp4", "proj")


class TestDownloadImageNoRecord:
    def test_no_record_when_disabled(self, tmp_path, monkeypatch):
        import img2vid.common.download as dl_mod
        monkeypatch.setattr(dl_mod, "ASSETS_DIR", tmp_path)

        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"imgdata"]
        mock_resp.raise_for_status = MagicMock()

        with patch("img2vid.common.download.requests.get", return_value=mock_resp), \
             patch("img2vid.common.download.record_download") as mock_record:
            download_image("https://example.com/img.jpg", "testproj", record=False)
        mock_record.assert_not_called()



class TestHasMoovAtomEdgeCases:
    def test_short_header_mid_stream(self, tmp_path):
        """File truncated mid-box: header read returns < 8 bytes."""
        fp = str(tmp_path / "truncated.mp4")
        with open(fp, 'wb') as f:
            # Write a valid ftyp box
            data = b'isom'
            size = 8 + len(data)
            f.write(struct.pack('>I', size))
            f.write(b'ftyp')
            f.write(data)
            # Then write only 4 bytes (incomplete header)
            f.write(b'\x00\x00\x00\x20')
        assert _has_moov_atom(fp) is False

    def test_64bit_extended_size(self, tmp_path):
        """Box with size==1 uses 64-bit extended size."""
        fp = str(tmp_path / "ext64.mp4")
        with open(fp, 'wb') as f:
            # Write a box with 64-bit size
            f.write(struct.pack('>I', 1))       # size=1 means extended
            f.write(b'free')                     # box type
            f.write(struct.pack('>Q', 24))       # 64-bit size: 16 header + 8 body
            f.write(b'\x00' * 8)                 # body
            # Write moov box
            moov_body = b'\x00' * 8
            f.write(struct.pack('>I', 8 + len(moov_body)))
            f.write(b'moov')
            f.write(moov_body)
        assert _has_moov_atom(fp) is True

    def test_64bit_extended_size_truncated(self, tmp_path):
        """Box with size==1 but truncated before 64-bit size can be read."""
        fp = str(tmp_path / "ext64trunc.mp4")
        with open(fp, 'wb') as f:
            f.write(struct.pack('>I', 1))       # size=1
            f.write(b'free')                     # box type
            f.write(b'\x00\x00\x00')             # only 3 bytes of 64-bit size (need 8)
        assert _has_moov_atom(fp) is False

    def test_box_size_zero(self, tmp_path):
        """Box with size==0 extends to end of file — no moov."""
        fp = str(tmp_path / "zero_size.mp4")
        with open(fp, 'wb') as f:
            f.write(struct.pack('>I', 0))  # size=0
            f.write(b'mdat')               # box type
            f.write(b'\x00' * 100)
        assert _has_moov_atom(fp) is False

    def test_box_size_less_than_8(self, tmp_path):
        """Box with size < 8 should break the loop."""
        fp = str(tmp_path / "small_box.mp4")
        with open(fp, 'wb') as f:
            f.write(struct.pack('>I', 4))  # size=4, which is < 8
            f.write(b'ftyp')
        assert _has_moov_atom(fp) is False


class TestGetFilenameFromUrlException:
    def test_exception_returns_none(self):
        """When urlparse throws an exception, return None."""
        with patch("img2vid.common.download.urlparse", side_effect=Exception("parse error")):
            assert get_filename_from_url("https://example.com/video.mp4") is None

