"""Unified model registry + runtime generator.

One ModelSpec per model replaces the old class-per-model hierarchy: it is the
data (VALID_* for the catalogue/validation, the endpoint, the family) and a
factory for the runtime object. One PolloGenerator replaces all 44 generator
classes: it resolves inputs + builds the payload via the family functions, and
carries the submit/estimate/metadata behaviour the callers use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from web.core.cloudflare import is_cloudflare_block
from web.core.config import POLLO_API_TIMEOUT, POLLO_API_V1_BASE
from web.core.get_inputs import get_image_url, get_prompt

from ._shared import _UNSET, _aspect_ratio, _bool_env, _valid_length
from .legacy_image import LEGACY_IMAGE, legacy_image_model_url, legacy_image_payload
from .legacy_ref import (
    _REF_VALID_LENGTHS,
    LEGACY_REF,
    _build_ref_list,
    legacy_ref_model_url,
    legacy_ref_payload,
)
from .legacy_video import LEGACY_VIDEO, _legacy_cfg, _legacy_inputs, legacy_video_model_url, legacy_video_payload
from .v1_image import V1_IMAGE, _img_cfg, v1_image_model_url, v1_image_payload
from .v1_video import V1_VIDEO, _cfg, _process_inputs, v1_video_model_url, v1_video_payload

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


# Registries (model_id -> ModelSpec).
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
