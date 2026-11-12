"""web.request_log keeps each user's provider-call log to themselves."""

from web import request_log
from web.core import metadata


def _prompts():
    return [e["request"]["prompt"] for e in request_log.recent()]


def test_log_is_per_tenant():
    """Two users' provider calls go to separate per-tenant logs, so the.

    Request log never shows one user another user's prompts/content.
    """
    token = metadata.set_tenant("user-a")
    try:
        request_log.record("venice", "POST", "/image/generate", {"prompt": "a-secret"})
    finally:
        metadata.reset_tenant(token)

    token = metadata.set_tenant("user-b")
    try:
        request_log.record("venice", "POST", "/image/generate", {"prompt": "b-secret"})
        assert _prompts() == ["b-secret"]  # B sees only B's
    finally:
        metadata.reset_tenant(token)

    token = metadata.set_tenant("user-a")
    try:
        assert _prompts() == ["a-secret"]  # A sees only A's
    finally:
        metadata.reset_tenant(token)
