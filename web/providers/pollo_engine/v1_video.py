"""V1 video API bodies: the generic family plus Kling, extend and recast."""

from __future__ import annotations

import os
from typing import Any

from web.core.config import POLLO_API_V1_BASE

from ._shared import _aspect_ratio, _bool_env, _valid_length

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
    # Kling video: reuses the generic payload, then remaps the resolution
    # tier to a mode and applies end-frame rules
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
