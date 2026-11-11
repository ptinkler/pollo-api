"""Self-hosted source media: serve a local upload at a signed, expiring,
unauthenticated URL so a provider that only takes a URL (Pollo) can fetch it
from *this* instance instead of a third-party temp host (catbox/tmpfiles).

The token signs the file path with the session secret, so it can't be forged
or widened; the route additionally confines reads to the media roots. Links
expire after the configured TTL — the same short-lived, unguessable exposure
model as the public temp hosts, but on the instance's own domain.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from web.core import config

from .auth import user_secret

router = APIRouter(prefix="/api/public-media")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _media_roots() -> list[Path]:
    """Directories a self-host link may serve from — every source a Pollo upload
    can draw from: chat uploads/outputs, character reference images, and the
    per-user library. Resolved so a signed-but-crafted path can't escape."""
    return [(config.ROOT_DIR / d).resolve() for d in ("chat", "characters", "library")]


def _under_media_root(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(root) for root in _media_roots())


def sign_media_token(filepath: Path, ttl_seconds: int) -> str:
    """A signed, expiring token referencing an absolute local media path."""
    b64path = _b64(str(Path(filepath).resolve()).encode())
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{b64path}.{exp}"
    sig = hmac.new(user_secret(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(sig)}"


def _resolve_token(token: str) -> Path | None:
    """The valid, unexpired, in-bounds file a token points to, else None."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    b64path, exp_s, sig_b64 = parts
    payload = f"{b64path}.{exp_s}"
    expected = hmac.new(user_secret(), payload.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        if time.time() > int(exp_s):
            return None
        path = Path(_unb64(b64path).decode())
    except (ValueError, TypeError):
        return None
    if not _under_media_root(path) or not path.is_file():
        return None
    return path


def selfhost_url(filepath: Path, base_url: str, ttl_seconds: int) -> str:
    """Public URL for a provider to fetch *filepath* from this instance.
    Raises ValueError if no reachable base URL is configured."""
    base = (base_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ValueError(
            "Self-host upload needs a public base URL — set it in Settings → Media uploads "
            "(or PUBLIC_BASE_URL). It must be the https address this instance is reachable at."
        )
    return f"{base}/api/public-media/{sign_media_token(filepath, ttl_seconds)}"


@router.get("/{token}")
def serve_public_media(token: str):
    """Stream a signed, unexpired media file. Public (no login): providers can't
    present our cookie. 404 on a bad/expired/out-of-bounds token so the route
    leaks nothing about what does or doesn't exist."""
    path = _resolve_token(token)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)
