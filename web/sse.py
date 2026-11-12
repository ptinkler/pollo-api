"""Parse OpenAI-style server-sent chat completion streams.

Shared by the OpenRouter and Venice clients.
"""

import json
import time
from collections.abc import Callable, Iterable, Iterator
from typing import cast

from web.types import ChatChunk, JsonValue


def chat_chunks(
    lines: Iterable[str],
    error: Callable[[str, int | None], Exception],
    max_seconds: float | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[ChatChunk]:
    """The parsed chunk dicts from a response's lines, until "[DONE]".

    Blank separators and ":" keep-alives are skipped but still checked
    against `max_seconds` (a cap on the whole call) and `should_stop`
    (polled on every line, so a cancel is noticed while no tokens flow).
    An error chunk raises `error(message, status)`.
    """
    deadline = time.monotonic() + max_seconds if max_seconds else None
    for line in lines:
        if should_stop and should_stop():
            return
        if deadline and time.monotonic() > deadline:
            raise error(f"The model didn't finish within {int(max_seconds)}s", 504)  # noqa: TRY003
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            chunk = cast("dict[str, JsonValue]", json.loads(payload))
        except json.JSONDecodeError:
            continue
        err = chunk.get("error")
        if err:
            if isinstance(err, dict):
                message = err.get("message")
                raise error(message if isinstance(message, str) else str(message), None)
            raise error(str(err), None)
        yield cast("ChatChunk", chunk)
