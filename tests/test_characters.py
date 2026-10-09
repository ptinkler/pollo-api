"""Tests for web.characters — characters shared by chat and generations."""

import json
from unittest.mock import patch

import pytest

from tests.test_chat import (  # noqa: F401
    SETTINGS,
    _events,
    _png_bytes,
    _text_chunks,
    _tool_chunks,
    chat,
    client,
    conv,
    db,
)


def _make(client, name="Linh", description="Short black hair, red scarf", images=1, **extra):
    c = client.post("/api/characters", json={"name": name, "description": description, **extra}).json()
    for i in range(images):
        c = client.post(
            f"/api/characters/{c['id']}/images",
            files={"file": (f"{i}.png", _png_bytes(color=(i * 50, 0, 0)), "image/png")},
        ).json()
    return c


class TestManagement:
    def test_crud(self, client):
        c = _make(client, images=2)
        assert c["name"] == "Linh" and len(c["images"]) == 2 and c["adhoc"] is False
        img = client.get(f"/api/characters/{c['id']}/images/{c['images'][0]}")
        assert img.status_code == 200 and img.headers["content-type"] == "image/png"

        r = client.patch(f"/api/characters/{c['id']}", json={"name": " Linh Tran ", "images": [c["images"][1]]})
        assert r.json()["name"] == "Linh Tran" and r.json()["images"] == [c["images"][1]]
        # The dropped image's file is gone
        assert client.get(f"/api/characters/{c['id']}/images/{c['images'][0]}").status_code == 404

        assert client.delete(f"/api/characters/{c['id']}").status_code == 200
        assert client.get(f"/api/characters/{c['id']}").status_code == 404

    def test_unknown_image_in_reorder_is_rejected(self, client):
        c = _make(client)
        assert client.patch(f"/api/characters/{c['id']}", json={"images": ["nope.png"]}).status_code == 400

    def test_image_limit(self, client, monkeypatch):
        import web.characters as characters_mod

        monkeypatch.setattr(characters_mod, "MAX_IMAGES", 1)
        c = _make(client)
        r = client.post(f"/api/characters/{c['id']}/images", files={"file": ("a.png", _png_bytes(), "image/png")})
        assert r.status_code == 400

    def test_copy_image_from_chat(self, client, conv, chat):
        (chat._conv_dir(conv["id"]) / "g.png").write_bytes(_png_bytes())
        c = _make(client, images=0)
        r = client.post(
            f"/api/characters/{c['id']}/images/from-chat", json={"conversation_id": conv["id"], "file": "g.png"}
        )
        assert len(r.json()["images"]) == 1
        bad = client.post(
            f"/api/characters/{c['id']}/images/from-chat", json={"conversation_id": conv["id"], "file": "../x.png"}
        )
        assert bad.status_code == 400

    def test_adhoc_characters_belong_to_their_chat(self, client, conv, db):
        other = client.post("/api/chat/conversations", json={}).json()
        saved = _make(client, name="Saved", images=0)
        adhoc = _make(client, name="Adhoc", images=0, conversation_id=conv["id"])
        assert adhoc["adhoc"] is True
        # Created in a chat = attached to it
        assert db.get_conversation(conv["id"]).character_ids == [adhoc["id"]]

        names = lambda q: [c["name"] for c in client.get(f"/api/characters{q}").json()["characters"]]  # noqa: E731
        assert names(f"?conversation_id={conv['id']}") == ["Adhoc", "Saved"]
        assert names(f"?conversation_id={other['id']}") == ["Saved"]
        assert names("?include_adhoc=true") == ["Adhoc", "Saved"]
        assert saved["adhoc"] is False

    def test_promote(self, client, conv):
        adhoc = _make(client, images=0, conversation_id=conv["id"])
        r = client.post(f"/api/characters/{adhoc['id']}/promote").json()
        assert r["adhoc"] is False and r["conversation_id"] is None
        # Promoted characters survive their chat
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert client.get(f"/api/characters/{adhoc['id']}").status_code == 200

    def test_deleting_a_chat_deletes_its_adhoc_characters(self, client, conv):
        adhoc = _make(client, conversation_id=conv["id"])
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert client.get(f"/api/characters/{adhoc['id']}").status_code == 404

    def test_attach_to_chat(self, client, conv):
        c = _make(client, images=0)
        r = client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [c["id"]]})
        assert r.json()["character_ids"] == [c["id"]]
        assert client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [999]}).status_code == 400
        # Deleting a character detaches it
        client.delete(f"/api/characters/{c['id']}")
        assert client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["character_ids"] == []


