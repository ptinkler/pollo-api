"""Tests for web.api — the endpoints and helpers that remain after the legacy
generation/projects/jobs subsystem was removed (auth, SPA serving, lifespan).
"""

import asyncio

import pytest

import web.api as api_mod
from web.api import _static_file

pytest_plugins = ["tests.api_fixtures"]


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
    @pytest.fixture
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
        brute-force against one account trips the throttle even from fresh IPs.
        """
        api_mod._login_attempts.clear()
        last = None
        for i in range(api_mod.LOGIN_MAX_ATTEMPTS + 2):
            last = client.post(
                "/api/auth/login",
                json={"email": "victim@example.com", "password": "wrong"},
                headers={"X-Real-IP": f"10.0.0.{i}"},  # a different IP each attempt
            )
        assert last.status_code == 429
