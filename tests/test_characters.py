"""Tests for web.characters — characters shared by chat and generations."""

import json

import web.characters as characters_mod
from tests.chat_fixtures import SETTINGS, _events, _png_bytes, _text_chunks, _tool_chunks
from web.providers import openrouter

pytest_plugins = ["tests.chat_fixtures"]


def _make(client, name="Linh", description="Short black hair, red scarf", images=1, **extra):
    c = client.post("/api/characters", json={"name": name, "description": description, **extra}).json()
    for i in range(images):
        c = client.post(
            f"/api/characters/{c['id']}/images",
            files={"file": (f"{i}.png", _png_bytes(color=(i * 50, 0, 0)), "image/png")},
        ).json()
    return c


class TestManagement:
    """Tests for management."""

    def test_crud(self, client):
        """Test that crud."""
        c = _make(client, images=2)
        assert c["name"] == "Linh"
        assert len(c["images"]) == 2
        assert c["adhoc"] is False
        img = client.get(f"/api/characters/{c['id']}/images/{c['images'][0]}")
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/png"

        r = client.patch(f"/api/characters/{c['id']}", json={"name": " Linh Tran ", "images": [c["images"][1]]})
        assert r.json()["name"] == "Linh Tran"
        assert r.json()["images"] == [c["images"][1]]
        # The dropped image's file is gone
        assert client.get(f"/api/characters/{c['id']}/images/{c['images'][0]}").status_code == 404

        assert client.delete(f"/api/characters/{c['id']}").status_code == 200
        assert client.get(f"/api/characters/{c['id']}").status_code == 404

    def test_unknown_image_in_reorder_is_rejected(self, client):
        """Test that unknown image in reorder is rejected."""
        c = _make(client)
        assert client.patch(f"/api/characters/{c['id']}", json={"images": ["nope.png"]}).status_code == 400

    def test_image_limit(self, client, monkeypatch):
        """Test that image limit."""
        monkeypatch.setattr(characters_mod, "MAX_IMAGES", 1)
        c = _make(client)
        r = client.post(f"/api/characters/{c['id']}/images", files={"file": ("a.png", _png_bytes(), "image/png")})
        assert r.status_code == 400

    def test_copy_image_from_chat(self, client, conv, chat):
        """Test that copy image from chat."""
        (chat.conversation_dir(conv["id"]) / "g.png").write_bytes(_png_bytes())
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
        """Test that adhoc characters belong to their chat."""
        other = client.post("/api/chat/conversations", json={}).json()
        saved = _make(client, name="Saved", images=0)
        adhoc = _make(client, name="Adhoc", images=0, conversation_id=conv["id"])
        assert adhoc["adhoc"] is True
        # Created in a chat = attached to it
        assert db.get_conversation(conv["id"]).character_ids == [adhoc["id"]]

        def names(q):
            return [c["name"] for c in client.get(f"/api/characters{q}").json()["characters"]]

        assert names(f"?conversation_id={conv['id']}") == ["Adhoc", "Saved"]
        assert names(f"?conversation_id={other['id']}") == ["Saved"]
        assert names("?include_adhoc=true") == ["Adhoc", "Saved"]
        assert saved["adhoc"] is False

    def test_promote(self, client, conv):
        """Test that promote."""
        adhoc = _make(client, images=0, conversation_id=conv["id"])
        r = client.post(f"/api/characters/{adhoc['id']}/promote").json()
        assert r["adhoc"] is False
        assert r["conversation_id"] is None
        # Promoted characters survive their chat
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert client.get(f"/api/characters/{adhoc['id']}").status_code == 200

    def test_deleting_a_chat_deletes_its_adhoc_characters(self, client, conv):
        """Test that deleting a chat deletes its adhoc characters."""
        adhoc = _make(client, conversation_id=conv["id"])
        client.delete(f"/api/chat/conversations/{conv['id']}")
        assert client.get(f"/api/characters/{adhoc['id']}").status_code == 404

    def test_attach_to_chat(self, client, conv):
        """Test that attach to chat."""
        c = _make(client, images=0)
        r = client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [c["id"]]})
        assert r.json()["character_ids"] == [c["id"]]
        assert client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [999]}).status_code == 400
        # Deleting a character detaches it
        client.delete(f"/api/characters/{c['id']}")
        assert client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["character_ids"] == []