class TestInChat:
    def _attach(self, client, conv, *chars):
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [c["id"] for c in chars]})

    def _capture(self, chat, monkeypatch):
        got = {}
        monkeypatch.setattr(
            chat.openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        return got

    def test_chat_model_is_told_and_tool_lists_names(self, client, conv, chat, monkeypatch):
        linh = _make(client)
        self._attach(client, conv, linh)
        seen = {}

        def stream(model, messages, tools=None, **kw):
            seen.update(messages=messages, tools=tools)
            return _text_chunks("Hi")

        monkeypatch.setattr(chat.openrouter, "stream_chat", stream)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        system = " ".join(m["content"] for m in seen["messages"] if m["role"] == "system")
        assert "Linh: Short black hair, red scarf" in system
        image_tool = next(t for t in seen["tools"] if t["function"]["name"] == "generate_image")
        assert image_tool["function"]["parameters"]["properties"]["characters"]["items"]["enum"] == ["Linh"]

    def test_named_character_sends_description_and_images(self, client, conv, chat, monkeypatch):
        linh, bao = _make(client, images=2), _make(client, name="Bao", description="Tall", images=1)
        self._attach(client, conv, linh, bao)
        replies = iter(
            [
                _tool_chunks("generate_image", {"prompt": "Linh at the beach", "characters": ["linh"]}, text="Here."),
                _text_chunks("Done."),
            ]
        )
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        item = ev[-1]["message"]["media"][0]
        assert item["prompt"] == "Linh at the beach"  # stored as the model wrote it
        assert "Linh: Short black hair" in got["prompt"] and "Bao" not in got["prompt"]
        assert item["params"]["refs"] == [f"char:{linh['id']}/{f}" for f in linh["images"]]
        assert item["params"]["characters"] == [linh["id"]]
        assert len(got["input_images"]) == 2

    def _overlapping_names(self, client, conv):
        chloe = _make(client, name="Chloe", description="Slim")
        muscle = _make(client, name="Chloe Muscle", description="Bodybuilder")
        self._attach(client, conv, muscle)
        return chloe, muscle

    def _attached_ids(self, client, conv):
        return client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["character_ids"]

    def test_short_name_means_the_attached_character_in_auto_mode(self, client, conv, chat, monkeypatch):
        chloe, muscle = self._overlapping_names(client, conv)
        # The model calls her by the short name, in the argument and its prompt
        replies = iter(
            [
                _tool_chunks("generate_image", {"prompt": "Chloe flexing", "characters": ["Chloe"]}, text="Here."),
                _text_chunks("Done."),
            ]
        )
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "create an image of chloe", **SETTINGS},
            )
        )
        assert ev[-1]["message"]["media"][0]["params"]["characters"] == [muscle["id"]]
        assert "Bodybuilder" in got["prompt"] and "Slim" not in got["prompt"]
        assert self._attached_ids(client, conv) == [muscle["id"]]

    def test_short_name_is_ignored_when_ambiguous(self, client, conv, chat, monkeypatch):
        a, b = _make(client, name="Chloe Muscle"), _make(client, name="Chloe Slim")
        self._attach(client, conv, a, b)
        replies = iter(
            [_tool_chunks("generate_image", {"prompt": "Chloe waving", "characters": ["Chloe"]}), _text_chunks("Done.")]
        )
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert "characters" not in ev[-1]["message"]["media"][0]["params"]

    def test_full_name_in_prompt_does_not_also_match_the_shorter_one(self, client, conv, chat, monkeypatch):
        chloe, muscle = _make(client, name="Chloe"), _make(client, name="Chloe Muscle")
        self._attach(client, conv, chloe, muscle)
        replies = iter([_tool_chunks("generate_image", {"prompt": "Chloe Muscle at the gym"}), _text_chunks("Done.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert ev[-1]["message"]["media"][0]["params"]["characters"] == [muscle["id"]]

    def test_image_mode_uses_every_attached_character(self, client, conv, chat, monkeypatch):
        linh, bao = _make(client), _make(client, name="Bao", images=1)
        self._attach(client, conv, linh, bao)
        got = self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "both at the park", **SETTINGS, "mode": "image"},
            )
        )
        item = ev[-1]["message"]["media"][0]
        assert item["params"]["refs"] == [
            f"char:{linh['id']}/{linh['images'][0]}",
            f"char:{bao['id']}/{bao['images'][0]}",
        ]
        assert "Linh:" in got["prompt"] and "- Bao" in got["prompt"]

    def test_character_images_come_before_pins_and_recent_picks(self, client, conv, chat, db, monkeypatch):
        """The priority when a model takes fewer images than that (Venice edit models keep the first N)."""
        linh = _make(client)
        self._attach(client, conv, linh)
        (chat._conv_dir(conv["id"]) / "g.png").write_bytes(_png_bytes())
        db.add_chat_message(conv["id"], "user", "x")
        msg = db.add_chat_message(
            conv["id"],
            "assistant",
            "",
            media=[
                {"id": "g", "kind": "image", "source": "generated", "status": "done", "file": "g.png", "prompt": "p"}
            ],
        )
        client.post(f"/api/chat/messages/{msg.id}/media/g/pin", json={"pinned": True})
        replies = iter([_tool_chunks("generate_image", {"prompt": "Linh", "characters": ["Linh"]}), _text_chunks("ok")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert ev[-1]["message"]["media"][0]["params"]["refs"] == [f"char:{linh['id']}/{linh['images'][0]}", "g.png"]

    def test_character_refs_are_shared_round_robin(self, chat, client):
        a, b = _make(client, name="A", images=3), _make(client, name="B", images=3)
        import web.characters as characters_mod

        refs = characters_mod.reference_refs(characters_mod.load([a["id"], b["id"]]), 3)
        assert refs == [
            f"char:{a['id']}/{a['images'][0]}",
            f"char:{b['id']}/{b['images'][0]}",
            f"char:{a['id']}/{a['images'][1]}",
        ]

    def test_video_mode_does_not_use_characters(self, client, conv, chat, monkeypatch):
        linh = _make(client)
        self._attach(client, conv, linh)
        sent = {}
        monkeypatch.setattr(
            chat.openrouter, "submit_video", lambda model, prompt, **kw: (sent.update(prompt=prompt), {"id": "job1"})[1]
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "Linh dancing", **SETTINGS, "mode": "video"},
            )
        )
        assert sent["prompt"] == "Linh dancing"

    def test_image_model_without_references_does_not_use_characters(self, client, conv, chat, db, monkeypatch):
        chat._models_cache.update(
            at=9e18, data={"text": [], "video": [], "image": [{"id": "i/model", "input_modalities": ["text"]}]}
        )
        linh = _make(client)
        self._attach(client, conv, linh)
        got = self._capture(chat, monkeypatch)
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "Linh on a bike", **SETTINGS, "mode": "image"},
            )
        )
        assert got["prompt"] == "Linh on a bike"
        # Still attached, for when a model that can use it is picked again
        assert db.get_conversation(conv["id"]).character_ids == [linh["id"]]

    def test_chat_model_without_tools_is_not_told_in_auto(self, client, conv, chat, monkeypatch):
        chat._models_cache.update(
            at=9e18,
            data={
                "image": [],
                "video": [],
                "text": [{"id": "t/model", "supports_tools": False, "input_modalities": ["text"]}],
            },
        )
        self._attach(client, conv, _make(client))
        seen = {}
        monkeypatch.setattr(
            chat.openrouter,
            "stream_chat",
            lambda model, messages, tools=None, **kw: (seen.update(m=messages), _text_chunks("Hi"))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        assert not any("Linh" in str(m["content"]) for m in seen["m"] if m["role"] == "system")

    def test_chat_mode_tells_the_chat_model(self, client, conv, chat, monkeypatch):
        self._attach(client, conv, _make(client))
        seen = {}
        monkeypatch.setattr(
            chat.openrouter,
            "stream_chat",
            lambda model, messages, tools=None, **kw: (seen.update(m=messages), _text_chunks("Hi"))[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS, "mode": "text"}
            )
        )
        assert any("Linh: Short black hair" in m["content"] for m in seen["m"] if m["role"] == "system")


