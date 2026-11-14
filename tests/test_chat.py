"""Tests for web.chat — OpenRouter chat mode. OpenRouter is always mocked."""

import base64
import importlib.util
import io
import json
import socket
import threading
import time
import time as _t
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from PIL import Image

import web.characters as characters_mod
import web.chat as chat_mod
import web.core.config as config
import web.media as media_mod
import web.providers.pollo_engine as registry
from tests.chat_fixtures import SETTINGS, _events, _png_bytes, _text_chunks, _tool_chunks
from web import request_log
from web.chat import catalogue
from web.core.metadata import MetadataDB, reset_tenant, set_tenant
from web.providers import openrouter, pollo_estimate
from web.providers import pollo as pollo_provider

pytest_plugins = ["tests.chat_fixtures"]

# Fixtures (db, chat, client, conv) come from this plugin; pytest injects them
# by name, so they are not imported here.

ROOT_DIR = Path(__file__).parent.parent.resolve()


class TestModelCatalogue:
    """The /models catalogue lists each provider independently — no provider.

    gates the endpoint, so media models show with only a Pollo key.
    """

    def test_media_models_load_without_a_chat_provider(self, client, monkeypatch, provider_keys):
        # Only Pollo configured — no OpenRouter/Venice text provider.
        """Test that media models load without a chat provider."""
        provider_keys["openrouter"] = None
        provider_keys["venice"] = None
        provider_keys["pollo"] = "pollo-test"

        catalogue.clear_models()

        def fake_list(kind, refresh=False):
            return [{"id": "pollo/seedream", "name": "Seedream"}] if kind == "image" else []

        monkeypatch.setattr(pollo_provider, "list_models", fake_list)

        r = client.get("/api/chat/models")
        assert r.status_code == 200
        data = r.json()
        assert data["errors"] == {}
        assert data["text"] == []  # no chat provider, but the endpoint still serves
        assert [m["id"] for m in data["image"]] == ["pollo/seedream"]


class TestConversations:
    """Tests for conversations."""

    def test_crud(self, client):
        """Test that crud."""
        c = client.post("/api/chat/conversations", json={"text_model": "a/b"}).json()
        assert c["title"] == "New chat"
        assert c["text_model"] == "a/b"
        assert [x["id"] for x in client.get("/api/chat/conversations").json()["conversations"]] == [c["id"]]
        r = client.patch(f"/api/chat/conversations/{c['id']}", json={"title": "  Renamed "})
        assert r.json()["title"] == "Renamed"
        assert client.delete(f"/api/chat/conversations/{c['id']}").status_code == 200
        assert client.get(f"/api/chat/conversations/{c['id']}").status_code == 404

    def test_kind_persists_through_create_patch_list_and_fetch(self, client):
        # Create as a gallery thread → kind sticks on create, list and fetch.
        """Test that kind persists through create patch list and fetch."""
        g = client.post("/api/chat/conversations", json={"kind": "gallery"}).json()
        assert g["kind"] == "gallery"
        # GET returns a { conversation, messages } envelope — kind is on the conversation.
        assert client.get(f"/api/chat/conversations/{g['id']}").json()["conversation"]["kind"] == "gallery"
        listed = {c["id"]: c["kind"] for c in client.get("/api/chat/conversations").json()["conversations"]}
        assert listed[g["id"]] == "gallery"
        # The "Opens on Chat/Gallery" toggle (PATCH kind) persists too.
        assert client.patch(f"/api/chat/conversations/{g['id']}", json={"kind": "chat"}).json()["kind"] == "chat"
        assert client.get(f"/api/chat/conversations/{g['id']}").json()["conversation"]["kind"] == "chat"
        # An unknown kind falls back to "chat" rather than being stored raw.
        c = client.post("/api/chat/conversations", json={"kind": "bogus"}).json()
        assert c["kind"] == "chat"

    def test_gallery_lane_stays_beside_the_chat_branch(self, client, db):
        """Test that gallery lane stays beside the chat branch."""
        c = client.post("/api/chat/conversations", json={}).json()
        u = db.add_chat_message(c["id"], "user", "story")
        g = db.add_chat_message(c["id"], "user", "a cat", lane="gallery")
        ga = db.add_chat_message(c["id"], "assistant", parent_id=g.id, lane="gallery")
        nxt = db.add_chat_message(c["id"], "user", "go on")
        # The gallery exchange neither moves the chat's leaf nor becomes its parent
        assert nxt.parent_id == u.id
        assert g.parent_id is None
        assert ga.parent_id == g.id
        assert db.get_chat_leaf_id(c["id"]) == nxt.id
        out = client.get(f"/api/chat/conversations/{c['id']}").json()["messages"]
        chat = [m["id"] for m in out if not m["lane"]]
        assert chat == [u.id, nxt.id]
        assert {m["id"] for m in out if m["lane"]} == {g.id, ga.id}
        # No version arrows from sharing "no parent" with the chat's first turn
        assert next(m for m in out if m["id"] == u.id)["siblings"] == [u.id]
        # Deleting the gallery exchange leaves the chat alone
        after = client.delete(f"/api/chat/messages/{g.id}").json()["messages"]
        assert [m["id"] for m in after] == [u.id, nxt.id]

    def test_conversation_thumbs_returns_newest_image(self, client, db):
        """Test that conversation thumbs returns newest image."""
        c = client.post("/api/chat/conversations", json={}).json()

        def img(mid, f):
            return [{"id": mid, "kind": "image", "status": "done", "file": f}]

        db.add_chat_message(c["id"], "assistant", media=img("m1", "old.png"))
        db.add_chat_message(c["id"], "assistant", media=img("m2", "new.png"))
        # Newest image wins; the route isn't shadowed by /conversations/{id}; unknown ids are absent.
        r = client.get(f"/api/chat/conversations/thumbs?ids={c['id']},nope")
        assert r.json() == {"thumbs": {c["id"]: "new.png"}}

    def test_status_reports_key(self, client, provider_keys):
        """Test that status reports key."""
        assert client.get("/api/chat/status").json() == {"configured": True, "openrouter": True, "venice": False}
        provider_keys["openrouter"] = None
        assert client.get("/api/chat/status").json()["configured"] is False
        provider_keys["venice"] = "v-test"  # Venice alone can run the chat
        assert client.get("/api/chat/status").json() == {"configured": True, "openrouter": False, "venice": True}

    def test_openrouter_balance(self, client, chat, monkeypatch):
        """Test that openrouter balance."""
        monkeypatch.setattr(
            openrouter,
            "_get",
            lambda path, params=None: (
                {"data": {"total_credits": 60, "total_usage": 52.78926312}} if path == "/credits" else pytest.fail(path)
            ),
        )
        assert client.get("/api/chat/credits").json() == {
            "total_credits": 60.0,
            "total_usage": 52.78926312,
            "remaining": 7.2107,
        }

    def test_openrouter_balance_error_is_502(self, client, chat, monkeypatch):
        """Test that openrouter balance error is 502."""

        def boom(path, params=None):
            raise openrouter.OpenRouterError("nope", 500)

        monkeypatch.setattr(openrouter, "_get", boom)
        assert client.get("/api/chat/credits").status_code == 502

    def test_send_without_key_is_503(self, client, conv, provider_keys):
        """Test that send without key is 503."""
        provider_keys["openrouter"] = None
        r = client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS})
        assert r.status_code == 503


class TestMedia:
    """Tests for media."""

    def test_upload_and_serve(self, client, conv):
        """Test that upload and serve."""
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments", files={"file": ("a.png", _png_bytes(), "image/png")}
        )
        name = r.json()["file"]
        assert name.startswith("up_")
        assert name.endswith(".png")
        assert client.get(f"/api/chat/media/{conv['id']}/{name}").content == _png_bytes()

    def test_rejects_non_image(self, client, conv):
        """Test that rejects non image."""
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments", files={"file": ("a.png", b"not an image", "image/png")}
        )
        assert r.status_code == 400

    @pytest.mark.parametrize(("conv_id", "name"), [("abc", "../x.png"), ("..", "metadata.db"), ("abc", ".hidden")])
    def test_path_traversal_blocked(self, chat, conv_id, name):
        """Test that path traversal blocked."""
        with pytest.raises(HTTPException) as e:
            chat.routes.api_chat_media(conv_id, name)
        assert e.value.status_code == 400

    def test_an_image_already_in_the_chat_can_be_attached(self, client, conv, chat, db, monkeypatch):
        """Attaching by name: "make a video from this image" uses it as the first frame."""
        (chat.conversation_dir(conv["id"]) / "img_old.png").write_bytes(_png_bytes())
        submitted = {}
        monkeypatch.setattr(
            openrouter, "submit_video", lambda model, prompt, **kw: (submitted.update(kw), {"id": "vid-1"})[1]
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "slow zoom", "attachments": ["img_old.png"], "mode": "video", **SETTINGS},
            )
        )
        assert submitted["first_frame"].startswith("data:image/")

    def test_unknown_attachment_rejected(self, client, conv):
        """Test that unknown attachment rejected."""
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/messages",
            json={"content": "x", "attachments": ["nope.png"], **SETTINGS},
        )
        assert r.status_code == 400


