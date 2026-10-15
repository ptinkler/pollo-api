"""Tests for web.chatgpt_import — importing chats from a ChatGPT data export."""

import json
import time
import zipfile
from datetime import UTC, datetime

import pytest

from tests.test_chat import SETTINGS, _png_bytes, _text_chunks, chat, client, db  # noqa: F401

T0 = 1_790_000_000.0  # the first prompt's time


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


def _msg(mid, role, parts, t, content_type="text", **meta):
    return {
        "id": mid,
        "author": {"role": role},
        "content": {"content_type": content_type, "parts": parts},
        "create_time": t,
        "recipient": "all",
        "metadata": meta,
    }


def _pointer(file_id):
    return {"content_type": "image_asset_pointer", "asset_pointer": f"sediment://{file_id}"}


def _conversation(cid, title, messages, update_time):
    """A chat whose messages follow one another (the exported branch)."""
    mapping = {"root": {"id": "root", "message": None, "parent": None, "children": []}}
    parent = "root"
    for m in messages:
        mapping[m["id"]] = {"id": m["id"], "message": m, "parent": parent, "children": []}
        mapping[parent]["children"].append(m["id"])
        parent = m["id"]
    return {
        "id": cid,
        "conversation_id": cid,
        "title": title,
        "create_time": T0 - 5,
        "update_time": update_time,
        "current_node": parent,
        "mapping": mapping,
    }


def _story_messages():
    return [
        _msg("u1", "user", [_pointer("file_up1"), "draw her in the rain"], T0, "multimodal_text"),
        _msg("r1", "assistant", [""], T0 + 1, content_type="reasoning_recap"),
        _msg("a1", "assistant", [""], T0 + 20, model_slug="gpt-4o"),
        _msg("u2", "user", ["now a story about it"], T0 + 100),
        _msg(
            "a2",
            "assistant",
            [':::writing{variant="document" id="1" title="Rainy Day"}\nIt rained.\n:::'],
            T0 + 105,
            model_slug="gpt-4o",
        ),
        _msg("a2b", "assistant", ["Want another?"], T0 + 106, model_slug="gpt-4o"),
    ]


def _library(*files):
    return [
        {
            "file_id": fid,
            "file_name": name,
            "mime_type": "image/png",
            "origination_thread_id": thread,
            "created_at": _iso(t),
        }
        for fid, name, thread, t in files
    ]


STORY_LIBRARY = _library(
    ("file_up1", "image.png", "c1", T0 - 2),  # the upload
    ("file_gen1", "Rainy Street.png", "c1", T0 + 15),  # made for the first prompt
    ("file_gone", "Never Finished.png", "c1", T0 + 16),  # not in the zip
)


def _export(path, conversations, library, files=("file_up1", "file_gen1")):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
        zf.writestr("library_files.json", json.dumps(library))
        for fid in files:
            zf.writestr(f"{fid}.dat", _png_bytes())
    return path


@pytest.fixture()
def imp(chat, db, monkeypatch):
    import web.chatgpt_import as imp_mod

    monkeypatch.setattr(imp_mod, "get_db", lambda: db)
    imp_mod._job.clear()
    imp_mod._job["state"] = "idle"
    return imp_mod


@pytest.fixture()
def story_zip(tmp_path):
    return _export(tmp_path / "export1.zip", [_conversation("c1", "Rain", _story_messages(), T0 + 200)], STORY_LIBRARY)


def _shown(client, conv_id):
    return client.get(f"/api/chat/conversations/{conv_id}").json()["messages"]


def _space(client):
    return next((sp for sp in client.get("/api/chat/spaces").json()["spaces"] if sp["name"] == "ChatGPT"), None)


def _imported(client):
    """The chats in the ChatGPT space."""
    space = _space(client)
    convs = client.get("/api/chat/conversations").json()["conversations"]
    return [c for c in convs if space and c["space_id"] == space["id"]]


