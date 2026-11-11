"""Image API bodies."""

from __future__ import annotations

from typing import Any

from web.core.config import POLLO_GENERATION_BASE
from web.providers.pollo_engine._shared import parse_aspect_ratio

_V1_IMAGE_DEFAULTS: dict[str, Any] = {
    "VALID_RATIOS": (),
    "VALID_RESOLUTIONS": (),
    "DEFAULT_RATIO_KEYWORD": "square",
    "HAS_SEED": False,
    "ACCEPTS_IMAGES": True,
    "MAX_IMAGES": 0,
    "ASPECT_RATIO_WITH_IMAGES": True,
}

IMAGE_MODELS: dict[str, dict[str, Any]] = {
    "pollojourney": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollojourney-v8-2-image",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "HAS_SEED": True,
    },
    "seedream": {
        "PROVIDER": "bytedance",
        "MODEL": "seedream-5-0-lite",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9"),
        "VALID_RESOLUTIONS": ("2K", "3K", "4K"),
        "MAX_IMAGES": 14,
    },
    "nanobanana2": {
        "PROVIDER": "google",
        "MODEL": "nano-banana-2",
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
    "klingv3image": {
        "PROVIDER": "kling-ai",
        "MODEL": "kling-v3-image",
        "VALID_RATIOS": ("1:1", "3:2", "2:3", "3:4", "4:3", "16:9", "9:16", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 1,
    },
    "klingv3omniimage": {
        "PROVIDER": "kling-ai",
        "MODEL": "kling-v3-omni",
        "VALID_RATIOS": ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "auto"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "MAX_IMAGES": 10,
    },
    "seedreampro": {
        "PROVIDER": "bytedance",
        "MODEL": "seedream-5-0-pro",
        "VALID_RATIOS": ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 10,
    },
    "seedreamflash": {
        "PROVIDER": "bytedance",
        "MODEL": "seedream-5-0-flash",
        "VALID_RATIOS": ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "1.5K", "2K"),
        "MAX_IMAGES": 10,
    },
    "qwenimage3": {
        "PROVIDER": "alibaba",
        "MODEL": "qwen-image-3",
        "VALID_RATIOS": ("1:1", "3:4", "4:3", "16:9", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 3,
    },
    "qwenimage3pro": {
        "PROVIDER": "alibaba",
        "MODEL": "qwen-image-3-pro",
        "VALID_RATIOS": ("1:1", "3:4", "4:3", "16:9", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 3,
    },
    "qwenimageflash": {
        "PROVIDER": "alibaba",
        "MODEL": "pre-qwen-image-flash",
        "VALID_RATIOS": ("1:1", "3:4", "4:3", "16:9", "9:16"),
        "ACCEPTS_IMAGES": False,
    },
    # --- Newer frontier models (added 2026-11) ---
    "nanobananapro": {
        "PROVIDER": "google",
        "MODEL": "nano-banana-pro",
        "VALID_RATIOS": ("1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "MAX_IMAGES": 14,
    },
    "nanobanana21": {
        "PROVIDER": "google",
        "MODEL": "nano-banana-2-1",
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
    "fluxkontextpro": {
        "PROVIDER": "flux",
        "MODEL": "flux-kontext-pro",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "MAX_IMAGES": 1,
    },
    "fluxkontextmax": {
        "PROVIDER": "flux",
        "MODEL": "flux-kontext-max",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "MAX_IMAGES": 1,
    },
    "flux2max": {
        "PROVIDER": "flux",
        "MODEL": "flux-2-max",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "MAX_IMAGES": 10,
    },
    "gptimage25": {
        "PROVIDER": "openai",
        "MODEL": "gpt-image-2-5",
        "VALID_RATIOS": ("auto", "1:1", "9:16", "16:9", "21:9", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4"),
        "VALID_RESOLUTIONS": ("1K", "2K", "4K"),
        "MAX_IMAGES": 16,
    },
    "seedream45": {
        "PROVIDER": "bytedance",
        "MODEL": "seedream-4-5",
        "VALID_RATIOS": ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"),
        "VALID_RESOLUTIONS": ("2K", "4K"),
        "MAX_IMAGES": 10,
    },
    "midjourneyv82": {
        "PROVIDER": "midjourney",
        "MODEL": "midjourney-v8-2",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 1,
    },
    "grokimage20": {
        "PROVIDER": "xai",
        "MODEL": "grok-imagine-image-2-0",
        "VALID_RATIOS": ("auto", "1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "2:1", "1:2", "21:9"),
        "VALID_RESOLUTIONS": ("1K", "2K"),
        "MAX_IMAGES": 1,
    },
    "recraftv3": {
        "PROVIDER": "recraft",
        "MODEL": "recraft-v3",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "ACCEPTS_IMAGES": False,
    },
    "ideogramv2turbo": {
        "PROVIDER": "ideogram",
        "MODEL": "ideogram-v2-turbo",
        "VALID_RATIOS": ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"),
        "ACCEPTS_IMAGES": False,
    },
    # Image tools (added 2026-11): a source image in, an image out, no prompt.
    # "TOOL" picks the body; image upscale's `scale` rides the resolution picker.
    "imageupscale": {
        "V1_URL": f"{POLLO_GENERATION_BASE}/image-upscale",
        "TOOL": "upscale",
        "VALID_RESOLUTIONS": ("1x", "2x", "4x", "8x", "16x"),
        "MAX_IMAGES": 1,
    },
    "imagebgremove": {
        "V1_URL": f"{POLLO_GENERATION_BASE}/image-background-remove",
        "TOOL": "bgremove",
        "MAX_IMAGES": 1,
    },
}


def img_cfg(model_id: str) -> dict[str, Any]:
    return {**_V1_IMAGE_DEFAULTS, **IMAGE_MODELS[model_id]}


def image_model_url(model_id: str) -> str:
    c = img_cfg(model_id)
    return c.get("V1_URL") or f"{POLLO_GENERATION_BASE}/{c['PROVIDER']}/{c['MODEL']}/image"


def _tool_payload(c: dict[str, Any], image_url: str | None, **kw: Any) -> dict[str, Any]:
    """An image tool: {image} (+ upscale's integer scale from "2x"-style values)."""
    image = image_url or next(iter(kw.get("images") or []), None)
    if not image:
        raise ValueError("This tool needs a source image")
    attrs: dict[str, Any] = {"image": image}
    if c["TOOL"] == "upscale":
        scale = str(kw.get("resolution") or "2x")
        attrs["scale"] = int(scale[:-1]) if scale in c["VALID_RESOLUTIONS"] else 2
    return {"input": attrs}


def image_payload(model_id: str, *, prompt: str, image_url: str | None, **kw: Any) -> dict[str, Any]:
    """Build the image API body."""
    c = img_cfg(model_id)
    if c.get("TOOL"):
        return _tool_payload(c, image_url, **kw)
    aspect_ratio = kw.get("aspect_ratio") or parse_aspect_ratio(c["DEFAULT_RATIO_KEYWORD"])
    resolution = kw.get("resolution")
    resolution = resolution if resolution in c["VALID_RESOLUTIONS"] else None
    seed = kw.get("seed") if c["HAS_SEED"] else None

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
