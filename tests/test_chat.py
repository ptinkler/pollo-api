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


def _tool_chunks(name, args, call_id="call_1", text=""):
    raw = json.dumps(args)
    if text:
        yield {"choices": [{"delta": {"content": text}}]}
    yield {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": call_id, "function": {"name": name, "arguments": raw[:5]}}]}}]}
    yield {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"arguments": raw[5:]}}]}}]}
    yield {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"cost": 0.003}}


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

        def fake_stream(model, messages, tools=None, session_id=None, **kw):
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

    def test_auto_mode_image_then_model_continues(self, client, conv, chat, monkeypatch):
        rounds = iter([_tool_chunks("generate_image", {"prompt": "a cat", "aspect_ratio": "16:9"},
                                    text="Once upon a time, a cat."),
                       _text_chunks("The end.", cost=0.002)])
        calls = []

        def fake_stream(model, messages, tools=None, session_id=None, **kw):
            calls.append((messages, tools))
            return next(rounds)
        monkeypatch.setattr(chat.openrouter, "stream_chat", fake_stream)
        img_args = {}

        def fake_image(model, prompt, **kw):
            img_args.update(model=model, prompt=prompt, **kw)
            return [(_png_bytes(), "image/png")], 0.04
        monkeypatch.setattr(chat.openrouter, "generate_image", fake_image)

        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "a story about a cat, with a picture", "mode": "auto", **SETTINGS}))
        assert [t["function"]["name"] for t in calls[0][1]] == ["generate_image", "generate_video"]
        assert len(calls) == 2
        assert calls[1][0][-1]["role"] == "tool" and json.loads(calls[1][0][-1]["content"])["ok"]
        assert img_args["model"] == "i/model" and img_args["prompt"] == "a cat"
        assert img_args["aspect_ratio"] == "16:9"
        media_events = [e["item"] for e in ev if e["type"] == "media"]
        assert [m["status"] for m in media_events] == ["pending", "done"]
        done = ev[-1]["message"]
        assert done["content"] == "Once upon a time, a cat.\n\nThe end."
        assert done["media"][0]["file"].startswith("img_")
        assert done["cost"] == pytest.approx(0.045)  # both LLM rounds + image
        path = chat._chat_root() / conv["id"] / done["media"][0]["file"]
        assert path.read_bytes() == _png_bytes()

    def test_failed_tool_gets_follow_up_round(self, client, conv, chat, monkeypatch):
        rounds = iter([_tool_chunks("generate_image", {"prompt": "a cat"}, text="Drawing it."),
                       _text_chunks("Sorry, the image model is down.")])
        calls = []
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None, **kw: (calls.append(msgs), next(rounds))[1])

        def boom(*a, **k):
            raise chat.openrouter.OpenRouterError("[Seed] overloaded")
        monkeypatch.setattr(chat.openrouter, "generate_image", boom)

        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "draw a cat", **SETTINGS}))
        assert len(calls) == 2
        assert calls[1][-1]["role"] == "tool" and not json.loads(calls[1][-1]["content"])["ok"]
        done = ev[-1]["message"]
        assert done["status"] == "done"
        assert done["content"] == "Drawing it.\n\nSorry, the image model is down."
        assert done["media"][0]["status"] == "error"

    def test_chained_image_then_video_in_one_response(self, client, conv, chat, monkeypatch):
        args_img = json.dumps({"prompt": "a fox"})
        args_vid = json.dumps({"prompt": "the fox runs", "source_image": "latest"})
        chunks = [
            {"choices": [{"delta": {"content": "A fox, then it runs."}}]},
            {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "c1", "function": {"name": "generate_image", "arguments": args_img}},
                {"index": 1, "id": "c2", "function": {"name": "generate_video", "arguments": args_vid}}]}}]},
        ]
        calls = []
        replies = iter([iter(chunks), _text_chunks("Done.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda *a, **k: (calls.append(1), next(replies))[1])
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None))
        submitted = {}
        monkeypatch.setattr(chat.openrouter, "submit_video",
                            lambda model, prompt, **kw: (submitted.update(kw), {"id": "gen-vid-1"})[1])
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "draw a fox and animate it", **SETTINGS}))
        assert len(calls) == 2
        assert submitted["first_frame"].startswith("data:image/png;base64,")
        assert [m["kind"] for m in ev[-1]["message"]["media"]] == ["image", "video"]

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
        assert db.get_chat_message(msg.id).media[0] == {"id": "m1", "kind": "video", "status": "error", "error": "nsfw",
                                                        "moderated": True}

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
                            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(tools=tools, msgs=msgs),
                                                                          _text_chunks("ok"))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "hi", "mode": "auto", **SETTINGS}))
        assert seen["tools"] is None

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

    def test_history_records_past_media_as_tool_calls(self, client, conv, chat, db, monkeypatch):
        db.add_chat_message(conv["id"], "user", "draw a fox")
        db.add_chat_message(conv["id"], "assistant", "Here!", media=[
            {"id": "a", "kind": "image", "source": "generated", "status": "done", "file": "x.png", "prompt": "a fox",
             "params": {"aspect_ratio": "16:9"}},
            {"id": "b", "kind": "image", "source": "generated", "status": "error", "error": "flagged",
             "prompt": "another fox"}])
        seen = {}
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "nice", **SETTINGS}))
        m = seen["msgs"]
        assert m[2] == {"role": "assistant", "content": "Here!", "tool_calls": [
            {"id": "call_a", "type": "function",
             "function": {"name": "generate_image", "arguments": json.dumps({"prompt": "a fox", "aspect_ratio": "16:9"})}},
            {"id": "call_b", "type": "function",
             "function": {"name": "generate_image", "arguments": json.dumps({"prompt": "another fox"})}}]}
        assert m[3] == {"role": "tool", "tool_call_id": "call_a",
                        "content": json.dumps({"ok": True, "result": chat.IMAGE_TOOL_RESULT})}
        assert m[4] == {"role": "tool", "tool_call_id": "call_b", "content": json.dumps({"ok": False, "error": "flagged"})}
        assert m[5]["role"] == "user"
        assert not any("[generated image" in json.dumps(x) for x in m[1:])

    def test_history_uses_notes_when_no_tools_are_offered(self, client, conv, chat, db, monkeypatch):
        db.add_chat_message(conv["id"], "user", "draw a fox")
        db.add_chat_message(conv["id"], "assistant", "Here!", media=[
            {"id": "a", "kind": "image", "source": "generated", "status": "done", "file": "x.png", "prompt": "a fox"}])
        seen = {}
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "nice", "mode": "text", **SETTINGS}))
        assert seen["msgs"][2] == {"role": "assistant", "content": "Here!\n\n[generated image: a fox]"}
        assert not any("tool_calls" in x for x in seen["msgs"])


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
                            lambda m, msgs, tools=None, session_id=None, **kw: (seen.append(msgs), next(replies))[1])
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