class TestTurns:
    """Tests for turns."""

    def test_text_mode_streams_and_persists(self, client, conv, chat, monkeypatch):
        """Test that text mode streams and persists."""
        seen = {}

        def fake_stream(model, messages, tools=None, session_id=None, **kw):
            seen.update(model=model, messages=messages, tools=tools)
            return _text_chunks("Hel", "lo!")

        monkeypatch.setattr(openrouter, "stream_chat", fake_stream)

        r = client.post(
            f"/api/chat/conversations/{conv['id']}/messages", json={"content": "Say hello", "mode": "text", **SETTINGS}
        )
        ev = _events(r)
        assert ev[0]["type"] == "start"
        assert ev[0]["user_message"]["content"] == "Say hello"
        assert "".join(e["text"] for e in ev if e["type"] == "delta") == "Hello!"
        assert {"type": "title", "title": "Say hello"} in ev
        done = ev[-1]["message"]
        assert done["content"] == "Hello!"
        assert done["status"] == "done"
        assert done["cost"] == 0.001
        assert seen["tools"] is None
        assert seen["messages"][0]["role"] == "system"
        assert seen["messages"][-1] == {"role": "user", "content": [{"type": "text", "text": "Say hello"}]}
        # model picks are remembered on the conversation
        assert client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["text_model"] == "t/model"

    def test_text_plus_image_is_one_llm_call(self, client, conv, chat, monkeypatch):
        """Test that text plus image is one llm call."""
        rounds = iter(
            [
                _tool_chunks(
                    "generate_image", {"prompt": "a cat", "aspect_ratio": "16:9"}, text="Once upon a time, a cat."
                )
            ]
        )
        calls = []

        def fake_stream(model, messages, tools=None, session_id=None, **kw):
            calls.append((messages, tools))
            return next(rounds)

        monkeypatch.setattr(openrouter, "stream_chat", fake_stream)
        img_args = {}

        def fake_image(model, prompt, **kw):
            img_args.update(model=model, prompt=prompt, **kw)
            return [(_png_bytes(), "image/png")], 0.04

        monkeypatch.setattr(openrouter, "generate_image", fake_image)

        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "a story about a cat, with a picture", "mode": "auto", **SETTINGS},
            )
        )
        assert [t["function"]["name"] for t in calls[0][1]] == [
            "generate_image",
            "create_character",
            "generate_video",
            "create_instruction",
        ]
        assert len(calls) == 1  # reply written + image made → complete
        assert img_args["model"] == "i/model"
        assert img_args["prompt"] == "a cat"
        # The ratio is the composer's, not the model's: on "auto" with an image
        # model that has no auto value, nothing is sent (its natural shape)
        assert img_args["aspect_ratio"] is None
        media_events = [e["item"] for e in ev if e["type"] == "media"]
        assert [m["status"] for m in media_events] == ["pending", "done"]
        done = ev[-1]["message"]
        assert done["content"] == "Once upon a time, a cat."
        assert done["media"][0]["file"].startswith("img_")
        assert done["cost"] == pytest.approx(0.043)  # LLM round + image
        path = chat.helpers.chat_root() / conv["id"] / done["media"][0]["file"]
        assert path.read_bytes() == _png_bytes()

    def test_image_models_own_auto_beats_the_chat_models_ratio_pick(self, client, conv, chat, monkeypatch):
        # With the composer ratio left unset and the image model offering its
        # own "auto", that wins over whatever ratio the chat model guessed.
        """Test that image models own auto beats the chat models ratio pick."""
        chat.catalogue.seed_models(
            {"text": [], "video": [], "image": [{"id": "i/model", "aspect_ratios": ["auto", "16:9", "1:1"]}]},
        )
        rounds = iter([_tool_chunks("generate_image", {"prompt": "a cat", "aspect_ratio": "16:9"}, text="A cat.")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        img_args = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (
                img_args.update(aspect_ratio=kw.get("aspect_ratio")),
                ([(_png_bytes(), "image/png")], 0.04),
            )[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "draw a cat", "mode": "auto", **SETTINGS},
            )
        )
        assert img_args["aspect_ratio"] == "auto"  # the image model's auto, not the chat model's 16:9

    def test_model_can_create_and_attach_an_instruction(self, client, conv, chat, monkeypatch, db):
        """Test that model can create and attach an instruction."""
        rounds = iter(
            [
                _tool_chunks(
                    "create_instruction",
                    {"name": "Pirate", "content": "You are a pirate. Always talk like one."},
                    text="Aye, saving that.",
                ),
                _text_chunks("Arr, done!"),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda m, msgs, tools=None, session_id=None, **kw: next(rounds))

        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "always talk like a pirate from now on", "mode": "auto", **SETTINGS},
            )
        )

        saved = db.list_instructions()
        assert [i.name for i in saved] == ["Pirate"]
        assert saved[0].content == "You are a pirate. Always talk like one."
        # Attached to the chat, and the UI was told so the sidebar updates live
        assert db.get_conversation(conv["id"]).instruction_ids == [saved[0].id]
        attach = next(e for e in ev if e["type"] == "instructions")
        assert attach["instruction_ids"] == [saved[0].id]
        assert attach["instruction"]["name"] == "Pirate"
        # The model still wrote its reply after saving
        assert ev[-1]["message"]["content"] == "Aye, saving that.\n\nArr, done!"

    def test_create_instruction_rejects_a_name_already_in_this_chat(self, client, conv, chat, monkeypatch, db):
        """A name already applied to this chat is refused; elsewhere in the library it's fine."""
        existing = db.save_instruction(name="Pirate", content="existing")
        db.update_conversation(conv["id"], instruction_ids=[existing.id])
        rounds = iter(
            [
                _tool_chunks("create_instruction", {"name": "pirate", "content": "You are a pirate."}),
                _text_chunks("I couldn't save that."),
            ]
        )
        calls = []
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (calls.append(msgs), next(rounds))[1],
        )

        client.post(
            f"/api/chat/conversations/{conv['id']}/messages",
            json={"content": "save a pirate instruction", "mode": "auto", **SETTINGS},
        )

        # Only the original instruction exists; the model got an error result back
        assert len(db.list_instructions()) == 1
        result = json.loads(calls[1][-1]["content"])
        assert not result["ok"]
        assert "already has an instruction" in result["error"]

    def test_create_instruction_reuses_a_library_name(self, client, conv, chat, monkeypatch, db):
        """A library instruction not on this chat doesn't block the name."""
        db.save_instruction(name="Pirate", content="existing")
        rounds = iter([_tool_chunks("create_instruction", {"name": "Pirate", "content": "Arr."}), _text_chunks("ok")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "x", "mode": "auto", **SETTINGS})
        assert [i.name for i in db.list_instructions()] == ["Pirate", "Pirate"]

    def test_failed_tool_gets_follow_up_round(self, client, conv, chat, monkeypatch):
        """Test that failed tool gets follow up round."""
        rounds = iter(
            [
                _tool_chunks("generate_image", {"prompt": "a cat"}, text="Drawing it."),
                _text_chunks("Sorry, the image model is down."),
            ]
        )
        calls = []
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (calls.append(msgs), next(rounds))[1],
        )

        def boom(*a, **k):
            raise openrouter.OpenRouterError("[Seed] overloaded")  # noqa: TRY003

        monkeypatch.setattr(openrouter, "generate_image", boom)

        ev = _events(
            client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "draw a cat", **SETTINGS})
        )
        assert len(calls) == 2
        assert calls[1][-1]["role"] == "tool"
        assert not json.loads(calls[1][-1]["content"])["ok"]
        done = ev[-1]["message"]
        assert done["status"] == "done"
        assert done["content"] == "Drawing it.\n\nSorry, the image model is down."
        assert done["media"][0]["status"] == "error"

    def test_chained_image_then_video_in_one_response(self, client, conv, chat, monkeypatch):
        """Test that chained image then video in one response."""
        args_img = json.dumps({"prompt": "a fox"})
        args_vid = json.dumps({"prompt": "the fox runs", "source_image": "latest"})
        chunks = [
            {"choices": [{"delta": {"content": "A fox, then it runs."}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "id": "c1", "function": {"name": "generate_image", "arguments": args_img}},
                                {"index": 1, "id": "c2", "function": {"name": "generate_video", "arguments": args_vid}},
                            ]
                        }
                    }
                ]
            },
        ]
        calls = []
        replies = iter([iter(chunks), _text_chunks("Done.")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: (calls.append(1), next(replies))[1])
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        submitted = {}
        monkeypatch.setattr(
            openrouter, "submit_video", lambda model, prompt, **kw: (submitted.update(kw), {"id": "gen-vid-1"})[1]
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "draw a fox and animate it", **SETTINGS},
            )
        )
        assert len(calls) == 1
        assert submitted["first_frame"].startswith("data:image/png;base64,")
        assert [m["kind"] for m in ev[-1]["message"]["media"]] == ["image", "video"]

    def test_source_latest_uses_previous_image(self, client, conv, chat, monkeypatch):
        """Test that source latest uses previous image."""
        up = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments", files={"file": ("a.png", _png_bytes(), "image/png")}
        ).json()["file"]
        rounds = iter(
            [
                _tool_chunks("generate_image", {"prompt": "make it blue", "source_image": "latest"}),
                _text_chunks("Done."),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "make it blue", "attachments": [up], **SETTINGS},
            )
        )
        assert got["input_images"][0].startswith("data:image/png;base64,")

    def test_image_mode_skips_text_model(self, client, conv, chat, monkeypatch):
        """Test that image mode skips text model."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: pytest.fail("no LLM in image mode"))
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw), ([(_png_bytes(), "image/png")] * 2, 0.02))[1],
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={
                    "content": "a dog",
                    "mode": "image",
                    "image_options": {"aspect_ratio": "1:1", "resolution": "2K"},
                    **SETTINGS,
                },
            )
        )
        assert got["prompt"] == "a dog"
        assert got["aspect_ratio"] == "1:1"
        assert got["resolution"] == "2K"
        assert len(ev[-1]["message"]["media"]) == 2
        assert ev[-1]["message"]["model"] == "i/model"

    def test_video_mode_submits_and_polls(self, client, conv, chat, monkeypatch, db):
        """Test that video mode submits and polls."""
        started = []
        monkeypatch.setattr(chat.polling, "start_video_poller", lambda *a: started.append(a))
        monkeypatch.setattr(
            openrouter, "submit_video", lambda model, prompt, **kw: {"id": "gen-vid-1", "status": "pending"}
        )
        chat.catalogue.seed_models(
            {
                "text": [],
                "image": [],
                "video": [{"id": "v/model", "durations": [5, 10], "aspect_ratios": ["16:9"], "resolutions": ["720p"]}],
            },
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={
                    "content": "waves",
                    "mode": "video",
                    "video_options": {"duration": 7, "aspect_ratio": "1:1"},
                    **SETTINGS,
                },
            )
        )
        item = ev[-1]["message"]["media"][0]
        assert item["status"] == "pending"
        assert item["job_id"] == "gen-vid-1"
        assert item["params"]["duration"] == 5
        assert item["params"]["aspect_ratio"] is None
        conv_id, msg_id, media_id, job_id = started[0]

        # Now run the poller for real against mocked status/download
        statuses = iter([{"status": "in_progress"}, {"status": "completed", "usage": {"cost": 0.5}}])
        monkeypatch.setattr(openrouter, "get_video", lambda j: next(statuses))
        monkeypatch.setattr(openrouter, "download_video", lambda j, dest, index=0: dest.write_bytes(b"mp4"))
        chat.polling._poll_video(conv_id, msg_id, media_id, job_id)
        msg = client.get(f"/api/chat/messages/{msg_id}").json()
        assert msg["media"][0]["status"] == "done"
        assert msg["media"][0]["file"].endswith(".mp4")
        assert msg["cost"] == 0.5

    def test_video_failure_marks_item(self, chat, db, conv, monkeypatch):
        """Test that video failure marks item."""
        msg = db.add_chat_message(conv["id"], "assistant", media=[{"id": "m1", "kind": "video", "status": "pending"}])
        monkeypatch.setattr(openrouter, "get_video", lambda j: {"status": "failed", "error": "nsfw"})
        chat.polling._poll_video(conv["id"], msg.id, "m1", "gen-vid-x")
        assert db.get_chat_message(msg.id).media[0] == {
            "id": "m1",
            "kind": "video",
            "status": "error",
            "error": "nsfw",
            "moderated": True,
        }

    def test_openrouter_error_marks_message(self, client, conv, chat, monkeypatch):
        """Test that openrouter error marks message."""

        def boom(*a, **k):
            raise openrouter.OpenRouterError("Insufficient credits", 402)  # noqa: TRY003

        monkeypatch.setattr(openrouter, "stream_chat", boom)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        assert {"type": "error", "message": "Insufficient credits"} in ev
        assert ev[-1]["message"]["status"] == "error"

    def test_tools_withheld_for_models_without_tool_support(self, client, conv, chat, monkeypatch):
        """Test that tools withheld for models without tool support."""
        chat.catalogue.seed_models(
            {
                "image": [],
                "video": [],
                "text": [{"id": "t/model", "supports_tools": False, "input_modalities": ["text"]}],
            },
        )
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (
                seen.update(tools=tools, msgs=msgs),
                _text_chunks("ok"),
            )[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", "mode": "auto", **SETTINGS}
            )
        )
        assert seen["tools"] is None

    def test_retry_replaces_assistant_message(self, client, conv, chat, monkeypatch):
        """Test that retry replaces assistant message."""
        replies = iter([_text_chunks("first"), _text_chunks("second")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        first = _events(
            client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS})
        )[-1]["message"]
        ev = _events(
            client.post(f"/api/chat/conversations/{conv['id']}/retry", json={"message_id": first["id"], **SETTINGS})
        )
        assert ev[0]["user_message"] is None
        msgs = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
        assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "second")]

    def test_retry_uses_the_selected_mode(self, client, conv, chat, monkeypatch):
        """A reply sent in Chat mode, retried with Auto selected, reruns in Auto.

        (tools offered) and the prompt's mode tag follows it.
        """
        offered = []

        def stream(model, msgs, tools=None, **kw):
            offered.append(bool(tools))
            return _text_chunks("ok")

        monkeypatch.setattr(openrouter, "stream_chat", stream)
        first = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS, "mode": "text"}
            )
        )[-1]["message"]
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/retry",
                json={"message_id": first["id"], **SETTINGS, "mode": "auto"},
            )
        )
        assert offered == [False, True]
        msgs = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
        assert [(m["role"], m["mode"]) for m in msgs] == [("user", "auto"), ("assistant", "auto")]

    def test_history_records_past_media_as_tool_calls(self, client, conv, chat, db, monkeypatch):
        """Test that history records past media as tool calls."""
        db.add_chat_message(conv["id"], "user", "draw a fox")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "Here!",
            media=[
                {
                    "id": "a",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "x.png",
                    "prompt": "a fox",
                    "params": {"aspect_ratio": "16:9"},
                },
                {
                    "id": "b",
                    "kind": "image",
                    "source": "generated",
                    "status": "error",
                    "error": "flagged",
                    "prompt": "another fox",
                },
            ],
        )
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "nice", **SETTINGS}))
        m = seen["msgs"]
        assert m[2] == {
            "role": "assistant",
            "content": "Here!",
            "tool_calls": [
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {
                        "name": "generate_image",
                        "arguments": json.dumps({"prompt": "a fox", "aspect_ratio": "16:9"}),
                    },
                },
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "generate_image", "arguments": json.dumps({"prompt": "another fox"})},
                },
            ],
        }
        assert m[3] == {
            "role": "tool",
            "tool_call_id": "call_a",
            "content": json.dumps({"ok": True, "result": chat.tools.IMAGE_TOOL_RESULT}),
        }
        assert m[4] == {
            "role": "tool",
            "tool_call_id": "call_b",
            "content": json.dumps({"ok": False, "error": "flagged"}),
        }
        assert m[5]["role"] == "user"
        assert not any("[generated image" in json.dumps(x) for x in m[1:])

    def test_history_uses_notes_when_no_tools_are_offered(self, client, conv, chat, db, monkeypatch):
        """Test that history uses notes when no tools are offered."""
        db.add_chat_message(conv["id"], "user", "draw a fox")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "Here!",
            media=[
                {
                    "id": "a",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "x.png",
                    "prompt": "a fox",
                }
            ],
        )
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "nice", "mode": "text", **SETTINGS}
            )
        )
        assert seen["msgs"][2] == {"role": "assistant", "content": "Here!\n\n[generated image: a fox]"}
        assert not any("tool_calls" in x for x in seen["msgs"])


class TestStartupResume:
    """Tests for startup resume."""

    def test_resumes_pending_videos_and_fails_orphans(self, chat, db, conv, monkeypatch):
        """Test that resumes pending videos and fails orphans."""
        started = []
        monkeypatch.setattr(chat.polling, "start_video_poller", lambda *a: started.append(a))
        m1 = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[
                {"id": "v", "kind": "video", "status": "pending", "job_id": "gen-vid-9"},
                {"id": "i", "kind": "image", "status": "pending"},
            ],
        )
        m2 = db.add_chat_message(conv["id"], "assistant", status="streaming")
        chat.startup_resume_chat()
        assert started == [(conv["id"], m1.id, "v", "gen-vid-9")]
        assert db.get_chat_message(m1.id).media[1]["status"] == "error"
        assert db.get_chat_message(m2.id).status == "error"


@pytest.mark.no_tenant
def test_gallery_lane_backfill_converts_only_pure_gallery_threads():
    """Test that gallery lane backfill converts only pure gallery threads."""
    spec = importlib.util.spec_from_file_location("m0024", "alembic/versions/0024_backfill_gallery_lane.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE chat_conversations (id TEXT, kind TEXT, current_leaf_id INTEGER)"))
        c.execute(
            sa.text(
                "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, conversation_id TEXT, parent_id INTEGER,"
                " role TEXT, mode TEXT, lane TEXT)"
            )
        )
        c.execute(sa.text("INSERT INTO chat_conversations VALUES ('g','gallery',4),('m','gallery',7),('c','chat',9)"))
        rows = [
            (1, "g", None, "user", "image"), (2, "g", 1, "assistant", "image"),
            (3, "g", 2, "user", "image"), (4, "g", 3, "assistant", "image"),
            (5, "m", None, "user", "image"), (6, "m", 5, "assistant", "image"), (7, "m", 6, "user", "text"),
            (8, "c", None, "user", "image"), (9, "c", 8, "assistant", "image"),
        ]  # fmt: skip
        for r in rows:
            c.execute(
                sa.text("INSERT INTO chat_messages VALUES (:i,:c,:p,:r,:m,NULL)"), dict(zip("icprm", r, strict=True))
            )
        assert mod.backfill(c) == 1
        lanes = dict(c.execute(sa.text("SELECT conversation_id, MAX(lane) FROM chat_messages GROUP BY 1")).all())
        assert lanes == {"g": "gallery", "m": None, "c": None}
        assert c.execute(sa.text("SELECT parent_id FROM chat_messages WHERE id = 3")).scalar() is None
        assert c.execute(sa.text("SELECT parent_id FROM chat_messages WHERE id = 4")).scalar() == 3
        assert c.execute(sa.text("SELECT current_leaf_id FROM chat_conversations WHERE id='g'")).scalar() is None


def test_alembic_migration_creates_chat_tables(tmp_path):
    """0003 adds the chat tables to a pre-chat DB, and is a no-op when.

    create_all() already made them (the app creates tables on startup).
    """

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
    """Tests for open router errors."""

    def _resp(self, status, body):

        return httpx.Response(status, json=body)

    def test_names_upstream_provider(self):
        """Test that names upstream provider."""
        body = {
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "metadata": {"provider_name": "Google AI Studio"},
            }
        }
        with pytest.raises(openrouter.OpenRouterError) as e:
            openrouter._raise_for_response(self._resp(400, body))
        assert str(e.value) == "[Google AI Studio] API key not valid. Please pass a valid API key."
        assert e.value.status == 400

    def test_appends_raw_upstream_message(self):
        """Test that appends raw upstream message."""
        body = {
            "error": {
                "message": "Provider returned error",
                "metadata": {"provider_name": "Fal", "raw": "content policy"},
            }
        }
        with pytest.raises(openrouter.OpenRouterError) as e:
            openrouter._raise_for_response(self._resp(502, body))
        assert str(e.value) == "[Fal] Provider returned error: content policy"

    def test_non_json_body(self):
        """Test that non json body."""
        with pytest.raises(openrouter.OpenRouterError) as e:
            openrouter._raise_for_response(httpx.Response(503, text="upstream down"))
        assert str(e.value) == "upstream down"


class TestEditAndLibrary:
    """Tests for edit and library."""

    def _send(self, client, conv, content, **extra):
        return _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": content, **SETTINGS, **extra}
            )
        )

    def _messages(self, client, conv):
        return client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]

    def _switch(self, client, conv, message_id):
        """Document the  switch test helper."""
        return client.post(f"/api/chat/conversations/{conv['id']}/branch", json={"message_id": message_id})

    def test_edit_starts_a_branch_and_keeps_the_old_one(self, client, conv, chat, monkeypatch):
        """Test that edit starts a branch and keeps the old one."""
        replies = iter([_text_chunks("one"), _text_chunks("two"), _text_chunks("edited reply")])
        seen = []
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.append(msgs), next(replies))[1],
        )
        first = self._send(client, conv, "first")[0]["user_message"]
        self._send(client, conv, "second")

        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/edit",
                json={"message_id": first["id"], "content": "first, but better", **SETTINGS},
            )
        )
        edited = ev[0]["user_message"]
        assert edited["id"] != first["id"]
        assert edited["content"] == "first, but better"
        assert edited["siblings"] == [first["id"], edited["id"]]
        assert [(m["role"], m["content"]) for m in self._messages(client, conv)] == [
            ("user", "first, but better"),
            ("assistant", "edited reply"),
        ]
        # the model only saw the edited prompt, not the other branch
        assert [m["role"] for m in seen[-1]] == ["system", "user"]

        old = self._switch(client, conv, first["id"]).json()["messages"]
        assert [m["content"] for m in old] == ["first", "one", "second", "two"]
        assert old[0]["siblings"] == [first["id"], edited["id"]]
        assert [m["content"] for m in self._messages(client, conv)] == ["first", "one", "second", "two"]

    def test_messages_remember_their_mode(self, client, conv, chat, monkeypatch):
        """The UI reruns an edit/retry in the message's own mode, so it must be recorded."""
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        ev = self._send(client, conv, "a dog", mode="image")
        assert ev[0]["user_message"]["mode"] == "image"
        assert ev[-1]["message"]["mode"] == "image"
        edited = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/edit",
                json={"message_id": ev[0]["user_message"]["id"], "content": "a puppy", "mode": "image", **SETTINGS},
            )
        )
        assert edited[0]["user_message"]["mode"] == "image"
        assert [m["mode"] for m in self._messages(client, conv)] == ["image", "image"]

    def test_switching_goes_to_the_newest_end_of_a_branch(self, client, conv, chat, monkeypatch):
        """Test that switching goes to the newest end of a branch."""
        replies = iter([_text_chunks("a1"), _text_chunks("a2"), _text_chunks("b1"), _text_chunks("a3")])
        seen = []
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.append(msgs), next(replies))[1],
        )
        first = self._send(client, conv, "q1")[0]["user_message"]
        self._send(client, conv, "q2")
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/edit",
                json={"message_id": first["id"], "content": "other q1", **SETTINGS},
            )
        )
        self._switch(client, conv, first["id"])
        # A new message continues the branch being shown
        self._send(client, conv, "q3")
        assert [m["content"] for m in self._messages(client, conv)] == ["q1", "a1", "q2", "a2", "q3", "a3"]
        sent = [p["text"] for m in seen[-1] if m["role"] == "user" for p in m["content"]]
        assert sent == ["q1", "q2", "q3"]

    def test_switch_rejects_message_from_another_chat(self, client, conv, db):
        """Test that switch rejects message from another chat."""
        other = client.post("/api/chat/conversations", json={}).json()
        msg = db.add_chat_message(other["id"], "user", "hi")
        assert self._switch(client, conv, msg.id).status_code == 400

    def test_switch_rejected_while_streaming(self, client, conv, db):
        """Test that switch rejected while streaming."""
        user = db.add_chat_message(conv["id"], "user", "hi")
        db.add_chat_message(conv["id"], "assistant", status="streaming")
        assert self._switch(client, conv, user.id).status_code == 409

    def test_edit_keeps_attachments(self, client, conv, chat, monkeypatch):
        """Test that edit keeps attachments."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok"))
        up = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments", files={"file": ("a.png", _png_bytes(), "image/png")}
        ).json()["file"]
        first = self._send(client, conv, "what is this", attachments=[up])[0]["user_message"]
        edited = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/edit",
                json={"message_id": first["id"], "content": "describe it", **SETTINGS},
            )
        )[0]
        assert [i["file"] for i in edited["user_message"]["media"]] == [up]

    def test_edit_keeps_generated_media_on_the_old_branch(self, client, conv, chat, monkeypatch):
        """Test that edit keeps generated media on the old branch."""
        rounds = iter(
            [
                _tool_chunks("generate_image", {"prompt": "a cat"}),
                _text_chunks("Here."),
                _text_chunks("No image this time."),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], 0.04)
        )
        ev = self._send(client, conv, "draw a cat")
        user_id = ev[0]["user_message"]["id"]
        img = ev[-1]["message"]["media"][0]

        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/edit",
                json={"message_id": user_id, "content": "just say hi", **SETTINGS},
            )
        )
        assert all(not m["media"] for m in self._messages(client, conv))
        lib = client.get("/api/chat/library").json()["items"]
        assert [(i["id"], i["attached"]) for i in lib] == [(img["id"], True)]
        old = self._switch(client, conv, user_id).json()["messages"]
        assert old[1]["media"][0]["id"] == img["id"]

    def test_retry_adds_a_sibling_reply(self, client, conv, chat, monkeypatch):
        """Test that retry adds a sibling reply."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: pytest.fail("no LLM in image mode"))
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        first = self._send(client, conv, "a dog", mode="image")[-1]["message"]
        second = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/retry",
                json={"message_id": first["id"], "mode": "image", **SETTINGS},
            )
        )[-1]["message"]
        assert second["siblings"] == [first["id"], second["id"]]
        lib = client.get("/api/chat/library").json()["items"]
        assert {(i["id"], i["attached"]) for i in lib} == {
            (first["media"][0]["id"], True),
            (second["media"][0]["id"], True),
        }
        shown = self._switch(client, conv, first["id"]).json()["messages"]
        assert [m["id"] for m in shown][-1] == first["id"]

    def test_uploads_are_not_kept_in_library(self, client, conv, chat, db, monkeypatch):
        """Test that uploads are not kept in library."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok"))
        up = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments", files={"file": ("a.png", _png_bytes(), "image/png")}
        ).json()["file"]
        first = self._send(client, conv, "hi")[0]["user_message"]
        self._send(client, conv, "look", attachments=[up])
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/edit",
                json={"message_id": first["id"], "content": "hello", **SETTINGS},
            )
        )
        assert client.get("/api/chat/library").json()["items"] == []

    def test_edit_rejected_while_streaming(self, client, conv, db):
        """Test that edit rejected while streaming."""
        user = db.add_chat_message(conv["id"], "user", "hi")
        db.add_chat_message(conv["id"], "assistant", status="streaming")
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/edit", json={"message_id": user.id, "content": "x", **SETTINGS}
        )
        assert r.status_code == 409

    def test_edit_rejects_assistant_message(self, client, conv, db):
        """Test that edit rejects assistant message."""
        a = db.add_chat_message(conv["id"], "assistant", "hi")
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/edit", json={"message_id": a.id, "content": "x", **SETTINGS}
        )
        assert r.status_code == 400

    def test_pending_video_finishes_into_library(self, chat, db, conv, monkeypatch):
        """Test that pending video finishes into library."""
        db.add_chat_message(conv["id"], "user", "waves")
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "v1", "kind": "video", "source": "generated", "status": "pending", "job_id": "gen-vid-1"}],
        )
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        assert db.get_chat_message(msg.id) is None
        monkeypatch.setattr(openrouter, "get_video", lambda j: {"status": "completed", "usage": {"cost": 0.3}})
        monkeypatch.setattr(openrouter, "download_video", lambda j, dest, index=0: dest.write_bytes(b"mp4"))
        chat.polling._poll_video(conv["id"], msg.id, "v1", "gen-vid-1")
        item = db.get_chat_library_item("v1").item
        assert item["status"] == "done"
        assert item["file"].endswith(".mp4")
        assert item["cost"] == 0.3

    def test_startup_resumes_library_videos(self, chat, db, conv, monkeypatch):
        """Test that startup resumes library videos."""
        started = []
        monkeypatch.setattr(chat.polling, "start_video_poller", lambda *a: started.append(a))
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "v2", "kind": "video", "source": "generated", "status": "pending", "job_id": "gen-vid-2"}],
        )
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        chat.startup_resume_chat()
        assert started == [(conv["id"], 0, "v2", "gen-vid-2")]

    def test_delete_library_item(self, client, conv, chat, db):
        """Test that delete library item."""
        f = chat.conversation_dir(conv["id"]) / "img_x.png"
        f.write_bytes(b"png")
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "i1", "kind": "image", "source": "generated", "status": "done", "file": "img_x.png"}],
        )
        assert client.delete("/api/chat/library/i1").status_code == 404  # still attached
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        assert client.delete("/api/chat/library/i1").status_code == 200
        assert not f.exists()
        assert client.get("/api/chat/library").json()["items"] == []

    def test_deleting_conversation_removes_its_library_items(self, client, conv, db):
        """Test that deleting conversation removes its library items."""
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "i2", "kind": "image", "source": "generated", "status": "done", "file": "x.png"}],
        )
        db.truncate_chat(conv["id"], after_id=msg.id - 1)
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert db.get_chat_library_item("i2") is None

    def test_deleting_conversation_can_keep_its_files(self, client, conv, chat):
        """Test that deleting conversation can keep its files."""
        folder = chat.conversation_dir(conv["id"])
        (folder / "keep.png").write_bytes(b"x")
        client.delete(f"/api/chat/conversations/{conv['id']}?delete_media=false")
        assert (folder / "keep.png").exists()

    def test_deleting_conversation_deletes_files_by_default(self, client, conv, chat):
        """Test that deleting conversation deletes files by default."""
        folder = chat.conversation_dir(conv["id"])
        (folder / "gone.png").write_bytes(b"x")
        client.delete(f"/api/chat/conversations/{conv['id']}")
        for _ in range(50):  # the folder is removed on a background thread
            if not folder.exists():
                break
            time.sleep(0.05)
        assert not folder.exists()

    def test_deleting_an_exchange_can_delete_its_media(self, client, conv, chat, db):
        """Test that deleting an exchange can delete its media."""
        user = db.add_chat_message(conv["id"], "user", "draw")
        (chat.conversation_dir(conv["id"]) / "img_x.png").write_bytes(b"x")
        db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "m1", "kind": "image", "source": "generated", "status": "done", "file": "img_x.png"}],
        )
        client.delete(f"/api/chat/messages/{user.id}?delete_media=true")
        assert not (chat.conversation_dir(conv["id"]) / "img_x.png").exists()
        assert db.get_chat_library_item("m1") is None


def test_resend_same_prompt_gets_fresh_reply(client, conv, chat, monkeypatch):
    """Retry on a prompt = edit with unchanged text: a new branch with a fresh reply."""
    replies = iter([_text_chunks("a"), _text_chunks("b"), _text_chunks("c")])
    monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
    first = _events(
        client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "tell me a joke", **SETTINGS})
    )[0]["user_message"]
    _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "another", **SETTINGS}))
    _events(
        client.post(
            f"/api/chat/conversations/{conv['id']}/edit",
            json={"message_id": first["id"], "content": "tell me a joke", **SETTINGS},
        )
    )
    msgs = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "tell me a joke"), ("assistant", "c")]


class TestModerationAndRegenerate:
    """Tests for moderation and regenerate."""

    def _blocked(self, chat, status=403, msg="Your input was flagged by moderation"):
        def boom(*a, **k):
            raise openrouter.OpenRouterError(msg, status)

        return boom

    def test_moderation_block_ends_turn_without_retry(self, client, conv, chat, monkeypatch):
        """Test that moderation block ends turn without retry."""
        rounds = iter([_tool_chunks("generate_image", {"prompt": "risky", "aspect_ratio": "9:16"}, text="Here goes.")])
        calls = []
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: (calls.append(1), next(rounds))[1])
        monkeypatch.setattr(openrouter, "generate_image", self._blocked(chat))
        ev = _events(
            client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "draw it", **SETTINGS})
        )
        assert len(calls) == 1  # no follow-up round, so no silent re-attempt
        done = ev[-1]["message"]
        assert done["content"] == "Here goes."
        assert done["status"] == "done"
        item = done["media"][0]
        assert item["status"] == "error"
        assert item["moderated"] is True
        # The model's 9:16 is ignored — ratio is the composer's, left on auto here
        assert item["params"] == {"aspect_ratio": None, "resolution": None, "refs": []}

    @pytest.mark.parametrize(
        ("status", "msg", "expected"),
        [
            (403, "Forbidden", True),
            (400, "[Seed] Request rejected: content policy violation", True),
            (400, "Provider returned error: prompt contains sensitive content", True),
            (502, "Upstream timed out", False),
            (400, "Invalid aspect_ratio", False),
        ],
    )
    def test_moderation_detection(self, chat, status, msg, expected):
        """Test that moderation detection."""
        assert chat.generation.is_moderation_error(openrouter.OpenRouterError(msg, status)) is expected

    def _failed_image(self, db, conv, **extra):
        db.add_chat_message(conv["id"], "user", "draw")
        return db.add_chat_message(
            conv["id"],
            "assistant",
            "Here goes.",
            model="t/model",
            media=[
                {
                    "id": "m1",
                    "kind": "image",
                    "source": "generated",
                    "status": "error",
                    "error": "flagged",
                    "moderated": True,
                    "prompt": "a lighthouse",
                    "model": "i/model",
                    "params": {"aspect_ratio": "16:9", "resolution": None, "refs": []},
                    **extra,
                }
            ],
        )

    def _run_worker_inline(self, chat, monkeypatch):
        class Inline:
            def __init__(self, target, args, **kw):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        monkeypatch.setattr(threading, "Thread", Inline)

    def test_retry_same_model(self, client, conv, chat, db, monkeypatch):
        """Test that retry same model."""
        msg = self._failed_image(db, conv)
        self._run_worker_inline(chat, monkeypatch)
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (
                got.update(model=model, prompt=prompt, **kw),
                ([(_png_bytes(), "image/png")], 0.02),
            )[1],
        )
        r = client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        assert r.status_code == 200
        assert got["model"] == "i/model"
        assert got["prompt"] == "a lighthouse"
        assert got["aspect_ratio"] == "16:9"
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "done"
        assert item["file"].startswith("img_")
        assert item["moderated"] is False
        assert db.get_chat_message(msg.id).cost == 0.02

    def test_retry_with_different_model(self, client, conv, chat, db, monkeypatch):
        """Test that retry with different model."""
        msg = self._failed_image(db, conv)
        self._run_worker_inline(chat, monkeypatch)
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(model=model), ([(_png_bytes(), "image/png")], None))[1],
        )
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={"model": "other/model"})
        assert got["model"] == "other/model"
        assert db.get_chat_message(msg.id).media[0]["model"] == "other/model"

    def test_retry_blocked_again_stays_failed(self, client, conv, chat, db, monkeypatch):
        """Test that retry blocked again stays failed."""
        msg = self._failed_image(db, conv)
        self._run_worker_inline(chat, monkeypatch)
        monkeypatch.setattr(openrouter, "generate_image", self._blocked(chat))
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "error"
        assert item["moderated"] is True

    def test_retry_video_refits_params_for_new_model(self, client, conv, chat, db, monkeypatch):
        """Test that retry video refits params for new model."""
        db.add_chat_message(conv["id"], "user", "waves")
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[
                {
                    "id": "v1",
                    "kind": "video",
                    "source": "generated",
                    "status": "error",
                    "error": "flagged",
                    "prompt": "waves",
                    "model": "v/old",
                    "params": {"duration": 7, "aspect_ratio": "16:9", "resolution": None, "first_frame": None},
                }
            ],
        )
        chat.catalogue.seed_models(
            {
                "text": [],
                "image": [],
                "video": [{"id": "v/new", "durations": [5, 10], "aspect_ratios": ["16:9"], "resolutions": []}],
            },
        )
        self._run_worker_inline(chat, monkeypatch)
        started = []
        monkeypatch.setattr(chat.polling, "start_video_poller", lambda *a: started.append(a))
        got = {}
        monkeypatch.setattr(
            openrouter,
            "submit_video",
            lambda model, prompt, **kw: (got.update(model=model, **kw), {"id": "gen-vid-9"})[1],
        )
        client.post(f"/api/chat/messages/{msg.id}/media/v1/regenerate", json={"model": "v/new"})
        assert got["model"] == "v/new"
        assert got["duration"] == 5
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "pending"
        assert item["job_id"] == "gen-vid-9"
        assert started == [(conv["id"], msg.id, "v1", "gen-vid-9")]

    def test_finished_item_is_rerolled_as_a_new_item_beside_it(self, client, conv, db, chat, monkeypatch):
        """Test that finished item is rerolled as a new item beside it."""
        msg = self._failed_image(db, conv, status="done", file="x.png")
        self._run_worker_inline(chat, monkeypatch)
        monkeypatch.setattr(chat.routes_turns, "_regenerate_worker", lambda *a: None)
        r = client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        assert r.status_code == 200
        old, new = db.get_chat_message(msg.id).media
        assert old["file"] == "x.png"
        assert old["status"] == "done"
        assert new["id"] != "m1"
        assert new["status"] == "pending"
        assert not new.get("file")
        assert client.post(f"/api/chat/messages/{msg.id}/media/nope/regenerate", json={}).status_code == 404


class TestContext:
    """Tests for context."""

    def _capture(self, chat, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        return seen

    def _img(self, chat, conv, name):
        (chat.conversation_dir(conv["id"]) / name).write_bytes(_png_bytes())
        return {"id": name, "kind": "image", "source": "generated", "status": "done", "file": name, "prompt": name}

    def test_generated_image_is_sent_as_pixels_with_next_user_message(self, client, conv, chat, db, monkeypatch):
        """Test that generated image is sent as pixels with next user message."""
        db.add_chat_message(conv["id"], "user", "draw Linh")
        db.add_chat_message(conv["id"], "assistant", "Here she is.", media=[self._img(chat, conv, "g1.png")])
        seen = self._capture(chat, monkeypatch)
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "what is she wearing?", **SETTINGS}
            )
        )
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

    def _pixels_sent(self, client, conv, chat, db, monkeypatch, **settings):
        for i in range(8):
            db.add_chat_message(conv["id"], "user", f"draw {i}")
            db.add_chat_message(conv["id"], "assistant", "ok", media=[self._img(chat, conv, f"g{i}.png")])
        seen = self._capture(chat, monkeypatch)
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "next", **SETTINGS, **settings}
            )
        )
        return sum(
            1 for m in seen["msgs"] if isinstance(m["content"], list) for p in m["content"] if p["type"] == "image_url"
        )

    def test_only_most_recent_images_as_pixels(self, client, conv, chat, db, monkeypatch):
        """Test that only most recent images as pixels."""
        assert self._pixels_sent(client, conv, chat, db, monkeypatch) == chat.constants.DEFAULT_IMAGE_LIMIT == 6

    @pytest.mark.parametrize(("limit", "expected"), [(2, 2), (0, 0), (None, 8)])
    def test_image_slider_sets_how_many(self, client, conv, chat, db, monkeypatch, limit, expected):
        """Test that image slider sets how many."""
        assert self._pixels_sent(client, conv, chat, db, monkeypatch, image_limit=limit) == expected

    def test_no_pixels_for_text_only_models(self, client, conv, chat, db, monkeypatch):
        """Test that no pixels for text only models."""
        chat.catalogue.seed_models(
            {
                "image": [],
                "video": [],
                "text": [{"id": "t/model", "supports_tools": True, "input_modalities": ["text"]}],
            },
        )
        db.add_chat_message(conv["id"], "user", "draw")
        db.add_chat_message(conv["id"], "assistant", "ok", media=[self._img(chat, conv, "g.png")])
        seen = self._capture(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "next", **SETTINGS}))
        assert seen["msgs"][-1] == {"role": "user", "content": [{"type": "text", "text": "next"}]}

    def test_history_limit_keeps_recent_messages_starting_on_user(self, client, conv, chat, db, monkeypatch):
        """Test that history limit keeps recent messages starting on user."""
        for i in range(5):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        seen = self._capture(chat, monkeypatch)
        # limit 4 of 11 history messages → [a3?, q4, a4, now] trimmed to start on a user message
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "now", "history_limit": 4, **SETTINGS},
            )
        )
        body = seen["msgs"][1:]
        assert [m["role"] for m in body] == ["user", "assistant", "user"]
        assert body[0]["content"][0]["text"] == "q4"

    def test_no_limit_sends_everything(self, client, conv, chat, db, monkeypatch):
        """Test that no limit sends everything."""
        for i in range(3):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        seen = self._capture(chat, monkeypatch)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "now", **SETTINGS}))
        assert len(seen["msgs"]) == 1 + 7
        assert "omitted" not in seen["msgs"][0]["content"]

    def test_invalid_limit_rejected(self, client, conv):
        """Test that invalid limit rejected."""
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/messages", json={"content": "x", "history_limit": 0, **SETTINGS}
        )
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

        while True:
            _t.sleep(0.02)
            yield ": OPENROUTER PROCESSING"

    def test_deadline_breaks_a_keepalive_only_stream(self, chat, monkeypatch):
        """Test that deadline breaks a keepalive only stream."""
        monkeypatch.setattr(openrouter._client, "stream", lambda *a, **k: self._FakeStream(self._keepalives()))
        with pytest.raises(openrouter.OpenRouterError) as e:
            list(openrouter.stream_chat("m", [], max_seconds=0.2))
        assert e.value.status == 504

    def test_stop_is_noticed_during_keepalives(self, chat, monkeypatch):
        """Test that stop is noticed during keepalives."""
        monkeypatch.setattr(openrouter._client, "stream", lambda *a, **k: self._FakeStream(self._keepalives()))
        stop = threading.Event()
        threading.Timer(0.1, stop.set).start()
        t0 = _t.monotonic()
        assert list(openrouter.stream_chat("m", [], should_stop=stop.is_set)) == []
        assert _t.monotonic() - t0 < 2


class TestConsistencyReferences:
    """Tests for consistency references."""

    def _prior_images(self, chat, db, conv, n):
        db.add_chat_message(conv["id"], "user", "story with a photo")
        for i in range(n):
            f = f"g{i}.png"
            (chat.conversation_dir(conv["id"]) / f).write_bytes(_png_bytes(color=(i * 40, 0, 0)))
            db.add_chat_message(
                conv["id"],
                "assistant",
                f"scene {i}",
                media=[
                    {
                        "id": f"g{i}",
                        "kind": "image",
                        "source": "generated",
                        "status": "done",
                        "file": f,
                        "prompt": f"p{i}",
                    }
                ],
            )

    def _run(self, client, conv, chat, monkeypatch, tool_args):
        replies = iter([_tool_chunks("generate_image", tool_args, text="Next scene."), _text_chunks("Done.")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "continue the story", **SETTINGS}
            )
        )
        return got, ev[-1]["message"]["media"][0]

    def test_no_references_unless_the_model_asks(self, client, conv, chat, db, monkeypatch):
        """Test that no references unless the model asks."""
        self._prior_images(chat, db, conv, 1)
        got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "the same woman, now turned around"})
        assert got.get("input_images") is None
        assert item["params"]["refs"] == []

    def test_model_opts_in_and_prompt_is_passed_verbatim(self, client, conv, chat, db, monkeypatch):
        """Test that model opts in and prompt is passed verbatim."""
        self._prior_images(chat, db, conv, 1)
        replies = iter(
            [
                _tool_chunks(
                    "generate_image", {"prompt": "exactly what the model wrote", "keep_consistent": True}, text="Next."
                ),
                _text_chunks("Done."),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "continue", **SETTINGS}))
        assert got["prompt"] == "exactly what the model wrote"
        assert len(got["input_images"]) == 1

    def test_uses_only_the_most_recent_two(self, client, conv, chat, db, monkeypatch):
        """Test that uses only the most recent two."""
        self._prior_images(chat, db, conv, 3)
        _got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "scene 4", "keep_consistent": True})
        assert item["params"]["refs"] == ["g2.png", "g1.png"]

    def test_first_image_in_chat_has_no_refs(self, client, conv, chat, db, monkeypatch):
        """Test that first image in chat has no refs."""
        got, _item = self._run(client, conv, chat, monkeypatch, {"prompt": "Linh", "keep_consistent": True})
        assert got.get("input_images") is None

    def test_skipped_for_image_models_without_reference_support(self, client, conv, chat, db, monkeypatch):
        """Test that skipped for image models without reference support."""
        chat.catalogue.seed_models(
            {"text": [], "video": [], "image": [{"id": "i/model", "input_modalities": ["text"]}]}
        )
        self._prior_images(chat, db, conv, 1)
        got, _item = self._run(client, conv, chat, monkeypatch, {"prompt": "next", "keep_consistent": True})
        assert got.get("input_images") is None

    def test_edit_source_comes_first(self, client, conv, chat, db, monkeypatch):
        """Test that edit source comes first."""
        self._prior_images(chat, db, conv, 2)
        _got, item = self._run(
            client,
            conv,
            chat,
            monkeypatch,
            {"prompt": "make it night", "source_image": "latest", "keep_consistent": True},
        )
        assert item["params"]["refs"] == ["g1.png", "g0.png"]

    def test_edit_alone_sends_just_the_source(self, client, conv, chat, db, monkeypatch):
        """Test that edit alone sends just the source."""
        self._prior_images(chat, db, conv, 2)
        _got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "make it night", "source_image": "latest"})
        assert item["params"]["refs"] == ["g1.png"]

    def _pin(self, client, db, conv, media_id, pinned=True):
        msg = next(m for m in db.get_chat_messages(conv["id"]) if any(i["id"] == media_id for i in m.media))
        r = client.post(f"/api/chat/messages/{msg.id}/media/{media_id}/pin", json={"pinned": pinned})
        assert r.status_code == 200
        return r.json()

    def test_pinned_images_are_sent_without_the_model_asking(self, client, conv, chat, db, monkeypatch):
        """Test that pinned images are sent without the model asking."""
        self._prior_images(chat, db, conv, 3)
        out = self._pin(client, db, conv, "g0")
        assert out["media"][0]["pinned"] is True
        got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "next scene"})
        assert item["params"]["refs"] == ["g0.png"]
        assert len(got["input_images"]) == 1

    def test_order_is_edit_source_then_pins_then_recent_picks(self, client, conv, chat, db, monkeypatch):
        """Also the priority when a model takes fewer images (Venice edit models keep the first N)."""
        self._prior_images(chat, db, conv, 3)
        self._pin(client, db, conv, "g0")
        _got, item = self._run(
            client,
            conv,
            chat,
            monkeypatch,
            {"prompt": "make it night", "source_image": "latest", "keep_consistent": True},
        )
        assert item["params"]["refs"] == ["g2.png", "g0.png", "g1.png"]
        assert item["params"]["ref_args"] == {"source_image": "latest", "keep_consistent": True}

    def test_unpinned_images_stop_being_sent(self, client, conv, chat, db, monkeypatch):
        """Test that unpinned images stop being sent."""
        self._prior_images(chat, db, conv, 2)
        self._pin(client, db, conv, "g0")
        self._pin(client, db, conv, "g0", pinned=False)
        _got, item = self._run(client, conv, chat, monkeypatch, {"prompt": "next"})
        assert item["params"]["refs"] == []

    def test_pinned_upload_is_a_reference_in_image_mode(self, client, conv, chat, db, monkeypatch):
        """Test that pinned upload is a reference in image mode."""
        (chat.conversation_dir(conv["id"]) / "u.png").write_bytes(_png_bytes())
        db.add_chat_message(
            conv["id"],
            "user",
            "this is Linh",
            media=[{"id": "u1", "kind": "image", "source": "upload", "status": "done", "file": "u.png"}],
        )
        db.add_chat_message(conv["id"], "assistant", "Nice photo.")
        self._pin(client, db, conv, "u1")
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "Linh at the beach", **SETTINGS, "mode": "image"},
            )
        )
        assert ev[-1]["message"]["media"][0]["params"]["refs"] == ["u.png"]

    def test_pins_ignored_for_image_models_without_reference_support(self, client, conv, chat, db, monkeypatch):
        """Test that pins ignored for image models without reference support."""
        chat.catalogue.seed_models(
            {"text": [], "video": [], "image": [{"id": "i/model", "input_modalities": ["text"]}]}
        )
        self._prior_images(chat, db, conv, 1)
        self._pin(client, db, conv, "g0")
        got, _item = self._run(client, conv, chat, monkeypatch, {"prompt": "next"})
        assert got.get("input_images") is None

    def test_only_finished_images_can_be_pinned(self, client, conv, chat, db):
        """Test that only finished images can be pinned."""
        db.add_chat_message(conv["id"], "user", "go")
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            media=[
                {"id": "v", "kind": "video", "source": "generated", "status": "done", "file": "v.mp4", "prompt": "p"},
                {"id": "e", "kind": "image", "source": "generated", "status": "error", "prompt": "p"},
            ],
        )
        for mid in ("v", "e", "nope"):
            assert client.post(f"/api/chat/messages/{msg.id}/media/{mid}/pin", json={"pinned": True}).status_code == 404

    def test_history_replays_reference_choices(self, client, conv, chat, db, monkeypatch):
        """Test that history replays reference choices."""
        db.add_chat_message(conv["id"], "user", "draw Linh again")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "Here!",
            media=[
                {
                    "id": "a",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "x.png",
                    "prompt": "Linh",
                    "params": {"refs": ["p.png", "q.png"], "ref_args": {"keep_consistent": True}},
                }
            ],
        )
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "nice", **SETTINGS}))
        call = seen["msgs"][2]["tool_calls"][0]
        assert json.loads(call["function"]["arguments"]) == {"prompt": "Linh", "keep_consistent": True}
        assert json.loads(seen["msgs"][3]["content"]) == {
            "ok": True,
            "result": chat.tools.IMAGE_TOOL_RESULT,
            "reference_images": 2,
        }


class TestModelDecides:
    """The app never adds instructions or extra calls to steer the model."""

    def test_no_extra_call_when_model_skips_the_tool(self, client, conv, chat, monkeypatch):
        """Test that no extra call when model skips the tool."""
        calls = []
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda *a, **k: (calls.append(k), _text_chunks("A story, and here's the photo."))[1],
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "write a story and create an image of the scene", **SETTINGS},
            )
        )
        assert len(calls) == 1
        assert ev[-1]["message"]["content"] == "A story, and here's the photo."
        assert ev[-1]["message"]["media"] == []

    def test_system_prompt_is_static(self, client, conv, chat, db, monkeypatch):
        """Test that system prompt is static."""
        for i in range(4):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        chat.catalogue.seed_models(
            {
                "image": [],
                "video": [],
                "text": [{"id": "t/model", "supports_tools": False, "input_modalities": ["text"]}],
            },
        )
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", "history_limit": 3, **SETTINGS}
            )
        )

        today = datetime.now().astimezone().strftime("%A %d %B %Y")
        assert seen["msgs"][0]["content"] == chat.tools.SYSTEM_PROMPT.format(today=today)


class TestConversationalImageModels:
    """Gemini-style image models get the conversation, not a lone prompt."""

    CATALOGUE: ClassVar = {
        "text": [],
        "video": [],
        "image": [{"id": "i/model", "input_modalities": ["text", "image"], "conversational": True}],
    }

    def _setup(self, chat, db, conv, with_prior_image=True):
        chat.catalogue.seed_models(self.CATALOGUE)
        db.add_chat_message(conv["id"], "user", "write a story about Linh, with a photo")
        media = []
        if with_prior_image:
            (chat.conversation_dir(conv["id"]) / "g0.png").write_bytes(_png_bytes())
            media = [
                {
                    "id": "g0",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "g0.png",
                    "prompt": "Linh in the gym",
                }
            ]
        db.add_chat_message(conv["id"], "assistant", "Linh lifted.", media=media)

    def _fake_chat_image(self, chat, monkeypatch):
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image_chat",
            lambda model, messages, **kw: (
                got.update(model=model, messages=messages, **kw),
                ([(_png_bytes(), "image/png")], 0.04),
            )[1],
        )
        monkeypatch.setattr(openrouter, "generate_image", lambda *a, **k: pytest.fail("Images API not used"))
        return got

    def test_auto_mode_sends_conversation_reply_and_prompt(self, client, conv, chat, db, monkeypatch):
        """Test that auto mode sends conversation reply and prompt."""
        self._setup(chat, db, conv)
        replies = iter(
            [
                _tool_chunks(
                    "generate_image", {"prompt": "Linh turns around", "aspect_ratio": "3:4"}, text="She turned around."
                ),
                _text_chunks("Done."),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._fake_chat_image(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "can I see your muscles? (continue, with an image)", **SETTINGS},
            )
        )
        msgs = got["messages"]
        # The model's 3:4 pick is ignored; the composer (on auto) governs the ratio
        assert got["model"] == "i/model"
        assert got["aspect_ratio"] is None
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]
        assert msgs[0]["content"][0]["text"] == "write a story about Linh, with a photo"
        # the earlier generated image is in the context as pixels
        assert any(p["type"] == "image_url" for p in msgs[2]["content"])
        assert msgs[3] == {"role": "assistant", "content": "She turned around."}  # this reply so far
        assert msgs[4] == {"role": "user", "content": [{"type": "text", "text": "Linh turns around"}]}  # verbatim
        assert all(m["role"] != "system" for m in msgs)
        item = ev[-1]["message"]["media"][0]
        assert item["status"] == "done"
        assert item["params"]["context"] is True

    def test_image_mode_sends_conversation_ending_with_users_message(self, client, conv, chat, db, monkeypatch):
        """Test that image mode sends conversation ending with users message."""
        self._setup(chat, db, conv)
        got = self._fake_chat_image(chat, monkeypatch)
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "Linh and Marcus high-five", "mode": "image", **SETTINGS},
            )
        )
        last = got["messages"][-1]
        assert last["role"] == "user"
        assert last["content"][-1] == {"type": "text", "text": "Linh and Marcus high-five"}
        assert len(got["messages"]) == 3

    def test_memory_slider_applies_to_image_context(self, client, conv, chat, db, monkeypatch):
        """Test that memory slider applies to image context."""
        self._setup(chat, db, conv, with_prior_image=False)
        for i in range(3):
            db.add_chat_message(conv["id"], "user", f"q{i}")
            db.add_chat_message(conv["id"], "assistant", f"a{i}")
        got = self._fake_chat_image(chat, monkeypatch)
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "draw it", "mode": "image", "history_limit": 3, **SETTINGS},
            )
        )
        assert [m["role"] for m in got["messages"]] == ["user", "assistant", "user"]

    def test_non_conversational_models_still_use_images_api(self, client, conv, chat, db, monkeypatch):
        """Test that non conversational models still use images api."""
        chat.catalogue.seed_models(
            {
                "text": [],
                "video": [],
                "image": [{"id": "i/model", "input_modalities": ["text", "image"], "conversational": False}],
            },
        )
        monkeypatch.setattr(openrouter, "generate_image_chat", lambda *a, **k: pytest.fail("chat path not used"))
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "a dog", "mode": "image", **SETTINGS}
            )
        )
        assert "context" not in ev[-1]["message"]["media"][0]["params"]

    def test_retry_of_failed_image_rebuilds_context(self, client, conv, chat, db, monkeypatch):
        """Test that retry of failed image rebuilds context."""
        chat.catalogue.seed_models(self.CATALOGUE)
        db.add_chat_message(conv["id"], "user", "story please, with a photo")
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            "Linh lifted.",
            media=[
                {
                    "id": "m1",
                    "kind": "image",
                    "source": "generated",
                    "status": "error",
                    "error": "timeout",
                    "prompt": "Linh lifting",
                    "model": "i/model",
                    "params": {"aspect_ratio": None, "resolution": None, "refs": [], "context": True, "direct": False},
                }
            ],
        )

        class Inline:
            def __init__(self, target, args, **kw):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        monkeypatch.setattr(threading, "Thread", Inline)
        got = self._fake_chat_image(chat, monkeypatch)
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        assert [m["role"] for m in got["messages"]] == ["user", "assistant", "user"]
        assert got["messages"][1] == {"role": "assistant", "content": "Linh lifted."}
        assert got["messages"][2]["content"][0]["text"] == "Linh lifting"
        assert db.get_chat_message(msg.id).media[0]["status"] == "done"


class TestOpenRouterChatImages:
    """Tests for open router chat images."""

    def _resp(self, body):

        return httpx.Response(200, json=body)

    def test_parses_data_url_images_and_sends_modalities(self, chat, monkeypatch):
        """Test that parses data url images and sends modalities."""
        sent = {}
        b64 = base64.b64encode(_png_bytes()).decode()
        monkeypatch.setattr(
            openrouter._client,
            "post",
            lambda url, **kw: (
                sent.update(kw["json"]),
                self._resp(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "Here",
                                    "images": [
                                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                                    ],
                                }
                            }
                        ],
                        "usage": {"cost": 0.039},
                    }
                ),
            )[1],
        )
        images, cost = openrouter.generate_image_chat("g/img", [{"role": "user", "content": "hi"}], aspect_ratio="16:9")
        assert sent["modalities"] == ["image", "text"]
        assert sent["image_config"] == {"aspect_ratio": "16:9"}
        assert images == [(_png_bytes(), "image/png")]
        assert cost == 0.039

    def test_no_image_reports_models_text(self, chat, monkeypatch):
        """Test that no image reports models text."""
        monkeypatch.setattr(
            openrouter._client,
            "post",
            lambda url, **kw: self._resp({"choices": [{"message": {"content": "I can't draw that."}}]}),
        )
        with pytest.raises(openrouter.OpenRouterError) as e:
            openrouter.generate_image_chat("g/img", [])
        assert "I can't draw that." in str(e.value)

    def test_catalogue_marks_and_adds_conversational_models(self, chat, monkeypatch):
        """Test that catalogue marks and adds conversational models."""

        def fake_get(path, params=None):
            if path == "/images/models":
                return {"data": [{"id": "google/gem-img", "name": "Gem"}, {"id": "seed/dream", "name": "Seed"}]}
            return {
                "data": [
                    {"id": "google/gem-img", "architecture": {"output_modalities": ["image", "text"]}},
                    {
                        "id": "openai/gpt-img",
                        "name": "GPT Image",
                        "architecture": {"output_modalities": ["image", "text"], "input_modalities": ["text", "image"]},
                    },
                    {"id": "seed/dream", "architecture": {"output_modalities": ["image"]}},
                ]
            }

        monkeypatch.setattr(openrouter, "_get", fake_get)
        models = {m["id"]: m for m in openrouter.list_image_models()}
        assert models["google/gem-img"]["conversational"] is True
        assert models["seed/dream"]["conversational"] is False
        assert models["openai/gpt-img"]["conversational"] is True
        assert models["openai/gpt-img"]["name"] == "GPT Image"


class TestFollowUpRounds:
    """Tests for follow up rounds."""

    def _run(self, client, conv, chat, monkeypatch, rounds):
        calls = []
        rounds = iter(rounds)
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (calls.append(tools), next(rounds))[1],
        )
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "story and a picture", **SETTINGS}
            )
        )
        return calls, ev[-1]["message"]

    def test_tool_first_gets_one_text_only_follow_up(self, client, conv, chat, monkeypatch):
        """Test that tool first gets one text only follow up."""
        calls, done = self._run(
            client,
            conv,
            chat,
            monkeypatch,
            [
                _tool_chunks("generate_image", {"prompt": "scene"}),  # no text yet
                _text_chunks("Here is the story."),
            ],
        )
        assert len(calls) == 2
        assert calls[0]
        assert calls[1] is None
        assert done["content"] == "Here is the story."
        assert len(done["media"]) == 1

    def test_no_second_image_even_if_the_model_tries(self, client, conv, chat, monkeypatch):
        # With tools withheld, a model can't call generate_image again
        """Test that no second image even if the model tries."""
        _calls, done = self._run(
            client,
            conv,
            chat,
            monkeypatch,
            [
                _tool_chunks("generate_image", {"prompt": "scene"}),
                _text_chunks("Story."),
            ],
        )
        assert len(done["media"]) == 1

    def test_non_moderation_failure_keeps_tools_for_a_retry(self, client, conv, chat, monkeypatch):
        """Test that non moderation failure keeps tools for a retry."""
        attempts = []

        def image(model, prompt, **kw):
            attempts.append(prompt)
            if len(attempts) == 1:
                raise openrouter.OpenRouterError("Upstream timed out", 502)  # noqa: TRY003
            return [(_png_bytes(), "image/png")], None

        rounds = iter(
            [
                _tool_chunks("generate_image", {"prompt": "first"}, text="Story."),
                _tool_chunks("generate_image", {"prompt": "second"}, text="Trying again."),
            ]
        )
        calls = []
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (calls.append(tools), next(rounds))[1],
        )
        monkeypatch.setattr(openrouter, "generate_image", image)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "story and a picture", **SETTINGS}
            )
        )
        assert len(calls) == 2
        assert calls[1]
        assert attempts == ["first", "second"]
        assert [m["status"] for m in ev[-1]["message"]["media"]] == ["error", "done"]


def test_attribution_is_generic_and_hidden(chat, monkeypatch):
    """The app is named but not linkable: generic localhost URL, hidden from public rankings."""
    monkeypatch.setenv("OPENROUTER_REFERER", "https://example.com/should-be-ignored")
    assert openrouter._headers() == {
        "Authorization": "Bearer sk-test",
        "HTTP-Referer": "http://localhost",
        "X-OpenRouter-Title": "Pollo Chat",
        "X-OpenRouter-App-Visibility": "hidden",
    }


class TestCustomInstructions:
    """Tests for custom instructions."""

    def test_snippet_crud(self, client):
        """Test that snippet crud."""
        a = client.post("/api/chat/instructions", json={"name": "Terse", "content": "Be brief."}).json()
        b = client.post("/api/chat/instructions", json={"name": "Story", "content": "Write vividly."}).json()
        assert {i["name"] for i in client.get("/api/chat/instructions").json()["instructions"]} == {"Terse", "Story"}
        r = client.put(f"/api/chat/instructions/{a['id']}", json={"name": "Terse", "content": "Very brief."})
        assert r.json()["content"] == "Very brief."
        assert client.delete(f"/api/chat/instructions/{b['id']}").status_code == 200
        assert [i["name"] for i in client.get("/api/chat/instructions").json()["instructions"]] == ["Terse"]
        assert client.post("/api/chat/instructions", json={"name": "", "content": "x"}).status_code == 422

    def test_group_crud(self, client):
        """Test that group crud."""
        a = client.post("/api/chat/instructions", json={"name": "Tone", "content": "Be warm."}).json()
        b = client.post("/api/chat/instructions", json={"name": "Format", "content": "Use markdown."}).json()
        g = client.post(
            "/api/chat/instruction-groups", json={"name": "Starter", "snippet_ids": [a["id"], b["id"]]}
        ).json()
        data = client.get("/api/chat/instructions").json()
        assert [x["name"] for x in data["groups"]] == ["Starter"]
        assert data["groups"][0]["snippet_ids"] == [a["id"], b["id"]]
        assert (
            client.post("/api/chat/instruction-groups", json={"name": "Bad", "snippet_ids": [9999]}).status_code == 400
        )
        assert client.delete(f"/api/chat/instruction-groups/{g['id']}").status_code == 200
        assert client.get("/api/chat/instructions").json()["groups"] == []

    def test_deleting_a_snippet_removes_it_from_groups_and_chats(self, client, conv):
        """Test that deleting a snippet removes it from groups and chats."""
        a = client.post("/api/chat/instructions", json={"name": "A", "content": "x"}).json()
        b = client.post("/api/chat/instructions", json={"name": "B", "content": "y"}).json()
        g = client.post("/api/chat/instruction-groups", json={"name": "G", "snippet_ids": [a["id"], b["id"]]}).json()
        client.patch(
            f"/api/chat/conversations/{conv['id']}",
            json={"instruction_ids": [a["id"]], "instruction_group_ids": [g["id"]]},
        )
        client.delete(f"/api/chat/instructions/{a['id']}")
        assert client.get("/api/chat/instructions").json()["groups"][0]["snippet_ids"] == [b["id"]]
        gone = client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]
        assert gone["instruction_ids"] == []
        assert gone["instruction_group_ids"] == [g["id"]]

    def test_global_defaults_apply_live_to_every_chat(self, client, chat):
        """Test that global defaults apply live to every chat."""
        d = client.post("/api/chat/instructions", json={"name": "D", "content": "x"}).json()
        e = client.post("/api/chat/instructions", json={"name": "E", "content": "y"}).json()
        g = client.post("/api/chat/instruction-groups", json={"name": "G", "snippet_ids": [d["id"]]}).json()
        client.put(
            "/api/chat/settings",
            json={"default_instruction_ids": [d["id"], e["id"]], "default_instruction_group_ids": [g["id"]]},
        )
        made = client.post("/api/chat/conversations", json={}).json()
        # Nothing is copied in: the defaults apply on top of the chat's own (none here)
        assert made["instruction_ids"] == []
        assert made["instruction_group_ids"] == []
        assert chat.generation.conversation_instructions(made["id"]) == "x\n\ny"  # D once, though in G too
        # Changing the defaults changes the chat
        client.put("/api/chat/settings", json={"default_instruction_ids": [e["id"]]})
        assert chat.generation.conversation_instructions(made["id"]) == "y"
        assert client.post("/api/chat/conversations", json={"instruction_ids": [999]}).status_code == 400

    def test_global_settings_crud_and_validation(self, client):
        """Test that global settings crud and validation."""
        s = client.post("/api/chat/instructions", json={"name": "S", "content": "x"}).json()
        assert client.get("/api/chat/settings").json() == {
            "default_character_ids": [],
            "default_instruction_ids": [],
            "default_instruction_group_ids": [],
            "title_model": None,
        }
        updated = client.put("/api/chat/settings", json={"default_instruction_ids": [s["id"]]}).json()
        assert updated["default_instruction_ids"] == [s["id"]]
        assert client.put("/api/chat/settings", json={"default_instruction_ids": [999]}).status_code == 400
        # Deleting the snippet clears it from the global bucket
        client.delete(f"/api/chat/instructions/{s['id']}")
        assert client.get("/api/chat/settings").json()["default_instruction_ids"] == []

    def test_attach_and_detach_on_existing_chat(self, client, conv):
        """Test that attach and detach on existing chat."""
        i = client.post("/api/chat/instructions", json={"name": "I", "content": "x"}).json()
        assert client.patch(f"/api/chat/conversations/{conv['id']}", json={"instruction_ids": [i["id"]]}).json()[
            "instruction_ids"
        ] == [i["id"]]
        assert (
            client.patch(f"/api/chat/conversations/{conv['id']}", json={"instruction_ids": []}).json()[
                "instruction_ids"
            ]
            == []
        )

    def test_deleting_an_instruction_detaches_it(self, client, conv):
        """Test that deleting an instruction detaches it."""
        i = client.post("/api/chat/instructions", json={"name": "I", "content": "x"}).json()
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"instruction_ids": [i["id"]]})
        client.delete(f"/api/chat/instructions/{i['id']}")
        assert client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["instruction_ids"] == []

    def test_flattened_snippets_and_groups_sent_deduped_as_one_system_message(self, client, conv, chat, monkeypatch):
        """Test that flattened snippets and groups sent deduped as one system message."""
        tone = client.post("/api/chat/instructions", json={"name": "Tone", "content": "Be warm."}).json()
        fmt = client.post("/api/chat/instructions", json={"name": "Fmt", "content": "Use markdown."}).json()
        lang = client.post("/api/chat/instructions", json={"name": "Lang", "content": "In French."}).json()
        g = client.post(
            "/api/chat/instruction-groups", json={"name": "G", "snippet_ids": [tone["id"], fmt["id"]]}
        ).json()
        # tone is attached both via the group and individually: sent once
        client.patch(
            f"/api/chat/conversations/{conv['id']}",
            json={"instruction_group_ids": [g["id"]], "instruction_ids": [tone["id"], lang["id"]]},
        )
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        assert seen["msgs"][1] == {"role": "system", "content": "Be warm.\n\nUse markdown.\n\nIn French."}
        assert seen["msgs"][2]["role"] == "user"

    def test_not_sent_when_none_attached(self, client, conv, chat, monkeypatch):
        """Test that not sent when none attached."""
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        assert [m["role"] for m in seen["msgs"]] == ["system", "user"]

    def test_conversational_image_models_get_them_too(self, client, conv, chat, monkeypatch):
        """Test that conversational image models get them too."""
        chat.catalogue.seed_models(
            {
                "text": [],
                "video": [],
                "image": [{"id": "i/model", "input_modalities": ["text", "image"], "conversational": True}],
            },
        )
        i = client.post("/api/chat/instructions", json={"name": "I", "content": "Watercolour style only."}).json()
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"instruction_ids": [i["id"]]})
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image_chat",
            lambda model, messages, **kw: (got.update(messages=messages), ([(_png_bytes(), "image/png")], None))[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "a fox", "mode": "image", **SETTINGS}
            )
        )
        assert got["messages"][0] == {"role": "system", "content": "Watercolour style only."}


class TestChatSpaces:
    """Tests for chat spaces."""

    def test_crud(self, client):
        """Test that crud."""
        s = client.post("/api/chat/instructions", json={"name": "Tone", "content": "Be warm."}).json()
        g = client.post("/api/chat/instruction-groups", json={"name": "G", "snippet_ids": [s["id"]]}).json()
        sp = client.post(
            "/api/chat/spaces",
            json={"name": "Novel", "default_instruction_ids": [s["id"]], "default_instruction_group_ids": [g["id"]]},
        ).json()
        assert sp["name"] == "Novel"
        assert sp["default_instruction_ids"] == [s["id"]]
        assert [x["name"] for x in client.get("/api/chat/spaces").json()["spaces"]] == ["Novel"]
        upd = client.put(f"/api/chat/spaces/{sp['id']}", json={"name": "Renamed"}).json()
        assert upd["name"] == "Renamed"
        assert upd["default_instruction_ids"] == []
        assert client.delete(f"/api/chat/spaces/{sp['id']}").status_code == 200
        assert client.get("/api/chat/spaces").json()["spaces"] == []
        assert (
            client.post("/api/chat/spaces", json={"name": "Bad", "default_instruction_ids": [999]}).status_code == 400
        )

    def test_chat_in_space_stacks_global_and_space_defaults_deduped(self, client, chat):
        """Test that chat in space stacks global and space defaults deduped."""
        shared = client.post("/api/chat/instructions", json={"name": "Shared", "content": "both."}).json()
        spaceonly = client.post("/api/chat/instructions", json={"name": "SpaceOnly", "content": "Be warm."}).json()
        glob = client.post("/api/chat/instructions", json={"name": "Glob", "content": "x"}).json()
        # Global defaults: glob + shared. Space defaults: shared + spaceonly.
        client.put("/api/chat/settings", json={"default_instruction_ids": [glob["id"], shared["id"]]})
        sp = client.post(
            "/api/chat/spaces",
            json={"name": "Novel", "default_instruction_ids": [shared["id"], spaceonly["id"]]},
        ).json()
        conv = client.post("/api/chat/conversations", json={"space_id": sp["id"]}).json()
        assert conv["space_id"] == sp["id"]
        assert conv["instruction_ids"] == []
        # Global first, then the space's own, each snippet once (shared de-duped)
        assert chat.generation.conversation_instructions(conv["id"]) == "x\n\nboth.\n\nBe warm."
        # Out of the space, only the global defaults apply
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"space_id": None})
        assert chat.generation.conversation_instructions(conv["id"]) == "x\n\nboth."

    def test_chat_without_space_uses_only_global_defaults(self, client, chat, db):
        """Test that chat without space uses only global defaults."""
        glob = client.post("/api/chat/instructions", json={"name": "Glob", "content": "x"}).json()
        client.put("/api/chat/settings", json={"default_instruction_ids": [glob["id"]]})
        conv = client.post("/api/chat/conversations", json={}).json()
        assert conv["space_id"] is None
        assert chat.helpers._inherited(db.get_conversation(conv["id"]))["instruction"] == [glob["id"]]

    def test_space_character_defaults_apply_to_its_chats(self, client, chat, db):
        """Test that space character defaults apply to its chats."""
        c1 = db.create_character("Alice")
        c2 = db.create_character("Bob")
        sp = client.post("/api/chat/spaces", json={"name": "Novel", "default_character_ids": [c1.id]}).json()
        conv = client.post("/api/chat/conversations", json={"space_id": sp["id"], "character_ids": [c2.id]}).json()
        assert conv["character_ids"] == [c2.id]  # its own
        assert chat.helpers.effective_ids(db.get_conversation(conv["id"]), "character") == [c1.id, c2.id]

    def test_deleting_a_character_clears_it_from_global_and_space_defaults(self, client, db):
        """Test that deleting a character clears it from global and space defaults."""
        c1 = db.create_character("Alice")
        client.put("/api/chat/settings", json={"default_character_ids": [c1.id]})
        sp = client.post("/api/chat/spaces", json={"name": "Novel", "default_character_ids": [c1.id]}).json()
        assert sp["default_character_ids"] == [c1.id]
        db.delete_character(c1.id)  # symmetric with snippet/group deletion
        assert client.get("/api/chat/settings").json()["default_character_ids"] == []
        assert client.get("/api/chat/spaces").json()["spaces"][0]["default_character_ids"] == []

    def test_move_chat_between_spaces_and_unfiled(self, client, conv):
        """Test that move chat between spaces and unfiled."""
        sp = client.post("/api/chat/spaces", json={"name": "Novel"}).json()
        moved = client.patch(f"/api/chat/conversations/{conv['id']}", json={"space_id": sp["id"]}).json()
        assert moved["space_id"] == sp["id"]
        back = client.patch(f"/api/chat/conversations/{conv['id']}", json={"space_id": None}).json()
        assert back["space_id"] is None
        assert client.patch(f"/api/chat/conversations/{conv['id']}", json={"space_id": 999}).status_code == 400

    def test_deleting_space_unfiles_its_chats(self, client):
        """Test that deleting space unfiles its chats."""
        sp = client.post("/api/chat/spaces", json={"name": "Novel"}).json()
        conv = client.post("/api/chat/conversations", json={"space_id": sp["id"]}).json()
        client.delete(f"/api/chat/spaces/{sp['id']}")
        assert client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["space_id"] is None

    def test_deleting_a_snippet_clears_it_from_space_defaults(self, client):
        """Test that deleting a snippet clears it from space defaults."""
        s = client.post("/api/chat/instructions", json={"name": "Tone", "content": "x"}).json()
        client.post("/api/chat/spaces", json={"name": "Novel", "default_instruction_ids": [s["id"]]})
        client.delete(f"/api/chat/instructions/{s['id']}")
        assert client.get("/api/chat/spaces").json()["spaces"][0]["default_instruction_ids"] == []


class TestPolloImageModels:
    """Pollo image models in chat. Pollo is fully mocked — nothing here can.

    reach the real API (which would bill credits).
    """

    POLLO: ClassVar = {**SETTINGS, "image_model": "pollo/seedream"}

    @pytest.fixture
    def pollo(self, chat, monkeypatch, provider_keys):
        """Provide the pollo fixture."""
        provider_keys["pollo"] = "pollo-test"
        monkeypatch.setattr(pollo_provider, "POLL_INTERVAL", 0)
        calls = {"generators": [], "uploads": [], "statuses": iter([])}

        class FakeResponse:
            status_code = 200
            text = ""

            def __init__(self, body, content=b"", content_type="image/png"):
                self._body, self.content = body, content
                self.headers = {"Content-Type": content_type}

            def json(self):
                return self._body

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size=None):
                yield self.content

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeGenerator:
            api_key = "pollo-test"

            def __init__(self, key, **kwargs):
                calls["generators"].append((key, kwargs))
                self.payload_attrs = {}

            def send_request(self):
                k = calls["generators"][-1][1]
                self.payload_attrs = {
                    name: k.get(arg)
                    for name, arg in (
                        ("aspectRatio", "aspect_ratio"),
                        ("resolution", "resolution"),
                        ("duration", "length"),
                        ("generateAudio", "generate_audio"),
                    )
                    if k.get(arg) is not None
                }
                return FakeResponse({"code": "SUCCESS", "data": {"taskId": "task-1", "status": "waiting"}})

        monkeypatch.setattr(pollo_provider, "get_image_generator", lambda key, **kw: FakeGenerator(key, **kw))
        monkeypatch.setattr(pollo_provider, "get_video_generator", lambda key, **kw: FakeGenerator(key, **kw))
        monkeypatch.setattr(pollo_provider, "get_task_status", lambda task_id, key: next(calls["statuses"]))
        monkeypatch.setattr(
            pollo_provider.requests,
            "get",
            lambda url, timeout=None, stream=False: FakeResponse(
                None, b"mp4-bytes" if url.endswith(".mp4") else _png_bytes(), "image/jpeg"
            ),
        )
        monkeypatch.setattr(
            pollo_provider.image_hosts,
            "upload_file",
            lambda path, prefs=None: (calls["uploads"].append(path.name), f"https://tmp.example/{path.name}")[1],
        )
        return calls

    def _draw(self, client, conv, chat, monkeypatch, args, statuses, pollo):
        pollo["statuses"] = iter(statuses)
        rounds = iter([_tool_chunks("generate_image", args, text="Here you go."), _text_chunks("unused")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        monkeypatch.setattr(openrouter, "generate_image", lambda *a, **k: pytest.fail("should run on Pollo"))
        return _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "draw", "mode": "auto", **self.POLLO}
            )
        )[-1]["message"]

    def test_listed_in_the_image_catalogue_when_key_is_set(self, chat, monkeypatch, pollo, provider_keys):
        """Test that listed in the image catalogue when key is set."""
        for fn in ("list_text_models", "list_image_models", "list_video_models"):
            monkeypatch.setattr(openrouter, fn, list)
        models = {m["id"]: m for m in chat.catalogue.get_models(refresh=True)["image"]}
        assert models["pollo/seedream"]["name"] == "Pollo: Seedream 5.0 Lite"
        assert models["pollo/seedreampro"]["name"] == "Pollo: Seedream 5.0 Pro"
        assert "21:9" in models["pollo/seedream"]["aspect_ratios"]
        provider_keys["pollo"] = None
        assert not any(m["id"].startswith("pollo/") for m in chat.catalogue.get_models(refresh=True)["image"])

    def test_tool_call_runs_on_pollo(self, client, conv, chat, monkeypatch, pollo):
        """Test that tool call runs on pollo."""
        msg = self._draw(
            client,
            conv,
            chat,
            monkeypatch,
            {"prompt": "a red fox", "aspect_ratio": "16:9"},
            [[("processing", None, None, None)], [("succeed", None, "https://cdn/x.jpg", 6)]],
            pollo,
        )
        item = msg["media"][0]
        assert item["status"] == "done"
        assert item["file"].endswith(".jpg")
        assert item["credits"] == 6
        assert not item.get("cost")
        assert msg["cost"] == pytest.approx(0.003)  # OpenRouter text only — credits aren't dollars
        key, kwargs = pollo["generators"][0]
        assert key == "seedream"
        # The model's 16:9 is ignored; composer on auto → no ratio sent (model default)
        assert (kwargs["prompt"], kwargs["aspect_ratio"], kwargs["images"]) == ("a red fox", None, None)

    def test_unsupported_ratio_falls_back_to_model_default(self, client, conv, chat, monkeypatch, pollo):
        """Test that unsupported ratio falls back to model default."""
        self._draw(
            client,
            conv,
            chat,
            monkeypatch,
            {"prompt": "x", "aspect_ratio": "5:4"},
            [[("succeed", None, "https://cdn/x.png", 3)]],
            pollo,
        )
        assert pollo["generators"][0][1]["aspect_ratio"] is None

    def test_reference_images_are_uploaded_for_pollo(self, client, conv, chat, db, monkeypatch, pollo):
        """Test that reference images are uploaded for pollo."""
        (chat.conversation_dir(conv["id"]) / "img_prev.png").write_bytes(_png_bytes())
        db.add_chat_message(conv["id"], "user", "a cat")
        db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "p1", "kind": "image", "source": "generated", "status": "done", "file": "img_prev.png"}],
        )
        self._draw(
            client,
            conv,
            chat,
            monkeypatch,
            {"prompt": "same cat, in a hat", "source_image": "latest"},
            [[("succeed", None, "https://cdn/x.png", 3)]],
            pollo,
        )
        assert pollo["uploads"] == ["img_prev.png"]
        assert pollo["generators"][0][1]["images"] == ["https://tmp.example/img_prev.png"]

    def test_failure_marks_the_item_and_can_be_retried(self, client, conv, chat, db, monkeypatch, pollo):
        """Test that failure marks the item and can be retried."""
        msg = self._draw(
            client,
            conv,
            chat,
            monkeypatch,
            {"prompt": "x"},
            [[("failed", "Content flagged by moderation", None, None)]],
            pollo,
        )
        item = msg["media"][0]
        assert item["status"] == "error"
        assert item["moderated"] is True
        assert "Pollo" in item["error"]

        pollo["statuses"] = iter([[("succeed", None, "https://cdn/y.png", 3)]])
        monkeypatch.setattr(
            threading, "Thread", lambda target, args, **kw: type("T", (), {"start": lambda self: target(*args)})()
        )
        client.post(f"/api/chat/messages/{msg['id']}/media/{item['id']}/regenerate", json={})
        fixed = db.get_chat_message(msg["id"]).media[0]
        assert fixed["status"] == "done"
        assert fixed["credits"] == 3

    def test_polling_survives_transient_errors(self, chat, monkeypatch, pollo):
        """Test that polling survives transient errors."""
        pollo["statuses"] = iter(
            [
                [("cloudflare_blocked", "blocked", None, None)],
                [("error", "HTTP 502", None, None)],
                [("succeed", None, "https://cdn/x.png", 2)],
            ]
        )
        images, credits, _sent = pollo_provider.generate_image("pollo/nanobanana2", "x")
        assert len(images) == 1
        assert credits == 2

    # ── video ──
    VIDEO: ClassVar = {**SETTINGS, "video_model": "pollo/seedance20fast"}

    def test_video_models_listed_without_deprecated_ones(self, chat, monkeypatch, pollo):
        """Test that video models listed without deprecated ones."""
        for fn in ("list_text_models", "list_image_models", "list_video_models"):
            monkeypatch.setattr(openrouter, fn, list)
        models = {m["id"]: m for m in chat.catalogue.get_models(refresh=True)["video"]}
        fast = models["pollo/seedance20fast"]
        assert fast["name"] == "Pollo: Seedance 2.0 Fast"
        assert fast["durations"] == list(range(4, 16))
        assert fast["resolutions"] == ["480p", "720p"]
        assert fast["frame_images"] == ["first_frame"]
        assert fast["generate_audio"] is True
        assert "pollo/wan27" not in models  # marked deprecated on the Generate page

    def test_video_mode_submits_to_pollo_with_first_frame(self, client, conv, chat, monkeypatch, pollo):
        """Test that video mode submits to pollo with first frame."""
        monkeypatch.setattr(openrouter, "submit_video", lambda *a, **k: pytest.fail("should run on Pollo"))
        chat.catalogue.seed_models(
            {"video": [{"id": "pollo/seedance20fast", "durations": list(range(4, 16))}]}, stale=True
        )
        up = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments", files={"file": ("a.png", _png_bytes(), "image/png")}
        ).json()["file"]
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={
                    "content": "make it move",
                    "attachments": [up],
                    "mode": "video",
                    **self.VIDEO,
                    "video_options": {"duration": 20, "aspect_ratio": "9:16", "generate_audio": False},
                },
            )
        )[-1]["message"]
        item = msg["media"][0]
        assert item["status"] == "pending"
        assert item["job_id"] == "pollo:task-1"
        key, kwargs = pollo["generators"][0]
        assert key == "seedance20fast"
        assert pollo["uploads"] == [up]
        assert kwargs["image_url"] == f"https://tmp.example/{up}"
        assert (kwargs["prompt"], kwargs["length"], kwargs["generate_audio"]) == ("make it move", 15, False)
        assert kwargs["aspect_ratio"] == "9:16"  # picked in the composer, so it wins over the image's shape

    def test_auto_length_is_remembered_on_the_media_item(self, client, conv, chat, monkeypatch, pollo):
        """The composer resolves Auto to a number before sending, so the item.

        records that it *was* Auto — otherwise reusing its settings would pin
        whatever Auto worked out to.
        """
        monkeypatch.setattr(openrouter, "submit_video", lambda *a, **k: pytest.fail("should run on Pollo"))
        chat.catalogue.seed_models(
            {"video": [{"id": "pollo/seedance20fast", "durations": list(range(4, 16))}]}, stale=True
        )
        up = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments", files={"file": ("a.png", _png_bytes(), "image/png")}
        ).json()["file"]

        def send(video_options):
            return _events(
                client.post(
                    f"/api/chat/conversations/{conv['id']}/messages",
                    json={
                        "content": "make it move",
                        "attachments": [up],
                        "mode": "video",
                        **self.VIDEO,
                        "video_options": video_options,
                    },
                )
            )[-1]["message"]["media"][0]

        auto = send({"duration": 10, "duration_auto": True})
        assert auto["params"]["duration"] == 10
        assert auto["params"]["duration_auto"] is True
        picked = send({"duration": 10})
        assert picked["params"]["duration"] == 10
        assert picked["params"]["duration_auto"] is False
        # Either way Pollo is sent the resolved length, not the flag
        assert all("duration_auto" not in kwargs for _, kwargs in pollo["generators"])

    # ── audio ──
    AUDIO: ClassVar = {**SETTINGS, "audio_model": "pollo/elevenv3"}

    def test_audio_models_listed_with_their_type(self, chat, monkeypatch, pollo):
        """Test that audio models listed with their type."""
        for fn in ("list_text_models", "list_image_models", "list_video_models"):
            monkeypatch.setattr(openrouter, fn, list)
        models = {m["id"]: m for m in chat.catalogue.get_models(refresh=True)["audio"]}
        assert models["pollo/elevenv3"]["tags"] == ["tts"]
        assert models["pollo/elevenv3"]["options"] == ["voice"]
        assert models["pollo/sunov55"]["tags"] == ["music"]

    def test_audio_mode_submits_speech_with_the_picked_voice(self, client, conv, chat, monkeypatch, pollo):
        """Test that audio mode submits speech with the picked voice."""

        class Gen:
            payload_attrs: ClassVar = {"prompt": "hello", "voiceId": "v1"}

            def __init__(self, key, **kw):
                pollo["generators"].append((key, kw))

            def get_payload(self):
                return {}

            def send_request(self):
                return type(
                    "R", (), {"status_code": 200, "text": "", "json": lambda s: {"data": {"taskId": "task-1"}}}
                )()

        monkeypatch.setattr(pollo_provider, "get_audio_generator", lambda key, **kw: Gen(key, **kw))
        monkeypatch.setattr(chat.polling, "start_video_poller", lambda *a: None)
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "hello", "mode": "audio", **self.AUDIO, "audio_options": {"voice": "v1"}},
            )
        )[-1]["message"]
        item = msg["media"][0]
        assert item["kind"] == "audio"
        assert item["status"] == "pending"
        assert item["job_id"] == "pollo:task-1"
        key, kwargs = pollo["generators"][0]
        assert key == "elevenv3"
        assert kwargs["prompt"] == "hello"
        assert kwargs["voice"] == "v1"
        # the picks are remembered with the conversation's composer settings
        settings = client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["settings"]
        assert settings["audio_model"] == "pollo/elevenv3"
        assert settings["audio_options"]["voice"] == "v1"

    def _fake_audio_generator(self, monkeypatch, chat, pollo):
        class Gen:
            payload_attrs: ClassVar = {"prompt": "x"}

            def __init__(self, key, **kw):
                pollo["generators"].append((key, kw))

            def get_payload(self):
                return {}

            def send_request(self):
                return type(
                    "R", (), {"status_code": 200, "text": "", "json": lambda s: {"data": {"taskId": "task-1"}}}
                )()

        monkeypatch.setattr(pollo_provider, "get_audio_generator", lambda key, **kw: Gen(key, **kw))
        monkeypatch.setattr(chat.polling, "start_video_poller", lambda *a: None)

    def test_auto_mode_chat_model_can_call_generate_audio(self, client, conv, chat, monkeypatch, pollo):
        """Test that auto mode chat model can call generate audio."""
        self._fake_audio_generator(monkeypatch, chat, pollo)
        rounds = iter([_tool_chunks("generate_audio", {"prompt": "Hello there"}, text="On it."), _text_chunks("x")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "say hello", "mode": "auto", **self.AUDIO, "audio_options": {"voice": "v1"}},
            )
        )[-1]["message"]
        assert msg["media"][0]["kind"] == "audio"
        assert msg["media"][0]["job_id"] == "pollo:task-1"
        assert pollo["generators"][0][1]["prompt"] == "Hello there"

    def test_audio_estimate_prices_by_the_text(self, client, chat, monkeypatch, pollo):
        """Test that audio estimate prices by the text."""
        seen = {}

        def fake(model, kind, *args):
            seen.update(model=model, kind=kind, args=args)
            return {"credits": 3}

        monkeypatch.setattr(pollo_provider, "estimate_cost", fake)
        r = client.post(
            "/api/chat/estimate",
            json={"model": "pollo/elevenv3", "kind": "audio", "prompt": "hi", "audio_options": {"voice": "v1"}},
        )
        assert r.json() == {"estimate": {"credits": 3}}
        assert seen["kind"] == "audio"
        assert seen["args"][-2:] == ("hi", {"voice": "v1"})

    def test_a_tool_needs_no_prompt_but_an_image(self, client, conv, chat, monkeypatch, pollo):
        """Test that a tool needs no prompt but an image."""
        chat.catalogue.seed_models(
            {
                "image": [
                    {"id": "pollo/imageupscale", "name": "Pollo: Image Upscale", "tool": "upscale", "no_prompt": True}
                ]
            },
            stale=True,
        )
        body = {"content": "", "mode": "image", **SETTINGS, "image_model": "pollo/imageupscale"}
        r = client.post(f"/api/chat/conversations/{conv['id']}/messages", json=body)
        assert r.status_code == 200  # an empty message is fine for a tool…
        assert "needs an image" in _events(r)[-1]["message"]["error"]  # …but it must have an image

    def test_poller_keeps_the_result_extension(self, chat, db, conv, monkeypatch, pollo):
        """Test that poller keeps the result extension."""
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "pt1", "kind": "video", "source": "generated", "status": "pending", "job_id": "pollo:t-6"}],
        )
        pollo["statuses"] = iter([[("succeed", None, "https://cdn/cut.webm?sig=1", 2)]] * 2)
        chat.polling._poll_video(conv["id"], msg.id, "pt1", "pollo:t-6")
        assert db.get_chat_message(msg.id).media[0]["file"].endswith(".webm")

    def test_audio_mode_needs_a_prompt_and_a_model(self, client, conv, chat, monkeypatch, pollo):
        """Test that audio mode needs a prompt and a model."""
        msgs = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "hi", "mode": "audio", **SETTINGS},
            )
        )
        assert "No audio model" in msgs[-1]["message"]["error"]

    def _video_from_image(self, client, conv, chat, size, model, **extra):
        up = client.post(
            f"/api/chat/conversations/{conv['id']}/attachments",
            files={"file": ("a.png", _png_bytes(size), "image/png")},
        ).json()["file"]
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={
                    "content": "animate",
                    "attachments": [up],
                    "mode": "video",
                    **SETTINGS,
                    "video_model": model,
                    **extra,
                },
            )
        )

    def test_first_frame_sets_the_ratio_when_none_is_picked(self, client, conv, chat, monkeypatch, pollo):
        """Test that first frame sets the ratio when none is picked."""
        self._video_from_image(client, conv, chat, (60, 80), "pollo/seedance20fast")  # 3:4 photo
        assert pollo["generators"][0][1]["aspect_ratio"] == "3:4"

    def test_follow_image_ratio_preferred_when_the_model_has_one(self, client, conv, chat, monkeypatch, pollo):
        """Test that follow image ratio preferred when the model has one."""
        self._video_from_image(client, conv, chat, (60, 80), "pollo/seedance25")
        assert pollo["generators"][0][1]["aspect_ratio"] == "adaptive"

    def test_animating_ignores_the_chat_models_ratio_guess(self, client, conv, chat, db, monkeypatch, pollo):
        """Test that animating ignores the chat models ratio guess."""
        (chat.conversation_dir(conv["id"]) / "img_prev.png").write_bytes(_png_bytes((60, 80)))
        db.add_chat_message(conv["id"], "user", "a cat")
        db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "p1", "kind": "image", "source": "generated", "status": "done", "file": "img_prev.png"}],
        )
        rounds = iter(
            [
                _tool_chunks(
                    "generate_video",
                    {"prompt": "it walks", "aspect_ratio": "9:16", "source_image": "latest"},
                    text="Rolling.",
                ),
                _text_chunks("x"),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "animate it", "mode": "auto", **self.VIDEO},
            )
        )
        assert pollo["generators"][0][1]["aspect_ratio"] == "3:4"

    def test_poller_finishes_a_pollo_video(self, chat, db, conv, monkeypatch, pollo):
        """Test that poller finishes a pollo video."""
        monkeypatch.setattr(openrouter, "get_video", lambda *a: pytest.fail("should ask Pollo"))
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[
                {"id": "pv1", "kind": "video", "source": "generated", "status": "pending", "job_id": "pollo:task-9"}
            ],
        )
        pollo["statuses"] = iter(
            [
                [("processing", None, None, None)],
                [("cloudflare_blocked", "blocked", None, None)],
                [("succeed", None, "https://cdn/v.mp4", 40)],
                [("succeed", None, "https://cdn/v.mp4", 40)],
            ]
        )  # re-read for the download
        chat.polling._poll_video(conv["id"], msg.id, "pv1", "pollo:task-9")
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "done"
        assert item["credits"] == 40
        assert not item.get("cost")
        assert (chat.helpers.chat_root() / conv["id"] / item["file"]).read_bytes() == b"mp4-bytes"

    def test_poller_saves_a_pollo_audio_job_as_mp3(self, chat, db, conv, monkeypatch, pollo):
        """Test that poller saves a pollo audio job as mp3."""
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[{"id": "pa1", "kind": "audio", "source": "generated", "status": "pending", "job_id": "pollo:t-5"}],
        )
        pollo["statuses"] = iter([[("succeed", None, "https://cdn/a.mp3", 3)]] * 2)
        chat.polling._poll_video(conv["id"], msg.id, "pa1", "pollo:t-5")
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "done"
        assert item["file"].endswith(".mp3")
        assert item["credits"] == 3

    def test_failed_pollo_video_marks_the_item(self, chat, db, conv, monkeypatch, pollo):
        """Test that failed pollo video marks the item."""
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[
                {"id": "pv2", "kind": "video", "source": "generated", "status": "pending", "job_id": "pollo:task-8"}
            ],
        )
        pollo["statuses"] = iter([[("failed", "Your prompt violates our content policy", None, None)]])
        chat.polling._poll_video(conv["id"], msg.id, "pv2", "pollo:task-8")
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "error"
        assert item["moderated"] is True
        assert item["error"].startswith("Pollo:")

    def test_a_charged_failure_keeps_its_credits_and_shows_the_verdict(self, chat, db, conv, pollo):
        """Pollo bills a job that fails its own validation, so the credits have.

        to land on the item (they're real money) and the stored response has to
        be the verdict, not the "accepted" reply from submitting.
        """
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            media=[
                {
                    "id": "pv3",
                    "kind": "video",
                    "source": "generated",
                    "status": "pending",
                    "job_id": "pollo:task-11",
                    "response": {"code": "SUCCESS", "data": {"status": "waiting"}},
                }
            ],
        )
        pollo["statuses"] = iter([[("failed", "InvalidParameter Invalid video_url.", None, 61)]])
        chat.polling._poll_video(conv["id"], msg.id, "pv3", "pollo:task-11")
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "error"
        assert item["credits"] == 61
        assert item["response"]["generations"][0]["failMsg"] == "InvalidParameter Invalid video_url."
        # and it's counted as spend, since it was charged
        rows = db.spend_rows([conv["id"]])
        assert [r["credits"] for r in rows] == [61]

    def test_kling_and_qwen_models_offered_in_chat(self, chat, monkeypatch, pollo):
        """Test that kling and qwen models offered in chat."""
        for fn in ("list_text_models", "list_image_models", "list_video_models"):
            monkeypatch.setattr(openrouter, fn, list)
        data = chat.catalogue.get_models(refresh=True)
        images = {m["id"]: m for m in data["image"]}
        videos = {m["id"]: m for m in data["video"]}
        assert images["pollo/qwenimage3pro"]["input_modalities"] == ["text", "image"]
        assert images["pollo/qwenimageflash"]["input_modalities"] == ["text"]  # no reference images
        assert videos["pollo/klingv3"]["resolutions"] == ["std", "pro", "4K"]
        assert videos["pollo/klingv3"]["durations"] == list(range(3, 16))

    def test_image_only_kling_without_an_image_fails_on_the_card(self, client, conv, chat, db, monkeypatch, pollo):
        """Test that image only kling without an image fails on the card."""
        monkeypatch.setattr(pollo_provider, "get_video_generator", registry.video_generator)  # the real one
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "a fox running", "mode": "video", **SETTINGS, "video_model": "pollo/klingv21"},
            )
        )[-1]["message"]
        item = msg["media"][0]
        assert item["status"] == "error"
        assert "needs a source image" in item["error"]

    def test_auto_mode_uses_composer_video_settings_and_records_what_was_sent(
        self, client, conv, chat, monkeypatch, pollo
    ):
        """Test that auto mode uses composer video settings and records what was sent."""
        chat.catalogue.seed_models(
            {
                "video": [
                    {"id": "pollo/seedance20fast", "durations": list(range(4, 16)), "resolutions": ["480p", "720p"]}
                ]
            },
            stale=True,
        )
        rounds = iter(
            [_tool_chunks("generate_video", {"prompt": "waves", "duration": 6}, text="Rolling."), _text_chunks("x")]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={
                    "content": "make a video of waves",
                    "mode": "auto",
                    **self.VIDEO,
                    "video_options": {"resolution": "720p", "aspect_ratio": "16:9"},
                },
            )
        )[-1]["message"]
        kwargs = pollo["generators"][0][1]
        # composer picks apply in Auto; the chat model's duration fills the gap
        assert (kwargs["resolution"], kwargs["aspect_ratio"], kwargs["length"]) == ("720p", "16:9", 6)
        params = msg["media"][0]["params"]
        assert (params["resolution"], params["aspect_ratio"], params["duration"]) == ("720p", "16:9", 6)

    def test_model_pollo_doesnt_serve_explains_itself(self, client, conv, chat, monkeypatch, pollo):
        """Test that model pollo doesnt serve explains itself."""

        class NotServed:
            status_code, text = 404, ""

            def json(self):
                return {"message": "Not found", "code": "NOT_FOUND", "errorCode": "REJECTED"}

        class Gen:
            api_key, payload_attrs = "k", {}

            def send_request(self):
                return NotServed()

        monkeypatch.setattr(pollo_provider, "get_image_generator", lambda key, **kw: Gen())
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: pytest.fail("no LLM in image mode"))
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "a fox", "mode": "image", **SETTINGS, "image_model": "pollo/qwenimage3pro"},
            )
        )[-1]["message"]
        assert "isn't available to your API key" in msg["media"][0]["error"]

    def test_pollo_not_enabled_is_not_called_moderation(self, client, conv, chat, monkeypatch, pollo):
        """Pollo answers 403 for "not enabled for API access" — that's not a content block."""

        class Refused:
            status_code, text = 403, ""

            def json(self):
                return {"message": "This model is not enabled for API access.", "code": "FORBIDDEN"}

        class Gen:
            api_key, payload_attrs = "k", {}

            def send_request(self):
                return Refused()

        monkeypatch.setattr(pollo_provider, "get_image_generator", lambda key, **kw: Gen())
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: pytest.fail("no LLM in image mode"))
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "a gym", "mode": "image", **SETTINGS, "image_model": "pollo/seedreampro"},
            )
        )[-1]["message"]
        item = msg["media"][0]
        assert item["error"] == "Pollo: This model is not enabled for API access."
        assert item["moderated"] is False

    def test_pollo_content_rejection_is_still_moderation(self, chat):
        """Test that pollo content rejection is still moderation."""
        is_mod = chat.generation.is_moderation_error
        assert is_mod(pollo_provider.PolloError("Pollo: prompt flagged as sensitive content", 400))
        assert is_mod(openrouter.OpenRouterError("Forbidden", 403))  # OpenRouter's 403 still counts

    def test_models_not_enabled_for_the_key_are_flagged_hidden(self, chat, monkeypatch, pollo):
        """Test that models not enabled for the key are flagged hidden."""
        for fn in ("list_text_models", "list_image_models", "list_video_models"):
            monkeypatch.setattr(openrouter, fn, list)
        images = {m["id"]: m for m in chat.catalogue.get_models(refresh=True)["image"]}
        hidden = {k for k, m in images.items() if m["hidden"]}
        assert hidden == {"pollo/qwenimageflash"}
        # `hidden` carries the reason, shown in the picker behind "Show hidden"
        assert "unavailable" in images["pollo/qwenimageflash"]["hidden"]
        assert images["pollo/qwenimage3"]["hidden"] is None  # works since its address was fixed
        assert images["pollo/klingv3image"]["hidden"] is None  # confirmed working


