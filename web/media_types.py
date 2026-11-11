"""What counts as an image, a video or an audio clip.

One place for it. These sets were previously spelled out in six modules —
media.py, chatgpt_import.py, chat/constants.py, chat/routes.py,
chat/polling.py and chat/routes_turns.py — which is how a `.webm` could be
treated as a video in one and fall through to "image" in another.

`*_EXTS` map a media type to the extension a file of it is saved with;
`kind_of()` answers the reverse question for a filename.
"""

from pathlib import Path

# media type -> the extension we save it as
IMAGE_EXTS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}
VIDEO_EXTS = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}
AUDIO_EXTS = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
}

IMAGE_SUFFIXES = frozenset(IMAGE_EXTS.values())
VIDEO_SUFFIXES = frozenset(VIDEO_EXTS.values())
AUDIO_SUFFIXES = frozenset(AUDIO_EXTS.values())


def kind_of(name: str | Path) -> str | None:
    """ "image" | "video" | "audio" for a filename, or None if it is none of them."""
    suffix = Path(name).suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    return "image" if suffix in IMAGE_SUFFIXES else None