class TestModerationAndRegenerate:
    def _blocked(self, chat, status=403, msg="Your input was flagged by moderation"):
        def boom(*a, **k):
            raise chat.openrouter.OpenRouterError(msg, status)
        return boom

    def test_moderation_block_ends_turn_without_retry(self, client, conv, chat, monkeypatch):
        rounds = iter([_tool_chunks("generate_image", {"prompt": "risky", "aspect_ratio": "9:16"}, text="Here goes.")])
        calls = []
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda *a, **k: (calls.append(1), next(rounds))[1])
        monkeypatch.setattr(chat.openrouter, "generate_image", self._blocked(chat))
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "draw it", **SETTINGS}))
        assert len(calls) == 1  # no follow-up round, so no silent re-attempt
        done = ev[-1]["message"]
        assert done["content"] == "Here goes." and done["status"] == "done"
        item = done["media"][0]
        assert item["status"] == "error" and item["moderated"] is True
        assert item["params"] == {"aspect_ratio": "9:16", "resolution": None, "refs": []}

    @pytest.mark.parametrize("status,msg,expected", [
        (403, "Forbidden", True),
        (400, "[Seed] Request rejected: content policy violation", True),
        (400, "Provider returned error: prompt contains sensitive content", True),
        (502, "Upstream timed out", False),
        (400, "Invalid aspect_ratio", False),
    ])
    def test_moderation_detection(self, chat, status, msg, expected):
        assert chat._is_moderation_error(chat.openrouter.OpenRouterError(msg, status)) is expected

    def _failed_image(self, db, conv, **extra):
        db.add_chat_message(conv["id"], "user", "draw")
        return db.add_chat_message(conv["id"], "assistant", "Here goes.", model="t/model", media=[{
            "id": "m1", "kind": "image", "source": "generated", "status": "error", "error": "flagged",
            "moderated": True, "prompt": "a lighthouse", "model": "i/model",
            "params": {"aspect_ratio": "16:9", "resolution": None, "refs": []}, **extra}])

    def _run_worker_inline(self, chat, monkeypatch):
        class Inline:
            def __init__(self, target, args, **kw):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)
        monkeypatch.setattr(chat.threading, "Thread", Inline)

    def test_retry_same_model(self, client, conv, chat, db, monkeypatch):
        msg = self._failed_image(db, conv)
        self._run_worker_inline(chat, monkeypatch)
        got = {}
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: (got.update(model=model, prompt=prompt, **kw),
                                                         ([(_png_bytes(), "image/png")], 0.02))[1])
        r = client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        assert r.status_code == 200
        assert got["model"] == "i/model" and got["prompt"] == "a lighthouse" and got["aspect_ratio"] == "16:9"
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "done" and item["file"].startswith("img_") and item["moderated"] is False
        assert db.get_chat_message(msg.id).cost == 0.02

    def test_retry_with_different_model(self, client, conv, chat, db, monkeypatch):
        msg = self._failed_image(db, conv)
        self._run_worker_inline(chat, monkeypatch)
        got = {}
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: (got.update(model=model), ([(_png_bytes(), "image/png")], None))[1])
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={"model": "other/model"})
        assert got["model"] == "other/model"
        assert db.get_chat_message(msg.id).media[0]["model"] == "other/model"

    def test_retry_blocked_again_stays_failed(self, client, conv, chat, db, monkeypatch):
        msg = self._failed_image(db, conv)
        self._run_worker_inline(chat, monkeypatch)
        monkeypatch.setattr(chat.openrouter, "generate_image", self._blocked(chat))
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "error" and item["moderated"] is True

    def test_retry_video_refits_params_for_new_model(self, client, conv, chat, db, monkeypatch):
        db.add_chat_message(conv["id"], "user", "waves")
        msg = db.add_chat_message(conv["id"], "assistant", media=[{
            "id": "v1", "kind": "video", "source": "generated", "status": "error", "error": "flagged",
            "prompt": "waves", "model": "v/old",
            "params": {"duration": 7, "aspect_ratio": "16:9", "resolution": None, "first_frame": None}}])
        chat._models_cache.update(at=9e18, data={"text": [], "image": [], "video": [
            {"id": "v/new", "durations": [5, 10], "aspect_ratios": ["16:9"], "resolutions": []}]})
        self._run_worker_inline(chat, monkeypatch)
        started = []
        monkeypatch.setattr(chat, "start_video_poller", lambda *a: started.append(a))
        got = {}
        monkeypatch.setattr(chat.openrouter, "submit_video",
                            lambda model, prompt, **kw: (got.update(model=model, **kw), {"id": "gen-vid-9"})[1])
        client.post(f"/api/chat/messages/{msg.id}/media/v1/regenerate", json={"model": "v/new"})
        assert got["model"] == "v/new" and got["duration"] == 5
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "pending" and item["job_id"] == "gen-vid-9"
        assert started == [(conv["id"], msg.id, "v1", "gen-vid-9")]

    def test_only_failed_items_can_be_retried(self, client, conv, db):
        msg = self._failed_image(db, conv, status="done", file="x.png")
        assert client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={}).status_code == 400
        assert client.post(f"/api/chat/messages/{msg.id}/media/nope/regenerate", json={}).status_code == 404



