"""Tests for web.chat — OpenRouter chat mode. OpenRouter is always mocked."""
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from img2vid.common.metadata import MetadataDB


def _png_bytes(size=(8, 8), color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _text_chunks(*parts, cost=0.001):
    for p in parts:
        yield {"choices": [{"delta": {"content": p}}]}
    yield {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"cost": cost}}


def _tool_chunks(name, args, call_id="call_1"):
    raw = json.dumps(args)
    yield {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": call_id, "function": {"name": name, "arguments": raw[:5]}}]}}]}
    yield {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"arguments": raw[5:]}}]}}]}
    yield {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}


def _events(resp) -> list[dict]:
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


@pytest.fixture()
def db(tmp_path):
    return MetadataDB(db_path=tmp_path / "data" / "metadata.db")


@pytest.fixture()
def chat(monkeypatch, db):
    import web.chat as chat_mod
    monkeypatch.setattr(chat_mod, "get_db", lambda: db)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(chat_mod, "VIDEO_POLL_INTERVAL", 0)
    monkeypatch.setattr(chat_mod, "start_video_poller", lambda *a: None)
    chat_mod._models_cache.update(at=0.0, data=None)
    return chat_mod


@pytest.fixture()
def client(chat, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)
    import web.auth as auth_mod
    auth_mod.get_api_keys.cache_clear()
    import web.api as api_mod
    return TestClient(api_mod.app, raise_server_exceptions=False)


@pytest.fixture()
def conv(client):
    return client.post("/api/chat/conversations", json={}).json()


SETTINGS = {"text_model": "t/model", "image_model": "i/model", "video_model": "v/model"}


class TestConversations:
    def test_crud(self, client):
        c = client.post("/api/chat/conversations", json={"text_model": "a/b"}).json()
        assert c["title"] == "New chat" and c["text_model"] == "a/b"
        assert [x["id"] for x in client.get("/api/chat/conversations").json()["conversations"]] == [c["id"]]
        r = client.patch(f"/api/chat/conversations/{c['id']}", json={"title": "  Renamed "})
        assert r.json()["title"] == "Renamed"
        assert client.delete(f"/api/chat/conversations/{c['id']}").status_code == 200
        assert client.get(f"/api/chat/conversations/{c['id']}").status_code == 404

    def test_status_reports_key(self, client, monkeypatch):
        assert client.get("/api/chat/status").json() == {"configured": True}
        monkeypatch.delenv("OPENROUTER_API_KEY")
        assert client.get("/api/chat/status").json() == {"configured": False}

    def test_send_without_key_is_503(self, client, conv, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY")
        r = client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS})
        assert r.status_code == 503


class TestMedia:
    def test_upload_and_serve(self, client, conv):
        r = client.post(f"/api/chat/conversations/{conv['id']}/attachments",
                        files={"file": ("a.png", _png_bytes(), "image/png")})
        name = r.json()["file"]
        assert name.startswith("up_") and name.endswith(".png")
        assert client.get(f"/api/chat/media/{conv['id']}/{name}").content == _png_bytes()

    def test_rejects_non_image(self, client, conv):
        r = client.post(f"/api/chat/conversations/{conv['id']}/attachments",
                        files={"file": ("a.png", b"not an image", "image/png")})
        assert r.status_code == 400

    @pytest.mark.parametrize("conv_id,name", [("abc", "../x.png"), ("..", "metadata.db"), ("abc", ".hidden")])
    def test_path_traversal_blocked(self, chat, conv_id, name):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            chat.api_chat_media(conv_id, name)
        assert e.value.status_code == 400

    def test_unknown_attachment_rejected(self, client, conv):
        r = client.post(f"/api/chat/conversations/{conv['id']}/messages",
                        json={"content": "x", "attachments": ["nope.png"], **SETTINGS})
        assert r.status_code == 400


