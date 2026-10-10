"""
Provider request log — what was sent to the generation APIs, and what came back.

One JSON object per line in <data>/logs/requests.jsonl (newest last), so it
can be read in the app (GET /api/chat/request-log) or filtered with jq:

    {"at": "2026-10-10T14:03:11", "provider": "venice", "method": "POST",
     "path": "/image/multi-edit", "model": "seedream-v5-pro-edit",
     "status": 422, "seconds": 1.8, "error": "Venice: Your prompt violates…",
     "flags": {"x-venice-is-content-violation": "true"},
     "request": {…the body exactly as sent, images cut down to type and size…}}

The file is capped: past MAX_BYTES it's moved to requests.1.jsonl (replacing
the previous one) and a new one starts.

Providers wrap each generation call in `logged(...)`. The chat then reads the
body back for the media card's "Request" view: `take_last()` after a call
that worked, or the `request` attribute of the error raised.
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
_last = threading.local()  # the latest logged request on this thread (each chat turn runs on its own)


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
    return value


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
) -> None:
    """Append one entry. `request` should already be redacted. Never raises:
    a full disk mustn't fail a generation."""
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
    caller can fill in: "status" (HTTP status) and "flags" (headers worth
    keeping). An exception leaving the block is recorded as the error and
    gets the shown body as its `request` attribute."""
    shown = redact(body)
    _last.request = shown
    outcome: dict[str, Any] = {"status": None, "flags": None}
    start = time.monotonic()

    def done(error: str | None = None, status: int | None = None) -> None:
        record(
            provider,
            method,
            path,
            shown,
            status=status or outcome["status"],
            error=error,
            seconds=time.monotonic() - start,
            flags=outcome["flags"],
            model=model,
        )

    try:
        yield outcome
    except GeneratorExit:  # a streamed reply the app stopped reading (cancelled)
        done("stopped by the app")
        raise
    except Exception as e:
        done(str(e), getattr(e, "status", None))
        with contextlib.suppress(AttributeError):
            e.request = shown
        raise
    done()


def take_last() -> Any:
    """The body of the latest logged call on this thread (then forgets it)."""
    request = getattr(_last, "request", None)
    _last.request = None
    return request


def forget_last() -> None:
    """Call before a generation, so take_last() can't return an older call's body."""
    _last.request = None