class TestContext:
    def _capture(self, chat, monkeypatch):
        seen = {}
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1])
        return seen

    def _img(self, chat, conv, name):
        (chat._conv_dir(conv["id"]) / name).write_bytes(_png_bytes())
        return {"id": name, "kind": "image", "source": "generated", "status": "done", "file": name, "prompt": name}

    def test_generated_image_is_sent_as_pixels_with_next_user_message(self, client, conv, chat, db, monkeypatch):
        db.add_chat_message(conv["id"], "user", "draw Linh")
        db.add_chat_message(conv["id"], "assistant", "Here she is.", media=[self._img(chat, conv, "g1.png")])
        seen = self._capture(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "what is she wearing?", **SETTINGS}))
        last = seen["msgs"][-1]
        assert last["role"] == "user"
        kinds = [p["type"] for p in last["content"]]
        assert kinds == ["text", "image_url", "text"]
        assert "images you generated" in last["content"][0]["text"]
        assert last["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert last["content"][2]["text"] == "what is she wearing?"
        # the image appears in history as the tool call that made it
        assert seen["msgs"][-3]["tool_calls"][0]["function"]["name"] == "generate_image"
        assert seen["msgs"][-2]["role"] == "tool"

    def test_only_most_recent_images_as_pixels(self, client, conv, chat, db, monkeypatch):
        for i in range(6):
            db.add_chat_message(conv["id"], "user", f"draw {i}")
            db.add_chat_message(conv["id"], "assistant", "ok", media=[self._img(chat, conv, f"g{i}.png")])
        seen = self._capture(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "next", **SETTINGS}))
        n_pixels = sum(1 for m in seen["msgs"] if isinstance(m["content"], list)
                       for p in m["content"] if p["type"] == "image_url")
        assert n_pixels == chat.MAX_HISTORY_IMAGES

    def test_no_pixels_for_text_only_models(self, client, conv, chat, db, monkeypatch):
        chat._models_cache.update(at=9e18, data={"image": [], "video": [], "text": [
            {"id": "t/model", "supports_tools": True, "input_modalities": ["text"]}]})
        db.add_chat_message(conv["id"], "user", "draw")
        db.add_chat_message(conv["id"], "assistant", "ok", media=[self._img(chat, conv, "g.png")])
        seen = self._capture(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "next", **SETTINGS}))
        assert seen["msgs"][-1] == {"role": "user", "content": [{"type": "text", "text": "next"}]}

    def test_history_limit_keeps_recent_messages_starting_on_user(self, client, conv, chat, db, monkeypatch):
        for i in range(5):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        seen = self._capture(chat, monkeypatch)
        # limit 4 of 11 history messages → [a3?, q4, a4, now] trimmed to start on a user message
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "now", "history_limit": 4, **SETTINGS}))
        body = seen["msgs"][1:]
        assert [m["role"] for m in body] == ["user", "assistant", "user"]
        assert body[0]["content"][0]["text"] == "q4"

    def test_no_limit_sends_everything(self, client, conv, chat, db, monkeypatch):
        for i in range(3):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        seen = self._capture(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "now", **SETTINGS}))
        assert len(seen["msgs"]) == 1 + 7
        assert "omitted" not in seen["msgs"][0]["content"]

    def test_invalid_limit_rejected(self, client, conv):
        r = client.post(f"/api/chat/conversations/{conv['id']}/messages",
                        json={"content": "x", "history_limit": 0, **SETTINGS})
        assert r.status_code == 422