class TestInChat:
    """Tests for in chat."""

    def _attach(self, client, conv, *chars):
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [c["id"] for c in chars]})

    def _capture(self, chat, monkeypatch):
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        return got

    def test_chat_model_is_told_and_tool_lists_names(self, client, conv, chat, monkeypatch):
        """Test that chat model is told and tool lists names."""
        linh = _make(client)
        self._attach(client, conv, linh)
        seen = {}

        def stream(model, messages, tools=None, **kw):
            seen.update(messages=messages, tools=tools)
            return _text_chunks("Hi")

        monkeypatch.setattr(openrouter, "stream_chat", stream)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        system = " ".join(m["content"] for m in seen["messages"] if m["role"] == "system")
        assert "Linh: Short black hair, red scarf" in system
        image_tool = next(t for t in seen["tools"] if t["function"]["name"] == "generate_image")
        assert image_tool["function"]["parameters"]["properties"]["characters"]["items"]["enum"] == ["Linh"]

    def test_named_character_sends_description_and_images(self, client, conv, chat, monkeypatch):
        """Test that named character sends description and images."""
        linh, bao = _make(client, images=2), _make(client, name="Bao", description="Tall", images=1)
        self._attach(client, conv, linh, bao)
        replies = iter(
            [
                _tool_chunks("generate_image", {"prompt": "Linh at the beach", "characters": ["linh"]}, text="Here."),
                _text_chunks("Done."),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        item = ev[-1]["message"]["media"][0]
        assert item["prompt"] == "Linh at the beach"  # stored as the model wrote it
        assert "Linh: Short black hair" in got["prompt"]
        assert "Bao" not in got["prompt"]
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
        """Test that short name means the attached character in auto mode."""
        _chloe, muscle = self._overlapping_names(client, conv)
        # The model calls her by the short name, in the argument and its prompt
        replies = iter(
            [
                _tool_chunks("generate_image", {"prompt": "Chloe flexing", "characters": ["Chloe"]}, text="Here."),
                _text_chunks("Done."),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "create an image of chloe", **SETTINGS},
            )
        )
        assert ev[-1]["message"]["media"][0]["params"]["characters"] == [muscle["id"]]
        assert "Bodybuilder" in got["prompt"]
        assert "Slim" not in got["prompt"]
        assert self._attached_ids(client, conv) == [muscle["id"]]

    def test_short_name_is_ignored_when_ambiguous(self, client, conv, chat, monkeypatch):
        """Test that short name is ignored when ambiguous."""
        a, b = _make(client, name="Chloe Muscle"), _make(client, name="Chloe Slim")
        self._attach(client, conv, a, b)
        replies = iter(
            [_tool_chunks("generate_image", {"prompt": "Chloe waving", "characters": ["Chloe"]}), _text_chunks("Done.")]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert "characters" not in ev[-1]["message"]["media"][0]["params"]

    def test_full_name_in_prompt_does_not_also_match_the_shorter_one(self, client, conv, chat, monkeypatch):
        """Test that full name in prompt does not also match the shorter one."""
        chloe, muscle = _make(client, name="Chloe"), _make(client, name="Chloe Muscle")
        self._attach(client, conv, chloe, muscle)
        replies = iter([_tool_chunks("generate_image", {"prompt": "Chloe Muscle at the gym"}), _text_chunks("Done.")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert ev[-1]["message"]["media"][0]["params"]["characters"] == [muscle["id"]]

    def test_image_mode_uses_every_attached_character(self, client, conv, chat, monkeypatch):
        """Test that image mode uses every attached character."""
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
        assert "Linh:" in got["prompt"]
        assert "- Bao" in got["prompt"]

    def test_main_character_images_come_before_pins_and_recent_picks(self, client, conv, chat, db, monkeypatch):
        """The priority when a model takes fewer images than that (see TestReferenceCaps)."""
        linh = _make(client)
        self._attach(client, conv, linh)
        (chat.conversation_dir(conv["id"]) / "g.png").write_bytes(_png_bytes())
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
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert ev[-1]["message"]["media"][0]["params"]["refs"] == [f"char:{linh['id']}/{linh['images'][0]}", "g.png"]

    def test_character_refs_are_shared_round_robin(self, chat, client):
        """Test that character refs are shared round robin."""
        a, b = _make(client, name="A", images=3), _make(client, name="B", images=3)

        refs = characters_mod.reference_refs(characters_mod.load([a["id"], b["id"]]), 3)
        assert refs == [
            f"char:{a['id']}/{a['images'][0]}",
            f"char:{b['id']}/{b['images'][0]}",
            f"char:{a['id']}/{a['images'][1]}",
        ]

    def test_video_mode_does_not_use_characters(self, client, conv, chat, monkeypatch):
        """Test that video mode does not use characters."""
        linh = _make(client)
        self._attach(client, conv, linh)
        sent = {}
        monkeypatch.setattr(
            openrouter, "submit_video", lambda model, prompt, **kw: (sent.update(prompt=prompt), {"id": "job1"})[1]
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "Linh dancing", **SETTINGS, "mode": "video"},
            )
        )
        assert sent["prompt"] == "Linh dancing"

    def test_image_model_without_references_does_not_use_characters(self, client, conv, chat, db, monkeypatch):
        """Test that image model without references does not use characters."""
        chat.catalogue.seed_models(
            {"text": [], "video": [], "image": [{"id": "i/model", "input_modalities": ["text"]}]}
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
        """Test that chat model without tools is not told in auto."""
        chat.catalogue.seed_models(
            {
                "image": [],
                "video": [],
                "text": [{"id": "t/model", "supports_tools": False, "input_modalities": ["text"]}],
            },
        )
        self._attach(client, conv, _make(client))
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda model, messages, tools=None, **kw: (seen.update(m=messages), _text_chunks("Hi"))[1],
        )
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        assert not any("Linh" in str(m["content"]) for m in seen["m"] if m["role"] == "system")

    def test_chat_mode_tells_the_chat_model(self, client, conv, chat, monkeypatch):
        """Test that chat mode tells the chat model."""
        self._attach(client, conv, _make(client))
        seen = {}
        monkeypatch.setattr(
            openrouter,
            "stream_chat",
            lambda model, messages, tools=None, **kw: (seen.update(m=messages), _text_chunks("Hi"))[1],
        )
        _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS, "mode": "text"}
            )
        )
        assert any("Linh: Short black hair" in m["content"] for m in seen["m"] if m["role"] == "system")


