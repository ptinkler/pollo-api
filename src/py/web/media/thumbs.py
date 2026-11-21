"""Thumbnails for the media grids, made on a small background pool and cached on disk."""

import asyncio
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageOps

from web.core.env import number_env
from web.media import cache as media_cache
from web.media.paths import library_kind, thumb_dir
from web.media.video import first_frame_jpeg

THUMB_SIZE = 320  # px, the thumbnail's shorter side (grid tiles are square, cropped to fill)


DEFAULT_THUMB_WORKERS = 2


# Thumbnails made at once (env THUMB_WORKERS, default 2): a grid asks for many together, each costs CPU
THUMB_WORKERS = int(number_env("THUMB_WORKERS", DEFAULT_THUMB_WORKERS, minimum=1))


def thumb_path(path: Path, size: int = THUMB_SIZE) -> Path:
    """Return a file's thumbnail cache path, keyed by path, mtime, and size.

    An edited file therefore receives a fresh thumbnail.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    key = f"{path}:{mtime}" + (f":{size}" if size != THUMB_SIZE else "")
    return thumb_dir() / f"{hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()}.jpg"


def make_thumb(path: Path, size: int = THUMB_SIZE) -> Path | None:
    """Create or return a cached thumbnail for an image or video.

    The thumbnail's shorter side is at most ``size`` pixels. Return ``None``
    when the source cannot be read.
    """
    out = thumb_path(path, size)
    if out.is_file():
        return out
    try:
        if library_kind(path) == "video":
            frame = first_frame_jpeg(path)
            if not frame:
                return None
            img = Image.open(io.BytesIO(frame))
        else:
            img = Image.open(path)
        w, h = img.size
        scale = min(1.0, size / min(w, h))
        target = (max(1, round(w * scale)), max(1, round(h * scale)))
        img.draft("RGB", target)  # JPEGs decode straight at a reduced size — much faster
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail(target, Image.Resampling.LANCZOS, reducing_gap=2.0)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".part")
        img.save(tmp, "JPEG", quality=80)
        tmp.replace(out)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):  # broken files have no thumbnail
        return None
    else:
        return out


# New thumbnails are made on their own small pool, THUMB_WORKERS at a time
thumb_pool = ThreadPoolExecutor(max_workers=THUMB_WORKERS, thread_name_prefix="media-thumb")


async def thumb_response(path: Path, size: int = THUMB_SIZE) -> FileResponse:
    """Return a cached thumbnail, generating it in the thumbnail pool if needed.

    Awaiting the pool avoids blocking worker threads used by synchronous routes.
    """
    thumb = thumb_path(path, size)
    if not thumb.is_file():
        thumb = await asyncio.wrap_future(thumb_pool.submit(make_thumb, path, size))
    if not thumb:
        raise HTTPException(404, "No thumbnail")
    return FileResponse(
        thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )


def forget_file(path: Path) -> None:
    """Clear cached data for a file being deleted.

    Removes its thumbnail and cached duration.
    """
    thumb_path(path).unlink(missing_ok=True)
    media_cache.forget(path)
