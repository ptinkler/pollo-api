"""Tests for web.media — the library of every upload and creation."""

import io
import os
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

import web.core.config as config
import web.media as media_mod
import web.media_cache as media_cache
from web.core import metadata

pytest_plugins = ["tests.api_fixtures"]


def _png(color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def conv(db, tmp_path):
    """Provide the conv fixture."""
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
    """Tests for listing."""

    def test_lists_everything_with_sources(self, client, conv):
        """Test that lists everything with sources."""
        client.post("/api/media/upload", files={"file": ("a.png", _png(), "image/png")})
        items = _items(client)
        assert all(i["thumb_url"] for i in items.values())
        assert any(i["origin"] == "library" and i["source"] == "upload" for i in items.values())
        assert items[f"chat:{conv.id}:up_1.png"]["source"] == "upload"
        chat_gen = items[f"chat:{conv.id}:img_1.png"]
        assert chat_gen["source"] == "generated"
        assert chat_gen["conversation_title"] == "Fox chat"
        assert not any(i.startswith(f"chat:{conv.id}:") and "None" in i for i in items)  # pending skipped

    def test_upload_serve_delete(self, client):
        """Test that upload serve delete."""
        r = client.post("/api/media/upload", files={"file": ("a.png", _png(), "image/png")})
        item = r.json()
        assert item["origin"] == "library"
        assert item["source"] == "upload"
        assert client.get(item["url"]).content == _png()
        assert item["id"] in _items(client)
        assert client.delete(f"/api/media/{item['id']}").status_code == 200
        assert item["id"] not in _items(client)

    def test_bulk_download_and_delete(self, client):
        """Test that bulk download and delete."""
        ids = [
            client.post("/api/media/upload", files={"file": (f"{n}.png", _png(n), "image/png")}).json()["id"]
            for n in ("red", "blue")
        ]
        r = client.post("/api/media/bulk-download", json={"ids": [*ids, "lib:missing.png"]})
        assert r.headers["content-type"] == "application/zip"
        assert len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 2  # the missing one is skipped
        r = client.post("/api/media/bulk-delete", json={"ids": [*ids, "lib:missing.png"]}).json()
        assert sorted(r["deleted"]) == sorted(ids)
        assert r["failed"] == ["lib:missing.png"]
        assert not set(ids) & set(_items(client))

    def test_rejects_non_images(self, client):
        """Test that rejects non images."""
        assert client.post("/api/media/upload", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400

    @pytest.mark.parametrize("media_id", ["lib:../x.png", "proj:nope:a.png", "chat:abc:..", "zzz:1"])
    def test_bad_ids(self, client, media_id):
        """Test that bad ids."""
        assert client.delete(f"/api/media/{media_id}").status_code in (400, 404)

    def test_another_users_chat_media_is_not_reachable(self, client, db):
        """Chat files live under a global folder keyed only by the (random).

        conversation id. Knowing another user's id must not let you view,
        delete, or copy their files — only the owning user, or anyone for a
        truly orphaned folder with no conversation row (see test_delete).
        """
        token = metadata.set_tenant("other-user")  # a conversation someone else owns
        try:
            other = db.create_conversation(title="Not yours")
        finally:
            metadata.reset_tenant(token)
        d = config.ROOT_DIR / "chat" / other.id
        d.mkdir(parents=True)
        secret = d / "img_secret.png"
        secret.write_bytes(_png("blue"))
        mid = f"chat:{other.id}:img_secret.png"

        assert client.get(f"/api/media/thumb/{mid}").status_code == 404  # can't view
        assert client.delete(f"/api/media/{mid}").status_code == 404  # can't delete
        assert secret.is_file()  # left untouched
        mine = db.create_conversation(title="Mine")
        copy = client.post("/api/media/import", json={"media_id": mid, "target": "chat", "conversation_id": mine.id})
        assert copy.status_code == 404  # can't copy it out either

    def test_paginates_with_total(self, client):
        """Test that paginates with total."""
        for n in range(5):
            client.post("/api/media/upload", files={"file": (f"a{n}.png", _png((n, 0, 0)), "image/png")})
        full = client.get("/api/media").json()
        assert full["total"] == 5
        assert len(full["items"]) == 5
        page = client.get("/api/media?offset=0&limit=2").json()
        assert page["total"] == 5
        assert [i["id"] for i in page["items"]] == [i["id"] for i in full["items"][:2]]
        rest = client.get("/api/media?offset=2&limit=2").json()
        assert [i["id"] for i in rest["items"]] == [i["id"] for i in full["items"][2:4]]

    def test_filters_server_side(self, client, conv):
        """Test that filters server side."""
        images = client.get("/api/media?kind=image").json()
        assert images["items"]
        assert all(i["kind"] == "image" for i in images["items"])
        assert images["total"] == len(images["items"])
        chats = client.get("/api/media?origin=chat").json()
        assert chats["items"]
        assert all(i["origin"] == "chat" for i in chats["items"])
        found = client.get("/api/media?q=fox").json()  # matches prompts / names / where-from
        assert found["items"]
        assert found["total"] == len(found["items"])


class TestOrphans:
    """Tests for orphans."""

    @pytest.fixture
    def orphans(self, db, conv):
        """Conv plus an attachment nothing sent, a reference a reply was made.

        from, and the folder of a deleted chat — all old enough.
        """
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
        """Test that lists unrecorded chat files."""
        items = _items(client)
        orphaned = {k for k, i in items.items() if i["origin"] == "orphan"}
        # Multi-tenant: only orphans in the user's own conversation folders. A
        # folder with no owning conversation ("gone") can't be attributed to a
        # user, so it is shown to no one.
        assert orphaned == {f"chat:{conv.id}:up_lost.png"}
        assert items[f"chat:{conv.id}:up_lost.png"]["conversation_title"] == "Fox chat"
        assert "chat:gone:img_old.png" not in items
        assert items[f"chat:{conv.id}:img_1.png"]["origin"] == "chat"

    def test_delete(self, client, orphans):
        """Test that delete."""
        assert client.delete("/api/media/chat:gone:img_old.png").status_code == 200
        assert not (orphans / "gone" / "img_old.png").exists()


class TestImport:
    """Tests for import."""

    def test_into_a_chat(self, client, conv):
        """Test that into a chat."""
        lib = client.post("/api/media/upload", files={"file": ("a.png", _png(), "image/png")}).json()
        r = client.post(
            "/api/media/import",
            json={"media_id": lib["id"], "target": "chat", "conversation_id": conv.id},
        ).json()
        assert r["file"].startswith("up_")
        assert (config.ROOT_DIR / "chat" / conv.id / r["file"]).is_file()

    def test_into_a_character(self, client, conv):
        """Test that into a character."""
        char = client.post("/api/characters", json={"name": "Fox"}).json()
        r = client.post(
            "/api/media/import",
            json={"media_id": f"chat:{conv.id}:img_1.png", "target": "character", "character_id": char["id"]},
        ).json()
        assert len(r["images"]) == 1

    def test_videos_attach_to_chat_but_not_characters(self, client, conv):
        """Test that videos attach to chat but not characters."""
        (config.ROOT_DIR / "chat" / conv.id / "vid.mp4").write_bytes(b"fake mp4")
        mid = f"chat:{conv.id}:vid.mp4"
        # A video can be attached to a chat (as a reference-to-video ref)…
        chat = client.post("/api/media/import", json={"media_id": mid, "target": "chat", "conversation_id": conv.id})
        assert chat.status_code == 200
        # …but not added to a character (images only).
        char = client.post("/api/media/import", json={"media_id": mid, "target": "character", "character_id": 1})
        assert char.status_code == 400


class TestDelete:
    """Tests for delete."""

    def test_chat_item_leaves_its_message(self, client, db, conv):
        """Test that chat item leaves its message."""
        assert client.delete(f"/api/media/chat:{conv.id}:img_1.png").status_code == 200
        reply = db.get_chat_messages(conv.id)[-1]
        assert [i["id"] for i in reply.media] == ["p"]
        assert not (config.ROOT_DIR / "chat" / conv.id / "img_1.png").exists()

    def test_copies_survive(self, client, conv):
        """Test that copies survive."""
        char = client.post("/api/characters", json={"name": "Fox"}).json()
        client.post(
            "/api/media/import",
            json={"media_id": f"chat:{conv.id}:img_1.png", "target": "character", "character_id": char["id"]},
        )
        client.delete(f"/api/media/chat:{conv.id}:img_1.png")
        c = client.get(f"/api/characters/{char['id']}").json()
        assert client.get(f"/api/characters/{c['id']}/images/{c['images'][0]}").status_code == 200


class TestBlocked:
    """Tests for blocked."""

    @pytest.fixture
    def blocked(self, db, conv):
        """Conv plus: a moderated failure and a black image in a reply, an.

        ordinary failure (kept), and a moderated failure detached to the library.
        """
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

    @pytest.fixture(autouse=True)
    def _fresh_blank_checks(self, monkeypatch):

        monkeypatch.setattr(media_mod, "_blank_cache", None)

    def test_counts(self, client, blocked):
        """Test that counts."""
        assert client.get("/api/media/blocked").json() == {"moderated": 2, "black": 1}

    def test_black_images_are_checked_once_even_across_restarts(self, client, blocked, monkeypatch):
        """Test that black images are checked once even across restarts."""
        assert client.get("/api/media/blocked").json()["black"] == 1
        monkeypatch.setattr(media_mod, "_blank_cache", None)  # as after a restart

        def no_decoding(data):
            raise AssertionError("decoded again")  # noqa: TRY003

        monkeypatch.setattr(media_mod, "is_blank_image", no_decoding)
        assert client.get("/api/media/blocked").json()["black"] == 1

    def test_imported_images_are_not_checked(self, client, db, conv, blocked):
        """Test that imported images are not checked."""
        (blocked / "img_imported.png").write_bytes(_png("black"))
        db.add_chat_message(
            conv.id,
            "assistant",
            "",
            media=[
                {
                    "id": "i",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "img_imported.png",
                    "import_file": "file_x",
                }
            ],
        )
        assert client.get("/api/media/blocked").json()["black"] == 1  # only the app's own

    def test_clear_removes_them_and_keeps_the_rest(self, client, db, conv, blocked):
        """Test that clear removes them and keeps the rest."""
        assert client.post("/api/media/blocked/clear").json() == {"cleared": 3}
        media = {i["id"] for m in db.get_chat_messages(conv.id) for i in m.media}
        assert {"m", "b", "lm"}.isdisjoint(media)
        assert {"t", "g", "u", "p"} <= media
        assert not (blocked / "img_black.png").exists()
        assert (blocked / "img_1.png").exists()
        assert db.list_chat_library() == []
        assert client.get("/api/media/blocked").json() == {"moderated": 0, "black": 0}


class TestThumbnails:
    """Tests for thumbnails."""

    def _big_png(self, size=(1600, 900)) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", size, "purple").save(buf, "PNG")
        return buf.getvalue()

    def test_image_thumb_is_small_and_cached(self, client, monkeypatch):
        """Test that image thumb is small and cached."""
        item = client.post("/api/media/upload", files={"file": ("a.png", self._big_png(), "image/png")}).json()
        r = client.get(item["thumb_url"])
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        thumb = Image.open(io.BytesIO(r.content))
        assert min(thumb.size) == 320
        assert thumb.size[0] > thumb.size[1]
        # Second request comes from the cache — no re-encoding

        monkeypatch.setattr(media_mod.Image, "open", lambda *a, **k: pytest.fail("re-encoded"))
        assert client.get(item["thumb_url"]).content == r.content

    def test_video_thumb_uses_the_first_frame(self, client, conv, monkeypatch):
        """Test that video thumb uses the first frame."""
        (config.ROOT_DIR / "chat" / conv.id / "vid.mp4").write_bytes(b"fake mp4")
        buf = io.BytesIO()
        Image.new("RGB", (640, 360), "orange").save(buf, "JPEG")
        monkeypatch.setattr(media_mod, "first_frame_jpeg", lambda p: buf.getvalue())
        r = client.get(f"/api/media/thumb/chat:{conv.id}:vid.mp4")
        assert r.status_code == 200
        assert Image.open(io.BytesIO(r.content)).size == (569, 320)

    def test_unreadable_file_has_no_thumb(self, client, conv, monkeypatch):
        """Test that unreadable file has no thumb."""
        (config.ROOT_DIR / "chat" / conv.id / "vid.mp4").write_bytes(b"fake mp4")
        monkeypatch.setattr(media_mod, "first_frame_jpeg", lambda p: None)
        assert client.get(f"/api/media/thumb/chat:{conv.id}:vid.mp4").status_code == 404


class TestFirstFrameJpeg:
    """first_frame_jpeg: the video frame the library's thumbnails are made from."""

    def test_unopenable_file(self, tmp_path):
        """Test that unopenable file."""
        fp = tmp_path / "notavideo.mp4"
        fp.write_bytes(b"definitely not a video")
        assert media_mod.first_frame_jpeg(fp) is None

    def test_read_fails(self, tmp_path):
        """Test that read fails."""
        fp = tmp_path / "readfail.mp4"
        fp.write_bytes(b"\x00" * 100)
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)
        with patch("web.media.cv2.VideoCapture", return_value=cap):
            assert media_mod.first_frame_jpeg(fp) is None
        cap.release.assert_called_once()

    def test_success(self, tmp_path):
        """Test that success."""
        fp = tmp_path / "success.mp4"
        fp.write_bytes(b"\x00" * 100)
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, np.zeros((2, 2, 3), dtype=np.uint8))
        with patch("web.media.cv2.VideoCapture", return_value=cap):
            assert media_mod.first_frame_jpeg(fp) is not None

    def test_exception(self, tmp_path):
        """Test that exception."""
        fp = tmp_path / "exc.mp4"
        fp.write_bytes(b"\x00" * 100)
        with patch("web.media.cv2.VideoCapture", side_effect=Exception("cv2 error")):
            assert media_mod.first_frame_jpeg(fp) is None

    def test_delete_drops_the_cached_thumb(self, client):
        """Test that delete drops the cached thumb."""
        item = client.post("/api/media/upload", files={"file": ("a.png", _png(), "image/png")}).json()
        client.get(item["thumb_url"])
        assert list(media_mod.thumb_dir().iterdir())
        client.delete(f"/api/media/{item['id']}")
        assert not list(media_mod.thumb_dir().iterdir())

    def test_at_most_two_made_at_once(self, client, monkeypatch):
        """Test that at most two made at once."""
        ids = [
            client.post("/api/media/upload", files={"file": (f"{n}.png", _png((n, 0, 0)), "image/png")}).json()[
                "thumb_url"
            ]
            for n in range(8)
        ]
        real, lock, state = media_mod.make_thumb, threading.Lock(), {"now": 0, "peak": 0}

        def slow_thumb(path, size=media_mod.THUMB_SIZE):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            try:
                return real(path, size)
            finally:
                with lock:
                    state["now"] -= 1

        monkeypatch.setattr(media_mod, "make_thumb", slow_thumb)
        with ThreadPoolExecutor(8) as pool:
            codes = list(pool.map(lambda u: client.get(u).status_code, ids))
        assert codes == [200] * 8
        assert state["peak"] <= media_mod.THUMB_WORKERS


