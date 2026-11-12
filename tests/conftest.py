"""Global test fixtures — prevent tests from touching the real database, the.

real assets, the developer's .env, or the network.
"""

import types

import pytest
import requests

# Imported at collection, before any fixture patches anything: a module's
# `from x import y` names bind once, and whatever they point at then is what
# runs for the rest of the session.
import web.api
import web.core.config as config_mod
import web.users
from web.core import metadata

# Every setting the app reads from the environment. A developer's .env is
# loaded at import (web/core/config.py), so without this a test would behave
# differently on their machine than in CI — and DEV_LOGIN in particular sends
# /api/keys down a path that opens a SECOND connection to the same SQLite
# file, which blocks for 30s on `PRAGMA locking_mode=EXCLUSIVE` and then 500s.
# A test that wants one of these sets it itself.
_APP_ENV = (
    "ADMIN_EMAILS",
    "ALLOWED_EMAILS",
    "CHAT_TITLE_MODEL",
    "COOKIE_SECURE",
    "DEV_EMAIL",
    "DEV_LOGIN",
    "ENABLE_API_DOCS",
    "GLUETUN_API_KEY",
    "KEYS_SECRET",
    "OPENROUTER_BASE_URL",
    "OPEN_SIGNUP",
    "PASSWORD_PEPPER",
    "POLLO_DATA_DIR",
    "PUBLIC_BASE_URL",
    "SESSION_SECRET",
    "UPLOAD_BACKUP",
    "UPLOAD_EXPIRY_MINUTES",
    "UPLOAD_PRIMARY",
    "UPLOAD_SELFHOST_BASE",
    "VENICE_BASE_URL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Run every test against a bare environment, whatever is in .env."""
    for name in _APP_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _guard_real_db(monkeypatch, tmp_path):
    """Redirect config paths to a temp directory so no test can accidentally.

    create files in the real data/assets directories.
    """
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(config_mod, "DB_PATH", tmp_path / "data" / "metadata.db")


# Per-test provider keys, injected without ever touching the environment:
# production reads a user's keys from the DB, and nothing (prod or test) reads
# a provider key from an env var. Tests request the `provider_keys` fixture and
# set entries on it, e.g. provider_keys["pollo"] = "test-key".
_TEST_PROVIDER_KEYS: dict[str, str | None] = {}


@pytest.fixture(autouse=True)
def provider_keys(monkeypatch):
    """Inject per-user provider keys for a test via an in-memory dict, patching.

    only the resolver seam. No API key is read from the environment.
    """
    _TEST_PROVIDER_KEYS.clear()
    monkeypatch.setattr(
        "web.keyctx.provider_key",
        lambda provider: _TEST_PROVIDER_KEYS.get(provider) or None,
        raising=False,
    )
    return _TEST_PROVIDER_KEYS


def pytest_configure(config):
    """Document the pytest configure test helper."""
    config.addinivalue_line("markers", "no_tenant: run without a bound tenant (schema/migration tests on old DBs)")


@pytest.fixture(autouse=True)
def _tenant(request, monkeypatch):
    """Bind one test tenant so multi-tenant ORM scoping is consistent: rows.

    created directly via the db and via the API (middleware) all belong to it,
    and the middleware resolves this same admin without touching the real DB.

    Tests marked `no_tenant` opt out — they build pre-user_id schemas where the
    scope filter can't reference the column yet.
    """
    if "no_tenant" in request.keywords:
        yield None
        return

    admin = types.SimpleNamespace(
        id="test-user",
        is_admin=True,
        email="admin@local",
        name="Admin",
        password_hash=None,
        api_keys_json=None,
    )

    # Match the real 1-arg signature so a stale multi-arg call fails here too.
    # Patch every module that imported the name, not just where it is defined:
    # `from .users import resolve_current_user` binds at import, so patching
    # web.users alone would leave web.api's middleware calling the real one.
    def resolve(user_cookie=None):
        return admin

    # Patch every module that imported the name, not just where it is defined:
    # `from .users import resolve_current_user` binds at import, so patching
    # web.users alone would leave web.api's middleware calling the real one.
    for module in (web.users, web.api):
        monkeypatch.setattr(module, "resolve_current_user", resolve)
    token = metadata.set_tenant(admin.id)
    try:
        yield admin
    finally:
        metadata.reset_tenant(token)


@pytest.fixture(autouse=True)
def _no_outbound_http(monkeypatch):
    """Fail loudly instead of reaching a real API.

    Everything a test needs is mocked, so a real request means something is
    wrong — usually a background thread (a video poller, a turn worker) that
    outlived the test that started it and is now running with the mocks undone.
    Left alone that shows up as an unrelated test timing out 30 seconds later,
    which is very hard to trace back; this names it on the spot.
    """

    def blocked(*args, **kwargs):
        target = args[1] if len(args) > 1 else (args[0] if args else kwargs.get("url", "?"))
        raise AssertionError(f"a test tried to reach the network: {target}")

    for name in ("request", "get", "post", "put", "delete", "head"):
        monkeypatch.setattr(requests, name, blocked, raising=False)
    monkeypatch.setattr(requests.Session, "request", blocked, raising=False)
