"""Tests for web/uploads.py — image upload helpers shared by chat and Generate."""
import asyncio
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from web.uploads import image_media_type, read_image_upload, safe_filename


class FakeUpload:
    def __init__(self, content: bytes, content_type: str):
        self._content = content
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._content


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("name", ["", "a/b.png", "..", "x..png", "a\\b.png", ".env", "../x"])
def test_safe_filename_rejects(name):
    with pytest.raises(HTTPException) as e:
        safe_filename(name)
    assert e.value.status_code == 400


def test_safe_filename_accepts_plain_names():
    assert safe_filename("img_abc123.png") == "img_abc123.png"


def test_image_media_type():
    assert image_media_type("a.JPG") == "image/jpeg"
    assert image_media_type("a.webp") == "image/webp"
    assert image_media_type("a.mp4") is None


def test_read_image_upload_ok():
    content, ext = asyncio.run(read_image_upload(FakeUpload(_png(), "image/png")))
    assert ext == ".png" and content.startswith(b"\x89PNG")


@pytest.mark.parametrize("content,content_type,msg", [
    (b"x", "text/plain", "Unsupported file type"),
    (b"not an image", "image/png", "not a valid image"),
])
def test_read_image_upload_rejects(content, content_type, msg):
    with pytest.raises(HTTPException) as e:
        asyncio.run(read_image_upload(FakeUpload(content, content_type)))
    assert e.value.status_code == 400 and msg in e.value.detail
