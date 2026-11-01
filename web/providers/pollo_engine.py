"""Data-driven Pollo generation engine (replaces the old generator-class hierarchy).

Each model is a row in a family table (V1_VIDEO, V1_IMAGE, LEGACY_VIDEO,
LEGACY_IMAGE, LEGACY_REF); a small set of family builders turn a row + the
request inputs into the Pollo API body. ModelSpec exposes a model's static data
(the VALID_* the catalogue/validation read) and is a factory for PolloGenerator,
the single runtime object that resolves inputs, builds the payload, and
submits/prices a request — replacing the 44 former generator classes.

The builders were verified byte-identical to those classes (the oracle) before
the classes were removed; tests/test_pollo_engine.py now pins that proven output
as a golden snapshot.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from web.core.cloudflare import is_cloudflare_block
from web.core.config import POLLO_API_BASE, POLLO_API_TIMEOUT, POLLO_API_V1_BASE
from web.core.get_inputs import get_image_url, get_prompt

# Terminal task statuses from the Pollo API (used by the pollers in pollo.py /
# pollo_img2vid.py).
SUCCESS_STATUSES = ("succeed", "success", "succeeded", "complete", "completed")
ERROR_STATUSES = ("error", "failed")

_UNSET = object()

# ── helpers (ported from BaseVideoGenerator) ─────────────────────────

_RATIO_WORDS = {"portrait": "9:16", "landscape": "16:9", "square": "1:1"}


def _aspect_ratio(mode: str = "portrait") -> str:
    """A ratio string from a mode word or a direct 'W:H' value (default 9:16)."""
    if ":" in mode:
        return mode
    return _RATIO_WORDS.get(mode, "9:16")


def _valid_length(length_str: str, valid: tuple, default: int) -> int:
    """Parse + validate a length against `valid` (empty = accept any)."""
    try:
        length = int(length_str)
    except (ValueError, TypeError):
        return default
    if valid:
        return length if length in valid else default
    return length


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes")


# ── V1 video: generic family (BaseV1VideoGenerator) ──────────────────
# Config rows (introspected from the generator classes). Fields omitted here
# take the base defaults below.
_V1_VIDEO_DEFAULTS: dict[str, Any] = {
    "VALID_LENGTHS": (),
    "VALID_RESOLUTIONS": (),
    "VALID_RATIOS": (),
    "DEFAULT_RESOLUTION": "",
    "DEFAULT_LENGTH": 5,
    "HAS_GENERATE_AUDIO": False,
    "HAS_WEB_SEARCH": False,
    "HAS_SEED": False,
    "HAS_IMAGE_TAIL": False,
    "HAS_REFS": False,
    "HAS_MODE": False,
    "HAS_NEGATIVE_PROMPT_AUDIO": False,
    "HAS_ASPECT_RATIO_ON_IMAGE": False,
    "REF_TYPES": ("image", "video", "audio"),
    "MAX_REFS": 0,
    "REF_HAS_SEED": True,
    "REF_VALID_LENGTHS": (),
    "REF_VALID_RESOLUTIONS": (),
    # dispatch + endpoint
    "builder": "generic",
    "endpoint": "video",
    # Kling post-processing flags (ignored by the generic builder)
    "RESOLUTION_IS_MODE": False,
    "MODE_ON_TEXT": True,
    "TEXT_TO_VIDEO": True,
    "IMAGE_TAIL_NEEDS_PRO": False,
    "NO_AUDIO_WITH_IMAGE_TAIL": False,
}

# Kling models share these base values (layered under each Kling row).
_KLING_BASE: dict[str, Any] = {
    "V1_PROVIDER": "kling-ai",
    "VALID_LENGTHS": (5, 10),
    "VALID_RATIOS": ("16:9", "9:16", "1:1"),
    "DEFAULT_RESOLUTION": "",
}

# model_id -> overrides of the defaults above (plus V1_PROVIDER/V1_MODEL)
V1_VIDEO: dict[str, dict[str, Any]] = {
    "pollo20v1": {
        "V1_PROVIDER": "pollo-ai",
        "V1_MODEL": "pollo-v2",
        "VALID_LENGTHS": (5, 10),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("16:9", "9:16", "4:3", "3:4", "1:1"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_REFS": True,
        "REF_TYPES": ("image",),
        "MAX_REFS": 7,
        "REF_VALID_LENGTHS": (1, 2, 3, 4, 5, 6, 7, 8),
        "REF_VALID_RESOLUTIONS": ("540p", "720p", "1080p"),
    },
    "pollo25v1": {
        "V1_PROVIDER": "pollo-ai",
        "V1_MODEL": "pollo-v2-5",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 15),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "VALID_RATIOS": ("16:9", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_MODE": True,
        "MODE_DEFAULT": "basic",
    },
    "pollodance20v1": {
        "V1_PROVIDER": "pollo-ai",
        "V1_MODEL": "pollo-dance-2-0",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 13,
        "REF_HAS_SEED": False,
    },
    "pollodance20fastv1": {
        "V1_PROVIDER": "pollo-ai",
        "V1_MODEL": "pollo-dance-2-0-fast",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 13,
        "REF_HAS_SEED": False,
    },
    "pollo30v1": {
        "V1_PROVIDER": "pollo-ai",
        "V1_MODEL": "pollo-v3-0",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p", "4K"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_MODE": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 13,
        "MODE_PRO_RESOLUTIONS": ("1080p", "4K"),
    },
    "pollo30fastv1": {
        "V1_PROVIDER": "pollo-ai",
        "V1_MODEL": "pollo-v3-0-fast",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 13,
        "REF_HAS_SEED": False,
    },
    "seedance20v1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedance-2-0",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p", "4K"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 15,
    },
    "seedance20fastv1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedance-2-0-fast",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 15,
    },
    "seedance20miniv1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedance-2-0-mini",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 15,
    },
    "seedance25v1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedance-2-5",
        "VALID_LENGTHS": tuple(range(4, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 50,
        "DEFAULT_RATIO": "adaptive",
    },
    "seedance25draftv1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedance-2-5-draft",
        "VALID_LENGTHS": tuple(range(4, 31)),
        "VALID_RESOLUTIONS": ("480p",),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 50,
        "DEFAULT_RATIO": "adaptive",
        "FORCE_RESOLUTION": "480p",
    },
    "minimaxh3v1": {
        "V1_PROVIDER": "minimax",
        "V1_MODEL": "minimax-h3",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "768p", "2K"),
        "VALID_RATIOS": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 15,
    },
    "minimaxh3max": {
        "V1_PROVIDER": "minimax",
        "V1_MODEL": "minimax-h3-max",
        "VALID_LENGTHS": (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "768p", "1080p"),
        "VALID_RATIOS": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 12,
    },
    "wan27v1": {
        "V1_PROVIDER": "alibaba",
        "V1_MODEL": "wan-v2-7",
        "VALID_LENGTHS": tuple(range(2, 16)),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "VALID_RATIOS": ("16:9", "1:1", "4:3", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_NEGATIVE_PROMPT_AUDIO": True,
        "MAX_REFS": 10,
    },
    "wan30v1": {
        "V1_PROVIDER": "alibaba",
        "V1_MODEL": "wan-v3-0",
        "VALID_LENGTHS": tuple(range(2, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "REF_TYPES": ("image", "video", "audio", "file", "link"),
        "MAX_REFS": 22,
        "DEFAULT_RATIO": "adaptive",
    },
    "wan30primev1": {
        "V1_PROVIDER": "alibaba",
        "V1_MODEL": "wan-v3-0-prime",
        "VALID_LENGTHS": tuple(range(2, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "REF_TYPES": ("image", "video", "audio", "file", "link"),
        "MAX_REFS": 22,
        "DEFAULT_RATIO": "adaptive",
    },
    # ── Kling video (builder reuses the generic payload, then remaps the
    # resolution tier to a mode and applies end-frame rules) ──
    "klingv21v1": {
        "V1_MODEL": "kling-v2-1",
        "VALID_RESOLUTIONS": ("std", "pro"),
        "RESOLUTION_IS_MODE": True,
        "TEXT_TO_VIDEO": False,
        "builder": "kling",
    },
    "klingv21masterv1": {"V1_MODEL": "kling-v2-1-master", "builder": "kling"},
    "klingv25turbov1": {
        "V1_MODEL": "kling-v2-5-turbo",
        "VALID_RESOLUTIONS": ("std", "pro"),
        "HAS_IMAGE_TAIL": True,
        "RESOLUTION_IS_MODE": True,
        "MODE_ON_TEXT": False,
        "IMAGE_TAIL_NEEDS_PRO": True,
        "builder": "kling",
    },
    "klingvideoo1v1": {"V1_MODEL": "kling-video-o1", "HAS_IMAGE_TAIL": True, "builder": "kling"},
    "klingv26v1": {
        "V1_MODEL": "kling-v2-6",
        "HAS_IMAGE_TAIL": True,
        "HAS_GENERATE_AUDIO": True,
        "NO_AUDIO_WITH_IMAGE_TAIL": True,
        "builder": "kling",
    },
    "klingv3v1": {
        "V1_MODEL": "kling-v3",
        "VALID_LENGTHS": tuple(range(3, 16)),
        "VALID_RESOLUTIONS": ("std", "pro", "4K"),
        "HAS_IMAGE_TAIL": True,
        "HAS_GENERATE_AUDIO": True,
        "RESOLUTION_IS_MODE": True,
        "builder": "kling",
    },
    "klingv3turbov1": {
        "V1_MODEL": "kling-v3-turbo",
        "VALID_LENGTHS": tuple(range(3, 16)),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "builder": "kling",
    },
    "klingv3omniv1": {
        "V1_MODEL": "kling-v3-omni",
        "VALID_LENGTHS": tuple(range(3, 16)),
        "VALID_RESOLUTIONS": ("std", "pro", "4K"),
        "HAS_IMAGE_TAIL": True,
        "HAS_GENERATE_AUDIO": True,
        "RESOLUTION_IS_MODE": True,
        "builder": "kling",
    },
    # ── Bespoke V1 video shapes ──
    "seedance25extendv1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seedance-2-5",
        "endpoint": "video-extend",
        "VALID_LENGTHS": tuple(range(4, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_SEED": True,
        "HAS_GENERATE_AUDIO": True,
        "builder": "extend",
    },
    "recastv1": {
        "V1_PROVIDER": "alibaba",
        "V1_MODEL": "wan-2-2-animate-mix",
        "endpoint": "motion",
        "HAS_MODE": True,
        "DEFAULT_MODE": "std",
        "builder": "recast",
    },
}


def _cfg(model_id: str) -> dict[str, Any]:
    row = V1_VIDEO[model_id]
    base = {**_V1_VIDEO_DEFAULTS}
    if row.get("builder") == "kling":
        base.update(_KLING_BASE)
    return {**base, **row}


def v1_video_model_url(model_id: str) -> str:
    c = _cfg(model_id)
    return f"{POLLO_API_V1_BASE}/{c['V1_PROVIDER']}/{c['V1_MODEL']}/{c['endpoint']}"


def _normalize_refs(refs: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not refs:
        return None
    out: list[dict[str, Any]] = []
    for ref in refs:
        url = str(ref.get("url") or ref.get("image") or ref.get("video") or ref.get("audio") or "").strip()
        if not url:
            continue
        item: dict[str, Any] = {"url": url}
        if ref.get("type"):
            item["type"] = ref["type"]
        out.append(item)
    return out or None


def _resolve_resolution(c: dict[str, Any], **kw) -> str:
    if c.get("FORCE_RESOLUTION"):
        return c["FORCE_RESOLUTION"]
    return kw.get("resolution") or os.getenv("RESOLUTION", c["DEFAULT_RESOLUTION"])


def _resolve_length(c: dict[str, Any], **kw) -> int:
    length_str = str(kw.get("length") or os.getenv("LENGTH", str(c["DEFAULT_LENGTH"])))
    if kw.get("refs") and c["REF_VALID_LENGTHS"]:
        length = int(length_str) if length_str.isdigit() else c["DEFAULT_LENGTH"]
        return min(c["REF_VALID_LENGTHS"], key=lambda v: abs(v - length))
    return _valid_length(length_str, c["VALID_LENGTHS"], c["DEFAULT_LENGTH"])


def _resolve_aspect_ratio(c: dict[str, Any], **kw) -> str:
    # explicit kwarg, then env, then a model default ("adaptive" on a few),
    # else the base "portrait" → 9:16.
    if kw.get("aspect_ratio"):
        return kw["aspect_ratio"]
    if os.getenv("ASPECT_RATIO") or os.getenv("RATIO"):
        return _aspect_ratio(os.getenv("ASPECT_RATIO") or os.getenv("RATIO"))
    return c.get("DEFAULT_RATIO") or _aspect_ratio("portrait")


def _resolve_mode(c: dict[str, Any], resolution: str, mode: str | None) -> str | None:
    if not c["HAS_MODE"]:
        return None
    if c.get("MODE_PRO_RESOLUTIONS"):
        return "pro" if resolution.upper() in {r.upper() for r in c["MODE_PRO_RESOLUTIONS"]} else "basic"
    return mode or os.getenv("MODE", c.get("MODE_DEFAULT"))


def _process_inputs(c: dict[str, Any], image_url: str | None, **kw) -> dict[str, Any]:
    """Resolve the request inputs against a model's config, mirroring
    BaseV1VideoGenerator.__init__ (kwarg, then env, then default)."""
    refs = _normalize_refs(kw.get("refs")) if c["HAS_REFS"] else None
    resolution = _resolve_resolution(c, **kw)
    return {
        "refs": refs,
        "is_text_only": image_url is None,
        "resolution": resolution,
        "length": _resolve_length(c, **kw),
        "aspect_ratio": _resolve_aspect_ratio(c, **kw),
        "image_tail": (kw.get("image_tail") or os.getenv("IMAGE_TAIL")) if c["HAS_IMAGE_TAIL"] else None,
        "seed": (kw.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None)) if c["HAS_SEED"] else None,
        "generate_audio": (
            (kw.get("generate_audio") if kw.get("generate_audio") is not None else _bool_env("GENERATE_AUDIO", True))
            if c["HAS_GENERATE_AUDIO"]
            else None
        ),
        "web_search": (
            (kw.get("web_search") if kw.get("web_search") is not None else _bool_env("WEBSEARCH", False))
            if c["HAS_WEB_SEARCH"]
            else None
        ),
        "mode": _resolve_mode(c, resolution, kw.get("mode")),
        "negative_prompt": kw.get("negative_prompt") or os.getenv("NEGATIVE_PROMPT")
        if c["HAS_NEGATIVE_PROMPT_AUDIO"]
        else None,
        "audio_url": kw.get("audio_url") if c["HAS_NEGATIVE_PROMPT_AUDIO"] else None,
    }


def _generic_payload(c: dict[str, Any], prompt: str, image_url: str | None, s: dict[str, Any]) -> dict[str, Any]:
    refs, is_text_only = s["refs"], s["is_text_only"]
    attrs: dict[str, Any] = {"prompt": prompt}
    if refs:
        attrs["refs"] = refs
    elif not is_text_only:
        attrs["image"] = image_url
    attrs["duration"] = s["length"]
    attrs["resolution"] = s["resolution"]
    if refs or is_text_only or c["HAS_ASPECT_RATIO_ON_IMAGE"]:
        attrs["aspectRatio"] = s["aspect_ratio"]

    has_refs = bool(refs)
    image_branch = not has_refs and not is_text_only
    candidates = {
        "imageTail": ((s["image_tail"] or None) if c["HAS_IMAGE_TAIL"] else None, image_branch),
        "generateAudio": (s["generate_audio"], True),
        "webSearch": (s["web_search"], not has_refs),
        "seed": (s["seed"], c["REF_HAS_SEED"] or not has_refs),
        "mode": (s["mode"] or None, True),
        "negativePrompt": (s["negative_prompt"] or None, True),
        "audio": (s["audio_url"] or None, not has_refs),
    }
    attrs.update({k: v for k, (v, allowed) in candidates.items() if v is not None and allowed})
    return {"input": attrs}


def _kling_payload(c: dict[str, Any], prompt: str, image_url: str | None, s: dict[str, Any]) -> dict[str, Any]:
    if s["is_text_only"] and not c["TEXT_TO_VIDEO"]:
        raise ValueError(f"{c['V1_MODEL']} needs a source image (it has no text-to-video mode)")
    payload = _generic_payload(c, prompt, image_url, s)
    attrs = payload["input"]
    tier = attrs.pop("resolution", None)
    if tier in c["VALID_RESOLUTIONS"]:
        if not c["RESOLUTION_IS_MODE"]:
            attrs["resolution"] = tier
        elif c["MODE_ON_TEXT"] or not s["is_text_only"]:
            attrs["mode"] = tier
    if "imageTail" in attrs:
        if c["IMAGE_TAIL_NEEDS_PRO"]:
            attrs["mode"] = "pro"
        if c["NO_AUDIO_WITH_IMAGE_TAIL"]:
            attrs.pop("generateAudio", None)
    return payload


def _extend_payload(c: dict[str, Any], prompt: str, image_url: str | None, s: dict[str, Any], **kw) -> dict[str, Any]:
    video_url = kw.get("video_url")
    if not video_url:
        raise ValueError("Extending needs the source video's URL")
    attrs: dict[str, Any] = {"video": video_url}
    if prompt:
        attrs["prompt"] = prompt
    attrs["duration"] = s["length"]
    attrs["resolution"] = s["resolution"]
    if s["generate_audio"] is not None:
        attrs["generateAudio"] = s["generate_audio"]
    if s["seed"] is not None:
        attrs["seed"] = s["seed"]
    return {"input": attrs}


def _recast_payload(c: dict[str, Any], prompt: str, image_url: str | None, s: dict[str, Any], **kw) -> dict[str, Any]:
    video_url = kw.get("video_url")
    if not video_url:
        raise ValueError("Recast needs the source video's URL")
    if not image_url:
        raise ValueError("Recast needs a reference image URL")
    return {"input": {"image": image_url, "video": video_url, "mode": s["mode"] or c["DEFAULT_MODE"]}}


def v1_video_payload(model_id: str, *, prompt: str, image_url: str | None, **kw) -> dict[str, Any]:
    """Build the v1 video API body for any model, dispatching on its family."""
    c = _cfg(model_id)
    s = _process_inputs(c, image_url, **kw)
    builder = c["builder"]
    if builder == "generic":
        return _generic_payload(c, prompt, image_url, s)
    if builder == "kling":
        return _kling_payload(c, prompt, image_url, s)
    if builder == "extend":
        return _extend_payload(c, prompt, image_url, s, **kw)
    if builder == "recast":
        return _recast_payload(c, prompt, image_url, s, **kw)
    raise ValueError(f"unknown builder {builder!r} for {model_id}")


# ── V1 image (BaseV1ImageGenerator) ──────────────────────────────────
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


# ── Legacy video (pre-v1 API, behind the web UI's "legacy mode") ─────
def _image_dimensions(image_path) -> tuple[int, int]:
    from PIL import Image  # local import: only the CLI-era local-file path needs it

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


_LEGACY_VIDEO_DEFAULTS: dict[str, Any] = {
    "VALID_LENGTHS": (),
    "VALID_RATIOS": (),
    "DEFAULT_RESOLUTION": "480p",
    "DEFAULT_LENGTH": 10,
    "DEFAULT_RATIO": "portrait",
    "INCLUDE_ASPECT_RATIO": True,
    "HAS_SEED": False,
    "HAS_IMAGE_TAIL": False,
    "ASPECT_FROM_IMAGE": False,
    "ASPECT_SKIP_NONNUMERIC": False,
}

_DANCE = {
    "VALID_LENGTHS": tuple(range(4, 16)),
    "VALID_RATIOS": ("4:3", "3:4", "1:1", "16:9", "9:16", "21:9"),
    "HAS_SEED": True,
    "HAS_IMAGE_TAIL": True,
    "ASPECT_FROM_IMAGE": True,
    "builder": "pollo",
}
_SEEDANCE25 = {
    **_DANCE,
    "VALID_LENGTHS": tuple(range(4, 31)),
    "VALID_RATIOS": ("4:3", "3:4", "1:1", "16:9", "9:16", "21:9", "adaptive"),
    "ASPECT_SKIP_NONNUMERIC": True,
}

LEGACY_VIDEO: dict[str, dict[str, Any]] = {
    "pollo20": {"pm": "pollo/pollo-v2-0", "VALID_LENGTHS": (5, 10), "builder": "pollo"},
    "pollo25": {
        "pm": "pollo/pollo-v2-5",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 15),
        "DEFAULT_RESOLUTION": "1080p",
        "INCLUDE_ASPECT_RATIO": False,
        "builder": "pollo",
    },
    "pollodance20": {**_DANCE, "pm": "pollo/pollo-dance-2-0"},
    "pollodance20fast": {**_DANCE, "pm": "pollo/pollo-dance-2-0-fast"},
    "seedance20": {**_DANCE, "pm": "bytedance/seedance-2-0"},
    "seedance20fast": {**_DANCE, "pm": "bytedance/seedance-2-0-fast"},
    "seedance20mini": {**_DANCE, "pm": "bytedance/seedance-2-0-mini"},
    "seedance25": {**_SEEDANCE25, "pm": "bytedance/seedance-2-5"},
    "seedance25draft": {**_SEEDANCE25, "pm": "bytedance/seedance-2-5-draft", "FORCE_RESOLUTION": "480p"},
    "minimaxh3": {
        "pm": "minimax/minimax-h3",
        "VALID_LENGTHS": tuple(range(4, 16)),
        "DEFAULT_RESOLUTION": "2K",
        "builder": "minimax",
    },
    "wan27": {
        "pm": "wanx/wan-v2-7",
        "VALID_LENGTHS": tuple(range(2, 16)),
        "DEFAULT_RESOLUTION": "1080P",
        "DEFAULT_LENGTH": 5,
        "builder": "wan27",
    },
    "wan30": {
        "pm": "wanx/wan-v3-0",
        "VALID_LENGTHS": tuple(range(2, 31)),
        "DEFAULT_RESOLUTION": "1080P",
        "DEFAULT_LENGTH": 5,
        "builder": "wan30",
    },
    "wan30prime": {
        "pm": "wanx/wan-v3-0-prime",
        "VALID_LENGTHS": tuple(range(2, 31)),
        "DEFAULT_RESOLUTION": "1080P",
        "DEFAULT_LENGTH": 5,
        "builder": "wan30",
    },
}


def _legacy_cfg(model_id: str) -> dict[str, Any]:
    return {**_LEGACY_VIDEO_DEFAULTS, **LEGACY_VIDEO[model_id]}


def legacy_video_model_url(model_id: str) -> str:
    return f"{POLLO_API_BASE}/{LEGACY_VIDEO[model_id]['pm']}"


def _legacy_inputs(c: dict[str, Any], image_path, **kw) -> dict[str, Any]:
    resolution = kw.get("resolution") or os.getenv("RESOLUTION", c["DEFAULT_RESOLUTION"])
    if c.get("FORCE_RESOLUTION"):
        resolution = c["FORCE_RESOLUTION"]
    length = _valid_length(
        str(kw.get("length") or os.getenv("LENGTH", str(c["DEFAULT_LENGTH"]))), c["VALID_LENGTHS"], c["DEFAULT_LENGTH"]
    )
    aspect_ratio = kw.get("aspect_ratio") or _aspect_ratio(
        os.getenv("ASPECT_RATIO") or os.getenv("RATIO", c["DEFAULT_RATIO"])
    )
    if c["ASPECT_FROM_IMAGE"]:
        aspect_ratio = _aspect_from_image(image_path, c["VALID_RATIOS"], c["ASPECT_SKIP_NONNUMERIC"]) or aspect_ratio
    num_outputs = kw.get("num_outputs")
    if num_outputs is None:
        num_outputs = int(os.getenv("NUM_OUTPUTS")) if os.getenv("NUM_OUTPUTS") else 1
    return {
        "resolution": resolution,
        "length": length,
        "aspect_ratio": aspect_ratio,
        "generate_audio": kw.get("generate_audio")
        if kw.get("generate_audio") is not None
        else _bool_env("GENERATE_AUDIO", True),
        "web_search": kw.get("web_search") if kw.get("web_search") is not None else _bool_env("WEBSEARCH", False),
        "seed": kw.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None),
        "image_tail": kw.get("image_tail") or os.getenv("IMAGE_TAIL"),
        "negative_prompt": kw.get("negative_prompt") or os.getenv("NEGATIVE_PROMPT"),
        "audio_url": kw.get("audio_url"),
        "prompt_optimizer": kw.get("prompt_optimizer")
        if kw.get("prompt_optimizer") is not None
        else _bool_env("PROMPT_OPTIMIZER", True),
        "num_outputs": max(1, min(4, int(num_outputs))),
    }


def _legacy_pollo(c, prompt, image_url, s) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if c["INCLUDE_ASPECT_RATIO"]:
        attrs["aspectRatio"] = s["aspect_ratio"]
    attrs |= {
        "resolution": s["resolution"],
        "length": s["length"],
        "generateAudio": s["generate_audio"],
        "webSearch": s["web_search"],
        "prompt": prompt,
    }
    if image_url is not None:
        attrs["image"] = image_url
    if c["HAS_SEED"] and s["seed"] is not None:
        attrs["seed"] = s["seed"]
    if c["HAS_IMAGE_TAIL"] and s["image_tail"]:
        attrs["imageTail"] = s["image_tail"]
    return {"input": attrs}


def _legacy_minimax(c, prompt, image_url, s) -> dict[str, Any]:
    attrs = {
        "prompt": prompt,
        "resolution": s["resolution"],
        "length": s["length"],
        "promptOptimizer": s["prompt_optimizer"],
    }
    if image_url is not None:
        attrs["image"] = image_url
    if s["image_tail"]:
        attrs["imageTail"] = s["image_tail"]
    return {"input": attrs}


def _legacy_wan27(c, prompt, image_url, s) -> dict[str, Any]:
    attrs = {"prompt": prompt, "resolution": s["resolution"], "length": s["length"]}
    if image_url is not None:
        attrs["image"] = image_url
    if s["image_tail"]:
        attrs["imageTail"] = s["image_tail"]
    if s["negative_prompt"]:
        attrs["negativePrompt"] = s["negative_prompt"]
    if s["seed"] is not None:
        attrs["seed"] = s["seed"]
    if s["audio_url"]:
        attrs["audioUrl"] = s["audio_url"]
    return {"input": attrs}


def _legacy_wan30(c, prompt, image_url, s) -> dict[str, Any]:
    attrs = {
        "prompt": prompt,
        "resolution": s["resolution"],
        "length": s["length"],
        "generateAudio": s["generate_audio"],
        "numOutputs": s["num_outputs"],
    }
    if image_url is not None:
        attrs["image"] = image_url
    return {"input": attrs}


_LEGACY_BUILDERS = {"pollo": _legacy_pollo, "minimax": _legacy_minimax, "wan27": _legacy_wan27, "wan30": _legacy_wan30}


def legacy_video_payload(model_id: str, *, prompt: str, image_url: str | None, image_path=None, **kw) -> dict[str, Any]:
    """Build a legacy (pre-v1) video API body, matching the old classes exactly."""
    c = _legacy_cfg(model_id)
    s = _legacy_inputs(c, image_path, **kw)
    return _LEGACY_BUILDERS[c["builder"]](c, prompt, image_url, s)


# ── Legacy image (pre-v1 API) ────────────────────────────────────────
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


# ── Legacy ref-to-video (pollo-dance / seedance ref2video) ───────────
# All five share one payload shape; only the model slug differs.
LEGACY_REF: dict[str, str] = {
    "pollodanceref": "pollo/pollo-dance-2-0/ref2video",
    "pollodancereffast": "pollo/pollo-dance-2-0-fast/ref2video",
    "seedanceref": "bytedance/seedance-2-0/ref2video",
    "seedancereffast": "bytedance/seedance-2-0-fast/ref2video",
    "seedanceminiref": "bytedance/seedance-2-0-mini/ref2video",
}
_REF_VALID_LENGTHS = tuple(range(4, 16))


def legacy_ref_model_url(model_id: str) -> str:
    return f"{POLLO_API_BASE}/{LEGACY_REF[model_id]}"


def _validate_ref(ref: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one ref for the ref2video payload (or drop it if urlless)."""
    ref_type = ref.get("type", "image")
    name = str(ref.get("name", ""))[:20]
    if ref_type == "subject":
        images = []
        for img in ref.get("images", [])[:3]:
            url = img.get("url", "").strip() if isinstance(img, dict) else str(img).strip()
            if url:
                images.append({"url": url})
        if not images:
            return None
        return {"type": "subject", "name": name, "images": images, "subjectId": ref.get("subjectId", "")}
    url = str(ref.get(ref_type) or ref.get("url") or "").strip()
    if not url:
        return None
    result = {"type": ref_type, "name": name, ref_type: url, "order": ref.get("order", 1)}
    if ref_type == "image" and ref.get("avatarId"):
        result["avatarId"] = ref["avatarId"]
    return result