class TestOpenRouterConnection:
    """Tests for open router connection."""

    def test_connections_use_tcp_keepalive(self, chat):
        """Test that connections use tcp keepalive."""
        opts = openrouter.keepalive_socket_options()
        assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in opts
        if hasattr(socket, "TCP_KEEPIDLE"):
            assert (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5) in opts

    def test_dropped_connection_fails_the_card_with_an_explanation(self, client, conv, chat, monkeypatch):
        """httpx.RemoteProtocolError used to escape as a raw error and leave the image pending."""

        def drop(*a, **k):
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")  # noqa: TRY003

        monkeypatch.setattr(openrouter._client, "stream", drop)
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: pytest.fail("no LLM in image mode"))
        msg = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "a fox", "mode": "image", **SETTINGS}
            )
        )[-1]["message"]
        item = msg["media"][0]
        assert item["status"] == "error"
        assert item["moderated"] is False
        assert "connection to OpenRouter dropped after" in item["error"]
        assert "RemoteProtocolError" in item["error"]


class TestOpenRouterImageStream:
    """/images is streamed so the connection isn't silent while the image renders."""

    class _Stream:
        def __init__(self, lines, content_type="text/event-stream", status=200, body=None):
            self.lines, self.status_code, self._body = lines, status, body
            self.headers = {"content-type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self):
            yield from self.lines

        def read(self):
            return b""

        def json(self):
            return self._body

    def _b64(self, color="red"):

        return base64.b64encode(_png_bytes(color=color)).decode()

    def test_keeps_only_completed_images_and_cost(self, chat, monkeypatch):
        """Test that keeps only completed images and cost."""
        sent = {}
        lines = [
            ": OPENROUTER PROCESSING",
            "",
            "event: image_generation.partial_image",
            "data: " + json.dumps({"type": "image_generation.partial_image", "b64_json": self._b64("blue")}),
            "",
            ": OPENROUTER PROCESSING",
            "",
            "event: image_generation.completed",
            "data: "
            + json.dumps({"type": "image_generation.completed", "b64_json": self._b64(), "usage": {"cost": 0.03}}),
            "",
            "data: [DONE]",
        ]
        monkeypatch.setattr(
            openrouter._client,
            "stream",
            lambda method, url, **kw: (sent.update(kw["json"]), self._Stream(lines))[1],
        )
        images, cost = openrouter.generate_image("x/img", "a fox")
        assert sent["stream"] is True
        assert images == [(_png_bytes(), "image/png")]
        assert cost == 0.03

    def test_logs_the_request_and_the_card_keeps_it(self, client, conv, chat, monkeypatch):
        """Test that logs the request and the card keeps it."""
        lines = ["event: error", "data: " + json.dumps({"error": {"message": "flagged by moderation"}}), ""]
        monkeypatch.setattr(openrouter._client, "stream", lambda *a, **k: self._Stream(lines))
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "a fox", **SETTINGS, "mode": "image"},
            )
        )
        item = ev[-1]["message"]["media"][0]
        [entry] = [e for e in request_log.recent() if e["path"] == "/images"]
        assert entry["provider"] == "openrouter"
        assert entry["model"] == "i/model"
        assert entry["status"] == 200
        error = entry["error"]
        assert isinstance(error, str)
        assert "flagged" in error
        assert item["request"] == entry["request"]
        assert item["request"]["prompt"] == "a fox"

    def test_reference_images_are_cut_short_in_the_log(self, chat, monkeypatch):
        """Test that reference images are cut short in the log."""
        lines = ["event: image_generation.completed", "data: " + json.dumps({"b64_json": self._b64()}), ""]
        monkeypatch.setattr(openrouter._client, "stream", lambda *a, **k: self._Stream(lines))
        request_log.forget_last()
        openrouter.generate_image("x/img", "a fox", input_images=["data:image/png;base64," + "A" * 4096])
        last = request_log.take_last()
        assert last is not None
        assert last["response"] == {"images": ["image/png"], "cost": None}
        request = last.get("request")
        assert isinstance(request, dict)
        refs = request["input_references"]
        assert refs == [{"type": "image_url", "image_url": {"url": "data:image/png;base64,… (3 KB)"}}]

    def test_event_name_alone_identifies_the_final_image(self, chat, monkeypatch):
        """Test that event name alone identifies the final image."""
        lines = ["event: image_generation.completed", "data: " + json.dumps({"b64_json": self._b64()}), ""]
        monkeypatch.setattr(openrouter._client, "stream", lambda *a, **k: self._Stream(lines))
        images, _ = openrouter.generate_image("x/img", "a fox")
        assert len(images) == 1

    def test_error_event_raises(self, chat, monkeypatch):
        """Test that error event raises."""
        lines = ["event: error", "data: " + json.dumps({"error": {"message": "flagged by moderation"}}), ""]
        monkeypatch.setattr(openrouter._client, "stream", lambda *a, **k: self._Stream(lines))
        with pytest.raises(openrouter.OpenRouterError, match="flagged"):
            openrouter.generate_image("x/img", "a fox")

    def test_plain_json_answer_still_works(self, chat, monkeypatch):
        """Test that plain json answer still works."""
        body = {"data": [{"b64_json": self._b64(), "media_type": "image/png"}], "usage": {"cost": 0.01}}
        monkeypatch.setattr(
            openrouter._client,
            "stream",
            lambda *a, **k: self._Stream([], content_type="application/json", body=body),
        )
        images, cost = openrouter.generate_image("x/img", "a fox")
        assert len(images) == 1
        assert cost == 0.01

    def test_stream_without_an_image_raises(self, chat, monkeypatch):
        """Test that stream without an image raises."""
        monkeypatch.setattr(openrouter._client, "stream", lambda *a, **k: self._Stream(["data: [DONE]"]))
        with pytest.raises(openrouter.OpenRouterError, match="no images"):
            openrouter.generate_image("x/img", "a fox")