class TestTurns:
    def test_text_mode_streams_and_persists(self, client, conv, chat, monkeypatch):
        seen = {}

        def fake_stream(model, messages, tools=None, session_id=None):
            seen.update(model=model, messages=messages, tools=tools)
            return _text_chunks("Hel", "lo!")
        monkeypatch.setattr(chat.openrouter, "stream_chat", fake_stream)

        r = client.post(f"/api/chat/conversations/{conv['id']}/messages",
                        json={"content": "Say hello", "mode": "text", **SETTINGS})
        ev = _events(r)
        assert ev[0]["type"] == "start" and ev[0]["user_message"]["content"] == "Say hello"
        assert "".join(e["text"] for e in ev if e["type"] == "delta") == "Hello!"
        assert {"type": "title", "title": "Say hello"} in ev
        done = ev[-1]["message"]
        assert done["content"] == "Hello!" and done["status"] == "done" and done["cost"] == 0.001
        assert seen["tools"] is None
        assert seen["messages"][0]["role"] == "system"
        assert seen["messages"][-1] == {"role": "user", "content": [{"type": "text", "text": "Say hello"}]}
        # model picks are remembered on the conversation
        assert client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["text_model"] == "t/model"

    def test_auto_mode_tool_call_generates_image(self, client, conv, chat, monkeypatch):
        rounds = iter([_tool_chunks("generate_image", {"prompt": "a cat", "aspect_ratio": "16:9"}),
                       _text_chunks("Here you go.")])
        calls = []

        def fake_stream(model, messages, tools=None, session_id=None):
            calls.append((messages, tools))
            return next(rounds)
        monkeypatch.setattr(chat.openrouter, "stream_chat", fake_stream)
        img_args = {}

        def fake_image(model, prompt, **kw):
            img_args.update(model=model, prompt=prompt, **kw)
            return [(_png_bytes(), "image/png")], 0.04
        monkeypatch.setattr(chat.openrouter, "generate_image", fake_image)

        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "draw a cat", "mode": "auto", **SETTINGS}))
        assert [t["function"]["name"] for t in calls[0][1]] == ["generate_image", "generate_video"]
        assert img_args["model"] == "i/model" and img_args["prompt"] == "a cat"
        assert img_args["aspect_ratio"] == "16:9"
        # second round sees the tool result
        assert calls[1][0][-1]["role"] == "tool" and json.loads(calls[1][0][-1]["content"])["ok"]
        media_events = [e["item"] for e in ev if e["type"] == "media"]
        assert [m["status"] for m in media_events] == ["pending", "done"]
        done = ev[-1]["message"]
        assert done["content"] == "Here you go."
        assert done["media"][0]["file"].startswith("img_")
        assert done["cost"] == pytest.approx(0.041)
        path = chat._chat_root() / conv["id"] / done["media"][0]["file"]
        assert path.read_bytes() == _png_bytes()

    def test_source_latest_uses_previous_image(self, client, conv, chat, monkeypatch):
        up = client.post(f"/api/chat/conversations/{conv['id']}/attachments",
                         files={"file": ("a.png", _png_bytes(), "image/png")}).json()["file"]
        rounds = iter([_tool_chunks("generate_image", {"prompt": "make it blue", "source_image": "latest"}),
                       _text_chunks("Done.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(rounds))
        got = {}
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: (got.update(kw), ([(_png_bytes(), "image/png")], None))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "make it blue", "attachments": [up], **SETTINGS}))
        assert got["input_images"][0].startswith("data:image/png;base64,")

    def test_image_mode_skips_text_model(self, client, conv, chat, monkeypatch):
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: pytest.fail("no LLM in image mode"))
        got = {}
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw),
                                                         ([(_png_bytes(), "image/png")] * 2, 0.02))[1])
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "a dog", "mode": "image",
                                       "options": {"aspect_ratio": "1:1", "resolution": "2K"}, **SETTINGS}))
        assert got["prompt"] == "a dog" and got["aspect_ratio"] == "1:1" and got["resolution"] == "2K"
        assert len(ev[-1]["message"]["media"]) == 2
        assert ev[-1]["message"]["model"] == "i/model"

    def test_video_mode_submits_and_polls(self, client, conv, chat, monkeypatch, db):
        started = []
        monkeypatch.setattr(chat, "start_video_poller", lambda *a: started.append(a))
        monkeypatch.setattr(chat.openrouter, "submit_video",
                            lambda model, prompt, **kw: {"id": "gen-vid-1", "status": "pending"})
        chat._models_cache.update(at=9e18, data={"text": [], "image": [], "video": [
            {"id": "v/model", "durations": [5, 10], "aspect_ratios": ["16:9"], "resolutions": ["720p"]}]})
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "waves", "mode": "video",
                                       "options": {"duration": 7, "aspect_ratio": "1:1"}, **SETTINGS}))
        item = ev[-1]["message"]["media"][0]
        assert item["status"] == "pending" and item["job_id"] == "gen-vid-1"
        assert item["params"]["duration"] == 5 and item["params"]["aspect_ratio"] is None  # snapped to model
        conv_id, msg_id, media_id, job_id = started[0]

        # Now run the poller for real against mocked status/download
        statuses = iter([{"status": "in_progress"},
                         {"status": "completed", "usage": {"cost": 0.5}}])
        monkeypatch.setattr(chat.openrouter, "get_video", lambda j: next(statuses))
        monkeypatch.setattr(chat.openrouter, "download_video", lambda j, dest, index=0: dest.write_bytes(b"mp4"))
        chat._poll_video(conv_id, msg_id, media_id, job_id)
        msg = client.get(f"/api/chat/messages/{msg_id}").json()
        assert msg["media"][0]["status"] == "done" and msg["media"][0]["file"].endswith(".mp4")
        assert msg["cost"] == 0.5

    def test_video_failure_marks_item(self, chat, db, conv, monkeypatch):
        msg = db.add_chat_message(conv["id"], "assistant", media=[{"id": "m1", "kind": "video", "status": "pending"}])
        monkeypatch.setattr(chat.openrouter, "get_video", lambda j: {"status": "failed", "error": "nsfw"})
        chat._poll_video(conv["id"], msg.id, "m1", "gen-vid-x")
        assert db.get_chat_message(msg.id).media[0] == {"id": "m1", "kind": "video", "status": "error", "error": "nsfw"}

    def test_openrouter_error_marks_message(self, client, conv, chat, monkeypatch):
        def boom(*a, **k):
            raise chat.openrouter.OpenRouterError("Insufficient credits", 402)
        monkeypatch.setattr(chat.openrouter, "stream_chat", boom)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "hi", **SETTINGS}))
        assert {"type": "error", "message": "Insufficient credits"} in ev
        assert ev[-1]["message"]["status"] == "error"

    def test_tools_withheld_for_models_without_tool_support(self, client, conv, chat, monkeypatch):
        chat._models_cache.update(at=9e18, data={"image": [], "video": [], "text": [
            {"id": "t/model", "supports_tools": False, "input_modalities": ["text"]}]})
        seen = {}
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None: (seen.update(tools=tools, msgs=msgs),
                                                                          _text_chunks("ok"))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "hi", "mode": "auto", **SETTINGS}))
        assert seen["tools"] is None
        assert "unavailable" in seen["msgs"][0]["content"]

    def test_retry_replaces_assistant_message(self, client, conv, chat, monkeypatch):
        replies = iter([_text_chunks("first"), _text_chunks("second")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        first = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                    json={"content": "hi", **SETTINGS}))[-1]["message"]
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/retry",
                                 json={"message_id": first["id"], **SETTINGS}))
        assert ev[0]["user_message"] is None
        msgs = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
        assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "second")]

    def test_history_includes_media_notes(self, client, conv, chat, db, monkeypatch):
        db.add_chat_message(conv["id"], "user", "draw a fox")
        db.add_chat_message(conv["id"], "assistant", "Here!", media=[
            {"id": "a", "kind": "image", "source": "generated", "status": "done", "file": "x.png", "prompt": "a fox"}])
        seen = {}
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None: (seen.update(msgs=msgs), _text_chunks("ok"))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "nice", **SETTINGS}))
        assert seen["msgs"][2] == {"role": "assistant", "content": "Here!\n\n[generated image: a fox]"}