def _build_ref_list(image_url: str | None, subject_url: str | None, refs) -> list[dict[str, Any]]:
    """refs passed through as-is; otherwise built from the primary image +
    subject URL (the CLI-era refs.txt path is not used on the web)."""
    if refs:
        return refs
    out: list[dict[str, Any]] = []
    order = 1
    if image_url:
        out.append({"type": "image", "name": "reference", "image": image_url, "order": order})
        order += 1
    if subject_url:
        out.append({"type": "image", "name": "subject", "image": subject_url, "order": order})
    return out


def legacy_ref_payload(
    model_id: str, *, prompt: str, image_url: str | None, subject_url: str | None = None, **kw
) -> dict[str, Any]:
    """Build a legacy ref2video API body, matching PolloDanceRefVideoGenerator."""
    aspect_ratio = kw.get("aspect_ratio") or _aspect_ratio(os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "portrait"))
    resolution = kw.get("resolution") or os.getenv("RESOLUTION", "720p")
    duration = _valid_length(
        str(kw.get("length") or kw.get("duration") or os.getenv("LENGTH", "10")), _REF_VALID_LENGTHS, 10
    )
    generate_audio = (
        kw.get("generate_audio") if kw.get("generate_audio") is not None else _bool_env("GENERATE_AUDIO", True)
    )
    video_num = kw.get("video_num") or int(os.getenv("VIDEO_NUM", "1"))
    if video_num < 1 or video_num > 4:
        video_num = 1

    refs = _build_ref_list(image_url, subject_url, kw.get("refs"))
    validated = [v for r in refs if (v := _validate_ref(r))][:13]
    attrs: dict[str, Any] = {
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
        "aspectRatio": aspect_ratio,
        "refs": validated,
        "generateAudio": generate_audio,
        "videoNum": video_num,
    }
    if kw.get("image_meta"):
        attrs["imageMeta"] = kw["image_meta"]
    return {"input": attrs}


