"""Legacy (pre-v1) video API bodies, behind the web UI's "legacy mode"."""

from __future__ import annotations

from typing import Any

from web.core.config import POLLO_API_BASE

from ._shared import _aspect_from_image, _aspect_ratio, _valid_length

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
    resolution = c.get("FORCE_RESOLUTION") or kw.get("resolution") or c["DEFAULT_RESOLUTION"]
    length = _valid_length(str(kw.get("length") or c["DEFAULT_LENGTH"]), c["VALID_LENGTHS"], c["DEFAULT_LENGTH"])
    aspect_ratio = kw.get("aspect_ratio") or _aspect_ratio(c["DEFAULT_RATIO"])
    if c["ASPECT_FROM_IMAGE"]:
        aspect_ratio = _aspect_from_image(image_path, c["VALID_RATIOS"], c["ASPECT_SKIP_NONNUMERIC"]) or aspect_ratio
    num_outputs = 1 if kw.get("num_outputs") is None else kw["num_outputs"]
    return {
        "resolution": resolution,
        "length": length,
        "aspect_ratio": aspect_ratio,
        "generate_audio": True if kw.get("generate_audio") is None else kw["generate_audio"],
        "web_search": False if kw.get("web_search") is None else kw["web_search"],
        "seed": kw.get("seed"),
        "image_tail": kw.get("image_tail"),
        "negative_prompt": kw.get("negative_prompt"),
        "audio_url": kw.get("audio_url"),
        "prompt_optimizer": True if kw.get("prompt_optimizer") is None else kw["prompt_optimizer"],
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