class TestStallProtection:
    """A stalled upstream only sends keep-alives; we must not hang forever."""

    class _FakeStream:
        def __init__(self, lines):
            self.lines = lines
            self.status_code = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def iter_lines(self):
            yield from self.lines

    def _keepalives(self):
        import time as _t
        while True:
            _t.sleep(0.02)
            yield ": OPENROUTER PROCESSING"

    def test_deadline_breaks_a_keepalive_only_stream(self, chat, monkeypatch):
        monkeypatch.setattr(chat.openrouter.httpx, "stream", lambda *a, **k: self._FakeStream(self._keepalives()))
        with pytest.raises(chat.openrouter.OpenRouterError) as e:
            list(chat.openrouter.stream_chat("m", [], max_seconds=0.2))
        assert e.value.status == 504

    def test_stop_is_noticed_during_keepalives(self, chat, monkeypatch):
        import threading, time as _t
        monkeypatch.setattr(chat.openrouter.httpx, "stream", lambda *a, **k: self._FakeStream(self._keepalives()))
        stop = threading.Event()
        threading.Timer(0.1, stop.set).start()
        t0 = _t.monotonic()
        assert list(chat.openrouter.stream_chat("m", [], should_stop=stop.is_set)) == []
        assert _t.monotonic() - t0 < 2