# ── Unified model registry + runtime generator ──────────────────────
# One ModelSpec per model replaces the old class-per-model hierarchy: it is the
# data (VALID_* for the catalogue/validation, the endpoint, the family) and a
# factory for the runtime object. One PolloGenerator replaces all 44 generator
# classes: it resolves inputs + builds the payload via the family functions
# above, and carries the submit/estimate/metadata behaviour the callers use.

# Resolution tiers the catalogue/validation advertise for legacy video (the
# legacy builders don't themselves validate resolution).
_LEGACY_VIDEO_RESOLUTIONS: dict[str, tuple] = {
    "pollo25": ("720p", "1080p"),
    "seedance25": ("480p", "720p"),
    "seedance25draft": ("480p",),
    "minimaxh3": ("480P", "768P", "2K"),
    "wan27": ("720P", "1080P"),
    "wan30": ("480P", "720P", "1080P"),
    "wan30prime": ("480P", "720P", "1080P"),
}
_REF_RATIOS = ("4:3", "3:4", "1:1", "16:9", "9:16", "21:9")
_V1_FAMILY = {"generic": "v1video", "kling": "kling", "extend": "extend", "recast": "recast"}


@dataclass
class ModelSpec:
    """A model's static data + a factory for its runtime generator. Exposes the
    VALID_*/ACCEPTS_IMAGES/MAX_IMAGES attributes the catalogue and validation
    read off the (former) class, and is callable like the old class was."""

    model_id: str
    kind: str  # "video" | "image"
    family: str  # v1video | kling | extend | recast | legacyvideo | ref | v1image | legacyimage
    model_url: str
    VALID_RATIOS: tuple = ()
    VALID_LENGTHS: tuple = ()
    VALID_RESOLUTIONS: tuple = ()
    ACCEPTS_IMAGES: bool = True
    MAX_IMAGES: int = 0
    video_edit: bool = False

    def __call__(self, **kwargs) -> PolloGenerator:
        return PolloGenerator(self, **kwargs)


