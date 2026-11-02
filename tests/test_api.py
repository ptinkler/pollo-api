"""Tests for web.api — the endpoints and helpers that remain after the legacy
generation/projects/jobs subsystem was removed (auth, SPA serving, the video
first-frame helper the media library uses, lifespan)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web.core.metadata import MetadataDB


@pytest.fixture(autouse=True)
def _setup_env(tmp_path, monkeypatch, provider_keys):
    monkeypatch.setenv("POLLO_DATA_DIR", str(tmp_path))
    provider_keys["pollo"] = "test-key"
    (tmp_path / "data").mkdir()


@pytest.fixture()
def db(tmp_path):
    return MetadataDB(db_path=tmp_path / "data" / "metadata.db")


@pytest.fixture()
def client(db, monkeypatch):
    """A test client with the DB patched everywhere it's resolved: every
    already-imported web.* module that pulled in `get_db` (importing web.api
    loads the whole app graph), so it doesn't matter which submodule a route
    lives in."""
    import sys

    import web.api as api_mod  # noqa: F401 — loads the app and its whole import graph

    for name, mod in list(sys.modules.items()):
        if name.startswith("web.") and getattr(mod, "get_db", None) is not None:
            monkeypatch.setattr(mod, "get_db", lambda: db)
    return TestClient(api_mod.app, raise_server_exceptions=False)


class TestExtractFirstFrameUncached:
    """_extract_first_frame_uncached: used by the media library for video thumbs."""

    def test_cap_not_opened(self, tmp_path):
        import web.api as api_mod

        fp = tmp_path / "notavideo.mp4"
        fp.write_bytes(b"definitely not a video")
        assert api_mod._extract_first_frame_uncached(fp) is None

    def test_read_fails(self, tmp_path):
        import web.api as api_mod

        fp = tmp_path / "readfail.mp4"
        fp.write_bytes(b"\x00" * 100)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        with patch("web.api.cv2.VideoCapture", return_value=mock_cap):
            assert api_mod._extract_first_frame_uncached(fp) is None
        mock_cap.release.assert_called_once()

    def test_success(self, tmp_path):
        import numpy as np

        import web.api as api_mod

        fp = tmp_path / "success.mp4"
        fp.write_bytes(b"\x00" * 100)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((2, 2, 3), dtype=np.uint8))
        with patch("web.api.cv2.VideoCapture", return_value=mock_cap):
            assert api_mod._extract_first_frame_uncached(fp) is not None

    def test_exception(self, tmp_path):
        import web.api as api_mod

        fp = tmp_path / "exc.mp4"
        fp.write_bytes(b"\x00" * 100)
        with patch("web.api.cv2.VideoCapture", side_effect=Exception("cv2 error")):
            assert api_mod._extract_first_frame_uncached(fp) is None


class TestLifespan:
    def test_lifespan_runs(self, client, db):
        import web.api as api_mod

        async def run_lifespan():
            async with api_mod.lifespan(api_mod.app):
                pass

        asyncio.run(run_lifespan())


class TestMainGuards:
    def test_api_main_guard(self):
        import web.api as api_mod

        assert hasattr(api_mod, "app")


class TestStaticFile:
    @pytest.fixture()
    def static(self, tmp_path):
        d = tmp_path / "static"
        (d / "assets").mkdir(parents=True)
        (d / "index.html").write_text("index")
        (d / "favicon.ico").write_text("icon")
        (tmp_path / ".env").write_text("SECRET=1")
        return d

    def test_serves_existing_file(self, static):
        from web.api import _static_file

        assert _static_file("favicon.ico", static) == (static / "favicon.ico").resolve()

    def test_unknown_path_falls_back_to_index(self, static):
        from web.api import _static_file

        assert _static_file("project/foo/gallery", static) == static / "index.html"

    @pytest.mark.parametrize("path", ["../.env", "assets/../../.env", "/etc/passwd", "..", "../static2/x"])
    def test_traversal_falls_back_to_index(self, static, path):
        from web.api import _static_file

        assert _static_file(path, static) == static / "index.html"


class TestLoginThrottle:
    def test_throttle_is_per_account_despite_ip_spoofing(self, client):
        """Rotating the client-IP headers must not lift the per-email cap: a
        brute-force against one account trips the throttle even from fresh IPs."""
        import web.api as api_mod

        api_mod._login_attempts.clear()
        last = None
        for i in range(api_mod.LOGIN_MAX_ATTEMPTS + 2):
            last = client.post(
                "/api/auth/login",
                json={"email": "victim@example.com", "password": "wrong"},
                headers={"X-Real-IP": f"10.0.0.{i}"},  # a different IP each attempt
            )
        assert last.status_code == 429
