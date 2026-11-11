"""Fixtures and shared helpers for the chat-mode tests, loaded via
`pytest_plugins`.

A fixture plugin rather than a cross-module import: pytest resolves fixtures by
name, so the test modules need no import of this file to use them (and no F401
or F811 to excuse one). The helpers below are imported normally, because they
are called rather than injected.
"""

import io
import json
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import web.api as api_mod
import web.chat as chat_mod
from web.core.metadata import MetadataDB

SETTINGS = {"text_model": "t/model", "image_model": "i/model", "video_model": "v/model"}


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
    yield {
        "choices": [
            {"delta": {"tool_calls": [{"index": 0, "id": call_id, "function": {"name": name, "arguments": raw[:5]}}]}}
        ]
    }
    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": raw[5:]}}]}}]}
    yield {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"cost": 0.003}}


def _events(resp) -> list[dict]:
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def db(tmp_path):
    return MetadataDB(db_path=tmp_path / "data" / "metadata.db")


@pytest.fixture
def chat(monkeypatch, db, provider_keys):
    # Patch get_db wherever it was imported (chat is a package now: routes,
    # helpers and catalogue each resolve their own get_db).
    for name, mod in list(sys.modules.items()):
        if name.startswith("web.") and getattr(mod, "get_db", None) is not None:
            monkeypatch.setattr(mod, "get_db", lambda: db)
    provider_keys["openrouter"] = "sk-test"
    provider_keys["venice"] = None  # tests never reach the real Venice
    monkeypatch.setattr(chat_mod.polling, "VIDEO_POLL_INTERVAL", 0)
    monkeypatch.setattr(chat_mod.polling, "start_video_poller", lambda *a: None)
    monkeypatch.setattr(chat_mod.generation, "generate_title", lambda model, prompt: (None, 0.0))  # tests opt in
    chat_mod.catalogue.clear_models()
    return chat_mod


@pytest.fixture
def client(chat):
    return TestClient(api_mod.app, raise_server_exceptions=False)


@pytest.fixture
def conv(client):
    return client.post("/api/chat/conversations", json={}).json()