def _build_payload(spec: ModelSpec, prompt: str, image_url: str | None, **kw) -> dict[str, Any]:
    if spec.kind == "image":
        fn = v1_image_payload if spec.family == "v1image" else legacy_image_payload
        return fn(spec.model_id, prompt=prompt, image_url=image_url, **kw)
    if spec.family in ("v1video", "kling", "extend", "recast"):
        return v1_video_payload(spec.model_id, prompt=prompt, image_url=image_url, **kw)
    if spec.family == "legacyvideo":
        return legacy_video_payload(spec.model_id, prompt=prompt, image_url=image_url, **kw)
    return legacy_ref_payload(spec.model_id, prompt=prompt, image_url=image_url, **kw)


def _video_state(spec: ModelSpec, image_url: str | None, **kw) -> dict[str, Any]:
    """The resolved aspect/resolution/length/audio for job records — the values
    the old __init__ stored as attributes (whether or not the payload sends them)."""
    if spec.family in ("v1video", "kling", "extend", "recast"):
        s = _process_inputs(_cfg(spec.model_id), image_url, **kw)
        return {
            "aspect_ratio": s["aspect_ratio"],
            "resolution": s["resolution"],
            "length": s["length"],
            "duration": None,
            "generate_audio": s["generate_audio"],
        }
    if spec.family == "legacyvideo":
        s = _legacy_inputs(_legacy_cfg(spec.model_id), kw.get("image_path"), **kw)
        return {
            "aspect_ratio": s["aspect_ratio"],
            "resolution": s["resolution"],
            "length": s["length"],
            "duration": None,
            "generate_audio": s["generate_audio"],
        }
    # ref2video
    duration = _valid_length(
        str(kw.get("length") or kw.get("duration") or os.getenv("LENGTH", "10")), _REF_VALID_LENGTHS, 10
    )
    return {
        "aspect_ratio": kw.get("aspect_ratio")
        or _aspect_ratio(os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "portrait")),
        "resolution": kw.get("resolution") or os.getenv("RESOLUTION", "720p"),
        "length": None,
        "duration": duration,
        "generate_audio": kw.get("generate_audio")
        if kw.get("generate_audio") is not None
        else _bool_env("GENERATE_AUDIO", True),
    }