class TestDeleteExchange:
    """Tests for delete exchange."""

    def _chat(self, db, conv):
        u1 = db.add_chat_message(conv["id"], "user", "draw a fox")
        a1 = db.add_chat_message(
            conv["id"],
            "assistant",
            "Here!",
            media=[
                {
                    "id": "f1",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "fox.png",
                    "prompt": "fox",
                }
            ],
        )
        u2 = db.add_chat_message(conv["id"], "user", "now a cat", parent_id=a1.id)
        a2 = db.add_chat_message(
            conv["id"],
            "assistant",
            "Meow",
            parent_id=u2.id,
            media=[
                {
                    "id": "c1",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "cat.png",
                    "prompt": "cat",
                }
            ],
        )
        u3 = db.add_chat_message(conv["id"], "user", "thanks", parent_id=a2.id)
        a3 = db.add_chat_message(conv["id"], "assistant", "Welcome", parent_id=u3.id)
        return u1, a1, u2, a2, u3, a3

    def test_removes_prompt_and_reply_and_rejoins_the_chat(self, client, conv, chat, db, monkeypatch):
        """Test that removes prompt and reply and rejoins the chat."""
        _u1, _a1, u2, _a2, _u3, _a3 = self._chat(db, conv)
        r = client.delete(f"/api/chat/messages/{u2.id}")
        assert r.status_code == 200
        assert [m["content"] for m in r.json()["messages"]] == ["draw a fox", "Here!", "thanks", "Welcome"]
        # The models no longer see it
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda m, msgs, tools=None, session_id=None, **kw: (seen.update(msgs=msgs), _text_chunks("ok"))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "more", **SETTINGS}))
        assert "now a cat" not in json.dumps(seen["msgs"])
        assert "Meow" not in json.dumps(seen["msgs"])
        # Its image is kept, in the library
        lib = client.get("/api/chat/library").json()["items"]
        cat = next(i for i in lib if i["id"] == "c1")
        assert cat["attached"] is False
        assert cat["file"] == "cat.png"

    def test_whole_turn_goes_and_only_the_shown_continuation_stays(self, client, conv, chat, db):
        """Test that whole turn goes and only the shown continuation stays."""
        u1, a1, u2, _a2, u3, a3 = self._chat(db, conv)
        # Another reply version, an edited prompt version, each with follow-ups
        retry = db.add_chat_message(
            conv["id"],
            "assistant",
            "Purr",
            parent_id=u2.id,
            media=[
                {"id": "r1", "kind": "image", "source": "generated", "status": "done", "file": "r.png", "prompt": "r"}
            ],
        )
        db.add_chat_message(conv["id"], "user", "on the retry branch", parent_id=retry.id)
        edit = db.add_chat_message(conv["id"], "user", "now a dog", parent_id=a1.id)
        edit_reply = db.add_chat_message(conv["id"], "assistant", "Woof", parent_id=edit.id)
        db.add_chat_message(conv["id"], "user", "on the edit branch", parent_id=edit_reply.id)
        db.set_chat_leaf(conv["id"], a3.id)  # looking at the original version

        info = client.get(f"/api/chat/messages/{u2.id}/delete-info").json()
        # Both generated images go with the turn, so the confirmation can name them
        assert info == {"other_versions": 1, "other_messages": 2, "media": {"image": 2}}

        msgs = client.delete(f"/api/chat/messages/{u2.id}").json()["messages"]
        assert [m["content"] for m in msgs] == ["draw a fox", "Here!", "thanks", "Welcome"]
        ids = {m.id for m in db.get_chat_messages(conv["id"])}
        assert ids == {u1.id, a1.id, u3.id, a3.id}
        assert db.get_chat_message(u3.id).parent_id == a1.id
        assert client.get(f"/api/chat/messages/{u3.id}").json()["siblings"] == [u3.id]  # no stray versions
        lib = {i["id"] for i in client.get("/api/chat/library").json()["items"] if not i["attached"]}
        assert {"c1", "r1"} <= lib

    def test_shown_branch_decides_what_stays(self, client, conv, db):
        """Test that shown branch decides what stays."""
        _u1, a1, _u2, _a2, _u3, _a3 = self._chat(db, conv)
        edit = db.add_chat_message(conv["id"], "user", "now a dog", parent_id=a1.id)
        edit_reply = db.add_chat_message(conv["id"], "assistant", "Woof", parent_id=edit.id)
        edit_next = db.add_chat_message(conv["id"], "user", "walkies", parent_id=edit_reply.id)
        db.set_chat_leaf(conv["id"], edit_next.id)  # looking at the edited version
        msgs = client.delete(f"/api/chat/messages/{edit.id}").json()["messages"]
        assert [m["content"] for m in msgs] == ["draw a fox", "Here!", "walkies"]

    def test_info_is_quiet_without_other_versions(self, client, conv, db):
        """Test that info is quiet without other versions."""
        _u1, _a1, u2, *_ = self._chat(db, conv)
        assert client.get(f"/api/chat/messages/{u2.id}/delete-info").json() == {
            "other_versions": 0,
            "other_messages": 0,
            "media": {"image": 1},
        }

    def test_info_counts_no_media_when_the_generation_failed(self, client, conv, db):
        """Test that info counts no media when the generation failed."""
        u = db.add_chat_message(conv["id"], "user", "make a video")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            parent_id=u.id,
            media=[{"id": "f1", "kind": "video", "source": "generated", "status": "error", "error": "nope"}],
        )
        info = client.get(f"/api/chat/messages/{u.id}/delete-info").json()
        assert info["media"] == {}  # nothing was made, so there's nothing to offer to delete

    def test_info_ignores_uploads(self, client, conv, db):
        """Test that info ignores uploads."""
        u = db.add_chat_message(
            conv["id"],
            "user",
            "here you go",
            media=[{"id": "up1", "kind": "image", "source": "upload", "status": "done", "file": "up_a.png"}],
        )
        db.add_chat_message(conv["id"], "assistant", "Nice", parent_id=u.id)
        assert client.get(f"/api/chat/messages/{u.id}/delete-info").json()["media"] == {}

    def test_deleting_the_last_exchange_shows_the_one_before(self, client, conv, db):
        """Test that deleting the last exchange shows the one before."""
        _u1, _a1, _u2, _a2, u3, _a3 = self._chat(db, conv)
        msgs = client.delete(f"/api/chat/messages/{u3.id}").json()["messages"]
        assert [m["content"] for m in msgs][-1] == "Meow"

    def test_only_prompts_and_not_while_replying(self, client, conv, db):
        """Test that only prompts and not while replying."""
        u1, a1, *_ = self._chat(db, conv)
        assert client.delete(f"/api/chat/messages/{a1.id}").status_code == 400
        db.add_chat_message(conv["id"], "assistant", "", status="streaming")
        assert client.delete(f"/api/chat/messages/{u1.id}").status_code == 409
        assert client.delete("/api/chat/messages/999999").status_code == 404


