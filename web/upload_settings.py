"""Per-user source-media hosting preferences.

Providers like Pollo only accept a URL, so a source image/audio/video the user
attaches must be hosted somewhere public first. This picks where: a third-party
temp host (litterbox / tmpfiles) or self-hosting from this instance. One setting
covers all media kinds. Stored as plain JSON on the user row (non-secret), over
an instance-wide default from the environment.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from web.core import config
from web.core.metadata import User, current_tenant, get_db
from web.net_guard import UnsafeURLError, get_public
from web.public_media import selfhost_url
from web.users import require_user

router = APIRouter(prefix="/api/settings/uploads")

HOSTS = ("litterbox", "tmpfiles", "selfhost")
# Litterbox only keeps files for these spans; we present them as the expiry
# choices and map to the nearest for other hosts (self-host TTL, tmpfiles secs).
EXPIRY_OPTIONS = (60, 720, 1440, 4320)  # 1h / 12h / 24h / 72h, in minutes
# Hosts whose retention the user can actually choose (tmpfiles is fixed).
EXPIRY_CONFIGURABLE = ("litterbox", "selfhost")


def _public_base_default() -> str:
    return (os.getenv("UPLOAD_SELFHOST_BASE") or os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")


def default_prefs() -> dict[str, object]:
    """Return the instance-wide upload defaults from the environment.

    Litterbox remains the primary host for large videos, with tmpfiles as backup.
    """
    primary = os.getenv("UPLOAD_PRIMARY", "litterbox").strip()
    backup = os.getenv("UPLOAD_BACKUP", "tmpfiles").strip()
    try:
        expiry = int(os.getenv("UPLOAD_EXPIRY_MINUTES", "60"))
    except ValueError:
        expiry = 60
    return {
        "primary": primary if primary in HOSTS else "litterbox",
        "backup": backup if backup in HOSTS else None,
        "expiry_minutes": min(EXPIRY_OPTIONS, key=lambda v: abs(v - expiry)),
        "selfhost_base": _public_base_default(),
    }


def _sanitize(raw: dict[str, object], base: dict[str, object]) -> dict[str, object]:
    """Merge valid stored preferences over the supplied defaults.

    Invalid values are dropped so a malformed stored blob cannot break uploads.
    """
    out = dict(base)
    if raw.get("primary") in HOSTS:
        out["primary"] = raw["primary"]
    if "backup" in raw:
        out["backup"] = raw["backup"] if raw["backup"] in HOSTS else None
    if raw.get("expiry_minutes") in EXPIRY_OPTIONS:
        out["expiry_minutes"] = raw["expiry_minutes"]
    if isinstance(raw.get("selfhost_base"), str) and raw["selfhost_base"].strip():
        out["selfhost_base"] = raw["selfhost_base"].strip().rstrip("/")
    # A backup equal to the primary is just "no backup".
    if out["backup"] == out["primary"]:
        out["backup"] = None
    return out


def resolve_prefs(user: User) -> dict[str, object]:
    """The effective prefs for a user: their stored choices over the default."""
    base = default_prefs()
    blob = getattr(user, "upload_prefs_json", None)
    if not blob:
        return base
    try:
        raw = json.loads(blob)
    except (ValueError, TypeError):
        return base
    return _sanitize(raw, base) if isinstance(raw, dict) else base


def current_upload_prefs() -> dict[str, object]:
    """Return upload preferences for the current request.

    Resolve them through the bound tenant, or use instance defaults anonymously.
    """
    uid = current_tenant()
    if uid:
        user = get_db().get_user(uid)
        if user:
            return resolve_prefs(user)
    return default_prefs()


class UploadPrefsUpdate(BaseModel):
    """Optional upload-host preferences submitted by a user."""

    primary: str | None = None
    backup: str | None = None
    expiry_minutes: int | None = None
    selfhost_base: str | None = None


def _meta() -> dict[str, object]:
    return {
        "hosts": list(HOSTS),
        "expiry_options": list(EXPIRY_OPTIONS),
        "expiry_configurable": list(EXPIRY_CONFIGURABLE),
        "selfhost_base_default": _public_base_default(),
        "public_base_url_set": bool(_public_base_default()),
    }


@router.get("")
async def get_upload_prefs(user: Annotated[User, Depends(require_user)]) -> dict[str, object]:
    """Return the user's upload preferences and available choices."""
    return {"prefs": resolve_prefs(user), **_meta()}


@router.put("")
async def set_upload_prefs(data: UploadPrefsUpdate, user: Annotated[User, Depends(require_user)]) -> dict[str, object]:
    """Save the user's upload preferences."""
    merged = _sanitize({k: v for k, v in data.model_dump().items() if v is not None}, resolve_prefs(user))
    get_db().set_user_upload_prefs(user.id, json.dumps(merged))
    return {"prefs": merged, **_meta()}


class SelfhostTest(BaseModel):
    """Optional self-host base URL to check."""

    selfhost_base: str | None = None


@router.post("/test-selfhost")
async def check_selfhost(data: SelfhostTest, user: Annotated[User, Depends(require_user)]) -> dict[str, bool | str]:
    """Check that the configured self-host URL can serve media externally.

    Stage a small file, fetch its signed public URL and verify the returned bytes.
    """
    base = (data.selfhost_base or resolve_prefs(user).get("selfhost_base") or "").strip()
    token = secrets.token_hex(8)
    test_dir = config.ROOT_DIR / "chat" / "__selfhost_test__"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / f"{token}.txt"
    test_file.write_text(token)
    try:
        url = selfhost_url(test_file, base, ttl_seconds=120)
        with httpx.Client() as client:
            resp = get_public(client, url, timeout=10)
        if resp.status_code != 200:
            return {"ok": False, "detail": f"The URL returned HTTP {resp.status_code} — check the base URL and proxy."}
        if resp.text.strip() != token:
            return {"ok": False, "detail": "The URL was reachable but served the wrong content (proxy/caching?)."}
    except ValueError as e:
        return {"ok": False, "detail": str(e)}
    except UnsafeURLError as e:
        return {"ok": False, "detail": f"Not publicly reachable: {e}. Pollo needs a public https address."}
    except httpx.HTTPError as e:
        return {"ok": False, "detail": f"Couldn't reach the URL: {e}"}
    finally:
        test_file.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            test_dir.rmdir()  # remove the staging dir when empty
    return {"ok": True, "detail": f"Reachable — Pollo can fetch source media from {base}."}
