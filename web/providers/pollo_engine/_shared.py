"""Shared primitives for the Pollo engine family builders: terminal statuses,
input-parsing helpers, and aspect-ratio maths."""

from __future__ import annotations

from PIL import Image

# Terminal task statuses from the Pollo API (used by the poller in pollo.py).
SUCCESS_STATUSES = ("succeed", "success", "succeeded", "complete", "completed")
ERROR_STATUSES = ("error", "failed")

_RATIO_WORDS = {"portrait": "9:16", "landscape": "16:9", "square": "1:1"}


def parse_aspect_ratio(mode: str = "portrait") -> str:
    """A ratio string from a mode word or a direct 'W:H' value (default 9:16)."""
    if ":" in mode:
        return mode
    return _RATIO_WORDS.get(mode, "9:16")


def valid_length(length_str: str, valid: tuple, default: int) -> int:
    """Parse + validate a length against `valid` (empty = accept any)."""
    try:
        length = int(length_str)
    except (ValueError, TypeError):
        return default
    if valid:
        return length if length in valid else default
    return length


def _image_dimensions(image_path) -> tuple[int, int]:
    return Image.open(image_path).size


def _closest_ratio(width: int, height: int, ratios: tuple[str, ...]) -> str:
    actual = width / height
    return min(ratios, key=lambda r: abs((lambda w, h: w / h)(*map(int, r.split(":"))) - actual))


def closest_aspect_ratio(width: int, height: int, ratios: tuple[str, ...]) -> str:
    """The ratio in `ratios` closest to width/height (public: used by pollo.py)."""
    return _closest_ratio(width, height, ratios)


def _aspect_from_image(image_path, valid_ratios: tuple, skip_nonnumeric: bool) -> str | None:
    ratios = tuple(r for r in valid_ratios if ":" in r) if skip_nonnumeric else valid_ratios
    if not ratios or not image_path:
        return None
    return _closest_ratio(*_image_dimensions(image_path), ratios)
