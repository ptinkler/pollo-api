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


# Per-test provider keys, injected without ever touching the environment:
# production reads a user's keys from the DB, and nothing (prod or test) reads
# a provider key from an env var. Tests request the `provider_keys` fixture and
# set entries on it, e.g. provider_keys["pollo"] = "test-key".
_TEST_PROVIDER_KEYS: dict[str, str | None] = {}


@pytest.fixture(autouse=True)
def provider_keys(monkeypatch):
    """Inject per-user provider keys for a test via an in-memory dict, patching
    only the resolver seam. No API key is read from the environment."""
    import web.api  # noqa: F401 — ensure app import side effects have run

    _TEST_PROVIDER_KEYS.clear()
    monkeypatch.setattr(
        "web.keyctx.provider_key",
        lambda provider: _TEST_PROVIDER_KEYS.get(provider) or None,
        raising=False,
    )
    return _TEST_PROVIDER_KEYS


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
    # Match the real 1-arg signature so a stale multi-arg call fails here too.
    monkeypatch.setattr("web.users.resolve_current_user", lambda user_cookie=None: admin, raising=False)
    token = metadata.set_tenant(admin.id)
    try:
        yield admin
    finally:
        metadata.reset_tenant(token)
