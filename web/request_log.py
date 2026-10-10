"""
Provider request log — what was sent to the generation APIs, and what came back.

One JSON object per line in <data>/logs/requests.jsonl (newest last), so it
can be read in the app (GET /api/chat/request-log) or filtered with jq:

    {"at": "2026-10-10T14:03:11", "provider": "venice", "method": "POST",
     "path": "/image/multi-edit", "model": "seedream-v5-pro-edit",
     "status": 422, "seconds": 1.8, "error": "Venice: Your prompt violates…",
     "flags": {"x-venice-is-content-violation": "true"},
     "request": {…the body exactly as sent, images cut down to type and size…},
     "response": {…what came back: an error's body as sent, a JSON answer,
                  a chat reply's text and tool calls, or a file's type and size…}}

The file is capped: past MAX_BYTES it's moved to requests.1.jsonl (replacing
the previous one) and a new one starts.

Providers wrap each generation call in `logged(...)` and put what came back
in its outcome (`response_of(resp)`, or `chat_reply` for a streamed chat).
The chat then reads the request and response back for the media card's
"Request" view: `take_last()` after a call, or the error's `log_entry`.
"""

import contextlib
import json
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from img2vid.common import config

MAX_BYTES = 5 * 1024 * 1024
_lock = threading.Lock()
_last = threading.local()  # the latest logged call on this thread (each chat turn runs on its own)
MAX_TEXT = 4000  # a non-JSON response body is kept up to this many characters


def log_path() -> Path:
    # Read config at call time so tests can redirect ROOT_DIR
    return config.ROOT_DIR / "logs" / "requests.jsonl"


def redact(value: Any) -> Any:
    """A request body as it can be shown and logged: images (data URLs) cut
    down to their type and size, everything else exactly as sent."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str) and value.startswith("data:") and ";base64," in value:
        head, data = value.split(",", 1)
        return f"{head},… ({len(data) * 3 // 4 // 1024} KB)"
    if isinstance(value, str) and len(value) > 2000 and " " not in value:
        return f"… ({len(value) * 3 // 4 // 1024} KB of base64)"  # a bare base64 image, e.g. Venice's "images"
    return value


def response_of(resp: Any) -> Any:
    """What an HTTP response (httpx or requests, already read) said, for the
    log: its JSON (images cut short), its text, or a file's type and size."""
    content_type = ((getattr(resp, "headers", None) or {}).get("content-type") or "").split(";")[0].strip()
    if "json" in content_type or not content_type:
        with contextlib.suppress(Exception):
            return redact(resp.json())
    if content_type.startswith("text/") or not content_type:
        with contextlib.suppress(Exception):
            text = resp.text
            return text if len(text) <= MAX_TEXT else f"{text[:MAX_TEXT]}… ({len(text)} characters)"
        return None
    return {"content_type": content_type, "bytes": len(resp.content)}


def chat_reply(chunks: Iterator[dict], outcome: dict) -> Iterator[dict]:
    """Pass a streamed chat reply's chunks through, building its response for
    the log as they go (so a reply cut short still shows how far it got):
    the text, the tool calls, why it finished, and the usage."""
    reply: dict[str, Any] = {"content": "", "tool_calls": {}, "finish_reason": None, "usage": None}
    outcome["response"] = reply
    for chunk in chunks:
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            reply["content"] += delta.get("content") or ""
            for call in delta.get("tool_calls") or []:
                slot = reply["tool_calls"].setdefault(call.get("index", 0), {"name": "", "arguments": ""})
                fn = call.get("function") or {}
                slot["name"] += fn.get("name") or ""
                slot["arguments"] += fn.get("arguments") or ""
            reply["finish_reason"] = choice.get("finish_reason") or reply["finish_reason"]
        if chunk.get("usage"):
            reply["usage"] = chunk["usage"]
        yield chunk


def record(
    provider: str,
    method: str,
    path: str,
    request: dict | None,
    *,
    status: int | None = None,
    seconds: float | None = None,
    error: str | None = None,
    flags: dict | None = None,
    model: str | None = None,
    response: Any = None,
) -> dict:
    """Append one entry and return it. `request` and `response` should
    already be redacted. Never raises: a full disk mustn't fail a generation."""
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "method": method,
        "path": path,
        "model": model or (request or {}).get("model") or (request or {}).get("modelId"),
        "status": status,
        "seconds": None if seconds is None else round(seconds, 1),
        "error": error,
        "flags": flags or None,
        "request": request,
        "response": _jsonable(response),
    }
    try:
        with _lock:
            p = log_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.is_file() and p.stat().st_size > MAX_BYTES:
                p.replace(p.with_name("requests.1.jsonl"))
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return entry


def _jsonable(value: Any) -> Any:
    """Chat replies collect tool calls by index (int keys): list them instead."""
    if isinstance(value, dict) and isinstance(value.get("tool_calls"), dict):
        return {**value, "tool_calls": list(value["tool_calls"].values()) or None}
    return value


def recent(limit: int = 100) -> list[dict]:
    """The latest entries, newest first."""
    p = log_path()
    if not p.is_file():
        return []
    with _lock:
        lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out


@contextlib.contextmanager
def logged(provider: str, method: str, path: str, body: Any, model: str | None = None) -> Iterator[dict]:
    """Record one provider call made inside the block. Yields a dict the
    caller fills in: "status" (HTTP status), "flags" (headers worth keeping)
    and "response" (see response_of / chat_reply) — set it before raising on
    an error response, so the log shows what the provider said. An exception
    leaving the block is recorded as the error and gets the entry as its
    `log_entry` attribute."""
    shown = redact(body)
    outcome: dict[str, Any] = {"status": None, "flags": None, "response": None}
    _last.entry = {"request": shown, "response": None}
    start = time.monotonic()

    def done(error: str | None = None, status: int | None = None) -> dict:
        entry = record(
            provider,
            method,
            path,
            shown,
            status=status or outcome["status"],
            error=error,
            seconds=time.monotonic() - start,
            flags=outcome["flags"],
            model=model,
            response=outcome["response"],
        )
        _last.entry = entry
        return entry

    try:
        yield outcome
    except GeneratorExit:  # a streamed reply the app stopped reading (cancelled)
        done("stopped by the app")
        raise
    except Exception as e:
        entry = done(str(e), getattr(e, "status", None))
        with contextlib.suppress(AttributeError):
            e.log_entry = entry
        raise
    done()


def take_last() -> dict | None:
    """The latest logged call on this thread, as {"request", "response"} (then forgets it)."""
    entry = getattr(_last, "entry", None)
    _last.entry = None
    return {"request": entry["request"], "response": entry.get("response")} if entry else None


def forget_last() -> None:
    """Call before a generation, so take_last() can't return an older call."""
    _last.entry = None