class TestConsistencyReferences:
    def _prior_images(self, chat, db, conv, n):
        db.add_chat_message(conv["id"], "user", "story with a photo")
        for i in range(n):
            f = f"g{i}.png"
            (chat._conv_dir(conv["id"]) / f).write_bytes(_png_bytes(color=(i * 40, 0, 0)))
            db.add_chat_message(conv["id"], "assistant", f"scene {i}", media=[
                {"id": f"g{i}", "kind": "image", "source": "generated", "status": "done", "file": f, "prompt": f"p{i}"}])

    def _run(self, client, conv, chat, monkeypatch, tool_args):
        replies = iter([_tool_chunks("generate_image", tool_args, text="Next scene."), _text_chunks("Done.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = {}
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: (got.update(kw), ([(_png_bytes(), "image/png")], None))[1])
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "continue the story", **SETTINGS}))
        return got, ev[-1]["message"]["media"][0]

    def test_no_references_unless_the_model_asks(self, client, conv, chat, db, monkeypatch):
        self._prior_images(chat, db, conv, 1)
        got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "the same woman, now turned around"})
        assert got.get("input_images") is None and item["params"]["refs"] == []

    def test_model_opts_in_and_prompt_is_passed_verbatim(self, client, conv, chat, db, monkeypatch):
        self._prior_images(chat, db, conv, 1)
        replies = iter([_tool_chunks("generate_image", {"prompt": "exactly what the model wrote",
                                                        "keep_consistent": True}, text="Next."),
                        _text_chunks("Done.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = {}
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw), ([(_png_bytes(), "image/png")], None))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "continue", **SETTINGS}))
        assert got["prompt"] == "exactly what the model wrote"
        assert len(got["input_images"]) == 1

    def test_uses_only_the_most_recent_two(self, client, conv, chat, db, monkeypatch):
        self._prior_images(chat, db, conv, 3)
        got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "scene 4", "keep_consistent": True})
        assert item["params"]["refs"] == ["g2.png", "g1.png"]

    def test_first_image_in_chat_has_no_refs(self, client, conv, chat, db, monkeypatch):
        got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "Linh", "keep_consistent": True})
        assert got.get("input_images") is None

    def test_skipped_for_image_models_without_reference_support(self, client, conv, chat, db, monkeypatch):
        chat._models_cache.update(at=9e18, data={"text": [], "video": [], "image": [
            {"id": "i/model", "input_modalities": ["text"]}]})
        self._prior_images(chat, db, conv, 1)
        got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "next", "keep_consistent": True})
        assert got.get("input_images") is None

    def test_edit_source_comes_first(self, client, conv, chat, db, monkeypatch):
        self._prior_images(chat, db, conv, 2)
        got, item = self._run(client, conv, chat, monkeypatch,
                              {"prompt": "make it night", "source_image": "latest", "keep_consistent": True})
        assert item["params"]["refs"] == ["g1.png", "g0.png"]

    def test_edit_alone_sends_just_the_source(self, client, conv, chat, db, monkeypatch):
        self._prior_images(chat, db, conv, 2)
        got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "make it night", "source_image": "latest"})
        assert item["params"]["refs"] == ["g1.png"]