class TestFork:
    """Tests for fork."""

    def _chat(self, chat, db, conv):
        d = chat.conversation_dir(conv["id"])
        (d / "fox.png").write_bytes(_png_bytes())
        (d / "cat.png").write_bytes(_png_bytes(color="blue"))
        u1 = db.add_chat_message(conv["id"], "user", "draw a fox", mode="auto")
        a1 = db.add_chat_message(
            conv["id"],
            "assistant",
            "Here!",
            model="t/model",
            media=[
                {
                    "id": "f1",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "fox.png",
                    "pinned": True,
                }
            ],
        )
        db.update_chat_message(a1.id, cost=0.02)
        u2 = db.add_chat_message(conv["id"], "user", "now a cat", parent_id=a1.id)
        a2 = db.add_chat_message(
            conv["id"],
            "assistant",
            "Meow",
            parent_id=u2.id,
            media=[{"id": "c1", "kind": "image", "source": "generated", "status": "done", "file": "cat.png"}],
        )
        return u1, a1, u2, a2

    def _fork(self, client, conv, message_id):
        return client.post(f"/api/chat/conversations/{conv['id']}/fork", json={"message_id": message_id})

    def test_new_chat_ends_at_the_prompt_and_its_reply(self, client, conv, chat, db):
        """Test that new chat ends at the prompt and its reply."""
        u1, _a1, _u2, _a2 = self._chat(chat, db, conv)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"title": "Animals", **SETTINGS})
        r = self._fork(client, conv, u1.id)
        assert r.status_code == 200
        new = r.json()
        assert new["id"] != conv["id"]
        assert new["title"] == "Animals (branch)"
        assert (new["text_model"], new["image_model"]) == ("t/model", "i/model")

        msgs = client.get(f"/api/chat/conversations/{new['id']}").json()["messages"]
        assert [(m["role"], m["content"]) for m in msgs] == [("user", "draw a fox"), ("assistant", "Here!")]
        assert msgs[0]["mode"] == "auto"
        assert msgs[1]["cost"] == 0.02
        assert msgs[1]["model"] == "t/model"
        assert msgs[1]["parent_id"] == msgs[0]["id"]
        assert msgs[0]["parent_id"] is None
        img = msgs[1]["media"][0]
        assert img["file"] == "fox.png"
        assert img["pinned"]
        assert img["id"] != "f1"
        assert client.get(f"/api/chat/media/{new['id']}/fox.png").status_code == 200
        # The original is untouched
        orig = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
        assert [m["content"] for m in orig] == ["draw a fox", "Here!", "now a cat", "Meow"]

    def test_new_chat_survives_deleting_the_original(self, client, conv, chat, db):
        """Test that new chat survives deleting the original."""
        u1, *_ = self._chat(chat, db, conv)
        new = self._fork(client, conv, u1.id).json()
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert client.get(f"/api/chat/media/{new['id']}/fox.png").status_code == 200

    def test_takes_the_shown_reply(self, client, conv, chat, db):
        """Test that takes the shown reply."""
        _u1, _a1, u2, a2 = self._chat(chat, db, conv)
        retry = db.add_chat_message(conv["id"], "assistant", "Purr", parent_id=u2.id)
        db.set_chat_leaf(conv["id"], a2.id)
        new = self._fork(client, conv, u2.id).json()
        msgs = client.get(f"/api/chat/conversations/{new['id']}").json()["messages"]
        assert [m["content"] for m in msgs] == ["draw a fox", "Here!", "now a cat", "Meow"]
        assert all(m["siblings"] == [m["id"]] for m in msgs)  # no other versions come along
        db.set_chat_leaf(conv["id"], retry.id)
        new = self._fork(client, conv, u2.id).json()
        assert client.get(f"/api/chat/conversations/{new['id']}").json()["messages"][-1]["content"] == "Purr"

    def test_media_shows_once(self, client, conv, chat, db):
        """Test that media shows once."""
        u1, *_ = self._chat(chat, db, conv)
        self._fork(client, conv, u1.id)
        items = [i for i in client.get("/api/media").json()["items"] if i["origin"] == "chat"]
        assert sorted(i["name"] for i in items) == ["cat.png", "fox.png"]
        assert all(i["conversation_id"] == conv["id"] for i in items)

    def test_pending_video_is_not_copied_as_pending(self, client, conv, chat, db):
        """Test that pending video is not copied as pending."""
        u = db.add_chat_message(conv["id"], "user", "a clip")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            media=[
                {"id": "v1", "kind": "video", "source": "generated", "status": "pending", "file": None, "job_id": "j"}
            ],
        )
        new = self._fork(client, conv, u.id).json()
        item = client.get(f"/api/chat/conversations/{new['id']}").json()["messages"][1]["media"][0]
        assert item["status"] == "error"

    def test_only_messages_in_this_chat_and_not_while_replying(self, client, conv, chat, db):
        """Test that only messages in this chat and not while replying."""
        u1, _a1, *_ = self._chat(chat, db, conv)
        other = client.post("/api/chat/conversations", json={}).json()
        assert self._fork(client, other, u1.id).status_code == 400
        db.add_chat_message(conv["id"], "assistant", "", status="streaming")
        assert self._fork(client, conv, u1.id).status_code == 409

    def test_chat_made_characters_are_copied_and_saved_ones_shared(self, client, conv, chat, db):
        """Test that chat made characters are copied and saved ones shared."""
        saved = db.create_character("Rex", "a dog")
        own = db.create_character("Bob", "a fox", conversation_id=conv["id"])
        d = characters_mod.char_dir(own.id)
        d.mkdir(parents=True)
        (d / "img_bob.png").write_bytes(_png_bytes())
        own = db.update_character(own.id, images=["img_bob.png"])
        unused = db.create_character("Ann", "", conversation_id=conv["id"])
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [saved.id, own.id]})
        (chat.conversation_dir(conv["id"]) / "bob.png").write_bytes(_png_bytes())
        (chat.conversation_dir(conv["id"]) / "up_src.png").write_bytes(_png_bytes())
        u = db.add_chat_message(conv["id"], "user", "draw Bob")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            media=[
                {
                    "id": "b1",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "bob.png",
                    "params": {"characters": [own.id], "refs": ["up_src.png", f"char:{own.id}/img_bob.png"]},
                }
            ],
        )

        new = self._fork(client, conv, u.id).json()
        copy_id = next(i for i in new["character_ids"] if i != saved.id)
        assert new["character_ids"] == [saved.id, copy_id]
        assert copy_id != own.id
        copy = db.get_character(copy_id)
        assert (copy.name, copy.conversation_id, copy.images) == ("Bob", new["id"], ["img_bob.png"])
        assert (characters_mod.char_dir(copy_id) / "img_bob.png").is_file()
        assert not any(c.name == "Ann" and c.conversation_id == new["id"] for c in db.list_characters())

        params = client.get(f"/api/chat/conversations/{new['id']}").json()["messages"][1]["media"][0]["params"]
        assert params == {"characters": [copy_id], "refs": ["up_src.png", f"char:{copy_id}/img_bob.png"]}
        assert (chat.conversation_dir(new["id"]) / "up_src.png").is_file()

        # Deleting the original takes its own characters, not the branch's
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert db.get_character(own.id) is None
        assert db.get_character(unused.id) is None
        assert client.get(f"/api/chat/conversations/{new['id']}").json()["conversation"]["character_ids"] == [
            saved.id,
            copy_id,
        ]
        assert (characters_mod.char_dir(copy_id) / "img_bob.png").is_file()

    def test_branching_from_a_reply_ends_with_that_reply(self, client, conv, chat, db):
        """Test that branching from a reply ends with that reply."""
        _u1, a1, _u2, _a2 = self._chat(chat, db, conv)
        new = self._fork(client, conv, a1.id).json()
        msgs = client.get(f"/api/chat/conversations/{new['id']}").json()["messages"]
        assert [m["content"] for m in msgs] == ["draw a fox", "Here!"]

    def test_branch_remembers_its_origin_and_the_original_lists_it(self, client, conv, chat, db):
        """Test that branch remembers its origin and the original lists it."""
        _u1, _a1, u2, _a2 = self._chat(chat, db, conv)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"title": "Animals"})
        new = self._fork(client, conv, u2.id).json()
        got = client.get(f"/api/chat/conversations/{new['id']}").json()["conversation"]
        assert got["forked_from"] == {"id": conv["id"], "title": "Animals", "message_id": u2.id, "exists": True}
        orig = client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"]
        assert {m["id"]: m["forks"] for m in orig}[u2.id] == [{"id": new["id"], "title": "Animals (branch)"}]
        assert all(not m["forks"] for m in orig if m["id"] != u2.id)
        client.delete(f"/api/chat/conversations/{conv['id']}")
        got = client.get(f"/api/chat/conversations/{new['id']}").json()["conversation"]
        assert got["forked_from"]["exists"] is False
        assert got["forked_from"]["title"] is None

    def test_branch_spend_says_what_came_with_it(self, client, conv, chat, db):
        """Test that branch spend says what came with it."""
        u1, a1, *_ = self._chat(chat, db, conv)
        db.update_chat_message(a1.id, media=[{**db.get_chat_message(a1.id).media[0], "credits": 30}])
        new = self._fork(client, conv, u1.id).json()
        u = db.add_chat_message(new["id"], "user", "more")
        a = db.add_chat_message(new["id"], "assistant", "ok", parent_id=u.id)
        db.update_chat_message(a.id, cost=0.01)
        spend = client.get(f"/api/chat/conversations/{new['id']}/spend").json()
        assert spend == {"usd": 0.03, "credits": 30, "inherited_usd": 0.02, "inherited_credits": 30}


