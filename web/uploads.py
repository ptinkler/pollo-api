"""
Image upload and filename helpers shared by the Generate page (web/api.py)
and chat (web/chat.py).
"""
import io
import mimetypes
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

# Image uploads both pages accept (content type → saved extension)
IMAGE_UPLOAD_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_IMAGE_UPLOAD_BYTES = 20 * 1024 * 1024


def safe_filename(name: str) -> str:
    """A bare filename from a URL path, or 400 — no directories, traversal or dotfiles."""
    if not name or Path(name).name != name or "\\" in name or ".." in name or name.startswith("."):
        raise HTTPException(400, "Invalid filename")
    return name


def image_media_type(path: Path | str) -> str | None:
    """The image MIME type for a filename, from its extension."""
    media_type = mimetypes.guess_type(str(path))[0]
    return media_type if media_type and media_type.startswith("image/") else None


async def read_image_upload(file: UploadFile) -> tuple[bytes, str]:
    """Validate an uploaded image (type, size, real image content); returns
    (bytes, file extension to save it with)."""
    ext = IMAGE_UPLOAD_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Use PNG, JPEG, WebP or GIF.")
    content = await file.read()
    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_IMAGE_UPLOAD_BYTES // 1024 // 1024} MB)")
    # Check the actual content regardless of the client-supplied content type
    try:
        Image.open(io.BytesIO(content)).verify()
    except Exception:
        raise HTTPException(400, "File is not a valid image")
    return content, ext