class TestModelDecides:
    """The app never adds instructions or extra calls to steer the model."""

    def test_no_extra_call_when_model_skips_the_tool(self, client, conv, chat, monkeypatch):
        calls = []
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda *a, **k: (calls.append(k), _text_chunks("A story, and here's the photo."))[1])
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "write a story and create an image of the scene", **SETTINGS}))
        assert len(calls) == 1
        assert ev[-1]["message"]["content"] == "A story, and here's the photo." and ev[-1]["message"]["media"] == []

    def test_system_prompt_is_static(self, client, conv, chat, db, monkeypatch):
        for i in range(4):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        chat._models_cache.update(at=9e18, data={"image": [], "video": [], "text": [
            {"id": "t/model", "supports_tools": False, "input_modalities": ["text"]}]})
        seen = {}
        monkeypatch.setattr(chat.openrouter, "stream_chat",
                            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1])
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "hi", "history_limit": 3, **SETTINGS}))
        from datetime import datetime
        assert seen["msgs"][0]["content"] == chat.SYSTEM_PROMPT.format(today=datetime.now().strftime("%A %d %B %Y"))


class TestConversationalImageModels:
    """Gemini-style image models get the conversation, not a lone prompt."""

    CATALOGUE = {"text": [], "video": [], "image": [
        {"id": "i/model", "input_modalities": ["text", "image"], "conversational": True}]}

    def _setup(self, chat, db, conv, with_prior_image=True):
        chat._models_cache.update(at=9e18, data=self.CATALOGUE)
        db.add_chat_message(conv["id"], "user", "write a story about Linh, with a photo")
        media = []
        if with_prior_image:
            (chat._conv_dir(conv["id"]) / "g0.png").write_bytes(_png_bytes())
            media = [{"id": "g0", "kind": "image", "source": "generated", "status": "done", "file": "g0.png",
                      "prompt": "Linh in the gym"}]
        db.add_chat_message(conv["id"], "assistant", "Linh lifted.", media=media)

    def _fake_chat_image(self, chat, monkeypatch):
        got = {}
        monkeypatch.setattr(chat.openrouter, "generate_image_chat",
                            lambda model, messages, **kw: (got.update(model=model, messages=messages, **kw),
                                                           ([(_png_bytes(), "image/png")], 0.04))[1])
        monkeypatch.setattr(chat.openrouter, "generate_image", lambda *a, **k: pytest.fail("Images API not used"))
        return got

    def test_auto_mode_sends_conversation_reply_and_prompt(self, client, conv, chat, db, monkeypatch):
        self._setup(chat, db, conv)
        replies = iter([_tool_chunks("generate_image", {"prompt": "Linh turns around", "aspect_ratio": "3:4"},
                                     text="She turned around."),
                        _text_chunks("Done.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._fake_chat_image(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "can I see your muscles? (continue, with an image)", **SETTINGS}))
        msgs = got["messages"]
        assert got["model"] == "i/model" and got["aspect_ratio"] == "3:4"
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]
        assert msgs[0]["content"][0]["text"] == "write a story about Linh, with a photo"
        # the earlier generated image is in the context as pixels
        assert any(p["type"] == "image_url" for p in msgs[2]["content"])
        assert msgs[3] == {"role": "assistant", "content": "She turned around."}      # this reply so far
        assert msgs[4] == {"role": "user", "content": [{"type": "text", "text": "Linh turns around"}]}  # verbatim
        assert all(m["role"] != "system" for m in msgs)
        item = ev[-1]["message"]["media"][0]
        assert item["status"] == "done" and item["params"]["context"] is True

    def test_image_mode_sends_conversation_ending_with_users_message(self, client, conv, chat, db, monkeypatch):
        self._setup(chat, db, conv)
        got = self._fake_chat_image(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "Linh and Marcus high-five", "mode": "image", **SETTINGS}))
        last = got["messages"][-1]
        assert last["role"] == "user" and last["content"][-1] == {"type": "text", "text": "Linh and Marcus high-five"}
        assert len(got["messages"]) == 3

    def test_memory_slider_applies_to_image_context(self, client, conv, chat, db, monkeypatch):
        self._setup(chat, db, conv, with_prior_image=False)
        for i in range(3):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        got = self._fake_chat_image(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                            json={"content": "draw it", "mode": "image", "history_limit": 3, **SETTINGS}))
        assert [m["role"] for m in got["messages"]] == ["user", "assistant", "user"]

    def test_non_conversational_models_still_use_images_api(self, client, conv, chat, db, monkeypatch):
        chat._models_cache.update(at=9e18, data={"text": [], "video": [], "image": [
            {"id": "i/model", "input_modalities": ["text", "image"], "conversational": False}]})
        monkeypatch.setattr(chat.openrouter, "generate_image_chat", lambda *a, **k: pytest.fail("chat path not used"))
        monkeypatch.setattr(chat.openrouter, "generate_image",
                            lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None))
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages",
                                 json={"content": "a dog", "mode": "image", **SETTINGS}))
        assert "context" not in ev[-1]["message"]["media"][0]["params"]

    def test_retry_of_failed_image_rebuilds_context(self, client, conv, chat, db, monkeypatch):
        chat._models_cache.update(at=9e18, data=self.CATALOGUE)
        db.add_chat_message(conv["id"], "user", "story please, with a photo")
        msg = db.add_chat_message(conv["id"], "assistant", "Linh lifted.", media=[{
            "id": "m1", "kind": "image", "source": "generated", "status": "error", "error": "timeout",
            "prompt": "Linh lifting", "model": "i/model",
            "params": {"aspect_ratio": None, "resolution": None, "refs": [], "context": True, "direct": False}}])

        class Inline:
            def __init__(self, target, args, **kw): self.target, self.args = target, args
            def start(self): self.target(*self.args)
        monkeypatch.setattr(chat.threading, "Thread", Inline)
        got = self._fake_chat_image(chat, monkeypatch)
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        assert [m["role"] for m in got["messages"]] == ["user", "assistant", "user"]
        assert got["messages"][1] == {"role": "assistant", "content": "Linh lifted."}
        assert got["messages"][2]["content"][0]["text"] == "Linh lifting"
        assert db.get_chat_message(msg.id).media[0]["status"] == "done"


