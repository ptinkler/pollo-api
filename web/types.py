"""Shared types for data exchanged with JSON APIs and persisted as JSON."""

from collections.abc import Mapping, Sequence
from typing import NotRequired, TypedDict

type JsonValue = str | int | float | bool | Sequence[JsonValue] | Mapping[str, JsonValue] | None


class ToolFunctionDelta(TypedDict, total=False):
    """The function name and partial arguments in a streamed tool call."""

    name: str
    arguments: str


class ToolCallDelta(TypedDict, total=False):
    """One tool call delta within a streamed chat choice."""

    index: int
    id: str
    function: ToolFunctionDelta


class ChatDelta(TypedDict, total=False):
    """The text and tool-call deltas emitted for one choice."""

    content: str | None
    tool_calls: list[ToolCallDelta]


class ChatChoice(TypedDict, total=False):
    """A streamed completion choice."""

    delta: ChatDelta
    finish_reason: str | None


class ChatChunk(TypedDict):
    """One parsed chunk from a streamed chat completion."""

    choices: NotRequired[list[ChatChoice]]
    usage: NotRequired[dict[str, JsonValue]]


class VideoJob(TypedDict):
    """A submitted video job and the parameters sent with it."""

    id: str
    params: NotRequired[dict[str, JsonValue]]
    log: NotRequired[dict[str, JsonValue] | None]