class TestFirstImport:
    def test_turns_become_a_prompt_and_one_reply(self, imp, client, story_zip):
        stats = imp.run_import(story_zip)
        assert stats["new"] == 1 and stats["images"] == 2 and stats["missing_images"] == 1
        [conv] = _imported(client)
        assert conv["title"] == "Rain" and conv["import_source"] == "chatgpt"
        msgs = _shown(client, conv["id"])
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
        assert msgs[0]["content"] == "draw her in the rain"
        # Document markup becomes its title in bold; a turn's replies are joined
        assert msgs[3]["content"] == "**Rainy Day**\n\nIt rained.\n\nWant another?"
        assert msgs[3]["model"] == "chatgpt/gpt-4o"

    def test_uploads_on_their_prompt_and_generated_images_on_its_reply(self, imp, client, story_zip, tmp_path):
        imp.run_import(story_zip)
        conv = _imported(client)[0]
        msgs = _shown(client, conv["id"])
        [up] = msgs[0]["media"]
        assert up["source"] == "upload" and up["status"] == "done" and up["file"].endswith(".png")
        [gen] = msgs[1]["media"]  # the unfinished one is left out
        assert gen["source"] == "generated" and gen["prompt"] == "Rainy Street" and gen["model"] == "chatgpt"
        assert (tmp_path / "chat" / conv["id"] / gen["file"]).is_file()
        assert client.get(f"/api/chat/media/{conv['id']}/{gen['file']}").status_code == 200
        assert msgs[3]["media"] == []

    def test_a_missing_upload_is_noted(self, imp, client, tmp_path):
        path = _export(
            tmp_path / "e.zip", [_conversation("c1", "Rain", _story_messages(), T0 + 200)], STORY_LIBRARY, files=()
        )
        imp.run_import(path)
        [up] = _shown(client, _imported(client)[0]["id"])[0]["media"]
        assert up["status"] == "error" and up["error"] == imp.MISSING

    def test_keeps_chatgpt_dates(self, imp, client, story_zip):
        imp.run_import(story_zip)
        conv = _imported(client)[0]
        assert conv["updated_at"].startswith(datetime.fromtimestamp(T0 + 200).isoformat()[:19])
        assert _shown(client, conv["id"])[2]["created_at"].startswith(datetime.fromtimestamp(T0 + 100).isoformat()[:19])

    def test_older_exports_with_image_tool_messages(self, imp, client, tmp_path):
        messages = [
            _msg("u1", "user", ["draw a cat"], T0),
            _msg("t1", "tool", [_pointer("file_gen1")], T0 + 10, "multimodal_text"),
            _msg("a1", "assistant", ["Here it is"], T0 + 11),
        ]
        imp.run_import(_export(tmp_path / "e.zip", [_conversation("c1", "Cat", messages, T0 + 20)], []))
        msgs = _shown(client, _imported(client)[0]["id"])
        assert msgs[1]["content"] == "Here it is" and msgs[1]["media"][0]["source"] == "generated"

    def test_not_an_export(self, imp, tmp_path):
        path = tmp_path / "other.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("readme.txt", "hi")
        with pytest.raises(ValueError):
            imp.run_import(path)


