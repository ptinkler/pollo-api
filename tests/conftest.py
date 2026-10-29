"""Global test fixtures — prevent tests from touching the real database or assets."""

import pytest


@pytest.fixture(autouse=True)
def _guard_real_db(monkeypatch, tmp_path):
    """Redirect config paths to a temp directory so no test can accidentally
    create files in the real data/assets directories."""
    import img2vid.common.config as config_mod

    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(config_mod, "DB_PATH", tmp_path / "data" / "metadata.db")


@pytest.fixture(autouse=True)
def _provider_keys_from_env(monkeypatch):
    """Production resolves provider keys per user from the DB (no .env fallback).
    Tests inject keys the convenient way — via env vars — so patch only the
    resolver seam to read env in tests. Production keyctx is unchanged.

    Import web.api first so its load_dotenv() has run, then clear the provider
    keys to a clean baseline (otherwise a later first import would re-add the
    developer's .env keys and undo a test's delenv)."""
    import os

    import web.api  # noqa: F401 — ensure load_dotenv() has already run

    env = {"pollo": "POLLO_API_KEY", "venice": "VENICE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
    for var in env.values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        "web.keyctx.provider_key",
        lambda provider: os.getenv(env.get(provider, ""), "").strip() or None,
        raising=False,
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "no_tenant: run without a bound tenant (schema/migration tests on old DBs)")


@pytest.fixture(autouse=True)
def _tenant(request, monkeypatch):
    """Bind one test tenant so multi-tenant ORM scoping is consistent: rows
    created directly via the db and via the API (middleware) all belong to it,
    and the middleware resolves this same admin without touching the real DB.

    Tests marked `no_tenant` opt out — they build pre-user_id schemas where the
    scope filter can't reference the column yet."""
    import types

    from img2vid.common import metadata

    if "no_tenant" in request.keywords:
        yield None
        return

    admin = types.SimpleNamespace(id="test-user", is_admin=True, email="admin@local", api_keys_json=None)
    monkeypatch.setattr("web.users.resolve_current_user", lambda *a, **k: admin, raising=False)
    token = metadata.set_tenant(admin.id)
    try:
        yield admin
    finally:
        metadata.reset_tenant(token)