class TestConversationList:
    """Tests for conversation list."""

    def test_pinned_first_and_pinning_keeps_the_order_of_the_rest(self, client, db):
        """Test that pinned first and pinning keeps the order of the rest."""
        a = client.post("/api/chat/conversations", json={"title": "A"}).json()
        client.post("/api/chat/conversations", json={"title": "B"})
        client.post("/api/chat/conversations", json={"title": "C"})
        r = client.patch(f"/api/chat/conversations/{a['id']}", json={"pinned": True})
        assert r.json()["pinned"] is True

        def titles():
            return [x["title"] for x in client.get("/api/chat/conversations").json()["conversations"]]

        assert titles() == ["A", "C", "B"]
        client.patch(f"/api/chat/conversations/{a['id']}", json={"pinned": False})
        assert titles() == ["C", "B", "A"]

    def test_says_when_older_chats_are_left_out(self, client, chat, monkeypatch):
        """Test that says when older chats are left out."""
        monkeypatch.setattr(chat.routes, "CONVERSATION_LIST_LIMIT", 2)
        for t in "ABC":
            client.post("/api/chat/conversations", json={"title": t})
        data = client.get("/api/chat/conversations").json()
        assert len(data["conversations"]) == 2
        assert data["more"] is True

    def test_search_finds_titles_and_messages_on_any_branch(self, client, db):
        """Test that search finds titles and messages on any branch."""
        client.post("/api/chat/conversations", json={"title": "Fox story"})
        other = client.post("/api/chat/conversations", json={"title": "Misc"}).json()
        client.post("/api/chat/conversations", json={"title": "Nothing here"})
        db.add_chat_message(
            other["id"], "user", "a long intro " * 20 + "then a FOX appears in the snow " + "and more " * 20
        )
        db.add_chat_message(other["id"], "user", "edited away", parent_id=None)  # another branch shown
        res = client.get("/api/chat/conversations", params={"q": "fox"}).json()["conversations"]
        assert {c["title"] for c in res} == {"Fox story", "Misc"}
        by = {c["title"]: c for c in res}
        assert by["Fox story"]["snippet"] is None
        snip = by["Misc"]["snippet"]
        assert "FOX appears" in snip
        assert snip.startswith("…")
        assert snip.endswith("…")
        assert len(snip) <= 122

    def test_search_treats_wildcards_literally(self, client):
        """Test that search treats wildcards literally."""
        client.post("/api/chat/conversations", json={"title": "100% done"})
        client.post("/api/chat/conversations", json={"title": "1000 done"})
        res = client.get("/api/chat/conversations", params={"q": "0%"}).json()["conversations"]
        assert [c["title"] for c in res] == ["100% done"]