class TestUploadDedupe:
    """Tests for upload dedupe."""

    def test_same_image_is_stored_once_and_unsent_one_can_be_discarded(self, client, conv, db):
        """Test that same image is stored once and unsent one can be discarded."""
        c = db.create_conversation(title="Dup")
        url = f"/api/chat/conversations/{c.id}/attachments"
        a = client.post(url, files={"file": ("a.png", _png(), "image/png")}).json()["file"]
        b = client.post(url, files={"file": ("b.png", _png(), "image/png")}).json()["file"]
        assert a == b  # identical bytes → one file
        assert client.delete(f"{url}/{a}").json() == {"deleted": True}
        assert client.delete(f"{url}/{a}").json() == {"deleted": False}  # already gone


class TestVideoDurations:
    """Reading a length opens the file with OpenCV, which is slow on a NAS, so.

    building the list never does it: a request fills in the page it returns,
    and what's been read is kept in the database (MediaDuration).
    """

    @pytest.fixture
    def clips(self, db, conv):
        """Provide the clips fixture."""
        d = config.ROOT_DIR / "chat" / conv.id
        for n in range(3):
            (d / f"clip_{n}.mp4").write_bytes(b"not really a video")
        db.add_chat_message(
            conv.id,
            "assistant",
            "clips",
            media=[
                {
                    "id": f"v{n}",
                    "kind": "video",
                    "source": "generated",
                    "status": "done",
                    "file": f"clip_{n}.mp4",
                    "prompt": "x",
                }
                for n in range(3)
            ],
        )
        media_mod._invalidate_list()
        media_mod._durations = {}
        return media_mod

    def test_list_build_never_opens_a_video(self, client, clips, monkeypatch):
        """Test that list build never opens a video."""
        monkeypatch.setattr(clips, "_video_seconds", lambda *a: pytest.fail("the list build read a video header"))
        # The clips are in the library and get built into the list, but this
        # page holds no video, so nothing opens one
        r = client.get("/api/media?kind=image")
        assert r.status_code == 200
        assert r.json()["total"]
        assert not any(i["kind"] == "video" for i in r.json()["items"])

    def test_a_page_fills_in_its_own_lengths_and_remembers_them(self, client, clips, monkeypatch):
        """Test that a page fills in its own lengths and remembers them."""
        reads = []
        monkeypatch.setattr(clips, "_video_seconds", lambda path, mtime: reads.append(path) or 12.5)
        items = {i["id"]: i for i in client.get("/api/media").json()["items"]}
        clip = next(i for i in items.values() if i["name"] == "clip_0.mp4")
        assert clip["duration"] == 12.5
        assert len(reads) == 3
        # Read once: the next request (and the next process) uses what's stored
        reads.clear()
        clips._invalidate_list()
        clips._durations = None  # as a fresh process would start: nothing in memory
        again = {i["name"]: i for i in client.get("/api/media").json()["items"]}
        assert again["clip_0.mp4"]["duration"] == 12.5
        assert reads == []

    def test_a_re_encoded_file_is_read_again(self, client, clips, db, monkeypatch):
        """Test that a re encoded file is read again."""
        monkeypatch.setattr(clips, "_video_seconds", lambda path, mtime: 4.0)
        client.get("/api/media")
        (config.ROOT_DIR / "chat" / next(iter(db.list_conversations())).id / "clip_0.mp4").write_bytes(b"longer now")
        monkeypatch.setattr(clips, "_video_seconds", lambda path, mtime: 9.0)
        clips._invalidate_list()
        items = {i["name"]: i for i in client.get("/api/media").json()["items"]}
        assert items["clip_0.mp4"]["duration"] == 9.0
        assert items["clip_1.mp4"]["duration"] == 4.0

    def test_fill_is_capped_so_one_request_cannot_stall(self, client, clips, monkeypatch):
        """Test that fill is capped so one request cannot stall."""
        monkeypatch.setattr(clips, "_DURATION_FILL_BUDGET", 2)
        reads = []
        monkeypatch.setattr(clips, "_video_seconds", lambda path, mtime: reads.append(path) or 3.0)
        client.get("/api/media")
        assert len(reads) == 2