class TestStartupResume:
    def test_resumes_pending_videos_and_fails_orphans(self, chat, db, conv, monkeypatch):
        started = []
        monkeypatch.setattr(chat, "start_video_poller", lambda *a: started.append(a))
        m1 = db.add_chat_message(conv["id"], "assistant", media=[
            {"id": "v", "kind": "video", "status": "pending", "job_id": "gen-vid-9"},
            {"id": "i", "kind": "image", "status": "pending"}])
        m2 = db.add_chat_message(conv["id"], "assistant", status="streaming")
        chat.startup_resume_chat()
        assert started == [(conv["id"], m1.id, "v", "gen-vid-9")]
        assert db.get_chat_message(m1.id).media[1]["status"] == "error"
        assert db.get_chat_message(m2.id).status == "error"


def test_alembic_migration_creates_chat_tables(tmp_path):
    """0003 adds the chat tables to a pre-chat DB, and is a no-op when
    create_all() already made them (the app creates tables on startup)."""
    from alembic import command
    from alembic.config import Config
    import sqlalchemy as sa

    def cfg_for(path):
        cfg = Config(str(ROOT_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT_DIR / "alembic"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
        return cfg

    # Pre-chat DB: full schema minus the chat tables, stamped at 0002
    old = tmp_path / "old.db"
    MetadataDB(db_path=old).engine.dispose()
    eng = sa.create_engine(f"sqlite:///{old}")
    with eng.begin() as c:
        c.execute(sa.text("DROP TABLE chat_library_items"))
        c.execute(sa.text("DROP TABLE chat_messages"))
        c.execute(sa.text("DROP TABLE chat_conversations"))
    command.stamp(cfg_for(old), "0002")
    command.upgrade(cfg_for(old), "head")
    assert {"chat_conversations", "chat_messages", "chat_library_items"} <= set(sa.inspect(eng).get_table_names())

    # DB where create_all already made them
    fresh = tmp_path / "fresh.db"
    MetadataDB(db_path=fresh).engine.dispose()
    command.stamp(cfg_for(fresh), "0002")
    command.upgrade(cfg_for(fresh), "head")


class TestOpenRouterErrors:
    def _resp(self, status, body):
        import httpx
        return httpx.Response(status, json=body)

    def test_names_upstream_provider(self):
        from web import openrouter
        body = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                          "metadata": {"provider_name": "Google AI Studio"}}}
        with pytest.raises(openrouter.OpenRouterError) as e:
            openrouter._raise_for_response(self._resp(400, body))
        assert str(e.value) == "[Google AI Studio] API key not valid. Please pass a valid API key."
        assert e.value.status == 400

    def test_appends_raw_upstream_message(self):
        from web import openrouter
        body = {"error": {"message": "Provider returned error",
                          "metadata": {"provider_name": "Fal", "raw": "content policy"}}}
        with pytest.raises(openrouter.OpenRouterError) as e:
            openrouter._raise_for_response(self._resp(502, body))
        assert str(e.value) == "[Fal] Provider returned error: content policy"

    def test_non_json_body(self):
        import httpx
        from web import openrouter
        with pytest.raises(openrouter.OpenRouterError) as e:
            openrouter._raise_for_response(httpx.Response(503, text="upstream down"))
        assert str(e.value) == "upstream down"