class TestOpenRouterChatImages:
    def _resp(self, body):
        import httpx
        return httpx.Response(200, json=body)

    def test_parses_data_url_images_and_sends_modalities(self, chat, monkeypatch):
        import base64
        sent = {}
        b64 = base64.b64encode(_png_bytes()).decode()
        monkeypatch.setattr(chat.openrouter.httpx, "post", lambda url, **kw: (sent.update(kw["json"]), self._resp({
            "choices": [{"message": {"content": "Here", "images": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}}],
            "usage": {"cost": 0.039}}))[1])
        images, cost = chat.openrouter.generate_image_chat("g/img", [{"role": "user", "content": "hi"}], aspect_ratio="16:9")
        assert sent["modalities"] == ["image", "text"] and sent["image_config"] == {"aspect_ratio": "16:9"}
        assert images == [(_png_bytes(), "image/png")] and cost == 0.039

    def test_no_image_reports_models_text(self, chat, monkeypatch):
        monkeypatch.setattr(chat.openrouter.httpx, "post", lambda url, **kw: self._resp(
            {"choices": [{"message": {"content": "I can't draw that."}}]}))
        with pytest.raises(chat.openrouter.OpenRouterError) as e:
            chat.openrouter.generate_image_chat("g/img", [])
        assert "I can't draw that." in str(e.value)

    def test_catalogue_marks_and_adds_conversational_models(self, chat, monkeypatch):
        def fake_get(path, params=None):
            if path == "/images/models":
                return {"data": [{"id": "google/gem-img", "name": "Gem"}, {"id": "seed/dream", "name": "Seed"}]}
            return {"data": [
                {"id": "google/gem-img", "architecture": {"output_modalities": ["image", "text"]}},
                {"id": "openai/gpt-img", "name": "GPT Image", "architecture": {"output_modalities": ["image", "text"],
                                                                               "input_modalities": ["text", "image"]}},
                {"id": "seed/dream", "architecture": {"output_modalities": ["image"]}},
            ]}
        monkeypatch.setattr(chat.openrouter, "_get", fake_get)
        models = {m["id"]: m for m in chat.openrouter.list_image_models()}
        assert models["google/gem-img"]["conversational"] is True
        assert models["seed/dream"]["conversational"] is False
        assert models["openai/gpt-img"]["conversational"] is True and models["openai/gpt-img"]["name"] == "GPT Image"
