"""Fixtures for the plain-API tests, loaded via `pytest_plugins`.

A fixture plugin rather than a cross-module import: pytest resolves these by
name, so the modules that use them need no import of this file (and no F401 or
F811 to excuse one).
"""

import sys

import pytest
from fastapi.testclient import TestClient

import web.api as api_mod
from web.core.metadata import MetadataDB


@pytest.fixture(autouse=True)
def _setup_env(tmp_path, monkeypatch, provider_keys):
    monkeypatch.setenv("POLLO_DATA_DIR", str(tmp_path))
    provider_keys["pollo"] = "test-key"
    (tmp_path / "data").mkdir()


@pytest.fixture
def db(tmp_path):
    return MetadataDB(db_path=tmp_path / "data" / "metadata.db")


@pytest.fixture
def client(db, monkeypatch):
    """A test client with the DB patched everywhere it's resolved: every
    already-imported web.* module that pulled in `get_db` (importing web.api
    loads the whole app graph), so it doesn't matter which submodule a route
    lives in.
    """
    for name, mod in list(sys.modules.items()):
        if name.startswith("web.") and getattr(mod, "get_db", None) is not None:
            monkeypatch.setattr(mod, "get_db", lambda: db)
    return TestClient(api_mod.app, raise_server_exceptions=False)