class TestEditAndLibrary:
    def _send(self, client, conv, content, **extra):
        return _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                   json={"content": content, **SETTINGS, **extra}))

    def _messages(self, client, conv):
        return client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]

    def test_edit_replaces_reply_and_drops_later_turns(self, client, conv, chat, monkeypatch):
        replies = iter([_text_chunks("one"), _text_chunks("two"), _text_chunks("edited reply")])
        seen = []
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None: (seen.append(msgs), next(replies))[1])
        first = self._send(client, conv, "first")[0]["user_message"]
        self._send(client, conv, "second")

        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/edit",
                                 json={"message_id": first["id"], "content": "first, but better", **SETTINGS}))
        assert ev[0]["user_message"]["id"] == first["id"]
        assert ev[0]["user_message"]["content"] == "first, but better"
        assert [(m["role"], m["content"]) for m in self._messages(client, conv)] == [
            ("user", "first, but better"), ("assistant", "edited reply")]
        # the model only saw the edited prompt, not the dropped turns
        assert [m["role"] for m in seen[-1]] == ["system", "user"]

    def test_edit_moves_generated_media_to_library(self, client, conv, chat, monkeypatch):
        rounds = iter([_tool_chunks("generate_image", {"prompt": "a cat"}), _text_chunks("Here."),
                       _text_chunks("No image this time.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(rounds))
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], 0.04))
        ev = self._send(client, conv, "draw a cat")
        user_id = ev[0]["user_message"]["id"]
        img = ev[-1]["message"]["media"][0]

        _events(client.post(f"/api/chat/conversations/{conv['id']}/edit",
                            json={"message_id": user_id, "content": "just say hi", **SETTINGS}))
        msgs = self._messages(client, conv)
        assert all(not m["media"] for m in msgs)
        lib = client.get("/api/chat/library").json()["items"]
        assert [(i["id"], i["attached"], i["message_id"]) for i in lib] == [(img["id"], False, None)]
        assert lib[0]["conversation_title"] == "draw a cat"
        assert (chat._chat_root() / conv["id"] / img["file"]).is_file()  # file kept

    def test_retry_also_detaches_media(self, client, conv, chat, monkeypatch):
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: pytest.fail("no LLM in image mode"))
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None))
        first = self._send(client, conv, "a dog", mode="image")[-1]["message"]
        second = _events(client.post(f"/api/chat/conversations/{conv['id']}/retry",
                                      json={"message_id": first["id"], "mode": "image", **SETTINGS}))[-1]["message"]
        lib = client.get("/api/chat/library").json()["items"]
        assert {(i["id"], i["attached"]) for i in lib} == {
            (first["media"][0]["id"], False), (second["media"][0]["id"], True)}

    def test_uploads_are_not_kept_in_library(self, client, conv, chat, db, monkeypatch):
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok"))
        up = client.post(f"/api/chat/conversations/{conv['id']}/attachments",
                         files={"file": ("a.png", _png_bytes(), "image/png")}).json()["file"]
        first = self._send(client, conv, "hi")[0]["user_message"]
        self._send(client, conv, "look", attachments=[up])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/edit",
                            json={"message_id": first["id"], "content": "hello", **SETTINGS}))
        assert client.get("/api/chat/library").json()["items"] == []

    def test_edit_rejected_while_streaming(self, client, conv, db):
        user = db.add_chat_message(conv["id"], "user", "hi")
        db.add_chat_message(conv["id"], "assistant", status="streaming")
        r = client.post(f"/api/chat/conversations/{conv['id']}/edit",
                        json={"message_id": user.id, "content": "x", **SETTINGS})
        assert r.status_code == 409

    def test_edit_rejects_assistant_message(self, client, conv, db):
        a = db.add_chat_message(conv["id"], "assistant", "hi")
        r = client.post(f"/api/chat/conversations/{conv['id']}/edit",
                        json={"message_id": a.id, "content": "x", **SETTINGS})
        assert r.status_code == 400

    def test_pending_video_finishes_into_library(self, chat, db, conv, monkeypatch):
        db.add_chat_message(conv["id"], "user", "waves")
        msg = db.add_chat_message(conv["id"], "assistant", media=[
            {"id": "v1", "kind": "video", "source": "generated", "status": "pending", "job_id": "gen-vid-1"}])
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        assert db.get_chat_message(msg.id) is None
        monkeypatch.setattr(chat.openrouter, "get_video", lambda j: {"status": "completed", "usage": {"cost": 0.3}})
        monkeypatch.setattr(chat.openrouter, "download_video", lambda j, dest, index=0: dest.write_bytes(b"mp4"))
        chat._poll_video(conv["id"], msg.id, "v1", "gen-vid-1")
        item = db.get_chat_library_item("v1").item
        assert item["status"] == "done" and item["file"].endswith(".mp4") and item["cost"] == 0.3

    def test_startup_resumes_library_videos(self, chat, db, conv, monkeypatch):
        started = []
        monkeypatch.setattr(chat, "start_video_poller", lambda *a: started.append(a))
        msg = db.add_chat_message(conv["id"], "assistant", media=[
            {"id": "v2", "kind": "video", "source": "generated", "status": "pending", "job_id": "gen-vid-2"}])
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        chat.startup_resume_chat()
        assert started == [(conv["id"], 0, "v2", "gen-vid-2")]

    def test_delete_library_item(self, client, conv, chat, db):
        f = chat._conv_dir(conv["id"]) / "img_x.png"
        f.write_bytes(b"png")
        msg = db.add_chat_message(conv["id"], "assistant", media=[
            {"id": "i1", "kind": "image", "source": "generated", "status": "done", "file": "img_x.png"}])
        assert client.delete("/api/chat/library/i1").status_code == 404  # still attached
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        assert client.delete("/api/chat/library/i1").status_code == 200
        assert not f.exists()
        assert client.get("/api/chat/library").json()["items"] == []

    def test_deleting_conversation_removes_its_library_items(self, client, conv, db):
        msg = db.add_chat_message(conv["id"], "assistant", media=[
            {"id": "i2", "kind": "image", "source": "generated", "status": "done", "file": "x.png"}])
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert db.get_chat_library_item("i2") is None


def test_resend_same_prompt_gets_fresh_reply(client, conv, chat, monkeypatch):
    """Retry on a prompt = edit with unchanged text: later turns go, reply regenerates."""
    replies = iter([_text_chunks("a"), _text_chunks("b"), _text_chunks("c")])
    monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
    first = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                json={"content": "tell me a joke", **SETTINGS}))[0]["user_message"]
    _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "another", **SETTINGS}))
    _events(client.post(f"/api/chat/conversations/{conv['id']}/edit",
                        json={"message_id": first["id"], "content": "tell me a joke", **SETTINGS}))
    msgs = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "tell me a joke"), ("assistant", "c")]
