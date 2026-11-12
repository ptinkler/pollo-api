"""Provider request log — what was sent to the generation APIs, and what came back.

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
from collections.abc import Generator, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol, TypedDict, cast

from web.core import config
from web.core.metadata import current_tenant
from web.types import ChatChunk, JsonValue

MAX_BYTES = 5 * 1024 * 1024
_lock = threading.Lock()
_last = threading.local()  # the latest logged call on this thread (each chat turn runs on its own)
MAX_TEXT = 4000  # a non-JSON response body is kept up to this many characters


class _ToolReply(TypedDict):
    name: str
    arguments: str


class _ChatReply(TypedDict):
    content: str
    tool_calls: dict[int, _ToolReply]
    finish_reason: str | None
    usage: JsonValue


class LogOutcome(TypedDict):
    """Fields a provider fills while a request is being logged."""

    status: int | None
    flags: dict[str, str] | None
    response: JsonValue


class _RequestExchange(TypedDict):
    request: JsonValue
    response: JsonValue


class _Response(Protocol):
    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def text(self) -> str: ...

    @property
    def content(self) -> bytes: ...

    def json(self) -> object: ...


def log_path() -> Path:
    """Return the request-log path for the current tenant, if any."""
    # Read config at call time so tests can redirect ROOT_DIR. Per-tenant
    # (<data>/logs/<user_id>/) so one user's provider calls never surface in
    # another's Request log; calls made outside a request (startup) fall back
    # to the shared base file.
    base = config.ROOT_DIR / "logs"
    uid = current_tenant()
    return base / uid / "requests.jsonl" if uid else base / "requests.jsonl"


def redact(value: JsonValue) -> JsonValue:
    """Return a log-safe representation of a request body.

    Data URLs and long base64 strings are represented by type and size;
    other values are preserved.
    """
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


def response_of(resp: _Response) -> JsonValue:
    """Return a log-safe representation of a fully read HTTP response.

    JSON, text, and binary responses are represented by their contents or
    their content type and size, respectively.
    """
    headers = getattr(resp, "headers", {})
    content_type = (headers.get("content-type") or "").split(";")[0].strip()
    if "json" in content_type or not content_type:
        with contextlib.suppress(Exception):
            return redact(cast("JsonValue", resp.json()))
    if content_type.startswith("text/") or not content_type:
        with contextlib.suppress(Exception):
            text = resp.text
            return text if len(text) <= MAX_TEXT else f"{text[:MAX_TEXT]}… ({len(text)} characters)"
        return None
    return {"content_type": content_type, "bytes": len(resp.content)}


def chat_reply(chunks: Iterator[ChatChunk], outcome: LogOutcome) -> Iterator[ChatChunk]:
    """Pass through chat chunks while assembling their logged reply.

    The accumulated response includes text, tool calls, finish reason, and
    usage, including partial data when the stream ends early.
    """
    reply: _ChatReply = {"content": "", "tool_calls": {}, "finish_reason": None, "usage": None}
    outcome["response"] = cast("JsonValue", reply)
    for chunk in chunks:
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            reply["content"] += content if isinstance(content, str) else ""
            for call in delta.get("tool_calls") or []:
                slot = reply["tool_calls"].setdefault(call.get("index", 0), {"name": "", "arguments": ""})
                fn = call.get("function") or {}
                name, arguments = fn.get("name"), fn.get("arguments")
                slot["name"] += name if isinstance(name, str) else ""
                slot["arguments"] += arguments if isinstance(arguments, str) else ""
            reply["finish_reason"] = choice.get("finish_reason") or reply["finish_reason"]
        usage = chunk.get("usage")
        if usage:
            reply["usage"] = cast("JsonValue", usage)
        yield chunk


def record(
    provider: str,
    method: str,
    path: str,
    request: JsonValue,
    *,
    status: int | None = None,
    seconds: float | None = None,
    error: str | None = None,
    flags: dict[str, str] | None = None,
    model: str | None = None,
    response: JsonValue = None,
) -> dict[str, JsonValue]:
    """Append and return a provider-call log entry.

    ``request`` and ``response`` should already be redacted. Logging failures
    are ignored so a full disk cannot fail a generation.
    """
    request_model = None
    if isinstance(request, dict):
        candidate = request.get("model") or request.get("modelId")
        request_model = candidate if isinstance(candidate, str) else None
    entry: dict[str, JsonValue] = {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider": provider,
        "method": method,
        "path": path,
        "model": model or request_model,
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


def _jsonable(value: JsonValue) -> JsonValue:
    """Convert indexed chat tool calls to a JSON-friendly list."""
    if isinstance(value, dict):
        calls = value.get("tool_calls")
        if isinstance(calls, dict):
            return {**value, "tool_calls": list(calls.values()) or None}
    return value


def recent(limit: int = 100) -> list[dict[str, JsonValue]]:
    """The latest entries, newest first."""
    p = log_path()
    if not p.is_file():
        return []
    with _lock:
        lines = p.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, JsonValue]] = []
    for line in reversed(lines):
        try:
            out.append(cast("dict[str, JsonValue]", json.loads(line)))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out


@contextlib.contextmanager
def logged(provider: str, method: str, path: str, body: JsonValue, model: str | None = None) -> Generator[LogOutcome]:
    """Record one provider call made inside the block.

    Yields a dict the caller fills in with ``status`` (HTTP status), ``flags``
    (headers worth keeping), and ``response`` (see ``response_of`` /
    ``chat_reply``). Set these before raising on an error response so the log
    shows what the provider said. An exception leaving the block is recorded
    as the error and gets the entry as its ``log_entry`` attribute.
    """
    shown = redact(body)
    outcome: LogOutcome = {"status": None, "flags": None, "response": None}
    _last.entry = _RequestExchange(request=shown, response=None)
    start = time.monotonic()

    def done(error: str | None = None, status: int | None = None) -> dict[str, JsonValue]:
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
            e.__dict__["log_entry"] = entry
        raise
    done()


def take_last() -> dict[str, JsonValue] | None:
    """The latest logged call on this thread, as {"request", "response"} (then forgets it)."""
    entry = cast("_RequestExchange | None", getattr(_last, "entry", None))
    _last.entry = None
    return {"request": entry["request"], "response": entry.get("response")} if entry else None


def forget_last() -> None:
    """Call before a generation, so take_last() can't return an older call."""
    _last.entry = None
