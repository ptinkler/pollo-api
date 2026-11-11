"""Tests for web.api — the endpoints and helpers that remain after the legacy
generation/projects/jobs subsystem was removed (auth, SPA serving, lifespan)."""

import asyncio
import sys

import pytest
from fastapi.testclient import TestClient

import web.api as api_mod
from web.api import _static_file
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

    for name, mod in list(sys.modules.items()):
        if name.startswith("web.") and getattr(mod, "get_db", None) is not None:
            monkeypatch.setattr(mod, "get_db", lambda: db)
    return TestClient(api_mod.app, raise_server_exceptions=False)


class TestLifespan:
    def test_lifespan_runs(self, client, db):

        async def run_lifespan():
            async with api_mod.lifespan(api_mod.app):
                pass

        asyncio.run(run_lifespan())


class TestMainGuards:
    def test_api_main_guard(self):

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

        assert _static_file("favicon.ico", static) == (static / "favicon.ico").resolve()

    def test_unknown_path_falls_back_to_index(self, static):

        assert _static_file("project/foo/gallery", static) == static / "index.html"

    @pytest.mark.parametrize("path", ["../.env", "assets/../../.env", "/etc/passwd", "..", "../static2/x"])
    def test_traversal_falls_back_to_index(self, static, path):

        assert _static_file(path, static) == static / "index.html"


class TestLoginThrottle:
    def test_throttle_is_per_account_despite_ip_spoofing(self, client):
        """Rotating the client-IP headers must not lift the per-email cap: a
        brute-force against one account trips the throttle even from fresh IPs."""

        api_mod._login_attempts.clear()
        last = None
        for i in range(api_mod.LOGIN_MAX_ATTEMPTS + 2):
            last = client.post(
                "/api/auth/login",
                json={"email": "victim@example.com", "password": "wrong"},
                headers={"X-Real-IP": f"10.0.0.{i}"},  # a different IP each attempt
            )
        assert last.status_code == 429