class TestImportingAgain:
    def test_unchanged_chats_are_skipped(self, imp, client, story_zip):
        imp.run_import(story_zip)
        stats = imp.run_import(story_zip)
        assert stats["unchanged"] == 1 and stats["new"] == 0 and stats["images"] == 0
        assert len(_imported(client)) == 1

    def test_new_turns_are_added(self, imp, client, story_zip, tmp_path):
        imp.run_import(story_zip)
        messages = [
            *_story_messages(),
            _msg("u3", "user", ["one more picture"], T0 + 300),
            _msg("a3", "assistant", [""], T0 + 320),
        ]
        library = [*STORY_LIBRARY, *_library(("file_gen2", "Sunset.png", "c1", T0 + 310))]
        later = _export(
            tmp_path / "export2.zip",
            [
                _conversation("c1", "Rain", messages, T0 + 400),
                _conversation("c2", "Other", [_msg("x1", "user", ["hi"], T0)], T0 + 10),
            ],
            library,
            files=("file_up1", "file_gen1", "file_gen2"),
        )
        stats = imp.run_import(later)
        assert stats["updated"] == 1 and stats["new"] == 1 and stats["images"] == 1
        conv = next(c for c in _imported(client) if c["title"] == "Rain")
        msgs = _shown(client, conv["id"])
        assert [m["content"] for m in msgs[4:]] == ["one more picture", ""]
        assert msgs[5]["media"][0]["prompt"] == "Sunset"
        assert len(msgs[1]["media"]) == 1  # nothing added twice

    def test_a_chat_carried_on_here_gets_chatgpt_turns_as_a_branch(
        self, imp, client, chat, story_zip, tmp_path, monkeypatch
    ):
        imp.run_import(story_zip)
        conv = _imported(client)[0]
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: _text_chunks("Sure."))
        client.post(
            f"/api/chat/conversations/{conv['id']}/messages", json={"content": "continue", "mode": "text", **SETTINGS}
        )
        mine = _shown(client, conv["id"])
        assert mine[-1]["content"] == "Sure."

        messages = [*_story_messages(), _msg("u3", "user", ["from chatgpt"], T0 + 300)]
        imp.run_import(_export(tmp_path / "e2.zip", [_conversation("c1", "Rain", messages, T0 + 400)], STORY_LIBRARY))
        shown = _shown(client, conv["id"])
        assert [m["id"] for m in shown] == [m["id"] for m in mine]  # still showing what was carried on here
        assert shown[-2]["siblings"] == [mine[-2]["id"], shown[-2]["siblings"][1]]
        client.post(f"/api/chat/conversations/{conv['id']}/branch", json={"message_id": shown[-2]["siblings"][1]})
        assert _shown(client, conv["id"])[-1]["content"] == "from chatgpt"

    def test_deleted_chats_stay_deleted(self, imp, client, story_zip):
        imp.run_import(story_zip)
        client.delete(f"/api/chat/conversations/{_imported(client)[0]['id']}")
        stats = imp.run_import(story_zip)
        assert stats["deleted"] == 1 and _imported(client) == []


class TestSpace:
    def test_imported_chats_go_in_a_chatgpt_space(self, imp, client, story_zip):
        stats = imp.run_import(story_zip)
        space = _space(client)
        assert space and stats["space_id"] == space["id"]
        assert [c["title"] for c in _imported(client)] == ["Rain"]
        imp.run_import(story_zip)
        assert [sp["name"] for sp in client.get("/api/chat/spaces").json()["spaces"]] == ["ChatGPT"]  # just the one

    def test_no_space_until_there_is_something_to_import(self, imp, client, story_zip):
        imp.run_import(story_zip)
        client.delete(f"/api/chat/spaces/{_space(client)['id']}")
        imp.run_import(story_zip)  # nothing new
        assert _space(client) is None

    def test_new_chats_get_the_spaces_defaults(self, imp, client, story_zip):
        snippet = client.post("/api/chat/instructions", json={"name": "Style", "content": "Be brief."}).json()
        client.put("/api/chat/settings", json={"default_instruction_ids": [snippet["id"]]})
        imp.run_import(story_zip)
        assert _imported(client)[0]["instruction_ids"] == [snippet["id"]]

    def test_a_chat_moved_out_keeps_getting_imports_where_it_is(self, imp, client, story_zip, tmp_path):
        imp.run_import(story_zip)
        conv = _imported(client)[0]
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"space_id": None})
        messages = [*_story_messages(), _msg("u3", "user", ["more"], T0 + 300)]
        imp.run_import(_export(tmp_path / "e2.zip", [_conversation("c1", "Rain", messages, T0 + 400)], STORY_LIBRARY))
        assert _shown(client, conv["id"])[-1]["content"] == "more"
        assert _imported(client) == []
        moved = client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]
        assert moved["space_id"] is None

    def test_search_finds_imported_chats(self, imp, client, story_zip):
        imp.run_import(story_zip)
        found = client.get("/api/chat/conversations?q=rained").json()["conversations"]
        assert [c["title"] for c in found] == ["Rain"]


class TestRoutes:
    def test_lists_exports_and_runs_an_import(self, imp, client, story_zip, tmp_path):
        (tmp_path / "imports").mkdir()
        story_zip.rename(tmp_path / "imports" / "export1.zip")
        data = client.get("/api/chat/import/chatgpt").json()
        assert [f["name"] for f in data["files"]] == ["export1.zip"] and data["job"]["state"] == "idle"
        assert client.post("/api/chat/import/chatgpt", json={"file": "export1.zip"}).status_code == 200
        for _ in range(100):
            job = client.get("/api/chat/import/chatgpt").json()["job"]
            if job["state"] != "running":
                break
            time.sleep(0.05)
        assert job["state"] == "done" and job["new"] == 1
        assert len(_imported(client)) == 1

    def test_only_exports_in_the_imports_folder(self, imp, client):
        assert client.post("/api/chat/import/chatgpt", json={"file": "nope.zip"}).status_code == 404
        assert client.post("/api/chat/import/chatgpt", json={"file": "../x.zip"}).status_code == 400


