"""Tests for web.media — the library of every upload and creation."""

import io

import pytest
from PIL import Image

from tests.test_api import _setup_env, client, db  # noqa: F401 — fixtures


def _png(color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def project(db):
    import web.api as api_mod

    proj = db.create_project(name="Media Proj")
    folder = api_mod.ASSETS_DIR / proj.assets_folder
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "src-abc.png").write_bytes(_png())  # an upload
    (folder / "thumb.jpg").write_bytes(_png())  # project thumbnail — not media
    (folder / "vid1.mp4").write_bytes(b"fake mp4")  # a generated video
    (folder / "gen1.png").write_bytes(_png("blue"))  # a generated image
    db.create_job(job_id="jv", project=proj.slug, model="seedance20v1", prompt="a fox runs")
    db.update_job("jv", status="done", video_path=str(folder / "vid1.mp4"))
    db.create_job(job_id="ji", project=proj.slug, model="seedreamv1", prompt="a fox portrait", job_type="image")
    db.update_job("ji", status="done", video_path=str(folder / "gen1.png"))
    return proj


@pytest.fixture()
def conv(db, tmp_path):
    import img2vid.common.config as config

    c = db.create_conversation(title="Fox chat")
    d = config.ROOT_DIR / "chat" / c.id
    d.mkdir(parents=True)
    (d / "up_1.png").write_bytes(_png())
    (d / "img_1.png").write_bytes(_png("green"))
    db.add_chat_message(
        c.id,
        "user",
        "here",
        media=[{"id": "u", "kind": "image", "source": "upload", "status": "done", "file": "up_1.png"}],
    )
    db.add_chat_message(
        c.id,
        "assistant",
        "drawn",
        media=[
            {
                "id": "g",
                "kind": "image",
                "source": "generated",
                "status": "done",
                "file": "img_1.png",
                "prompt": "fox in snow",
                "model": "a/b",
            },
            {"id": "p", "kind": "video", "source": "generated", "status": "pending", "file": None, "prompt": "x"},
        ],
    )
    return c


def _items(client):
    return {i["id"]: i for i in client.get("/api/media").json()["items"]}