class TestInGenerations:
    @pytest.fixture()
    def project(self, db, tmp_path, monkeypatch):
        import web.api as api_mod

        monkeypatch.setattr(api_mod, "ASSETS_DIR", tmp_path / "assets")
        monkeypatch.setattr(api_mod, "get_db", lambda: db)
        api_mod._project_lookup_cache.clear()
        proj = db.create_project(name="Chars")
        (api_mod.ASSETS_DIR / proj.assets_folder).mkdir(parents=True, exist_ok=True)
        return proj

    @pytest.fixture()
    def uploads(self, monkeypatch):
        from web import image_hosts

        sent = []
        monkeypatch.setattr(image_hosts, "upload_image", lambda p: (sent.append(p), f"https://tmp/{p.name}")[1])
        return sent

    def _job(self, db, resp):
        assert resp.status_code == 200, resp.text
        job = db.get_job(resp.json()["job_id"])
        return job, json.loads(job.params_json)

    @patch("web.api.threading.Thread")
    def test_image_generation(self, thread, client, db, project, uploads):
        linh = _make(client, images=2)
        r = client.post(
            "/api/generate-image",
            json={
                "model": "seedream",
                "project": project.slug,
                "prompt": "Linh reading",
                "character_ids": [linh["id"]],
            },
        )
        job, params = self._job(db, r)
        kwargs = thread.call_args.kwargs["args"][2]
        assert job.prompt == "Linh reading" and params["character_ids"] == [linh["id"]]
        assert "Short black hair" in kwargs["prompt"]
        assert kwargs["images"] == [f"https://tmp/{f}" for f in linh["images"]]

    @patch("web.api.threading.Thread")
    def test_unknown_character_is_400(self, thread, client, project):
        r = client.post(
            "/api/generate-image",
            json={"model": "seedream", "project": project.slug, "prompt": "x", "character_ids": [999]},
        )
        assert r.status_code == 400

    @patch("web.api.threading.Thread")
    def test_video_outside_ref_mode_gets_description_only(self, thread, client, db, project, uploads):
        linh = _make(client)
        r = client.post(
            "/api/generate",
            json={
                "model": "seedance20v1",
                "project": project.slug,
                "prompt": "Linh waves",
                "image_url": "https://img/x.jpg",
                "character_ids": [linh["id"]],
            },
        )
        self._job(db, r)
        kwargs = thread.call_args.kwargs["args"][2]
        assert "Short black hair" in kwargs["prompt"] and "refs" not in kwargs and not uploads

    @patch("web.api.threading.Thread")
    def test_v1_ref_mode_adds_character_refs(self, thread, client, db, project, uploads):
        linh = _make(client, images=2)
        r = client.post(
            "/api/generate",
            json={
                "model": "seedance20v1",
                "project": project.slug,
                "prompt": "Linh waves",
                "ref_mode": True,
                "refs": [],
                "character_ids": [linh["id"]],
            },
        )
        job, params = self._job(db, r)
        kwargs = thread.call_args.kwargs["args"][2]
        assert [r["url"] for r in kwargs["refs"]] == [f"https://tmp/{f}" for f in linh["images"]]
        assert all(r["_character"].startswith("char:") for r in params["refs"])
        assert kwargs["image_url"] is None

    @patch("web.api.threading.Thread")
    def test_legacy_ref_model_names_character_refs(self, thread, client, db, project, uploads):
        linh = _make(client)
        r = client.post(
            "/api/generate",
            json={
                "model": "seedanceref",
                "project": project.slug,
                "prompt": "Linh waves",
                "character_ids": [linh["id"]],
                "refs": [{"type": "image", "name": "bg", "image": "https://x/bg.jpg", "order": 1}],
            },
        )
        self._job(db, r)
        refs = thread.call_args.kwargs["args"][2]["refs"]
        assert refs[1]["name"] == "Linh" and refs[1]["order"] == 2 and refs[1]["image"].startswith("https://tmp/")