class TestMediaCache:
    """The cache lives under <data>/cache with the thumbnails, so deleting that.

    folder wipes it — and it can't grow past one row per file that exists.
    """

    @pytest.fixture
    def cached(self, client, clips, db, conv):
        """Provide the cached fixture."""
        client.get("/api/media")  # fills in the clips' lengths
        return media_cache

    @pytest.fixture
    def clips(self, db, conv):
        """Provide the clips fixture."""
        return TestVideoDurations.clips.__wrapped__(TestVideoDurations(), db, conv)

    def test_it_sits_in_the_cache_folder_and_a_wipe_is_harmless(self, client, cached, monkeypatch):
        """Test that it sits in the cache folder and a wipe is harmless."""
        assert cached.db_path().parent == config.ROOT_DIR / "cache"
        assert cached.durations()
        shutil.rmtree(config.ROOT_DIR / "cache")  # what a user wiping the cache does
        assert cached.durations() == {}
        monkeypatch.setattr(cached, "_swept", False)
        assert client.get("/api/media").status_code == 200  # reads them again, no complaint

    def test_a_re_encoded_file_replaces_its_row(self, client, cached, clips, db, monkeypatch):
        """Test that a re encoded file replaces its row."""
        before = len(cached.durations())
        path = config.ROOT_DIR / "chat" / next(iter(db.list_conversations())).id / "clip_0.mp4"
        path.write_bytes(b"re-encoded")
        monkeypatch.setattr(clips, "_video_seconds", lambda p, m: 7.0)
        clips._invalidate_list()
        client.get("/api/media")
        assert len(cached.durations()) == before  # replaced, not added
        assert cached.durations()[str(path)][1] == 7.0

    def test_deleting_media_drops_its_row(self, client, cached, db):
        """Test that deleting media drops its row."""
        conv_id = next(iter(db.list_conversations())).id
        path = str(config.ROOT_DIR / "chat" / conv_id / "clip_0.mp4")
        assert path in cached.durations()
        assert client.delete(f"/api/media/chat:{conv_id}:clip_0.mp4").status_code == 200
        assert path not in cached.durations()

    def test_a_sweep_drops_rows_whose_file_has_gone(self, cached, db):
        """Test that a sweep drops rows whose file has gone."""
        (config.ROOT_DIR / "chat" / next(iter(db.list_conversations())).id / "clip_1.mp4").unlink()
        assert cached.sweep() == 1
        assert all("clip_1.mp4" not in p for p in cached.durations())

    def test_an_unusable_cache_file_just_means_no_cache(self, cached, monkeypatch, tmp_path):
        """Test that an unusable cache file just means no cache."""
        blocker = tmp_path / "blocker"  # a file where the cache folder should be
        blocker.write_text("x")
        monkeypatch.setattr(cached, "db_path", lambda: blocker / "media-cache.sqlite")
        assert cached.durations() == {}  # degraded, not raised
        cached.remember([("/a.mp4", 1, 2.0)])
        cached.forget("/a.mp4")
        assert cached.sweep() == 0
