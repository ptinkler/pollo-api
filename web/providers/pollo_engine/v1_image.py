"""V1 image API bodies (BaseV1ImageGenerator)."""

from __future__ import annotations

import os
from typing import Any

from web.core.config import POLLO_API_V1_BASE

from ._shared import _aspect_ratio

_V1_IMAGE_DEFAULTS: dict[str, Any] = {
    "VALID_RATIOS": (),
    "VALID_RESOLUTIONS": (),
    "DEFAULT_RATIO_KEYWORD": "square",
    "HAS_SEED": False,
    "ACCEPTS_IMAGES": True,
    "MAX_IMAGES": 0,
    "ASPECT_RATIO_WITH_IMAGES": True,
}

V1_IMAGE: dict[str, dict[str, Any]] = {
    "pollojourneyv1": {
        "V1_PROVIDER": "pollo-ai",
        "V1_MODEL": "pollojourney-v8-2-image",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "HAS_SEED": True,
    },
    "seedreamv1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedream-5-0-lite",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9"),
        "VALID_RESOLUTIONS": ("2K", "3K", "4K"),
        "MAX_IMAGES": 14,
    },
    "nanobanana2v1": {
        "V1_PROVIDER": "google",
        "V1_MODEL": "nano-banana-2",
        "VALID_RATIOS": (
            "1:1",
            "9:16",
            "16:9",
            "4:3",
            "3:4",
            "3:2",
            "2:3",
            "5:4",
            "4:5",
            "21:9",
            "1:4",
            "4:1",
            "8:1",
            "1:8",
        ),
        "VALID_RESOLUTIONS": ("0.5K", "1K", "2K", "4K"),
    },
    "klingv3imagev1": {
        "V1_PROVIDER": "kling-ai",
        "V1_MODEL": "kling-v3-image",
        "VALID_RATIOS": ("1:1", "3:2", "2:3", "3:4", "4:3", "16:9", "9:16", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 1,
    },
    "klingv3omniimagev1": {
        "V1_PROVIDER": "kling-ai",
        "V1_MODEL": "kling-v3-omni",
        "VALID_RATIOS": ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "auto"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "MAX_IMAGES": 10,
    },
    "seedreamprov1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedream-5-0-pro",
        "VALID_RATIOS": ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 10,
    },
    "seedreamflashv1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedream-5-0-flash",
        "VALID_RATIOS": ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "1.5K", "2K"),
        "MAX_IMAGES": 10,
    },
    "qwenimage3v1": {
        "V1_PROVIDER": "alibaba",
        "V1_MODEL": "qwen-image-3",
        "VALID_RATIOS": ("1:1", "3:4", "4:3", "16:9", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 3,
    },
    "qwenimage3prov1": {
        "V1_PROVIDER": "alibaba",
        "V1_MODEL": "qwen-image-3-pro",
        "VALID_RATIOS": ("1:1", "3:4", "4:3", "16:9", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 3,
    },
    "qwenimageflashv1": {
        "V1_PROVIDER": "alibaba",
        "V1_MODEL": "pre-qwen-image-flash",
        "VALID_RATIOS": ("1:1", "3:4", "4:3", "16:9", "9:16"),
        "ACCEPTS_IMAGES": False,
    },
    # --- Newer frontier models (added 2026-11) ---
    "nanobananaprov1": {
        "V1_PROVIDER": "google",
        "V1_MODEL": "nano-banana-pro",
        "VALID_RATIOS": ("1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "MAX_IMAGES": 14,
    },
    "nanobanana21v1": {
        "V1_PROVIDER": "google",
        "V1_MODEL": "nano-banana-2-1",
        "VALID_RATIOS": (
            "1:1",
            "9:16",
            "16:9",
            "4:3",
            "3:4",
            "3:2",
            "2:3",
            "5:4",
            "4:5",
            "21:9",
            "1:4",
            "4:1",
            "8:1",
            "1:8",
        ),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
    },
    "fluxkontextprov1": {
        "V1_PROVIDER": "flux",
        "V1_MODEL": "flux-kontext-pro",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "MAX_IMAGES": 1,
    },
    "fluxkontextmaxv1": {
        "V1_PROVIDER": "flux",
        "V1_MODEL": "flux-kontext-max",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "MAX_IMAGES": 1,
    },
    "flux2maxv1": {
        "V1_PROVIDER": "flux",
        "V1_MODEL": "flux-2-max",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "MAX_IMAGES": 10,
    },
    "gptimage25v1": {
        "V1_PROVIDER": "openai",
        "V1_MODEL": "gpt-image-2-5",
        "VALID_RATIOS": ("auto", "1:1", "9:16", "16:9", "21:9", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "MAX_IMAGES": 16,
    },
    "seedream45v1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedream-4-5",
        "VALID_RATIOS": ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"),
        "VALID_RESOLUTIONS": ("2K", "4K"),
        "MAX_IMAGES": 10,
    },
    "midjourneyv82v1": {
        "V1_PROVIDER": "midjourney",
        "V1_MODEL": "midjourney-v8-2",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 1,
    },
    "grokimage20v1": {
        "V1_PROVIDER": "xai",
        "V1_MODEL": "grok-imagine-image-2-0",
        "VALID_RATIOS": ("auto", "1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "2:1", "1:2", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 1,
    },
    "recraftv3v1": {
        "V1_PROVIDER": "recraft",
        "V1_MODEL": "recraft-v3",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "ACCEPTS_IMAGES": False,
    },
    "ideogramv2turbov1": {
        "V1_PROVIDER": "ideogram",
        "V1_MODEL": "ideogram-v2-turbo",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "ACCEPTS_IMAGES": False,
    },
}


def _img_cfg(model_id: str) -> dict[str, Any]:
    return {**_V1_IMAGE_DEFAULTS, **V1_IMAGE[model_id]}


def v1_image_model_url(model_id: str) -> str:
    c = _img_cfg(model_id)
    return f"{POLLO_API_V1_BASE}/{c['V1_PROVIDER']}/{c['V1_MODEL']}/image"


def v1_image_payload(model_id: str, *, prompt: str, image_url: str | None, **kw) -> dict[str, Any]:
    """Build the v1 image API body, matching BaseV1ImageGenerator exactly."""
    c = _img_cfg(model_id)
    aspect_ratio = kw.get("aspect_ratio") or _aspect_ratio(
        os.getenv("ASPECT_RATIO") or os.getenv("RATIO", c["DEFAULT_RATIO_KEYWORD"])
    )
    resolution = kw.get("resolution") or os.getenv("RESOLUTION")
    resolution = resolution if resolution in c["VALID_RESOLUTIONS"] else None
    seed = (kw.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None)) if c["HAS_SEED"] else None

    images = ([image_url] if image_url else []) + (kw.get("images") or [])
    if not c["ACCEPTS_IMAGES"]:
        images = []
    elif c["MAX_IMAGES"]:
        images = images[: c["MAX_IMAGES"]]

    attrs: dict[str, Any] = {"prompt": prompt}
    if not images or c["ASPECT_RATIO_WITH_IMAGES"]:
        attrs["aspectRatio"] = aspect_ratio
    if images:
        attrs["images"] = images
    if resolution:
        attrs["resolution"] = resolution
    if seed is not None:
        attrs["seed"] = seed
    return {"input": attrs}
