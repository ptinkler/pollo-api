"""Reading settings from the environment.

One parser, so "true"/"on"/"1" mean the same thing everywhere. `.env` itself is
loaded once, by absolute path and without override — see web/core/config.py.
"""

import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def bool_env(name: str, default: bool = False) -> bool:
    """A boolean setting: 1/true/yes/on or 0/false/no/off (any case), else `default`."""
    value = os.getenv(name, "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def bool_env_or_none(name: str) -> bool | None:
    """A boolean setting, or None when it isn't set to a recognised value — for
    settings whose default is computed rather than fixed."""
    value = os.getenv(name, "").strip().lower()
    return True if value in _TRUE else False if value in _FALSE else None


def email_set(name: str) -> set[str]:
    """A comma-separated list of email addresses, lower-cased, blanks dropped."""
    return {e.strip().lower() for e in os.getenv(name, "").split(",") if e.strip()}
