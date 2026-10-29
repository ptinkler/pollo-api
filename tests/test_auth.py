"""Email+password admin auth: hashing, registration gating, login."""

import pytest
from fastapi.testclient import TestClient

from img2vid.common.metadata import MetadataDB


@pytest.fixture()
def db(tmp_path):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return MetadataDB(db_path=tmp_path / "data" / "metadata.db")


@pytest.fixture()
def client(db, monkeypatch):
    import web.api as api_mod

    monkeypatch.setattr(api_mod, "get_db", lambda: db)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@x.com")
    return TestClient(api_mod.app, raise_server_exceptions=False)


class TestHashing:
    def test_roundtrip_and_pepper(self, monkeypatch):
        from web import passwords

        monkeypatch.setenv("PASSWORD_PEPPER", "pepper-one")
        h = passwords.hash_password("correct horse battery")
        assert h != "correct horse battery"  # not plaintext
        assert passwords.verify_password(h, "correct horse battery")
        assert not passwords.verify_password(h, "wrong")
        assert not passwords.verify_password(None, "anything")
        # A different pepper must fail to verify the same password.
        monkeypatch.setenv("PASSWORD_PEPPER", "pepper-two")
        assert not passwords.verify_password(h, "correct horse battery")

    def test_unique_salt(self, monkeypatch):
        from web import passwords

        monkeypatch.setenv("PASSWORD_PEPPER", "p")
        assert passwords.hash_password("samepassword") != passwords.hash_password("samepassword")


class TestLogin:
    """Admins are created via the CLI (web.provision_admin), not the app — there
    is no register endpoint. Login verifies against that CLI-set password."""

    def test_no_register_endpoint(self, client):
        r = client.post("/api/auth/register", json={"email": "admin@x.com", "password": "longenough1"})
        assert r.status_code in (404, 405)  # no such route — admins are CLI-only

    def test_unknown_user(self, client):
        r = client.post("/api/auth/login", json={"email": "ghost@x.com", "password": "whatever123"})
        assert r.status_code == 401

    def test_cli_created_admin_can_log_in(self, client, db):
        from web.passwords import hash_password

        db.create_local_admin("admin@x.com", hash_password("longenough1"), name="Admin")
        assert client.post("/api/auth/login", json={"email": "admin@x.com", "password": "nope"}).status_code == 401
        ok = client.post("/api/auth/login", json={"email": "admin@x.com", "password": "longenough1"})
        assert ok.status_code == 200 and ok.json()["email"] == "admin@x.com"
        assert client.cookies.get("user_session")
