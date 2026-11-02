"""Legacy ref-to-video (pollo-dance / seedance ref2video). All five share one
payload shape; only the model slug differs."""

from __future__ import annotations

import os
from typing import Any

from web.core.config import POLLO_API_BASE

from ._shared import _aspect_ratio, _bool_env, _valid_length

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