class TestRememberedSettings:
    """Tests for remembered settings."""

    def test_turn_settings_are_kept_on_the_chat_and_copied_to_branches(self, client, conv, chat, db, monkeypatch):
        """Test that turn settings are kept on the chat and copied to branches."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok"))
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={
                    "content": "hi",
                    **SETTINGS,
                    "mode": "text",
                    "history_limit": 10,
                    "image_limit": 2,
                    "image_options": {"aspect_ratio": "16:9"},
                },
            )
        )
        got = client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["settings"]
        assert got["mode"] == "text"
        assert got["history_limit"] == 10
        assert got["image_limit"] == 2
        assert got["image_options"]["aspect_ratio"] == "16:9"
        new = client.post(
            f"/api/chat/conversations/{conv['id']}/fork", json={"message_id": ev[0]["user_message"]["id"]}
        ).json()
        assert new["settings"] == got


class TestTitles:
    """Tests for titles."""

    def _send(self, client, conv, content="tell me about foxes in winter"):
        return _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": content, **SETTINGS, "mode": "text"}
            )
        )

    def test_model_title_and_its_cost(self, client, conv, chat, monkeypatch):
        """Test that model title and its cost."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok", cost=0.001))
        seen = {}
        monkeypatch.setattr(
            chat.generation,
            "generate_title",
            lambda model, prompt: (seen.update(model=model, prompt=prompt), ("Winter Foxes", 0.0005))[1],
        )
        ev = self._send(client, conv)
        assert {"type": "title", "title": "Winter Foxes"} in ev
        assert seen == {"model": "t/model", "prompt": "tell me about foxes in winter"}
        assert ev[-1]["message"]["cost"] == 0.0015
        assert client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["title"] == "Winter Foxes"
        # Only the first turn
        self._send(client, conv, "more")
        assert seen["prompt"] == "tell me about foxes in winter"

    def test_falls_back_to_the_prompt(self, client, conv, chat, monkeypatch):
        """Test that falls back to the prompt."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok"))

        def boom(model, prompt):
            raise openrouter.OpenRouterError("nope")

        monkeypatch.setattr(chat.generation, "generate_title", boom)
        ev = self._send(client, conv)
        assert {"type": "title", "title": "tell me about foxes in winter"} in ev

    def test_title_model_override(self, client, conv, chat, monkeypatch):
        """Test that title model override."""
        monkeypatch.setenv("CHAT_TITLE_MODEL", "cheap/model")
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok"))
        seen = {}
        monkeypatch.setattr(
            chat.generation, "generate_title", lambda model, prompt: (seen.update(model=model), ("T", 0))[1]
        )
        self._send(client, conv)
        assert seen["model"] == "cheap/model"

    def test_generate_title_cleans_the_reply(self, monkeypatch):
        """Test that generate title cleans the reply."""
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda model, msgs, **kw: _text_chunks('<think>hmm</think>**Title:** "Winter Foxes."\nextra', cost=0.0002),
        )
        assert chat_mod.generation.generate_title("t/model", "foxes") == ("Winter Foxes", 0.0002)

    def test_clean_title_rejects_rambling(self, chat):
        """Test that clean title rejects rambling."""
        assert chat.generation._clean_title("x" * 100) is None
        assert chat.generation._clean_title("   ") is None


class TestPolloRequestLog:
    """Tests for pollo request log."""

    def test_submit_is_logged_with_its_payload(self, chat):
        """Test that submit is logged with its payload."""

        class Resp:
            status_code = 200

            def json(self):
                return {"data": {"taskId": "t-9"}}

        class Gen:
            model_url = "https://pollo.ai/api/platform/generation/bytedance/seedance-2-0"

            def get_payload(self):
                return {"input": {"prompt": "waves", "image": "https://host/x.png"}}

            def send_request(self):
                return Resp()

        assert pollo_provider._submit(Gen()) == "t-9"
        entry = request_log.recent()[0]
        assert entry["provider"] == "pollo"
        assert entry["model"] == "seedance-2-0"
        assert entry["status"] == 200
        assert entry["path"] == "/api/platform/generation/bytedance/seedance-2-0"
        assert entry["request"] == {"input": {"prompt": "waves", "image": "https://host/x.png"}}


class TestHiddenDefaults:
    """A chat can switch off any of its defaults for itself only."""

    def test_hiding_a_default_in_one_chat_leaves_the_others(self, client, chat):
        """Test that hiding a default in one chat leaves the others."""
        a = client.post("/api/chat/instructions", json={"name": "A", "content": "aa"}).json()
        b = client.post("/api/chat/instructions", json={"name": "B", "content": "bb"}).json()
        client.put("/api/chat/settings", json={"default_instruction_ids": [a["id"], b["id"]]})
        one = client.post("/api/chat/conversations", json={}).json()
        two = client.post("/api/chat/conversations", json={}).json()
        hidden = client.patch(
            f"/api/chat/conversations/{one['id']}", json={"hidden_defaults": {"instruction": [a["id"]]}}
        ).json()
        assert hidden["hidden_defaults"]["instruction"] == [a["id"]]
        assert chat.generation.conversation_instructions(one["id"]) == "bb"
        assert chat.generation.conversation_instructions(two["id"]) == "aa\n\nbb"
        # Shown again
        client.patch(f"/api/chat/conversations/{one['id']}", json={"hidden_defaults": {}})
        assert chat.generation.conversation_instructions(one["id"]) == "aa\n\nbb"

    def test_a_new_chat_can_start_with_some_hidden(self, client, chat, db):
        """Test that a new chat can start with some hidden."""
        c1 = db.create_character("Alice")
        client.put("/api/chat/settings", json={"default_character_ids": [c1.id]})
        conv = client.post("/api/chat/conversations", json={"hidden_defaults": {"character": [c1.id]}}).json()
        assert chat.helpers.effective_ids(db.get_conversation(conv["id"]), "character") == []

    def test_a_branch_keeps_what_was_hidden(self, client, chat, db, monkeypatch):
        """Test that a branch keeps what was hidden."""
        a = client.post("/api/chat/instructions", json={"name": "A", "content": "aa"}).json()
        client.put("/api/chat/settings", json={"default_instruction_ids": [a["id"]]})
        conv = client.post("/api/chat/conversations", json={"hidden_defaults": {"instruction": [a["id"]]}}).json()
        msg = db.add_chat_message(conv["id"], "user", "hi")
        fork = client.post(f"/api/chat/conversations/{conv['id']}/fork", json={"message_id": msg.id}).json()
        assert fork["hidden_defaults"]["instruction"] == [a["id"]]

    def test_unknown_kinds_are_refused(self, client):
        """Test that unknown kinds are refused."""
        conv = client.post("/api/chat/conversations", json={}).json()
        resp = client.patch(f"/api/chat/conversations/{conv['id']}", json={"hidden_defaults": {"nope": [1]}})
        assert resp.status_code == 400


class TestPausedInstructions:
    """A chat can pause attached snippets/groups: kept attached, not sent."""

    def test_paused_snippets_and_groups_stay_attached_but_are_not_sent(self, client, conv, chat):
        """Test that paused snippets and groups stay attached but are not sent."""
        tone = client.post("/api/chat/instructions", json={"name": "Tone", "content": "Be warm."}).json()
        fmt = client.post("/api/chat/instructions", json={"name": "Fmt", "content": "Use markdown."}).json()
        lang = client.post("/api/chat/instructions", json={"name": "Lang", "content": "In French."}).json()
        g = client.post(
            "/api/chat/instruction-groups", json={"name": "G", "snippet_ids": [tone["id"], fmt["id"]]}
        ).json()
        client.patch(
            f"/api/chat/conversations/{conv['id']}",
            json={"instruction_group_ids": [g["id"]], "instruction_ids": [tone["id"], lang["id"]]},
        )
        assert chat.generation.conversation_instructions(conv["id"]) == "Be warm.\n\nUse markdown.\n\nIn French."
        # Pause the group: its Fmt drops, but Tone stays (attached individually too)
        r = client.patch(
            f"/api/chat/conversations/{conv['id']}", json={"paused_instructions": {"instruction_group": [g["id"]]}}
        ).json()
        assert r["paused_instructions"]["instruction_group"] == [g["id"]]
        assert r["instruction_group_ids"] == [g["id"]]  # still attached, just paused
        assert chat.generation.conversation_instructions(conv["id"]) == "Be warm.\n\nIn French."
        # Also pause the Tone snippet → only Lang is left
        client.patch(
            f"/api/chat/conversations/{conv['id']}",
            json={"paused_instructions": {"instruction_group": [g["id"]], "instruction": [tone["id"]]}},
        )
        assert chat.generation.conversation_instructions(conv["id"]) == "In French."
        # Resume everything
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"paused_instructions": {}})
        assert chat.generation.conversation_instructions(conv["id"]) == "Be warm.\n\nUse markdown.\n\nIn French."

    def test_an_inherited_default_can_be_paused(self, client, chat):
        """Test that an inherited default can be paused."""
        a = client.post("/api/chat/instructions", json={"name": "A", "content": "aa"}).json()
        b = client.post("/api/chat/instructions", json={"name": "B", "content": "bb"}).json()
        client.put("/api/chat/settings", json={"default_instruction_ids": [a["id"], b["id"]]})
        one = client.post("/api/chat/conversations", json={}).json()
        two = client.post("/api/chat/conversations", json={}).json()
        client.patch(f"/api/chat/conversations/{one['id']}", json={"paused_instructions": {"instruction": [a["id"]]}})
        assert chat.generation.conversation_instructions(one["id"]) == "bb"  # paused here
        assert chat.generation.conversation_instructions(two["id"]) == "aa\n\nbb"  # unaffected elsewhere

    def test_a_new_chat_can_start_with_some_paused(self, client, chat):
        """Test that a new chat can start with some paused."""
        a = client.post("/api/chat/instructions", json={"name": "A", "content": "aa"}).json()
        client.put("/api/chat/settings", json={"default_instruction_ids": [a["id"]]})
        conv = client.post("/api/chat/conversations", json={"paused_instructions": {"instruction": [a["id"]]}}).json()
        assert conv["paused_instructions"]["instruction"] == [a["id"]]
        assert chat.generation.conversation_instructions(conv["id"]) is None

    def test_a_branch_keeps_what_was_paused(self, client, db):
        """Test that a branch keeps what was paused."""
        a = client.post("/api/chat/instructions", json={"name": "A", "content": "aa"}).json()
        conv = client.post("/api/chat/conversations", json={"instruction_ids": [a["id"]]}).json()
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"paused_instructions": {"instruction": [a["id"]]}})
        msg = db.add_chat_message(conv["id"], "user", "hi")
        fork = client.post(f"/api/chat/conversations/{conv['id']}/fork", json={"message_id": msg.id}).json()
        assert fork["paused_instructions"]["instruction"] == [a["id"]]

    def test_unknown_kinds_are_refused(self, client, conv):
        """Test that unknown kinds are refused."""
        resp = client.patch(f"/api/chat/conversations/{conv['id']}", json={"paused_instructions": {"character": [1]}})
        assert resp.status_code == 400


class TestLargeChats:
    """Big chats (imports run to hundreds of messages and images) stay quick."""

    def test_images_have_a_small_preview(self, client, conv, tmp_path):
        """Test that images have a small preview."""
        folder = tmp_path / "chat" / conv["id"]
        folder.mkdir(parents=True)
        Image.new("RGB", (1536, 2048), "red").save(folder / "img_big.png")
        resp = client.get(f"/api/chat/media/{conv['id']}/img_big.png/preview")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert min(Image.open(io.BytesIO(resp.content)).size) == 768
        assert client.get(f"/api/chat/media/{conv['id']}/nope.png/preview").status_code == 404

    def test_deleting_a_chat_removes_its_messages_and_files(self, client, conv, db, tmp_path):
        """Test that deleting a chat removes its messages and files."""
        for i in range(30):
            db.add_chat_message(conv["id"], "user" if i % 2 == 0 else "assistant", f"m{i}")
        folder = tmp_path / "chat" / conv["id"]
        folder.mkdir(parents=True)
        (folder / "img_a.png").write_bytes(_png_bytes())
        assert client.delete(f"/api/chat/conversations/{conv['id']}").status_code == 200
        assert db.get_chat_messages(conv["id"]) == []
        assert not folder.exists()  # moved aside at once, then removed in the background
        for _ in range(50):
            if not list((tmp_path / "chat").glob(".deleting-*")):
                break
            time.sleep(0.02)
        assert not list((tmp_path / "chat").glob(".deleting-*"))

    def test_missing_thumbnails_are_made_in_the_background(self, chat, tmp_path):
        """Test that missing thumbnails are made in the background."""
        folder = tmp_path / "chat" / "c1"
        folder.mkdir(parents=True)
        Image.new("RGB", (1200, 1600), "blue").save(folder / "img_a.png")
        chat.polling._warm_missing_thumbnails()
        for size in (media_mod.THUMB_SIZE, chat.CHAT_PREVIEW_SIZE):
            assert media_mod._thumb_path(folder / "img_a.png", size).is_file()


class TestActiveGenerations:
    """The /generations/active endpoint behind the always-visible queue."""

    def gen(self, mid, kind="image", status="pending", **f):
        """Document the gen test helper."""
        return {"id": mid, "kind": kind, "source": "generated", "status": status, "prompt": "p", **f}

    def test_pending_across_threads_plus_known_completions(self, client, db):
        """Test that pending across threads plus known completions."""
        a = client.post("/api/chat/conversations", json={"title": "A"}).json()
        b = client.post("/api/chat/conversations", json={"title": "B"}).json()
        # One pending in each thread, and a finished one that is NOT pending.
        db.add_chat_message(a["id"], "assistant", media=[self.gen("p1")], status="done")
        db.add_chat_message(b["id"], "assistant", media=[self.gen("p2", kind="video")], status="done")
        done_msg = db.add_chat_message(a["id"], "assistant", media=[self.gen("d1", status="done", file="x.png")])

        # No `known`: only the two pending ones come back, from both threads.
        r = client.post("/api/chat/generations/active", json={}).json()["items"]
        by = {i["media_id"]: i for i in r}
        assert set(by) == {"p1", "p2"}
        assert by["p1"]["conversation_title"] == "A"
        assert by["p2"]["kind"] == "video"

        # Tracking the finished message resolves it to its done state.
        r = client.post("/api/chat/generations/active", json={"known": [done_msg.id]}).json()["items"]
        by = {i["media_id"]: i for i in r}
        assert set(by) == {"p1", "p2", "d1"}
        assert by["d1"]["status"] == "done"
        assert by["d1"]["file"] == "x.png"

    def test_reports_failure_and_ignores_non_generated(self, client, db):
        """Test that reports failure and ignores non generated."""
        c = client.post("/api/chat/conversations", json={}).json()
        m = db.add_chat_message(
            c["id"],
            "assistant",
            media=[
                self.gen("e1", status="error", error="boom", moderated=True),
                {"id": "u1", "kind": "image", "source": "upload", "status": "done", "file": "up.png"},
            ],
            status="done",
        )
        r = client.post("/api/chat/generations/active", json={"known": [m.id]}).json()["items"]
        by = {i["media_id"]: i for i in r}
        assert set(by) == {"e1"}  # the uploaded image isn't a generation
        assert by["e1"]["status"] == "error"
        assert by["e1"]["error"] == "boom"
        assert by["e1"]["moderated"] is True

    def test_scoped_to_the_signed_in_user(self, client, db):
        """Test that scoped to the signed in user."""
        c = client.post("/api/chat/conversations", json={}).json()
        tok = set_tenant("someone-else")
        try:
            other = db.create_conversation(title="theirs")
            db.add_chat_message(other.id, "assistant", media=[self.gen("x1")], status="done")
        finally:
            reset_tenant(tok)
        db.add_chat_message(c["id"], "assistant", media=[self.gen("mine")], status="done")
        items = client.post("/api/chat/generations/active", json={}).json()["items"]
        assert {i["media_id"] for i in items} == {"mine"}  # never the other user's


class TestEnhancePrompt:
    """Tests for enhance prompt."""

    def test_rewrites_only_on_request(self, client, monkeypatch):
        """Test that rewrites only on request."""

        def fake_stream(model, messages, **kw):
            assert "a cat" in messages[0]["content"]
            yield {"choices": [{"delta": {"content": "A fluffy cat, golden hour"}}], "usage": {"cost": 0.001}}

        monkeypatch.setattr(openrouter, "stream_chat", fake_stream)
        r = client.post("/api/chat/enhance-prompt", json={"prompt": "a cat", "model": "x/y", "kind": "image"})
        assert r.status_code == 200
        assert r.json() == {"prompt": "A fluffy cat, golden hour", "cost": 0.001}

    def test_empty_reply_is_an_error(self, client, monkeypatch):
        """Test that empty reply is an error."""
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: iter([]))
        r = client.post("/api/chat/enhance-prompt", json={"prompt": "a cat", "model": "x/y"})
        assert r.status_code == 502


class TestEstimate:
    """Tests for estimate."""

    def test_pollo_estimate_asks_pollo_and_others_get_none(self, client, provider_keys, monkeypatch):
        """Test that pollo estimate asks pollo and others get none."""
        provider_keys["pollo"] = "pk-test"
        seen = {}

        def fake_ask(url, payload, api_key):
            seen.update(url=url, payload=payload, key=api_key)
            return {"credits": 8, "full_credits": 10}, True

        monkeypatch.setattr(pollo_estimate, "_ask", fake_ask)
        pollo_estimate.clear_cache()
        body = {"model": "pollo/seedance20fast", "kind": "video", "duration": 5, "resolution": "480p"}
        got = client.post("/api/chat/estimate", json=body).json()
        assert got == {"estimate": {"credits": 8, "full_credits": 10}}
        assert seen["url"].endswith("/estimate")
        assert seen["key"] == "pk-test"
        # a Ref model (legacy ref2video) has no estimate endpoint; other providers aren't priced here
        ref = client.post("/api/chat/estimate", json={**body, "model": "pollo/nonexistentref"}).json()
        assert ref == {"estimate": None}
        assert client.post("/api/chat/estimate", json={**body, "model": "venice/x"}).json() == {"estimate": None}


class TestSpendBreakdown:
    """Tests for spend breakdown."""

    def test_groups_by_model_and_converts_credits_to_usd(self, client, conv, db):
        """Test that groups by model and converts credits to usd."""
        db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            media=[
                {"id": "a", "kind": "video", "status": "done", "model": "pollo/seedance25", "credits": 10},
                {"id": "b", "kind": "video", "status": "done", "model": "pollo/seedance25", "credits": 5},
            ],
        )
        body = client.get("/api/chat/spend/breakdown").json()
        row = next(r for r in body["rows"] if r["model"] == "pollo/seedance25")
        assert row["credits"] == 15
        assert row["count"] == 2
        assert row["usd"] == 0.9
        assert body["total_usd"] >= 0.9
        assert client.get("/api/chat/spend/breakdown?days=7").status_code == 200


class TestTitleModel:
    """Tests for title model."""

    def test_setting_round_trips(self, client):
        """Test that setting round trips."""
        assert client.get("/api/chat/settings").json()["title_model"] is None
        r = client.put("/api/chat/settings/title-model", json={"title_model": "x/cheap"}).json()
        assert r["title_model"] == "x/cheap"
        # saving the default lists doesn't touch it
        assert client.put("/api/chat/settings", json={}).json()["title_model"] == "x/cheap"
        assert client.put("/api/chat/settings/title-model", json={"title_model": ""}).json()["title_model"] is None


class TestEditAndRewordInPlace:
    """Editing a picture on its card, and writing a reply's words again,.

    without re-running the turn that made them.
    """

    def _reply_with_image(self, db, conv, **extra):
        db.add_chat_message(conv["id"], "user", "draw a fox")
        return db.add_chat_message(
            conv["id"],
            "assistant",
            "Here is your fox.",
            model="t/model",
            media=[
                {
                    "id": "m1",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "img_old.png",
                    "prompt": "a fox",
                    "model": "i/model",
                    "cost": 0.02,
                    "params": {"aspect_ratio": "16:9", "resolution": None, "refs": ["img_ref.png"]},
                    **extra,
                }
            ],
        )

    def _reply(self, db, conv, **extra):
        msg = self._reply_with_image(db, conv, **extra)
        db.update_chat_message(msg.id, cost=0.01)  # the words it already cost
        # the files must really be there: generation drops references it can't find

        d = config.ROOT_DIR / "chat" / conv["id"]
        d.mkdir(parents=True, exist_ok=True)
        for name in ("img_old.png", "img_ref.png"):
            (d / name).write_bytes(_png_bytes())
        return msg

    def _inline(self, chat, monkeypatch):
        class Inline:
            def __init__(self, target, args, **kw):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        monkeypatch.setattr(threading, "Thread", Inline)

    def _capture(self, monkeypatch, got):
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (
                got.update(model=model, prompt=prompt, **kw),
                ([(_png_bytes(), "image/png")], 0.03),
            )[1],
        )

    def test_edit_sends_the_picture_back_and_replaces_it(self, client, conv, chat, db, monkeypatch):
        """Test that edit sends the picture back and replaces it."""
        msg = self._reply(db, conv)
        self._inline(chat, monkeypatch)
        got = {}
        self._capture(monkeypatch, got)
        r = client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate",
            json={"prompt": "give it a hat", "edit": True, "replace": True},
        )
        assert r.status_code == 200
        assert got["prompt"] == "give it a hat"
        media = db.get_chat_message(msg.id).media
        # the picture itself leads the references; the one it was made from is dropped
        assert media[0]["params"]["refs"] == ["img_old.png"]
        assert len(got["input_images"]) == 1
        assert len(media) == 1  # replaced, not added beside
        assert media[0]["id"] == "m1"
        assert media[0]["status"] == "done"
        assert media[0]["file"] != "img_old.png"
        assert media[0]["prompt"] == "give it a hat"

    def test_the_replaced_picture_is_kept_as_a_version(self, client, conv, chat, db, monkeypatch):
        """Test that the replaced picture is kept as a version."""
        msg = self._reply(db, conv)
        self._inline(chat, monkeypatch)
        self._capture(monkeypatch, {})
        client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate",
            json={"prompt": "give it a hat", "edit": True, "replace": True},
        )
        item = db.get_chat_message(msg.id).media[0]
        assert [v["file"] for v in item["versions"]] == ["img_old.png"]
        assert item["versions"][0]["prompt"] == "a fox"

    def test_an_earlier_version_is_not_treated_as_an_orphan(self, client, conv, chat, db, monkeypatch):
        """Its file must stay referenced, or the media sweep would offer to delete it."""
        msg = self._reply(db, conv)
        self._inline(chat, monkeypatch)
        self._capture(monkeypatch, {})
        client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate",
            json={"prompt": "give it a hat", "edit": True, "replace": True},
        )
        item = db.get_chat_message(msg.id).media[0]
        assert "img_old.png" in media_mod.referenced_files(item)

    def test_redo_re_rolls_the_prompt_without_the_picture(self, client, conv, chat, db, monkeypatch):
        """Test that redo re rolls the prompt without the picture."""
        msg = self._reply(db, conv)
        self._inline(chat, monkeypatch)
        got = {}
        self._capture(monkeypatch, got)
        client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate",
            json={"prompt": "a fox, wider shot", "replace": True},
        )
        assert got["prompt"] == "a fox, wider shot"
        # not an edit: the picture isn't sent back, the original reference stands
        assert db.get_chat_message(msg.id).media[0]["params"]["refs"] == ["img_ref.png"]

    def test_the_picture_showing_is_the_real_one(self, client, conv, chat, db, monkeypatch):
        """Going back to an earlier picture makes it the item's file, prompt and settings."""
        msg = self._reply(db, conv)
        self._inline(chat, monkeypatch)
        self._capture(monkeypatch, {})
        client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={"prompt": "a fox, wider", "replace": True}
        )
        new_file = db.get_chat_message(msg.id).media[0]["file"]
        out = client.post(f"/api/chat/messages/{msg.id}/media/m1/version", json={"index": 0}).json()
        item = out["media"][0]
        assert (item["file"], item["prompt"], item["version_shown"]) == ("img_old.png", "a fox", 0)
        assert [v["file"] for v in item["versions"]] == [new_file]
        # and forward again
        item = client.post(f"/api/chat/messages/{msg.id}/media/m1/version", json={"index": 1}).json()["media"][0]
        assert (item["file"], item["version_shown"]) == (new_file, 1)
        assert [v["file"] for v in item["versions"]] == ["img_old.png"]

    def test_a_redo_from_an_earlier_picture_goes_last(self, client, conv, chat, db, monkeypatch):
        """With version 1 of 2 showing, a redo becomes version 3, keeping both."""
        msg = self._reply(db, conv)
        self._inline(chat, monkeypatch)
        self._capture(monkeypatch, {})
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={"prompt": "b", "replace": True})
        second = db.get_chat_message(msg.id).media[0]["file"]
        client.post(f"/api/chat/messages/{msg.id}/media/m1/version", json={"index": 0})
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={"prompt": "c", "replace": True})
        item = db.get_chat_message(msg.id).media[0]
        assert [v["file"] for v in item["versions"]] == ["img_old.png", second]
        assert item["version_shown"] == 2
        assert item["prompt"] == "c"

    def test_switching_keeps_every_charge(self, client, conv, chat, db):
        """Swapping which picture is live doesn't change what the chat spent."""
        msg = self._reply(db, conv, credits=5, versions=[{"file": "img_a.png", "credits": 3}])
        before = db.get_chat_spend(conv["id"])
        client.post(f"/api/chat/messages/{msg.id}/media/m1/version", json={"index": 0})
        assert db.get_chat_spend(conv["id"]) == before

    def test_a_failed_attempt_still_counts_after_going_back(self, client, conv, chat, db):
        """Pollo bills a failed generation: its credits stay in the spend when the card goes back."""
        msg = self._reply(
            db, conv, file=None, status="error", error="nope", credits=4, versions=[{"file": "img_a.png", "credits": 3}]
        )
        out = client.post(f"/api/chat/messages/{msg.id}/media/m1/version", json={"index": 0}).json()
        assert out["media"][0]["file"] == "img_a.png"
        assert out["media"][0]["status"] == "done"
        assert db.get_chat_spend(conv["id"])[1] == 7

    def test_no_switching_while_it_is_being_made(self, client, conv, chat, db):
        """Test that a pending card can't be switched."""
        msg = self._reply(db, conv, status="pending", versions=[{"file": "img_a.png"}])
        r = client.post(f"/api/chat/messages/{msg.id}/media/m1/version", json={"index": 0})
        assert r.status_code == 409

    def test_editing_without_a_picture_is_refused(self, client, conv, chat, db):
        """Test that editing without a picture is refused."""
        msg = self._reply(db, conv, file=None, status="error", error="nope")
        r = client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={"prompt": "x", "edit": True, "replace": True}
        )
        assert r.status_code == 400

    def test_gallery_re_roll_still_adds_a_second_picture(self, client, conv, chat, db, monkeypatch):
        """Without `replace` the old behaviour stands, for the gallery."""
        msg = self._reply(db, conv)
        self._inline(chat, monkeypatch)
        self._capture(monkeypatch, {})
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={})
        media = db.get_chat_message(msg.id).media
        assert len(media) == 2
        assert media[0]["file"] == "img_old.png"

    def test_reword_replaces_the_words_and_keeps_the_picture(self, client, conv, chat, db, monkeypatch):
        """Test that reword replaces the words and keeps the picture."""
        msg = self._reply(db, conv)
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("A fox, as requested."))
        monkeypatch.setattr(
            openrouter, "generate_image", lambda *a, **k: pytest.fail("rewording must not remake the picture")
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/reword", json={"message_id": msg.id, **SETTINGS}))
        after = db.get_chat_message(msg.id)
        assert after.content == "A fox, as requested."
        assert len(after.media) == 1
        assert after.media[0]["file"] == "img_old.png"

    def test_reword_keeps_everything_the_reply_cost(self, client, conv, chat, db, monkeypatch):
        """The old words were paid for (and stay as a version), so their cost stays in the total."""
        msg = self._reply(db, conv)
        db.update_chat_message(msg.id, cost=0.03)  # 0.01 of words + the picture's 0.02
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("Reworded."))
        _events(client.post(f"/api/chat/conversations/{conv['id']}/reword", json={"message_id": msg.id, **SETTINGS}))
        assert db.get_chat_message(msg.id).cost == 0.031

    def test_reword_keeps_the_old_words_as_a_version(self, client, conv, chat, db, monkeypatch):
        """Redo text files both wordings, and the arrows switch between them."""
        msg = self._reply(db, conv)
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("A new telling."))
        _events(client.post(f"/api/chat/conversations/{conv['id']}/reword", json={"message_id": msg.id, **SETTINGS}))
        after = db.get_chat_message(msg.id)
        assert after.to_dict()["text_versions"] == 2
        assert after.to_dict()["text_shown"] == 1
        back = client.post(f"/api/chat/messages/{msg.id}/text-version", json={"index": 0}).json()
        assert back["content"] == "Here is your fox."
        assert back["text_shown"] == 0
        # the picture is untouched by switching words
        assert back["media"][0]["file"] == "img_old.png"
        assert db.get_chat_message(msg.id).content == "Here is your fox."

    def test_a_failed_reword_adds_no_version(self, client, conv, chat, db, monkeypatch):
        """Nothing came back: the old words return and no empty version is filed."""
        msg = self._reply(db, conv)
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks(""))
        _events(client.post(f"/api/chat/conversations/{conv['id']}/reword", json={"message_id": msg.id, **SETTINGS}))
        assert db.get_chat_message(msg.id).to_dict()["text_versions"] == 0

    def test_edit_text_sends_the_old_words_and_the_instruction(self, client, conv, chat, db, monkeypatch):
        """Edit text: the model sees its reply and how to change it."""
        msg = self._reply(db, conv)
        sent = {}

        def fake(model, messages, *a, **k):
            sent["messages"] = messages
            return _text_chunks("A shorter fox.")

        monkeypatch.setattr(openrouter, "stream_chat", fake)
        body = {"message_id": msg.id, "instruction": "make it shorter", **SETTINGS}
        _events(client.post(f"/api/chat/conversations/{conv['id']}/reword", json=body))
        assert sent["messages"][-2] == {"role": "assistant", "content": "Here is your fox."}
        assert "make it shorter" in sent["messages"][-1]["content"]
        assert db.get_chat_message(msg.id).content == "A shorter fox."

    def test_switching_words_is_refused_mid_reply(self, client, conv, chat, db):
        """Test that the wording can't be switched while the reply streams."""
        msg = self._reply(db, conv)
        db.update_chat_message(
            msg.id, status="streaming", text_versions_json='{"items": [{"content": "a"}, {"content": "b"}], "shown": 1}'
        )
        r = client.post(f"/api/chat/messages/{msg.id}/text-version", json={"index": 0})
        assert r.status_code == 409

    def test_replaced_pictures_still_count_towards_spend(self, conv, db):
        """A redone picture's credits move into `versions`; they were still billed."""
        db.add_chat_message(conv["id"], "user", "draw")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            media=[
                {
                    "id": "m1",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "b.png",
                    "credits": 5,
                    "versions": [{"file": "a.png", "credits": 3}],
                }
            ],
        )
        assert db.get_chat_spend(conv["id"])[1] == 8

    def test_a_pollo_charge_is_credits_or_dollars_not_both(self, conv, db):
        """Pollo's costUsd is its credits converted: an item carrying both is charged once, in credits."""
        db.add_chat_message(conv["id"], "user", "draw")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            media=[
                {
                    "id": "m1",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "b.png",
                    "credits": 5,
                    "cost": 0.3,
                    "versions": [{"file": "a.png", "credits": 3, "cost": 0.18}],
                }
            ],
        )
        [row] = db.spend_rows([conv["id"]])
        assert (row["usd"], row["credits"]) == (0.0, 8)

    def test_reword_puts_the_old_words_back_if_nothing_comes_out(self, client, conv, chat, db, monkeypatch):
        """Test that reword puts the old words back if nothing comes out."""
        msg = self._reply(db, conv)
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks(""))
        _events(client.post(f"/api/chat/conversations/{conv['id']}/reword", json={"message_id": msg.id, **SETTINGS}))
        assert db.get_chat_message(msg.id).content == "Here is your fox."

    def test_reword_refuses_a_user_message(self, client, conv, chat, db):
        """Test that reword refuses a user message."""
        db.add_chat_message(conv["id"], "user", "hello")
        user = db.get_chat_messages(conv["id"])[-1]
        r = client.post(f"/api/chat/conversations/{conv['id']}/reword", json={"message_id": user.id, **SETTINGS})
        assert r.status_code == 400