class TestUseByName:
    """Only characters the user attached are used — a name coming up never attaches one."""

    def _capture(self, chat, monkeypatch):
        got = {}
        monkeypatch.setattr(
            openrouter,
            "generate_image",
            lambda model, prompt, **kw: (got.update(prompt=prompt, **kw), ([(_png_bytes(), "image/png")], None))[1],
        )
        return got

    def test_model_is_not_told_about_unattached_characters(self, client, conv, chat, monkeypatch):
        """Test that model is not told about unattached characters."""
        _make(client, name="Linh")
        seen = {}

        def stream(model, messages, tools=None, **kw):
            seen.update(messages=messages, tools=tools)
            return _text_chunks("Hi")

        monkeypatch.setattr(openrouter, "stream_chat", stream)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", **SETTINGS}))
        assert "Linh" not in json.dumps(seen["messages"])
        assert "Linh" not in json.dumps(seen["tools"])

    def test_naming_an_unattached_character_neither_uses_nor_attaches_it(self, client, conv, chat, db, monkeypatch):
        """Test that naming an unattached character neither uses nor attaches it."""
        _make(client)
        replies = iter(
            [
                _tool_chunks("generate_image", {"prompt": "Linh at the beach", "characters": ["Linh"]}),
                _text_chunks("Here she is."),
            ]
        )
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        got = self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages", json={"content": "use Linh, at the beach", **SETTINGS}
            )
        )
        assert "Short black hair" not in got["prompt"]
        assert not got.get("input_images")
        assert not any(e["type"] == "characters" for e in ev)
        assert db.get_conversation(conv["id"]).character_ids == []

    def test_image_mode_ignores_unattached_names(self, client, conv, chat, db, monkeypatch):
        """Test that image mode ignores unattached names."""
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
        """Test that name in the prompt counts when the model forgets the argument."""
        linh = _make(client)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [linh["id"]]})
        replies = iter([_tool_chunks("generate_image", {"prompt": "Linh reading in a café"}), _text_chunks("Done.")])
        monkeypatch.setattr(openrouter, "stream_chat", lambda *a, **k: next(replies))
        self._capture(chat, monkeypatch)
        ev = _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        assert ev[-1]["message"]["media"][0]["params"]["characters"] == [linh["id"]]

    def test_create_character_from_the_latest_image_then_draw_them(self, client, conv, chat, db, monkeypatch):
        """Test that create character from the latest image then draw them."""
        (chat.conversation_dir(conv["id"]) / "g.png").write_bytes(_png_bytes())
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
        monkeypatch.setattr(openrouter, "stream_chat", stream)
        got = self._capture(chat, monkeypatch)
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "make her a character called Mai and draw her in the rain", **SETTINGS},
            )
        )
        mai = next(c for c in db.list_characters() if c.name == "Mai")
        assert mai.conversation_id == conv["id"]
        assert len(mai.images) == 1
        # The second round's tool offers Mai by name
        enum = next(t for t in tools_seen[1] if t["function"]["name"] == "generate_image")
        assert "Mai" in enum["function"]["parameters"]["properties"]["characters"]["items"]["enum"]
        assert "Freckles" in got["prompt"]
        assert ev[-1]["message"]["media"][0]["params"]["refs"] == [f"char:{mai.id}/{mai.images[0]}"]

    def _chat_image(self, chat, conv, db):
        (chat.conversation_dir(conv["id"]) / "g.png").write_bytes(_png_bytes())
        db.add_chat_message(conv["id"], "user", "draw a girl")
        db.add_chat_message(
            conv["id"],
            "assistant",
            "Here.",
            media=[{"id": "g", "kind": "image", "source": "generated", "status": "done", "file": "g.png"}],
        )

    def _run(self, client, conv, monkeypatch, *calls):
        replies = iter([*calls, _text_chunks("Done.")])
        results = []

        def stream(model, messages, tools=None, **kw):
            results.extend(json.loads(m["content"]) for m in messages if m["role"] == "tool")
            return next(replies)

        monkeypatch.setattr(openrouter, "stream_chat", stream)
        _events(client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "go", **SETTINGS}))
        return results

    def test_create_character_needs_an_image(self, client, conv, chat, monkeypatch):
        """Test that create character needs an image."""
        results = self._run(client, conv, monkeypatch, _tool_chunks("create_character", {"name": "Mai"}))
        assert "no image" in results[0]["error"]

    def test_a_library_name_doesnt_stop_a_chat_making_its_own(self, client, conv, chat, db, monkeypatch):
        """Names needn't be unique: a library Linh not in this chat is someone else."""
        library = _make(client, name="Linh")
        self._chat_image(chat, conv, db)
        results = self._run(client, conv, monkeypatch, _tool_chunks("create_character", {"name": "Linh"}))
        assert results[0]["ok"]
        linhs = [c for c in db.list_characters() if c.name == "Linh"]
        assert len(linhs) == 2
        own = next(c for c in linhs if c.id != library["id"])
        assert own.conversation_id == conv["id"]

    def test_a_name_already_in_this_chat_is_used_not_made_again(self, client, conv, chat, db, monkeypatch):
        """Test that the model is told to use the chat's Linh rather than making another."""
        linh = _make(client, name="Linh")
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [linh["id"]]})
        self._chat_image(chat, conv, db)
        results = self._run(client, conv, monkeypatch, _tool_chunks("create_character", {"name": "linh"}))
        assert "already one of this chat's characters" in results[0]["error"]
        assert len([c for c in db.list_characters() if c.name == "Linh"]) == 1

    def test_a_shared_name_means_the_chats_own(self, db):
        """A library Linh attached beside the chat's own Linh: "Linh" means the chat's."""
        lib = db.create_character("Linh")
        own = db.create_character("Linh", conversation_id="c1")
        assert characters_mod.named([lib, own], ["linh"]) == [own]
        assert characters_mod.mentioned([lib, own], "Linh waves") == [own]