class PolloGenerator:
    """Runtime generator for one request: resolves inputs, builds the payload via
    the engine's family functions, and submits/prices it."""

    def __init__(self, spec: ModelSpec, **kwargs) -> None:
        self.spec = spec
        self.model_url = spec.model_url
        self.model_name = spec.model_id
        self.api_key = kwargs.get("api_key")
        self.project = kwargs.get("project") or os.getenv("PROJECT", "default")
        self.prompt = kwargs.get("prompt") or get_prompt(self.project)
        image_url = kwargs.get("image_url", _UNSET)
        self.image_url = get_image_url(self.project) if image_url is _UNSET else image_url
        if spec.family == "extend":
            self.image_url = None  # works on a source video; never a source image
        elif spec.family == "recast":
            self.prompt = kwargs.get("prompt") or " "  # recast ignores the prompt; the API wants it non-empty
        self.video_url = kwargs.get("video_url")
        # what the family builders take (resolved prompt/image_url pass explicitly)
        self._kwargs = {k: v for k, v in kwargs.items() if k not in ("api_key", "project", "prompt", "image_url")}
        self._payload: dict[str, Any] | None = None
        self.payload_attrs: dict[str, Any] = {}

        if spec.kind == "video":
            st = _video_state(spec, self.image_url, **self._kwargs)
            self.aspect_ratio, self.resolution = st["aspect_ratio"], st["resolution"]
            self.length, self.duration, self.generate_audio = st["length"], st["duration"], st["generate_audio"]
            self.refs = (
                _build_ref_list(self.image_url, kwargs.get("subject_url"), kwargs.get("refs"))
                if spec.family == "ref"
                else kwargs.get("refs")
            )
        else:
            self.aspect_ratio = self.resolution = self.length = self.duration = self.generate_audio = None
            self.refs = kwargs.get("refs")

    def get_payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = _build_payload(self.spec, self.prompt, self.image_url, **self._kwargs)
        self.payload_attrs = self._payload["input"]
        return self._payload

    @property
    def is_text_only(self) -> bool:
        if self.spec.video_edit:
            return False
        if self.spec.family == "ref":
            return not self.refs
        if self.spec.kind == "image":
            return self.image_url is None and not self._kwargs.get("images")
        return self.image_url is None

    @property
    def is_video_edit(self) -> bool:
        return self.spec.video_edit

    @property
    def estimate_url(self) -> str | None:
        if not self.model_url:
            return None
        if self.model_url.startswith(POLLO_API_V1_BASE):
            return f"{self.model_url}/estimate"
        return None if self.model_url.endswith("/ref2video") else f"{self.model_url}/validate"

    def send_request(self) -> requests.Response:
        if not self.model_url:
            raise ValueError("model_url must be set in the subclass.")
        payload = self.get_payload()
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        try:
            resp = requests.request("POST", self.model_url, json=payload, headers=headers, timeout=POLLO_API_TIMEOUT)
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Cannot reach API ({self.model_url}) — VPN/network may be down: {e}") from e
        except requests.exceptions.Timeout as e:
            raise ConnectionError(f"API request timed out ({self.model_url}) — VPN/network may be slow: {e}") from e
        if is_cloudflare_block(resp):
            raise ConnectionError(
                f"Cloudflare blocked the request (HTTP {resp.status_code}). "
                "Check your VPN — you may need to enable it, switch regions, or your IP is flagged."
            )
        return resp

    def build_download_metadata(self) -> dict[str, Any]:
        meta: dict[str, Any] = {"payload": self.payload_attrs}
        if self.spec.family == "ref":
            refs = self.refs or []
            meta["refs_count"] = len(refs)
            meta["ref_names"] = [r.get("name", "") for r in refs]
            meta["ref_types"] = [r.get("type", "image") for r in refs]
        return meta