class TestListing:
    def test_lists_everything_with_sources(self, client, project, conv):
        items = _items(client)
        slug = project.slug
        assert items[f"proj:{slug}:src-abc.png"]["source"] == "upload"
        assert items[f"proj:{slug}:vid1.mp4"]["kind"] == "video"
        assert items[f"proj:{slug}:vid1.mp4"]["thumb_url"] == f"/api/media/thumb/proj:{slug}:vid1.mp4"
        assert all(i["thumb_url"] for i in items.values())
        assert items[f"proj:{slug}:gen1.png"]["source"] == "generated"
        assert items[f"proj:{slug}:gen1.png"]["prompt"] == "a fox portrait"
        assert f"proj:{slug}:thumb.jpg" not in items
        assert items[f"chat:{conv.id}:up_1.png"]["source"] == "upload"
        chat_gen = items[f"chat:{conv.id}:img_1.png"]
        assert chat_gen["source"] == "generated" and chat_gen["conversation_title"] == "Fox chat"
        assert not any(i.startswith(f"chat:{conv.id}:") and "None" in i for i in items)  # pending skipped

    def test_upload_serve_delete(self, client):
        r = client.post("/api/media/upload", files={"file": ("a.png", _png(), "image/png")})
        item = r.json()
        assert item["origin"] == "library" and item["source"] == "upload"
        assert client.get(item["url"]).content == _png()
        assert item["id"] in _items(client)
        assert client.delete(f"/api/media/{item['id']}").status_code == 200
        assert item["id"] not in _items(client)

    def test_rejects_non_images(self, client):
        assert client.post("/api/media/upload", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400

    @pytest.mark.parametrize("media_id", ["lib:../x.png", "proj:nope:a.png", "chat:abc:..", "zzz:1"])
    def test_bad_ids(self, client, media_id):
        assert client.delete(f"/api/media/{media_id}").status_code in (400, 404)


class TestOrphans:
    @pytest.fixture()
    def orphans(self, db, conv):
        """conv plus an attachment nothing sent, a reference a reply was made
        from, and the folder of a deleted chat — all old enough."""
        import os

        import img2vid.common.config as config

        root = config.ROOT_DIR / "chat"
        (root / conv.id / "up_lost.png").write_bytes(_png())
        (root / conv.id / "up_ref.png").write_bytes(_png())
        db.add_chat_message(
            conv.id,
            "assistant",
            "",
            media=[
                {
                    "id": "r",
                    "kind": "image",
                    "source": "generated",
                    "status": "pending",
                    "params": {"refs": ["up_ref.png"]},
                }
            ],
        )
        (root / "gone").mkdir()
        (root / "gone" / "img_old.png").write_bytes(_png())
        for p in root.rglob("*.png"):
            os.utime(p, (0, 0))
        (root / conv.id / "up_new.png").write_bytes(_png())  # too new — may still be in the composer
        return root

    def test_lists_unrecorded_chat_files(self, client, conv, orphans):
        items = _items(client)
        orphaned = {k for k, i in items.items() if i["origin"] == "orphan"}
        assert orphaned == {f"chat:{conv.id}:up_lost.png", "chat:gone:img_old.png"}
        assert items[f"chat:{conv.id}:up_lost.png"]["conversation_title"] == "Fox chat"
        assert items["chat:gone:img_old.png"]["conversation_id"] is None
        assert items[f"chat:{conv.id}:img_1.png"]["origin"] == "chat"

    def test_delete(self, client, orphans):
        assert client.delete("/api/media/chat:gone:img_old.png").status_code == 200
        assert not (orphans / "gone" / "img_old.png").exists()


class TestImport:
    def test_into_a_project(self, client, project, conv):
        import web.api as api_mod

        r = client.post(
            "/api/media/import",
            json={
                "media_id": f"chat:{conv.id}:img_1.png",
                "target": "project",
                "project": project.slug,
                "prefix": "src",
            },
        ).json()
        name = r["image_url"].removeprefix("local:")
        assert name.startswith("src-") and (api_mod.ASSETS_DIR / project.assets_folder / name).is_file()
        # An upload already in that project is reused, not copied
        same = client.post(
            "/api/media/import",
            json={"media_id": f"proj:{project.slug}:src-abc.png", "target": "project", "project": project.slug},
        ).json()
        assert same == {"image_url": "local:src-abc.png"}

    def test_into_a_chat(self, client, project, conv):
        import img2vid.common.config as config

        r = client.post(
            "/api/media/import",
            json={"media_id": f"proj:{project.slug}:gen1.png", "target": "chat", "conversation_id": conv.id},
        ).json()
        assert r["file"].startswith("up_") and (config.ROOT_DIR / "chat" / conv.id / r["file"]).is_file()

    def test_into_a_character(self, client, conv):
        char = client.post("/api/characters", json={"name": "Fox"}).json()
        r = client.post(
            "/api/media/import",
            json={"media_id": f"chat:{conv.id}:img_1.png", "target": "character", "character_id": char["id"]},
        ).json()
        assert len(r["images"]) == 1

    def test_videos_cant_be_imported(self, client, project, conv):
        r = client.post(
            "/api/media/import",
            json={"media_id": f"proj:{project.slug}:vid1.mp4", "target": "chat", "conversation_id": conv.id},
        )
        assert r.status_code == 400


class TestDelete:
    def test_project_creation_deletes_its_job(self, client, db, project):
        assert client.delete(f"/api/media/proj:{project.slug}:vid1.mp4").status_code == 200
        assert db.get_job("jv") is None

    def test_project_upload_clears_the_project_image(self, client, db, project):
        db.update_project(project.slug, image_url="local:src-abc.png")
        assert client.delete(f"/api/media/proj:{project.slug}:src-abc.png").status_code == 200
        assert db.get_project_by_slug(project.slug).image_url is None

    def test_chat_item_leaves_its_message(self, client, db, conv):
        import img2vid.common.config as config

        assert client.delete(f"/api/media/chat:{conv.id}:img_1.png").status_code == 200
        reply = db.get_chat_messages(conv.id)[-1]
        assert [i["id"] for i in reply.media] == ["p"]
        assert not (config.ROOT_DIR / "chat" / conv.id / "img_1.png").exists()

    def test_copies_survive(self, client, conv):
        char = client.post("/api/characters", json={"name": "Fox"}).json()
        client.post(
            "/api/media/import",
            json={"media_id": f"chat:{conv.id}:img_1.png", "target": "character", "character_id": char["id"]},
        )
        client.delete(f"/api/media/chat:{conv.id}:img_1.png")
        c = client.get(f"/api/characters/{char['id']}").json()
        assert client.get(f"/api/characters/{c['id']}/images/{c['images'][0]}").status_code == 200


class TestBlocked:
    @pytest.fixture()
    def blocked(self, db, conv):
        """conv plus: a moderated failure and a black image in a reply, an
        ordinary failure (kept), and a moderated failure detached to the library."""
        import img2vid.common.config as config

        d = config.ROOT_DIR / "chat" / conv.id
        (d / "img_black.png").write_bytes(_png("black"))
        db.add_chat_message(conv.id, "user", "again")
        db.add_chat_message(
            conv.id,
            "assistant",
            "",
            media=[
                {
                    "id": "m",
                    "kind": "image",
                    "source": "generated",
                    "status": "error",
                    "moderated": True,
                    "error": "flagged",
                },
                {"id": "b", "kind": "image", "source": "generated", "status": "done", "file": "img_black.png"},
                {
                    "id": "t",
                    "kind": "image",
                    "source": "generated",
                    "status": "error",
                    "moderated": False,
                    "error": "timeout",
                },
            ],
        )
        old = db.add_chat_message(conv.id, "user", "older")
        db.add_chat_message(
            conv.id,
            "assistant",
            "",
            parent_id=old.id,
            media=[
                {
                    "id": "lm",
                    "kind": "video",
                    "source": "generated",
                    "status": "error",
                    "moderated": True,
                    "error": "nsfw",
                    "job_id": "venice:m:q",
                }
            ],
        )
        db.delete_chat_exchange(conv.id, old.id)
        return d

    def test_counts(self, client, blocked):
        assert client.get("/api/media/blocked").json() == {"moderated": 2, "black": 1}

    def test_clear_removes_them_and_keeps_the_rest(self, client, db, conv, blocked):
        assert client.post("/api/media/blocked/clear").json() == {"cleared": 3}
        media = {i["id"] for m in db.get_chat_messages(conv.id) for i in m.media}
        assert {"m", "b", "lm"}.isdisjoint(media) and {"t", "g", "u", "p"} <= media
        assert not (blocked / "img_black.png").exists() and (blocked / "img_1.png").exists()
        assert db.list_chat_library() == []
        assert client.get("/api/media/blocked").json() == {"moderated": 0, "black": 0}


class TestThumbnails:
    def _big_png(self, size=(1600, 900)) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", size, "purple").save(buf, "PNG")
        return buf.getvalue()

    def test_image_thumb_is_small_and_cached(self, client, monkeypatch):
        item = client.post("/api/media/upload", files={"file": ("a.png", self._big_png(), "image/png")}).json()
        r = client.get(item["thumb_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        thumb = Image.open(io.BytesIO(r.content))
        assert min(thumb.size) == 320 and thumb.size[0] > thumb.size[1]  # shorter side, shape kept
        # Second request comes from the cache — no re-encoding
        import web.media as media_mod

        monkeypatch.setattr(media_mod.Image, "open", lambda *a, **k: pytest.fail("re-encoded"))
        assert client.get(item["thumb_url"]).content == r.content

    def test_video_thumb_uses_the_first_frame(self, client, project, monkeypatch):
        import web.api as api_mod

        buf = io.BytesIO()
        Image.new("RGB", (640, 360), "orange").save(buf, "JPEG")
        monkeypatch.setattr(api_mod, "_extract_first_frame_uncached", lambda p: buf.getvalue())
        r = client.get(f"/api/media/thumb/proj:{project.slug}:vid1.mp4")
        assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (569, 320)

    def test_unreadable_file_has_no_thumb(self, client, project, monkeypatch):
        import web.api as api_mod

        monkeypatch.setattr(api_mod, "_extract_first_frame_uncached", lambda p: None)
        assert client.get(f"/api/media/thumb/proj:{project.slug}:vid1.mp4").status_code == 404

    def test_delete_drops_the_cached_thumb(self, client):
        import web.media as media_mod

        item = client.post("/api/media/upload", files={"file": ("a.png", _png(), "image/png")}).json()
        client.get(item["thumb_url"])
        assert list(media_mod.thumb_dir().iterdir())
        client.delete(f"/api/media/{item['id']}")
        assert not list(media_mod.thumb_dir().iterdir())

    def test_at_most_two_made_at_once(self, client, monkeypatch):
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor

        import web.media as media_mod

        ids = [
            client.post("/api/media/upload", files={"file": (f"{n}.png", _png(), "image/png")}).json()["thumb_url"]
            for n in range(8)
        ]
        real, lock, state = media_mod.make_thumb, threading.Lock(), {"now": 0, "peak": 0}

        def slow_thumb(path):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            try:
                return real(path)
            finally:
                with lock:
                    state["now"] -= 1

        monkeypatch.setattr(media_mod, "make_thumb", slow_thumb)
        with ThreadPoolExecutor(8) as pool:
            codes = list(pool.map(lambda u: client.get(u).status_code, ids))
        assert codes == [200] * 8 and state["peak"] <= media_mod.THUMB_WORKERS