class TestRetryAFailedPicture:
    """A failed generation can be run again with a changed prompt, and leaves.

    no empty version behind.
    """

    def _failed(self, db, conv):
        db.add_chat_message(conv["id"], "user", "draw a fox")
        return db.add_chat_message(
            conv["id"],
            "assistant",
            "Sorry.",
            model="t/model",
            media=[
                {
                    "id": "m1",
                    "kind": "image",
                    "source": "generated",
                    "status": "error",
                    "error": "flagged",
                    "prompt": "a fox",
                    "model": "i/model",
                    "params": {"aspect_ratio": "16:9", "resolution": None, "refs": []},
                }
            ],
        )

    def _inline(self, monkeypatch):
        class Inline:
            def __init__(self, target, args, **kw):
                """Document the   init   test helper."""
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        monkeypatch.setattr(threading, "Thread", Inline)

    def test_a_changed_prompt_is_used(self, client, conv, chat, db, monkeypatch):
        """Test that a changed prompt is used."""
        msg = self._failed(db, conv)
        self._inline(monkeypatch)
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(prompt=prompt), ([(_png_bytes(), "image/png")], 0.01))[1],
        )
        r = client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate",
            json={"prompt": "a fox, softer lighting", "replace": True},
        )
        assert r.status_code == 200
        assert got["prompt"] == "a fox, softer lighting"
        item = db.get_chat_message(msg.id).media[0]
        assert item["status"] == "done"
        assert item["prompt"] == "a fox, softer lighting"

    def test_it_leaves_no_empty_version(self, client, conv, chat, db, monkeypatch):
        """There was no picture, so there is nothing to flip back to."""
        msg = self._failed(db, conv)
        self._inline(monkeypatch)
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], 0.01)
        )
        client.post(f"/api/chat/messages/{msg.id}/media/m1/regenerate", json={"prompt": "try again", "replace": True})
        assert db.get_chat_message(msg.id).media[0].get("versions") in (None, [])

    def test_editing_a_failed_picture_is_still_refused(self, client, conv, chat, db):
        """`edit` needs a picture to send back; a failure has none."""
        msg = self._failed(db, conv)
        r = client.post(
            f"/api/chat/messages/{msg.id}/media/m1/regenerate",
            json={"prompt": "x", "edit": True, "replace": True},
        )
        assert r.status_code == 400


def test_a_webm_attachment_is_recorded_as_a_video(client, conv, chat, db):
    """Attachment kind comes from web.media_types now. Only ".mp4" counted.

    before, so a .webm or .mov clip was recorded as an image.
    """
    d = config.ROOT_DIR / "chat" / conv["id"]
    d.mkdir(parents=True, exist_ok=True)
    for name in ("upv_clip.webm", "upa_voice.ogg", "up_pic.png"):
        (d / name).write_bytes(b"fake")
    _events(
        client.post(
            f"/api/chat/conversations/{conv['id']}/messages",
            json={
                "content": "look",
                "attachments": ["upv_clip.webm", "upa_voice.ogg", "up_pic.png"],
                "mode": "text",
                **SETTINGS,
            },
        )
    )
    user = next(m for m in db.get_chat_messages(conv["id"]) if m.role == "user")
    assert [i["kind"] for i in user.media] == ["video", "audio", "image"]


class TestNoDoubleCharges:
    """Guards against paying twice for one request."""

    def test_a_second_send_while_a_reply_streams_is_refused(self, client, conv, db):
        """A double-clicked Send (or a second tab) can't start a second paid turn."""
        db.add_chat_message(conv["id"], "user", "hi")
        db.add_chat_message(conv["id"], "assistant", "", status="streaming")
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/messages", json={"content": "again", "mode": "auto", **SETTINGS}
        )
        assert r.status_code == 409

    def test_gallery_sends_still_run_side_by_side(self, client, conv, db, monkeypatch):
        """Gallery exchanges never wait on the chat."""
        db.add_chat_message(conv["id"], "user", "hi")
        db.add_chat_message(conv["id"], "assistant", "", status="streaming")
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: _text_chunks("ok"))
        r = client.post(
            f"/api/chat/conversations/{conv['id']}/messages",
            json={"content": "x", "mode": "text", "lane": "gallery", **SETTINGS},
        )
        assert r.status_code == 200

    def test_a_repeated_identical_tool_call_is_not_made_twice(self, client, conv, chat, monkeypatch):
        """A model repeating the same generate_image call word for word is only billed once."""
        args = {"prompt": "a cat"}
        rounds = iter(
            [_tool_chunks("generate_image", args), _tool_chunks("generate_image", args), _text_chunks("Done.")]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(rounds))
        made = []
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (made.append(prompt), ([(_png_bytes(), "image/png")], 0.04))[1],
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "draw a cat", "mode": "auto", **SETTINGS},
            )
        )
        assert made == ["a cat"]
        assert len(ev[-1]["message"]["media"]) == 1
