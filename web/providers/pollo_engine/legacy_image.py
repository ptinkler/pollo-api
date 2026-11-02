"""Legacy (pre-v1) image API bodies."""

from __future__ import annotations

import os
from typing import Any

from web.core.config import POLLO_API_BASE

from ._shared import _aspect_ratio

LEGACY_IMAGE: dict[str, dict[str, Any]] = {
    "pollojourney": {
        "pm": "pollojourney/pollojourney-v8-2-image/image",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "builder": "journey",
    },
    "nanobanana2": {
        "pm": "google/nano-banana-2/image",
        "VALID_RATIOS": ("1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "VALID_THINKING_LEVELS": ("minimal", "high"),
        "builder": "nano",
    },
    "seedream": {
        "pm": "seedream/seedream-5-0-lite/image",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9"),
        "VALID_RESOLUTIONS": ("2K", "3K", "4K"),
        "builder": "seedream",
    },
    "polloimage2": {
        "pm": "pollo/pollo-image-v2/image",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "4:5", "5:4"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "VALID_MODES": ("fast", "standard", "professional"),
        "builder": "polloimage2",
    },
    "qwenimage": {
        "pm": "qwen/qwen-image/image",
        "VALID_RATIOS": ("1:1", "3:4", "4:3", "16:9", "9:16"),
        "VALID_RESOLUTIONS": (),
        "builder": "qwen",
    },
}


def legacy_image_model_url(model_id: str) -> str:
    return f"{POLLO_API_BASE}/{LEGACY_IMAGE[model_id]['pm']}"


def _legacy_img_inputs(c: dict[str, Any], **kw) -> dict[str, Any]:
    resolution = kw.get("resolution") or os.getenv("RESOLUTION")
    thinking = kw.get("thinking_level") or os.getenv("THINKING_LEVEL")
    mode = kw.get("mode") or os.getenv("IMAGE_MODE")
    max_images = kw.get("max_images")
    if max_images is None:
        max_images = int(os.getenv("MAX_IMAGES")) if os.getenv("MAX_IMAGES") else None
    return {
        "aspect_ratio": kw.get("aspect_ratio")
        or _aspect_ratio(os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")),
        "resolution": resolution if resolution in c["VALID_RESOLUTIONS"] else None,
        "seed": kw.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None),
        "images": kw.get("images") or None,
        "thinking_level": thinking if thinking in c.get("VALID_THINKING_LEVELS", ()) else None,
        "mode": mode if mode in c.get("VALID_MODES", ()) else None,
        "max_images": max(1, min(4, int(max_images))) if max_images is not None else None,
    }


def _img_journey(c, prompt, image_url, s) -> dict[str, Any]:
    images = ([image_url] if image_url else []) + (s["images"] or [])
    attrs: dict[str, Any] = {"prompt": prompt, "aspectRatio": s["aspect_ratio"]}
    if images:
        attrs["images"] = images
    if s["resolution"]:
        attrs["resolution"] = s["resolution"]
    if s["seed"] is not None:
        attrs["seed"] = s["seed"]
    return {"input": attrs}


def _img_refs_split(prompt, image_url, s) -> dict[str, Any]:
    """Shared Nano/Seedream shape: a reference list in images[], the single
    upload in imageUrl alongside it."""
    attrs: dict[str, Any] = {"prompt": prompt, "aspectRatio": s["aspect_ratio"]}
    if s["images"]:
        attrs["images"] = s["images"]
        if image_url:
            attrs["imageUrl"] = image_url
    elif image_url:
        attrs["imageUrl"] = image_url
    return attrs


def _img_nano(c, prompt, image_url, s) -> dict[str, Any]:
    attrs = _img_refs_split(prompt, image_url, s)
    if s["resolution"]:
        attrs["resolution"] = s["resolution"]
    if s["thinking_level"]:
        attrs["thinkingLevel"] = s["thinking_level"]
    if s["max_images"] is not None:
        attrs["maxImages"] = s["max_images"]
    return {"input": attrs}


def _img_seedream(c, prompt, image_url, s) -> dict[str, Any]:
    attrs = _img_refs_split(prompt, image_url, s)
    attrs["responseFormat"] = "url"
    if s["resolution"]:
        attrs["resolution"] = s["resolution"]
    if s["max_images"] is not None:
        attrs["maxImages"] = s["max_images"]
    return {"input": attrs}


def _img_polloimage2(c, prompt, image_url, s) -> dict[str, Any]:
    images = ([image_url] if image_url else []) + (s["images"] or [])
    # 2K/4K only run in professional mode; otherwise honour the chosen mode
    mode = "professional" if s["resolution"] and s["resolution"] != "1K" else s["mode"]
    attrs: dict[str, Any] = {"prompt": prompt, "aspectRatio": s["aspect_ratio"]}
    if images:
        attrs["images"] = images
    if s["resolution"]:
        attrs["resolution"] = s["resolution"]
    if mode:
        attrs["mode"] = mode
    return {"input": attrs}


def _img_qwen(c, prompt, image_url, s) -> dict[str, Any]:
    ratio = s["aspect_ratio"] if s["aspect_ratio"] in c["VALID_RATIOS"] else "1:1"
    refs = ([image_url] if image_url else []) + (s["images"] or [])
    attrs: dict[str, Any] = {"prompt": prompt}
    if refs:
        attrs["imageUrl"] = refs[0]  # one reference; the image sets the shape
    else:
        attrs["aspectRatio"] = ratio
    return {"input": attrs}


_LEGACY_IMAGE_BUILDERS = {
    "journey": _img_journey,
    "nano": _img_nano,
    "seedream": _img_seedream,
    "polloimage2": _img_polloimage2,
    "qwen": _img_qwen,
}


def legacy_image_payload(model_id: str, *, prompt: str, image_url: str | None, **kw) -> dict[str, Any]:
    """Build a legacy (pre-v1) image API body, matching the old classes exactly."""
    c = LEGACY_IMAGE[model_id]
    s = _legacy_img_inputs(c, **kw)
    return _LEGACY_IMAGE_BUILDERS[c["builder"]](c, prompt, image_url, s)