class TestUpload:
    @pytest.fixture()
    def small_chunks(self, imp, monkeypatch):
        monkeypatch.setattr(imp, "UPLOAD_CHUNK", 1000)

    def _start(self, client, raw, name="export1.zip"):
        return client.post("/api/chat/import/chatgpt/uploads", json={"name": name, "size": len(raw)}).json()

    def _send(self, client, upload_id, offset, raw):
        return client.post(
            f"/api/chat/import/chatgpt/uploads/{upload_id}",
            data={"offset": str(offset)},
            files={"chunk": ("blob", raw, "application/octet-stream")},
        )

    def _upload(self, client, raw, name="export1.zip"):
        up = self._start(client, raw, name)
        for offset in range(0, len(raw), 1000):
            resp = self._send(client, up["id"], offset, raw[offset : offset + 1000])
        return resp

    def test_chunks_become_an_export_in_the_imports_folder(self, small_chunks, client, story_zip, tmp_path):
        raw = story_zip.read_bytes()
        assert len(raw) > 2000  # several chunks
        resp = self._upload(client, raw)
        assert resp.json() == {"received": len(raw), "file": "export1.zip"}
        assert (tmp_path / "imports" / "export1.zip").read_bytes() == raw
        files = client.get("/api/chat/import/chatgpt").json()["files"]
        assert [f["name"] for f in files] == ["export1.zip"]  # the upload's own files aren't listed
        assert sorted(p.name for p in (tmp_path / "imports").iterdir()) == ["export1.zip"]

    def test_a_resent_chunk_replaces_itself(self, small_chunks, client, story_zip, tmp_path):
        raw = story_zip.read_bytes()
        up = self._start(client, raw)
        assert self._send(client, up["id"], 0, raw[:1000]).json() == {"received": 1000}
        assert self._send(client, up["id"], 0, raw[:1000]).json() == {"received": 1000}
        assert self._send(client, up["id"], 2000, raw[2000:3000]).status_code == 409  # one was skipped
        for offset in range(1000, len(raw), 1000):
            resp = self._send(client, up["id"], offset, raw[offset : offset + 1000])
        assert resp.json()["file"] == "export1.zip"
        assert (tmp_path / "imports" / "export1.zip").read_bytes() == raw

    def test_the_same_name_twice_is_kept_apart(self, small_chunks, client, story_zip):
        raw = story_zip.read_bytes()
        self._upload(client, raw)
        assert self._upload(client, raw).json()["file"] == "export1 (2).zip"

    def test_only_chatgpt_exports(self, small_chunks, client, tmp_path):
        assert client.post("/api/chat/import/chatgpt/uploads", json={"name": "x.txt", "size": 5}).status_code == 400
        assert self._upload(client, b"not a zip").status_code == 400
        other = tmp_path / "other.zip"
        with zipfile.ZipFile(other, "w") as zf:
            zf.writestr("readme.txt", "hi")
        assert "conversations.json" in self._upload(client, other.read_bytes()).json()["detail"]
        assert list((tmp_path / "imports").iterdir()) == []

    def test_chunks_past_the_end_or_too_big(self, small_chunks, client):
        up = self._start(client, b"x" * 1500)
        assert self._send(client, up["id"], 1000, b"x" * 600).status_code == 400
        assert self._send(client, up["id"], 0, b"x" * 1001).status_code == 400

    def test_cancel_and_unknown_uploads(self, small_chunks, client, tmp_path):
        up = self._start(client, b"x" * 1500)
        client.delete(f"/api/chat/import/chatgpt/uploads/{up['id']}")
        assert list((tmp_path / "imports").iterdir()) == []
        assert self._send(client, up["id"], 0, b"x").status_code == 404
        assert self._send(client, "not-an-id", 0, b"x").status_code == 404
