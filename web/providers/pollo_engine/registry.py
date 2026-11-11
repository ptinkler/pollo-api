"""Unified model registry + runtime generator.

One ModelSpec per model: the data (VALID_* for the catalogue/validation, the
endpoint, the family) and a factory for the runtime object. One PolloGenerator
resolves inputs, builds the payload via the family functions, and submits or
prices the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from web.core.cloudflare import is_cloudflare_block
from web.core.config import POLLO_API_TIMEOUT

from .audio import AUDIO_MODELS, audio_model_url, audio_payload
from .image import IMAGE_MODELS, image_model_url, image_payload, img_cfg
from .video import VIDEO_MODELS, cfg, video_model_url, video_payload

# A video row's builder name -> the family a ModelSpec carries. They differ only
# for the catch-all builder, whose family is the plain "video".
_FAMILY = {"generic": "video"}
# families that work on a source video and take no source image
_VIDEO_ONLY_FAMILIES = ("extend", "edit", "upscale", "bgremove", "subtitle")


@dataclass
class ModelSpec:
    """A model's static data + a factory for its runtime generator: the VALID_*
    /ACCEPTS_IMAGES/MAX_IMAGES the catalogue and validation read, and the
    endpoint + family the payload builders dispatch on."""

    model_id: str
    kind: str  # "video" | "image" | "audio"
    family: str  # "image", "audio", or a video builder's family ("video", "kling", "extend"…)
    model_url: str
    VALID_RATIOS: tuple = ()
    VALID_LENGTHS: tuple = ()
    VALID_RESOLUTIONS: tuple = ()
    ACCEPTS_IMAGES: bool = True
    MAX_IMAGES: int = 0

    def __call__(self, **kwargs) -> PolloGenerator:
        return PolloGenerator(self, **kwargs)


def _build_payload(spec: ModelSpec, prompt: str, image_url: str | None, **kw) -> dict[str, Any]:
    if spec.kind == "audio":
        return audio_payload(spec.model_id, prompt=prompt, **kw)
    build = image_payload if spec.kind == "image" else video_payload
    return build(spec.model_id, prompt=prompt, image_url=image_url, **kw)


class PolloGenerator:
    """Runtime generator for one request: resolves inputs, builds the payload via
    the engine's family functions, and submits/prices it."""

    def __init__(self, spec: ModelSpec, **kwargs) -> None:
        self.spec = spec
        self.model_url = spec.model_url
        self.api_key = kwargs.get("api_key")
        self.prompt = kwargs.get("prompt") or ""
        self.image_url = kwargs.get("image_url")
        if spec.kind == "audio" or spec.family in _VIDEO_ONLY_FAMILIES:
            self.image_url = None  # audio, or works on a source video: never a source image
        if spec.family in ("motion", "upscale", "bgremove", "subtitle", "faceswap"):
            self.prompt = self.prompt or " "  # ignored by these; the API wants it non-empty
        # what the family builders take (resolved prompt/image_url pass explicitly)
        self._kwargs = {k: v for k, v in kwargs.items() if k not in ("api_key", "project", "prompt", "image_url")}
        self._payload: dict[str, Any] | None = None
        self.payload_attrs: dict[str, Any] = {}

    def get_payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = _build_payload(self.spec, self.prompt, self.image_url, **self._kwargs)
        self.payload_attrs = self._payload["input"]
        return self._payload

    @property
    def estimate_url(self) -> str | None:
        """The endpoint's free price-check twin (see web/providers/pollo_estimate.py)."""
        return f"{self.model_url}/estimate" if self.model_url else None

    def send_request(self) -> requests.Response:
        if not self.model_url:
            raise ValueError(f"No endpoint configured for {self.spec.model_id}")
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


# Registries (model_id -> ModelSpec), one per kind.
def _video_spec(model_id: str) -> ModelSpec:
    c = cfg(model_id)
    return ModelSpec(
        model_id,
        "video",
        _FAMILY.get(c["builder"], c["builder"]),
        video_model_url(model_id),
        VALID_RATIOS=tuple(c["VALID_RATIOS"]),
        VALID_LENGTHS=tuple(c["VALID_LENGTHS"]),
        VALID_RESOLUTIONS=tuple(c["VALID_RESOLUTIONS"]),
    )


def _image_spec(model_id: str) -> ModelSpec:
    c = img_cfg(model_id)
    return ModelSpec(
        model_id,
        "image",
        "image",
        image_model_url(model_id),
        VALID_RATIOS=tuple(c["VALID_RATIOS"]),
        VALID_RESOLUTIONS=tuple(c["VALID_RESOLUTIONS"]),
        ACCEPTS_IMAGES=c["ACCEPTS_IMAGES"],
        MAX_IMAGES=c["MAX_IMAGES"],
    )


VIDEO_GENERATORS: dict[str, ModelSpec] = {_mid: _video_spec(_mid) for _mid in VIDEO_MODELS}
IMAGE_GENERATORS: dict[str, ModelSpec] = {_mid: _image_spec(_mid) for _mid in IMAGE_MODELS}
AUDIO_GENERATORS: dict[str, ModelSpec] = {
    _mid: ModelSpec(_mid, "audio", _row["builder"], audio_model_url(_mid)) for _mid, _row in AUDIO_MODELS.items()
}


def audio_generator(model_id: str, **kwargs) -> PolloGenerator:
    try:
        return AUDIO_GENERATORS[model_id](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported audio model: {model_id}. Available: {', '.join(AUDIO_GENERATORS)}") from None


def video_generator(model_id: str, **kwargs) -> PolloGenerator:
    try:
        return VIDEO_GENERATORS[model_id](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported model: {model_id}. Available: {', '.join(VIDEO_GENERATORS)}") from None


def image_generator(model_id: str, **kwargs) -> PolloGenerator:
    try:
        return IMAGE_GENERATORS[model_id](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported image model: {model_id}. Available: {', '.join(IMAGE_GENERATORS)}") from None