class TestUseByName:
    """Only characters the user attached are used — a name coming up never attaches one."""

    def _capture(self, chat, monkeypatch):
        got = {}
        monkeypatch.setattr(
            chat.openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        return got

    def test_model_is_not_told_about_unattached_characters(self, client, conv, chat, monkeypatch):
        _make(client, name="Linh")
        seen = {}

        def stream(model, messages, tools=None, **kw):
            seen.update(messages=messages, tools=tools)
            return _text_chunks("Hi")

        monkeypatch.setattr(chat.openrouter, "stream_chat", stream)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        assert "Linh" not in json.dumps(seen["messages"]) and "Linh" not in json.dumps(seen["tools"])

    def test_naming_an_unattached_character_neither_uses_nor_attaches_it(self, client, conv, chat, db, monkeypatch):
        _make(client)
        replies = iter(
            [
                _tool_chunks("generate_image", {"prompt": "Linh at the beach", "characters": ["Linh"]}),
                _text_chunks("Here she is."),
            ]
        )
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "use Linh, at the beach", **SETTINGS}
            )
        )
        assert "Short black hair" not in got["prompt"] and not got.get("input_images")
        assert not any(e["type"] == "characters" for e in ev)
        assert db.get_conversation(conv["id"]).character_ids == []

    def test_image_mode_ignores_unattached_names(self, client, conv, chat, db, monkeypatch):
        _make(client)
        self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "linh on a bike", **SETTINGS, "mode": "image"},
            )
        )
        assert "characters" not in ev[-1]["message"]["media"][0]["params"]
        assert db.get_conversation(conv["id"]).character_ids == []

    def test_name_in_the_prompt_counts_when_the_model_forgets_the_argument(self, client, conv, chat, monkeypatch):
        linh = _make(client)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [linh["id"]]})
        replies = iter([_tool_chunks("generate_image", {"prompt": "Linh reading in a café"}), _text_chunks("Done.")])
        monkeypatch.setattr(chat.openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert ev[-1]["message"]["media"][0]["params"]["characters"] == [linh["id"]]

    def test_create_character_from_the_latest_image_then_draw_them(self, client, conv, chat, db, monkeypatch):
        (chat._conv_dir(conv["id"]) / "g.png").write_bytes(_png_bytes())
        db.add_chat_message(conv["id"], "user", "draw a girl")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "Here.",
            media=[
                {
                    "id": "g",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": "g.png",
                    "prompt": "a girl",
                }
            ],
        )
        tools_seen = []

        def stream(model, messages, tools=None, **kw):
            tools_seen.append(tools)
            return next(replies)

        replies = iter(
            [
                _tool_chunks("create_character", {"name": "Mai", "description": "Freckles, yellow raincoat"}),
                _tool_chunks("generate_image", {"prompt": "Mai in the rain", "characters": ["Mai"]}, call_id="c2"),
                _text_chunks("Here's Mai again."),
            ]
        )
        monkeypatch.setattr(chat.openrouter, "stream_chat", stream)
        got = self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "make her a character called Mai and draw her in the rain", **SETTINGS},
            )
        )
        mai = next(c for c in db.list_characters() if c.name == "Mai")
        assert mai.conversation_id == conv["id"] and len(mai.images) == 1  # ad hoc, from g.png
        # The second round's tool offers Mai by name
        enum = next(t for t in tools_seen[1] if t["function"]["name"] == "generate_image")
        assert "Mai" in enum["function"]["parameters"]["properties"]["characters"]["items"]["enum"]
        assert "Freckles" in got["prompt"]
        assert ev[-1]["message"]["media"][0]["params"]["refs"] == [f"char:{mai.id}/{mai.images[0]}"]

    def test_create_character_needs_an_image_and_a_new_name(self, client, conv, chat, monkeypatch):
        _make(client, name="Linh")
        replies = iter(
            [
                _tool_chunks("create_character", {"name": "Mai", "description": "x"}),
                _tool_chunks("create_character", {"name": "linh", "description": "x"}, call_id="c2"),
                _text_chunks("Sorry."),
            ]
        )
        results = []

        def stream(model, messages, tools=None, **kw):
            results.extend(json.loads(m["content"]) for m in messages if m["role"] == "tool")
            return next(replies)

        monkeypatch.setattr(chat.openrouter, "stream_chat", stream)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert "no image" in results[0]["error"]
        assert "already a character called linh" in results[-1]["error"]