def _video_specs() -> dict[str, ModelSpec]:
    specs: dict[str, ModelSpec] = {}
    for mid in LEGACY_VIDEO:
        c = _legacy_cfg(mid)
        specs[mid] = ModelSpec(
            mid,
            "video",
            "legacyvideo",
            legacy_video_model_url(mid),
            VALID_RATIOS=tuple(c["VALID_RATIOS"]),
            VALID_LENGTHS=tuple(c["VALID_LENGTHS"]),
            VALID_RESOLUTIONS=_LEGACY_VIDEO_RESOLUTIONS.get(mid, ()),
        )
    for mid in LEGACY_REF:
        specs[mid] = ModelSpec(
            mid, "video", "ref", legacy_ref_model_url(mid), VALID_RATIOS=_REF_RATIOS, VALID_LENGTHS=_REF_VALID_LENGTHS
        )
    return specs


# Registries (model_id -> ModelSpec). These replace pollo_img2vid's class dicts.
GENERATORS_LEGACY: dict[str, ModelSpec] = _video_specs()
GENERATORS_V1: dict[str, ModelSpec] = {}
for _mid in V1_VIDEO:
    _c = _cfg(_mid)
    _fam = _V1_FAMILY[_c["builder"]]
    GENERATORS_V1[_mid] = ModelSpec(
        _mid,
        "video",
        _fam,
        v1_video_model_url(_mid),
        VALID_RATIOS=tuple(_c["VALID_RATIOS"]),
        VALID_LENGTHS=tuple(_c["VALID_LENGTHS"]),
        VALID_RESOLUTIONS=tuple(_c["VALID_RESOLUTIONS"]),
        video_edit=_fam in ("extend", "recast"),
    )
