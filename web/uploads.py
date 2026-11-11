"""Reading and storing uploaded media, and encoding a stored file for a provider
that wants it inline. Shared by the HTTP routes and the provider layer.
"""

import base64
import hashlib
import io
import mimetypes
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

# Image uploads both pages accept (content type → saved extension)
IMAGE_UPLOAD_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_IMAGE_UPLOAD_BYTES = 20 * 1024 * 1024

# Video uploads (chat's Recast source video); clips are short (4-30s)
VIDEO_UPLOAD_TYPES = {"video/mp4": ".mp4"}
MAX_VIDEO_UPLOAD_BYTES = 200 * 1024 * 1024

# Audio uploads (chat's lip-sync track); content type → saved extension
AUDIO_UPLOAD_TYPES = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
}
MAX_AUDIO_UPLOAD_BYTES = 50 * 1024 * 1024

# Images above this go to a provider downscaled, so request bodies stay
# reasonable (providers cap inline image sizes).
MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024


def safe_filename(name: str) -> str:
    """A bare filename from a URL path, or 400 — no directories, traversal or dotfiles."""
    if not name or Path(name).name != name or "\\" in name or ".." in name or name.startswith("."):
        raise HTTPException(400, "Invalid filename")
    return name


def image_media_type(path: Path | str) -> str | None:
    """The image MIME type for a filename, from its extension."""
    media_type = mimetypes.guess_type(str(path))[0]
    return media_type if media_type and media_type.startswith("image/") else None


def is_blank_image(data: bytes) -> bool:
    """A solid black picture: what many providers' safety filters send instead
    of the image they blocked. Even a night scene has some brighter pixels.
    """
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("L")
            im.thumbnail((64, 64))
            return im.getextrema()[1] <= 4
    except Exception:
        return False  # not an image Pillow reads; leave it to the caller


def _is_real_image(content: bytes) -> bool:
    """The bytes really are an image, whatever content type the client claimed."""
    try:
        Image.open(io.BytesIO(content)).verify()
    except Exception:  # anything Pillow rejects is not an image
        return False
    return True


def _is_real_video(content: bytes) -> bool:
    """MP4/QuickTime files carry an "ftyp" box near the start — a cheap check
    that the bytes are really a video, not a renamed file.
    """
    return b"ftyp" in content[:64]


async def _read_upload(
    file: UploadFile,
    types: dict[str, str],
    max_bytes: int,
    accepted: str,
    check=None,
    kind: str = "",
) -> tuple[bytes, str]:
    """Validate one upload against its type map, size cap and (optionally) its
    real content; returns (bytes, the extension to save it with). `accepted`
    names the formats for the wrong-type message, `kind` the thing it should
    have been for the bad-content one.
    """
    ext = types.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Use {accepted}.")
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(400, f"File too large (max {max_bytes // 1024 // 1024} MB)")
    if check and not check(content):
        raise HTTPException(400, f"File is not a valid {kind}")
    return content, ext


async def read_image_upload(file: UploadFile) -> tuple[bytes, str]:
    return await _read_upload(
        file, IMAGE_UPLOAD_TYPES, MAX_IMAGE_UPLOAD_BYTES, "PNG, JPEG, WebP or GIF", _is_real_image, "image"
    )


async def read_video_upload(file: UploadFile) -> tuple[bytes, str]:
    return await _read_upload(file, VIDEO_UPLOAD_TYPES, MAX_VIDEO_UPLOAD_BYTES, "MP4", _is_real_video, "MP4 video")


async def read_audio_upload(file: UploadFile) -> tuple[bytes, str]:
    return await _read_upload(file, AUDIO_UPLOAD_TYPES, MAX_AUDIO_UPLOAD_BYTES, "MP3, WAV, M4A or AAC")


def file_to_data_url(path: Path) -> str:
    """Encode a local image as a data URL, downscaling big ones (and GIFs,
    which several providers reject) so request bodies stay reasonable.
    """
    raw = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    if len(raw) > MAX_INLINE_IMAGE_BYTES or mime == "image/gif":
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        img.thumbnail((2048, 2048))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        raw, mime = buf.getvalue(), "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def store_deduped(directory: Path, prefix: str, content: bytes, ext: str) -> str:
    """Save `content` as `<prefix><content hash><ext>` in `directory` and return
    the name. The same bytes always get the same name, so re-uploading or
    re-importing an image reuses the file instead of storing another copy.
    """
    name = f"{prefix}{hashlib.sha256(content).hexdigest()[:16]}{ext}"
    path = directory / name
    if not path.is_file():
        directory.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return name