class TestReferenceCaps:
    """Chat images are capped by the image slider (default 6); character images never are."""

    def test_every_character_image_is_sent_beyond_the_chat_cap(self, client, conv, chat, db, monkeypatch):
        """Test that every character image is sent beyond the chat cap."""
        linh, bao = _make(client, images=5), _make(client, name="Bao", images=4)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [linh["id"], bao["id"]]})
        # 8 pinned chat images: only the slider's number of them go
        db.add_chat_message(conv["id"], "user", "pics")
        for i in range(8):
            (chat.conversation_dir(conv["id"]) / f"p{i}.png").write_bytes(_png_bytes())
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
            openrouter,
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
        assert len(refs) - len(char_refs) == chat.constants.DEFAULT_IMAGE_LIMIT
        assert len(got["input_images"]) == 9 + chat.constants.DEFAULT_IMAGE_LIMIT

    def test_slider_raises_the_chat_image_cap(self, client, conv, chat, db, monkeypatch):
        """Test that slider raises the chat image cap."""
        db.add_chat_message(conv["id"], "user", "pics")
        for i in range(8):
            (chat.conversation_dir(conv["id"]) / f"p{i}.png").write_bytes(_png_bytes())
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
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "go", **SETTINGS, "mode": "image", "image_limit": None},
            )
        )
        assert len(ev[-1]["message"]["media"][0]["params"]["refs"]) == 8

    def _pins(self, chat, db, conv, n):
        db.add_chat_message(conv["id"], "user", "pics")
        for i in range(n):
            (chat.conversation_dir(conv["id"]) / f"p{i}.png").write_bytes(_png_bytes())
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
                for i in range(n)
            ],
        )

    def _send_image(self, client, conv, chat, monkeypatch, max_refs, **settings):
        real = chat.catalogue.model_info

        def fake_info(kind, mid):
            if kind == "image":
                return {"input_modalities": ["text", "image"], "max_refs": max_refs}
            return real(kind, mid)

        # model_info is read in both the turn (ref caps) and generation (modality) modules
        monkeypatch.setattr(chat.turn, "model_info", fake_info)
        monkeypatch.setattr(chat.generation, "model_info", fake_info)
        monkeypatch.setattr(
            openrouter, "generate_image", lambda model, prompt, **kw: ([(_png_bytes(), "image/png")], None)
        )
        ev = _events(
            client.post(
                f"/api/chat/conversations/{conv['id']}/messages",
                json={"content": "go", **SETTINGS, "mode": "image", **settings},
            )
        )
        return ev[-1]["message"]["media"][0]["params"]

    def test_a_model_maximum_keeps_room_for_chat_images(self, client, conv, chat, db, monkeypatch):
        """Each character's main image first, then pins, then the characters' other images."""
        a, b = _make(client, name="A", images=3), _make(client, name="B", images=3)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [a["id"], b["id"]]})
        self._pins(chat, db, conv, 2)
        params = self._send_image(client, conv, chat, monkeypatch, max_refs=6)

        def ref(c, i):
            return f"char:{c['id']}/{c['images'][i]}"

        assert params["refs"] == [ref(a, 0), ref(b, 0), "p0.png", "p1.png", ref(a, 1), ref(b, 1)]
        assert params["refs_dropped"] == [ref(a, 2), ref(b, 2)]

    def test_composer_picks_switch_references_on_and_off(self, client, conv, chat, db, monkeypatch):
        """Test that composer picks switch references on and off."""
        a = _make(client, name="A", images=3)
        client.patch(f"/api/chat/conversations/{conv['id']}", json={"character_ids": [a["id"]]})
        self._pins(chat, db, conv, 2)

        def ref(i):
            return f"char:{a['id']}/{a['images'][i]}"

        choices = {"on": [ref(2), "not-a-candidate.png"], "off": [ref(0), "p1.png"]}
        params = self._send_image(client, conv, chat, monkeypatch, max_refs=2, ref_choices=choices)
        # The forced one goes first, then the (new) main image; switched-off ones never go
        assert params["refs"] == [ref(2), ref(1)]
        assert params["refs_dropped"] == ["p0.png"]
        settings = client.get(f"/api/chat/conversations/{conv['id']}").json()["conversation"]["settings"]
        assert settings["ref_choices"] == choices  # remembered with the chat