GENERATORS: dict[str, ModelSpec] = {**GENERATORS_LEGACY, **GENERATORS_V1}

IMAGE_GENERATORS_V1: dict[str, ModelSpec] = {}
for _mid in V1_IMAGE:
    _c = _img_cfg(_mid)
    IMAGE_GENERATORS_V1[_mid] = ModelSpec(
        _mid,
        "image",
        "v1image",
        v1_image_model_url(_mid),
        VALID_RATIOS=tuple(_c["VALID_RATIOS"]),
        VALID_RESOLUTIONS=tuple(_c["VALID_RESOLUTIONS"]),
        ACCEPTS_IMAGES=_c["ACCEPTS_IMAGES"],
        MAX_IMAGES=_c["MAX_IMAGES"],
    )
IMAGE_GENERATORS_LEGACY: dict[str, ModelSpec] = {
    _mid: ModelSpec(
        _mid,
        "image",
        "legacyimage",
        legacy_image_model_url(_mid),
        VALID_RATIOS=tuple(_row.get("VALID_RATIOS", ())),
        VALID_RESOLUTIONS=tuple(_row.get("VALID_RESOLUTIONS", ())),
    )
    for _mid, _row in LEGACY_IMAGE.items()
}
IMAGE_GENERATORS: dict[str, ModelSpec] = {**IMAGE_GENERATORS_LEGACY, **IMAGE_GENERATORS_V1}


def video_generator(model_id: str, **kwargs) -> PolloGenerator:
    try:
        return GENERATORS[model_id](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported model: {model_id}. Available: {', '.join(GENERATORS)}") from None


def image_generator(model_id: str, **kwargs) -> PolloGenerator:
    try:
        return IMAGE_GENERATORS[model_id](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported image model: {model_id}. Available: {', '.join(IMAGE_GENERATORS)}") from None
