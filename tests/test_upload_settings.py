"""Per-user source-media hosting: prefs resolution, host dispatch order, and
the signed self-host serving route."""

import types

import pytest
from fastapi.testclient import TestClient

from web import image_hosts, public_media, upload_settings
from web.core import config


def _user(upload_prefs_json=None):
    return types.SimpleNamespace(id="u1", upload_prefs_json=upload_prefs_json)


class TestPrefsResolution:
    def test_default_from_env(self, monkeypatch):
        monkeypatch.setenv("UPLOAD_PRIMARY", "tmpfiles")
        monkeypatch.setenv("UPLOAD_BACKUP", "litterbox")
        monkeypatch.setenv("UPLOAD_EXPIRY_MINUTES", "1440")
        d = upload_settings.default_prefs()
        assert d["primary"] == "tmpfiles" and d["backup"] == "litterbox" and d["expiry_minutes"] == 1440

    def test_unset_user_gets_default(self):
        assert upload_settings.resolve_prefs(_user())["primary"] == upload_settings.default_prefs()["primary"]

    def test_stored_overrides_default(self):
        prefs = upload_settings.resolve_prefs(_user('{"primary": "selfhost", "selfhost_base": "https://x.test"}'))
        assert prefs["primary"] == "selfhost" and prefs["selfhost_base"] == "https://x.test"

    def test_invalid_host_and_expiry_dropped(self):
        prefs = upload_settings.resolve_prefs(_user('{"primary": "nope", "expiry_minutes": 7}'))
        d = upload_settings.default_prefs()
        assert prefs["primary"] == d["primary"] and prefs["expiry_minutes"] == d["expiry_minutes"]

    def test_backup_equal_to_primary_becomes_none(self):
        prefs = upload_settings.resolve_prefs(_user('{"primary": "litterbox", "backup": "litterbox"}'))
        assert prefs["backup"] is None

    def test_corrupt_blob_falls_back(self):
        assert upload_settings.resolve_prefs(_user("not json"))["primary"] == upload_settings.default_prefs()["primary"]


class TestDispatchOrder:
    def test_primary_then_backup(self, monkeypatch):
        calls = []
        monkeypatch.setattr(image_hosts, "_upload_to_litterbox", lambda p, e=60: calls.append("litterbox") or "L")
        monkeypatch.setattr(image_hosts, "_upload_to_tmpfiles", lambda p, e=60: calls.append("tmpfiles") or "T")
        prefs = {"primary": "tmpfiles", "backup": "litterbox", "expiry_minutes": 60}
        assert image_hosts.upload_file("f", prefs) == "T" and calls == ["tmpfiles"]

    def test_falls_back_to_backup_on_failure(self, monkeypatch):
        def boom(p, e=60):
            raise ValueError("down")

        monkeypatch.setattr(image_hosts, "_upload_to_tmpfiles", boom)
        monkeypatch.setattr(image_hosts, "_upload_to_litterbox", lambda p, e=60: "L")
        prefs = {"primary": "tmpfiles", "backup": "litterbox", "expiry_minutes": 60}
        assert image_hosts.upload_file("f", prefs) == "L"

    def test_all_fail_raises(self, monkeypatch):
        monkeypatch.setattr(image_hosts, "_upload_to_tmpfiles", lambda p, e=60: (_ for _ in ()).throw(ValueError("x")))
        prefs = {"primary": "tmpfiles", "backup": None, "expiry_minutes": 60}
        with pytest.raises(ValueError, match="All upload hosts failed"):
            image_hosts.upload_file("f", prefs)

    def test_litterbox_expiry_bucketed(self):
        assert image_hosts._litterbox_time(70) == "1h" and image_hosts._litterbox_time(4000) == "72h"


class TestSelfHost:
    def test_selfhost_url_requires_base(self, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"x")
        with pytest.raises(ValueError, match="public base URL"):
            public_media.selfhost_url(f, "", ttl_seconds=60)

    def test_token_round_trip_and_serve(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
        media = tmp_path / "chat" / "conv1"
        media.mkdir(parents=True)
        f = media / "clip.mp4"
        f.write_bytes(b"hello")
        url = public_media.selfhost_url(f, "https://my.box", ttl_seconds=120)
        token = url.rsplit("/", 1)[1]
        client = TestClient(_app())
        r = client.get(f"/api/public-media/{token}")
        assert r.status_code == 200 and r.content == b"hello"

    def test_serves_from_character_refs_root(self, tmp_path, monkeypatch):
        # Character reference images (ROOT_DIR/characters) are a valid Pollo
        # image-ref source, so the self-host route must serve them too.
        monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
        chars = tmp_path / "characters" / "7"
        chars.mkdir(parents=True)
        f = chars / "face.png"
        f.write_bytes(b"png")
        url = public_media.selfhost_url(f, "https://my.box", ttl_seconds=120)
        token = url.rsplit("/", 1)[1]
        assert TestClient(_app()).get(f"/api/public-media/{token}").content == b"png"

    def test_expired_token_404(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
        media = tmp_path / "chat"
        media.mkdir(parents=True)
        f = media / "clip.mp4"
        f.write_bytes(b"hi")
        token = public_media.sign_media_token(f, ttl_seconds=-1)  # already expired
        assert TestClient(_app()).get(f"/api/public-media/{token}").status_code == 404

    def test_tampered_token_404(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
        (tmp_path / "chat").mkdir(parents=True)
        f = tmp_path / "chat" / "clip.mp4"
        f.write_bytes(b"hi")
        token = public_media.sign_media_token(f, ttl_seconds=120)[:-2] + "zz"
        assert TestClient(_app()).get(f"/api/public-media/{token}").status_code == 404

    def test_out_of_bounds_path_404(self, tmp_path, monkeypatch):
        # A validly-signed token for a file outside the media roots must not serve.
        monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
        (tmp_path / "chat").mkdir(parents=True)
        secret = tmp_path / "secret.env"
        secret.write_bytes(b"KEY=1")
        token = public_media.sign_media_token(secret, ttl_seconds=120)
        assert TestClient(_app()).get(f"/api/public-media/{token}").status_code == 404


class TestApi:
    def test_get_returns_defaults_and_meta(self):
        r = TestClient(_app()).get("/api/settings/uploads")
        assert r.status_code == 200
        body = r.json()
        assert body["prefs"]["primary"] in upload_settings.HOSTS
        assert "litterbox" in body["hosts"] and body["expiry_options"] == list(upload_settings.EXPIRY_OPTIONS)


def _app():
    import web.api as api_mod

    return api_mod.app
