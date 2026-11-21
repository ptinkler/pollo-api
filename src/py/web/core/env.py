"""Reading settings from the environment.

One parser, so "true"/"on"/"1" mean the same thing everywhere. `.env` itself is
loaded once, by absolute path and without override — see web/core/config.py.
"""

import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def bool_env(name: str, *, default: bool = False) -> bool:
    """A boolean setting: 1/true/yes/on or 0/false/no/off (any case), else `default`."""
    value = os.getenv(name, "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def bool_env_or_none(name: str) -> bool | None:
    """Return a parsed boolean, or None when the setting is unrecognized."""
    value = os.getenv(name, "").strip().lower()
    return True if value in _TRUE else False if value in _FALSE else None


def email_set(name: str) -> set[str]:
    """A comma-separated list of email addresses, lower-cased, blanks dropped."""
    return {e.strip().lower() for e in os.getenv(name, "").split(",") if e.strip()}


def id_set(name: str) -> set[str]:
    """A comma-separated list of ids (case kept: a provider's user ids are case-sensitive), blanks dropped."""
    return {e.strip() for e in os.getenv(name, "").split(",") if e.strip()}


def number_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    """A number setting, at least `minimum`; `default` when it is unset or not a number."""
    try:
        return max(minimum, float(os.getenv(name, "")))
    except ValueError:
        return default