class TestReferenceCaps:
    """Chat images are capped by the image slider (default 6); character images never are."""

    def test_every_character_image_is_sent_beyond_the_chat_cap(self, client, conv, chat, db, monkeypatch):
        linh, bao = _make(client, images=5), _make(client, name="Bao", images=4)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [linh["id"], bao["id"]]})
        # 8 pinned chat images: only the slider's number of them go
        db.add_chat_message(conv["id"], "user", "pics")
        for i in range(8):
            (chat._conv_dir(conv["id"]) / f"p{i}.png").write_bytes(_png_bytes())
        db.add_chat_message(
            conv["id"],
            "assistant",
            "ok",
            media=[
                {
                    "id": f"p{i}",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": f"p{i}.png",
                    "prompt": "x",
                    "pinned": True,
                }
                for i in range(8)
            ],
        )
        got = {}
        monkeypatch.setattr(
            chat.openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "both", **SETTINGS, "mode": "image"}
            )
        )
        refs = ev[-1]["message"]["media"][0]["params"]["refs"]
        char_refs = [r for r in refs if r.startswith("char:")]
        assert len(char_refs) == 9  # all 5 + 4
        assert char_refs[:2] == [f"char:{linh['id']}/{linh['images'][0]}", f"char:{bao['id']}/{bao['images'][0]}"]
        assert len(refs) - len(char_refs) == chat.DEFAULT_IMAGE_LIMIT
        assert len(got["input_images"]) == 9 + chat.DEFAULT_IMAGE_LIMIT

    def test_slider_raises_the_chat_image_cap(self, client, conv, chat, db, monkeypatch):
        db.add_chat_message(conv["id"], "user", "pics")
        for i in range(8):
            (chat._conv_dir(conv["id"]) / f"p{i}.png").write_bytes(_png_bytes())
        db.add_chat_message(
            conv["id"],
            "assistant",
            "ok",
            media=[
                {
                    "id": f"p{i}",
                    "kind": "image",
                    "source": "generated",
                    "status": "done",
                    "file": f"p{i}.png",
                    "prompt": "x",
                    "pinned": True,
                }
                for i in range(8)
            ],
        )
        monkeypatch.setattr(
            chat.openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "go", **SETTINGS, "mode": "image", "image_limit": None},
            )
        )
        assert len(ev[-1]["message"]["media"][0]["params"]["refs"]) == 8

    @patch("web.api.threading.Thread")
    def test_generate_sends_every_character_image(self, thread, client, db, tmp_path, monkeypatch):
        import web.api as api_mod
        from web import image_hosts

        monkeypatch.setattr(api_mod, "ASSETS_DIR", tmp_path / "assets")
        monkeypatch.setattr(api_mod, "get_db", lambda: db)
        monkeypatch.setattr(image_hosts, "upload_image", lambda p: f"https://tmp/{p.name}")
        proj = db.create_project(name="Caps")
        linh = _make(client, images=6)
        r = client.post(
            "/api/generate-image",
            json={"model": "seedream", "project": proj.slug, "prompt": "Linh", "character_ids": [linh["id"]]},
        )
        assert r.status_code == 200
        assert len(thread.call_args.kwargs["args"][2]["images"]) == 6
