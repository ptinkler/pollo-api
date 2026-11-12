"""Shared types for data exchanged with JSON APIs and persisted as JSON."""

from collections.abc import Mapping, Sequence

type JsonValue = str | int | float | bool | Sequence[JsonValue] | Mapping[str, JsonValue] | None
