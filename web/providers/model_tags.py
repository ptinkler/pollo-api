"""Capability tags for every model, derived from the shaped catalogue dicts.

This keeps tags consistent across all three providers.

One source of truth for the tag slugs and their human labels (`TAGS`), plus
`tags_for(kind, model)` — called once per model by `web/chat/catalogue.py` as it
assembles the catalogue. Tags are what the model picker filters on; they're read
off fields the providers already emit (Pollo's `type`, Venice's `family`,
everyone's `frame_images`/`reference_images`/`generate_audio`/`input_modalities`),
so nothing new has to be stored per model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# slug -> human label shown on the filter chips, grouped by the kind it applies
# to. Order here is the order the chips appear in.
TAGS: dict[str, str] = {
    # video
    "img2vid": "Image→Video",
    "text2vid": "Text→Video",
    "ref2vid": "References→Video",
    "video_refs": "Video refs (recast)",
    "first_last": "First+Last frame",
    "video_edit": "Video edit",
    "video_extend": "Video extend",
    "motion": "Motion / recast",
    "lipsync": "Lip sync",
    "upscale": "Upscale",
    "bg_remove": "Background remove",
    "subtitle_remove": "Subtitle remove",
    "face_swap": "Face swap",
    "audio": "Makes audio",
    # audio
    "tts": "Text→Speech",
    "music": "Music",
    # image
    "text2img": "Text→Image",
    "image_edit": "Image edit",
    "tools": "Image tools",
    # text
    "vision": "Vision",
    "functions": "Tools / functions",
}


def tags_for(kind: str, m: dict[str, Any]) -> list[str]:
    """The capability tags for one shaped catalogue model of `kind`."""
    out: list[str] = []

    def add(*ts: str) -> None:
        for t in ts:
            if t not in out:
                out.append(t)

    if kind == "video":
        _video_tags(m, add)
    elif kind == "image":
        _image_tags(m, add)
    elif kind == "audio":
        add(*_AUDIO_TYPE_TAGS.get(m.get("type"), ()))
    elif kind == "text":
        if "image" in (m.get("input_modalities") or []):
            add("vision")
        if m.get("supports_tools"):
            add("functions")
    return out


_AUDIO_TYPE_TAGS = {"speech": ("tts",), "music": ("music",)}

# Pollo's `type` and Venice's `family` → capability tags (table-driven so the
# function stays simple). "standard" / img-animation is handled in the helper.
_POLLO_TYPE_TAGS = {
    "extend": ("video_extend",),
    "video_edit": ("video_edit",),
    "upscale": ("upscale",),
    "bgremove": ("bg_remove",),
    "subtitle_remove": ("subtitle_remove",),
    "faceswap": ("face_swap",),
    "motion": ("motion",),
    "lipsync": ("lipsync",),
    "ref": ("ref2vid",),
    "img2vid": ("img2vid", "text2vid"),
}
_VENICE_FAMILY_TAGS = {
    "video": ("video_edit",),
    "motion": ("motion",),
    "upscale": ("upscale",),
    "reference": ("ref2vid",),
    "frames": ("img2vid", "first_last"),
    "angles": ("img2vid",),
}
# Families/types where a "first_frame" is a role other than "animate this image"
_EDIT_TYPES = {
    "motion",
    "ref",
    "extend",
    "video_edit",
    "upscale",
    "bgremove",
    "subtitle_remove",
    "faceswap",
    "lipsync",
}
_VENICE_EDIT_FAMS = {"video", "motion", "upscale", "reference"}


def _video_tags(m: dict[str, Any], add: Callable[..., None]) -> None:
    typ = m.get("type")  # Pollo
    fam = m.get("family")  # Venice
    frames = m.get("frame_images") or []
    add(*_POLLO_TYPE_TAGS.get(typ, ()))
    add(*_VENICE_FAMILY_TAGS.get(fam, ()))
    if fam == "standard":
        add("text2vid")
    if m.get("reference_images"):
        add("ref2vid")
    refs = m.get("ref_mode") or {}  # the model's reference-to-video branch
    if refs:
        add("ref2vid")
    if "video" in (refs.get("types") or []):
        add("video_refs")  # takes a source video as a reference: replace/restyle part of a clip
    if "last_frame" in frames:
        add("first_last")
    if m.get("generate_audio"):
        add("audio")
    _video_img_tags(m, typ, fam, frames, add)


def _video_img_tags(
    m: dict[str, Any],
    typ: str | None,
    fam: str | None,
    frames: list[str],
    add: Callable[..., None],
) -> None:
    """Add image-to-video and text-to-video tags supported by the model.

    ``first_frame`` means image-to-video only for plain generators, not edit
    families where the image plays a different role.
    """
    special = typ in _EDIT_TYPES or fam in _VENICE_EDIT_FAMS
    if "first_frame" in frames and not special:
        add("img2vid")
    if not typ and not fam:  # OpenRouter video carries neither field
        if "image" in (m.get("input_modalities") or []) or "first_frame" in frames:
            add("img2vid")
        add("text2vid")


def _image_tags(m: dict[str, Any], add: Callable[..., None]) -> None:
    # Image tools (face-swap, background remover, …) are their own thing and
    # don't generate from a bare prompt — a later stage sets `tool`.
    if m.get("tool"):
        add("tools")
        return
    add("text2img")
    mods = m.get("input_modalities") or []
    if "image" in mods or m.get("conversational") or m.get("max_refs"):
        add("image_edit")
