"""Tests for reading number settings from the environment."""

import pytest

from web.core.env import number_env


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 10.0),  # unset: the default
        ("", 10.0),
        ("fast", 10.0),  # not a number: the default, not a crash at startup
        ("0.5", 0.5),
        ("0", 0.1),  # below the floor: the floor, so a typo can't make a loop spin
        ("-3", 0.1),
    ],
)
def test_number_env(monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: float) -> None:
    """Unset or unreadable falls back to the default; anything else is held at the minimum."""
    if raw is None:
        monkeypatch.delenv("SOME_SECONDS", raising=False)
    else:
        monkeypatch.setenv("SOME_SECONDS", raw)
    assert number_env("SOME_SECONDS", 10, minimum=0.1) == expected
