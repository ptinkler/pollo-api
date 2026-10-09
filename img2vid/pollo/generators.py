import os
from pathlib import Path
from typing import Any, ClassVar

import requests
from PIL import Image

from ..common.cloudflare import is_cloudflare_block
from ..common.config import POLLO_API_BASE, POLLO_API_TIMEOUT, POLLO_API_V1_BASE
from ..common.get_inputs import get_audio_url, get_image_path, get_image_url, get_prompt, get_subject_url

# Sentinel for distinguishing "not passed" from None
_UNSET = object()


# Terminal success statuses from the API
SUCCESS_STATUSES = ("succeed", "success", "succeeded", "complete", "completed")
ERROR_STATUSES = ("error", "failed")


def _parse_bool_env(name: str, default: bool = False) -> bool:
    """Parse a boolean from environment variable."""
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes")


class BaseVideoGenerator:
    api_key: str
    project: str
    image_url: str | None
    image_path: Path | None
    prompt: str
    payload_attrs: dict[str, Any]
    model_url: str | None
    model_name: str
    VALID_RATIOS: ClassVar[tuple] = ()

    @staticmethod
    def get_aspect_ratio(ratio_mode: str = "portrait") -> str:
        ratios: dict[str, str] = {
            "portrait": "9:16",
            "landscape": "16:9",
            "square": "1:1",
        }
        # If it's a direct ratio value (contains ':'), return as-is
        if ":" in ratio_mode:
            return ratio_mode
        return ratios.get(ratio_mode, "9:16")  # Default to portrait if invalid mode

    @staticmethod
    def get_image_dimensions(image_path: Path) -> tuple[int, int]:
        """Read image from disk and return (width, height)."""
        img = Image.open(image_path)
        return img.size

    @staticmethod
    def get_closest_aspect_ratio(width: int, height: int, valid_ratios: tuple[str, ...]) -> str:
        """Find the closest valid aspect ratio to the image's actual ratio."""
        actual_ratio = width / height

        def parse_ratio(ratio_str: str) -> float:
            w, h = map(int, ratio_str.split(":"))
            return w / h

        closest = min(valid_ratios, key=lambda r: abs(parse_ratio(r) - actual_ratio))
        return closest

    def get_aspect_ratio_from_image(self) -> str | None:
        """Get closest valid aspect ratio based on image dimensions, or None if no VALID_RATIOS or no image."""
        if not self.VALID_RATIOS or not self.image_path:
            return None
        width, height = self.get_image_dimensions(self.image_path)
        return self.get_closest_aspect_ratio(width, height, self.VALID_RATIOS)

    @property
    def is_text_only(self) -> bool:
        """Check if this is a text-only generation (no image URL)."""
        return self.image_url is None

    @classmethod
    def _get_valid_length(cls, length_str: str, default: int = 10) -> int:
        """Parse and validate video length against VALID_LENGTHS."""
        try:
            length = int(length_str)
            if hasattr(cls, "VALID_LENGTHS") and cls.VALID_LENGTHS:
                if length in cls.VALID_LENGTHS:
                    return length
            else:
                return length
        except (ValueError, TypeError):
            pass
        return default

    def __init__(self, **kwargs) -> None:
        self.api_key = kwargs.get("api_key") or os.getenv("POLLO_API_KEY")
        self.project = kwargs.get("project") or os.getenv("PROJECT", "default")
        self.prompt = kwargs.get("prompt") or get_prompt(self.project)
        self.image_url = kwargs.get("image_url", _UNSET)
        if self.image_url is _UNSET:
            self.image_url = get_image_url(self.project)
        self.image_path = get_image_path(self.project) if not kwargs.get("image_url") else None
        self.payload_attrs = {}
        self.model_url = None
        self.model_name = self.__class__.__name__
        self._kwargs = kwargs  # Store for subclass use

    def get_payload(self) -> dict[str, Any]:
        # Override in subclasses for model-specific payloads
        raise NotImplementedError

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
        """Build metadata dict for download records."""
        return {"payload": self.payload_attrs}


class BaseV1VideoGenerator(BaseVideoGenerator):
    """
    Shared behavior for Pollo's newer "v1" generation API
    (https://pollo.ai/api/platform/v1/generation/{provider}/{model}/video),
    as documented at https://docs.pollo.ai and its OpenAPI spec
    (https://docs.pollo.ai/openapi.json, fetched 2026-09-18) — the source
    of truth for every v1 subclass in this file, in preference to live
    probing (which risks triggering real, billed generations on fields the
    API doesn't strictly validate; see MinimaxH3MaxVideoGenerator's
    docstring for a concrete instance of that happening).

    v1 unifies what the legacy API split across separate endpoints/URLs —
    text-to-video, image-to-video, and reference-to-video — into one
    endpoint whose `input` is a `oneOf` of three shapes, selected by
    which of image/refs/neither is present. It also renames "length" to
    "duration", and for most (not all — see each model's VALID_RESOLUTIONS)
    models lowercases the resolution enum compared to its legacy
    counterpart. Confirmed directly from the spec: every duration
    range/enum and resolution enum checked this way was otherwise
    unchanged from the legacy endpoint's own live-probed values, so the
    move to v1 is mostly a reshaping of the same underlying capability
    rather than a capability change — except where a subclass's docstring
    notes an addition (e.g. wan30's new `seed`) or removal (e.g. wan30's
    dropped, never-confirmed `numOutputs`).

    refs items are `{"url": str, "type": "image"|"video"|"audio"|...}` —
    notably simpler than the legacy ref2video endpoints' `{"type", "name",
    "image"/"video"/"audio", "order", ...}` shape (see
    PolloDanceRefVideoGenerator below); this class does not attempt to
    reuse that legacy ref-normalization logic since the two shapes aren't
    compatible.

    Subclasses configure themselves via the V1_PROVIDER/V1_MODEL slugs and
    the VALID_*/DEFAULT_*/HAS_* class attributes below rather than
    overriding get_payload(), unless their schema has a genuinely bespoke
    field (as wan27's negativePrompt/audio-driven-generation does).
    """

    V1_PROVIDER: ClassVar[str] = ""
    V1_MODEL: ClassVar[str] = ""

    VALID_LENGTHS: ClassVar[tuple] = ()
    VALID_RESOLUTIONS: ClassVar[tuple] = ()
    VALID_RATIOS: ClassVar[tuple] = ()
    DEFAULT_RESOLUTION: ClassVar[str] = ""
    DEFAULT_LENGTH: ClassVar[int] = 5

    HAS_GENERATE_AUDIO: ClassVar[bool] = False
    HAS_WEB_SEARCH: ClassVar[bool] = False
    HAS_SEED: ClassVar[bool] = False
    HAS_IMAGE_TAIL: ClassVar[bool] = False
    HAS_REFS: ClassVar[bool] = False
    HAS_MODE: ClassVar[bool] = False
    # Wan 2.7's bespoke pair: negativePrompt, and a separate "audio" field
    # for audio-driven generation (distinct from the generateAudio boolean
    # other models use — wan27 has no generateAudio at all).
    HAS_NEGATIVE_PROMPT_AUDIO: ClassVar[bool] = False
    # Most v1 image-to-video branches have no aspectRatio field at all (the
    # input image dictates it) — but pollo-dance-2-0(-fast) and
    # seedance-2-0(-fast/-mini) are exceptions: their image branch DOES take
    # aspectRatio, defaulting to "16:9" server-side when omitted. Confirmed
    # per-model from the OpenAPI spec, not assumed — see each subclass.
    HAS_ASPECT_RATIO_ON_IMAGE: ClassVar[bool] = False

    # Reference-To-Video branch, per the spec's `refs` schema. REF_TYPES and
    # MAX_REFS mirror web/api.py's MODEL_INFO "ref_mode" (kept in sync by a
    # test). The ref branch is its own schema: no model's has webSearch or
    # imageTail, some drop seed (REF_HAS_SEED), and a few have different
    # duration/resolution enums (REF_VALID_LENGTHS/REF_VALID_RESOLUTIONS,
    # empty = same as the image/text branches).
    REF_TYPES: ClassVar[tuple] = ("image", "video", "audio")
    MAX_REFS: ClassVar[int] = 0
    REF_HAS_SEED: ClassVar[bool] = True
    REF_VALID_LENGTHS: ClassVar[tuple] = ()
    REF_VALID_RESOLUTIONS: ClassVar[tuple] = ()

    resolution: str
    length: int
    aspect_ratio: str
    generate_audio: bool | None
    web_search: bool | None
    seed: int | None
    image_tail: str | None
    refs: list[dict[str, Any]] | None
    mode: str | None
    negative_prompt: str | None
    audio_url: str | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_V1_BASE}/{self.V1_PROVIDER}/{self.V1_MODEL}/video"
        self.refs = kwargs.get("refs") if self.HAS_REFS else None
        self.resolution = kwargs.get("resolution") or os.getenv("RESOLUTION", self.DEFAULT_RESOLUTION)
        length_str = str(kwargs.get("length") or os.getenv("LENGTH", str(self.DEFAULT_LENGTH)))
        if self.refs and self.REF_VALID_LENGTHS:
            # Snap to the nearest length the ref branch allows
            length = int(length_str) if length_str.isdigit() else self.DEFAULT_LENGTH
            self.length = min(self.REF_VALID_LENGTHS, key=lambda v: abs(v - length))
        else:
            self.length = self._get_valid_length(length_str, default=self.DEFAULT_LENGTH)
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "portrait")
        )
        self.image_tail = (kwargs.get("image_tail") or os.getenv("IMAGE_TAIL")) if self.HAS_IMAGE_TAIL else None
        self.seed = (
            (kwargs.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None)) if self.HAS_SEED else None
        )
        self.generate_audio = (
            (
                kwargs.get("generate_audio")
                if kwargs.get("generate_audio") is not None
                else _parse_bool_env("GENERATE_AUDIO", True)
            )
            if self.HAS_GENERATE_AUDIO
            else None
        )
        self.web_search = (
            (kwargs.get("web_search") if kwargs.get("web_search") is not None else _parse_bool_env("WEBSEARCH", False))
            if self.HAS_WEB_SEARCH
            else None
        )
        self.mode = (kwargs.get("mode") or os.getenv("MODE")) if self.HAS_MODE else None
        self.negative_prompt = None
        self.audio_url = None
        if self.HAS_NEGATIVE_PROMPT_AUDIO:
            self.negative_prompt = kwargs.get("negative_prompt") or os.getenv("NEGATIVE_PROMPT")
            audio_url = kwargs.get("audio_url", _UNSET)
            if audio_url is _UNSET:
                audio_url = get_audio_url(self.project)
            self.audio_url = audio_url

    @staticmethod
    def _normalize_refs(refs: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Normalize refs to the v1 shape: {"url": str, "type"?: str}."""
        if not refs:
            return None
        normalized: list[dict[str, Any]] = []
        for ref in refs:
            url = str(ref.get("url") or ref.get("image") or ref.get("video") or ref.get("audio") or "").strip()
            if not url:
                continue
            item: dict[str, Any] = {"url": url}
            ref_type = ref.get("type")
            if ref_type:
                item["type"] = ref_type
            normalized.append(item)
        return normalized or None

    def get_payload(self) -> dict[str, Any]:
        refs = self._normalize_refs(self.refs)
        attrs: dict[str, Any] = {"prompt": self.prompt}
        if refs:
            attrs["refs"] = refs
        elif not self.is_text_only:
            attrs["image"] = self.image_url
        attrs["duration"] = self.length
        attrs["resolution"] = self.resolution

        # aspectRatio usually only exists on the text/ref branches of the v1
        # schema — the image branch has no such field on most models (the
        # input image dictates it). A few models are exceptions and do take
        # it on the image branch too; see HAS_ASPECT_RATIO_ON_IMAGE.
        if refs or self.is_text_only or self.HAS_ASPECT_RATIO_ON_IMAGE:
            attrs["aspectRatio"] = self.aspect_ratio
        attrs.update(self._optional_attrs(has_refs=bool(refs)))
        self.payload_attrs = attrs
        return {"input": attrs}

    def _optional_attrs(self, has_refs: bool) -> dict[str, Any]:
        """The options that are set and that the chosen branch takes (the ref
        branch has no end frame, web search or audio; seed only on some)."""
        image_branch = not has_refs and not self.is_text_only
        candidates = {
            "imageTail": ((self.image_tail or None) if self.HAS_IMAGE_TAIL else None, image_branch),
            "generateAudio": (self.generate_audio, True),
            "webSearch": (self.web_search, not has_refs),
            "seed": (self.seed, self.REF_HAS_SEED or not has_refs),
            "mode": (self.mode or None, True),
            "negativePrompt": (self.negative_prompt or None, True),
            "audio": (self.audio_url or None, not has_refs),
        }
        return {key: value for key, (value, allowed) in candidates.items() if value is not None and allowed}


class Pollo20VideoGenerator(BaseVideoGenerator):
    VALID_LENGTHS: ClassVar[tuple] = (5, 10)

    aspect_ratio: str
    resolution: str
    length: int
    generate_audio: bool
    web_search: bool

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-v2-0"
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "portrait")
        )
        self.resolution = kwargs.get("resolution") or os.getenv("RESOLUTION", "480p")
        self.length = self._get_valid_length(str(kwargs.get("length") or os.getenv("LENGTH", "10")))
        self.generate_audio = (
            kwargs.get("generate_audio")
            if kwargs.get("generate_audio") is not None
            else _parse_bool_env("GENERATE_AUDIO", True)
        )
        self.web_search = (
            kwargs.get("web_search") if kwargs.get("web_search") is not None else _parse_bool_env("WEBSEARCH", False)
        )

    def get_payload(self) -> dict[str, Any]:
        self.payload_attrs = {
            "aspectRatio": self.aspect_ratio,
            "resolution": self.resolution,
            "length": self.length,
            "generateAudio": self.generate_audio,
            "webSearch": self.web_search,
            "prompt": self.prompt,
        }
        if not self.is_text_only:
            self.payload_attrs["image"] = self.image_url
        return {"input": self.payload_attrs}


class Pollo25VideoGenerator(Pollo20VideoGenerator):
    """
    Pollo 2.5 video generator.

    Confirmed live via direct probe against pollo/pollo-v2-5: length enum is
    4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 15 (not the (5, 10) inherited from
    Pollo 2.0 — notably 13 and 14 are absent while 15 is present), resolution
    is "720p" | "1080p" (not "480p"), and aspectRatio is optional and accepts
    "16:9" | "9:16" — but per user report the generated video ignores it
    regardless of value, so it's dropped from the payload rather than
    exposed as a user-facing setting.
    """

    VALID_LENGTHS: ClassVar[tuple] = (4, 5, 6, 7, 8, 9, 10, 11, 12, 15)
    VALID_RESOLUTIONS: ClassVar[tuple] = ("720p", "1080p")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-v2-5"
        self.resolution = kwargs.get("resolution") or os.getenv("RESOLUTION", "1080p")

    def get_payload(self) -> dict[str, Any]:
        payload = super().get_payload()
        payload["input"].pop("aspectRatio", None)
        return payload


class PolloDance20VideoGenerator(Pollo20VideoGenerator):
    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 16))
    VALID_RATIOS: ClassVar[tuple] = ("4:3", "3:4", "1:1", "16:9", "9:16", "21:9")

    seed: int | None
    image_tail: str | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-dance-2-0"
        self.aspect_ratio = self.get_aspect_ratio_from_image() or self.aspect_ratio
        self.seed = kwargs.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None)
        self.image_tail = kwargs.get("image_tail") or os.getenv("IMAGE_TAIL")

    def get_payload(self) -> dict[str, Any]:
        payload = super().get_payload()
        if self.seed is not None:
            payload["input"]["seed"] = self.seed
            self.payload_attrs["seed"] = self.seed
        if self.image_tail:
            payload["input"]["imageTail"] = self.image_tail
            self.payload_attrs["imageTail"] = self.image_tail
        return payload


class PolloDance20FastVideoGenerator(PolloDance20VideoGenerator):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-dance-2-0-fast"


class Seedance20VideoGenerator(PolloDance20VideoGenerator):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/bytedance/seedance-2-0"


class Seedance20FastVideoGenerator(PolloDance20VideoGenerator):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/bytedance/seedance-2-0-fast"


class Seedance20MiniVideoGenerator(PolloDance20VideoGenerator):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/bytedance/seedance-2-0-mini"


class Seedance25VideoGenerator(PolloDance20VideoGenerator):
    """
    ByteDance Seedance 2.5 video generator.

    Confirmed live via direct probe against bytedance/seedance-2-5: valid
    enums for resolution, aspectRatio, and length were read directly from
    the API's validation error responses.
    """

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 31))
    VALID_RATIOS: ClassVar[tuple] = ("4:3", "3:4", "1:1", "16:9", "9:16", "21:9", "adaptive")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/bytedance/seedance-2-5"

    def get_aspect_ratio_from_image(self) -> str | None:
        """Closest-ratio matching, skipping the non-numeric "adaptive" option."""
        ratios = tuple(r for r in self.VALID_RATIOS if ":" in r)
        if not ratios or not self.image_path:
            return None
        width, height = self.get_image_dimensions(self.image_path)
        return self.get_closest_aspect_ratio(width, height, ratios)


class MinimaxH3VideoGenerator(BaseVideoGenerator):
    """
    MiniMax H3 (Hailuo 03) video generator.

    Enabled for this account's API key as of 2026-08-25. Confirmed from
    Pollo's OpenAPI spec (2026-09-18): the current slug is "minimax/minimax-h3"
    — "minimax/hailuo-03" also exists in the legacy API (same schema) but
    "minimax/minimax-h3" is the one the v1 API keeps as non-deprecated, so
    it's used here for consistency. Resolution enum is "480P" | "768P" | "2K",
    length is 4-15, and promptOptimizer is confirmed against a live
    successful task response.
    """

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480P", "768P", "2K")

    resolution: str
    length: int
    image_tail: str | None
    prompt_optimizer: bool

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/minimax/minimax-h3"
        self.resolution = kwargs.get("resolution") or os.getenv("RESOLUTION", "2K")
        self.length = self._get_valid_length(str(kwargs.get("length") or os.getenv("LENGTH", "10")))
        self.image_tail = kwargs.get("image_tail") or os.getenv("IMAGE_TAIL")
        self.prompt_optimizer = (
            kwargs.get("prompt_optimizer")
            if kwargs.get("prompt_optimizer") is not None
            else _parse_bool_env("PROMPT_OPTIMIZER", True)
        )

    def get_payload(self) -> dict[str, Any]:
        self.payload_attrs = {
            "prompt": self.prompt,
            "resolution": self.resolution,
            "length": self.length,
            "promptOptimizer": self.prompt_optimizer,
        }
        if not self.is_text_only:
            self.payload_attrs["image"] = self.image_url
        if self.image_tail:
            self.payload_attrs["imageTail"] = self.image_tail
        return {"input": self.payload_attrs}


class MinimaxH3MaxVideoGenerator(BaseV1VideoGenerator):
    """
    MiniMax H3 Max video generator (v1 API only — no legacy-API
    counterpart exists for this model in this codebase).

    Initially probed live on 2026-09-18, before this codebase started
    using Pollo's OpenAPI spec (https://docs.pollo.ai/openapi.json) as the
    source of truth for v1 generators — that live probe found a "duration"
    field (not "length"), resolution enum "480p"|"768p"|"1080p", and no
    working promptOptimizer/imageTail (a wrong-typed promptOptimizer was
    silently accepted rather than rejected — exactly what an unvalidated
    field looks like). Reconfirmed against the spec: duration range is
    5-15 (the probe just hadn't tried 4, which the spec's minimum:5
    confirms is actually invalid), and — unlike the initial probe's
    conclusion — imageTail, aspectRatio ("auto"|"21:9"|"16:9"|"4:3"|"1:1"|
    "3:4"|"9:16", default "auto"), and refs (up to 12: max 9 images, 3
    videos, 3 audios, at least one image/video) ARE all present in the
    spec's schema, so they're included here after all. No generateAudio,
    webSearch, seed, or mode fields exist for this model.
    """

    V1_PROVIDER: ClassVar[str] = "minimax"
    V1_MODEL: ClassVar[str] = "minimax-h3-max"

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(5, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "768p", "1080p")
    VALID_RATIOS: ClassVar[tuple] = ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
    DEFAULT_RESOLUTION: ClassVar[str] = "480p"

    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    MAX_REFS: ClassVar[int] = 12


class Wan27VideoGenerator(BaseVideoGenerator):
    """
    Alibaba Wan 2.7 (wanx/wan-v2-7) video generator.

    Image-to-video: input.image is required by the API. Supports an
    optional tail image, negative prompt, seed, and audio-driven
    generation via audioUrl. Resolution enum values are uppercase
    ("720P", "1080P") per the API docs, unlike other models' lowercase.
    """

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(2, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("720P", "1080P")

    resolution: str
    length: int
    image_tail: str | None
    negative_prompt: str | None
    seed: int | None
    audio_url: str | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/wanx/wan-v2-7"
        self.resolution = kwargs.get("resolution") or os.getenv("RESOLUTION", "1080P")
        self.length = self._get_valid_length(str(kwargs.get("length") or os.getenv("LENGTH", "5")), default=5)
        self.image_tail = kwargs.get("image_tail") or os.getenv("IMAGE_TAIL")
        self.negative_prompt = kwargs.get("negative_prompt") or os.getenv("NEGATIVE_PROMPT")
        self.seed = kwargs.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None)
        audio_url = kwargs.get("audio_url", _UNSET)
        if audio_url is _UNSET:
            audio_url = get_audio_url(self.project)
        self.audio_url = audio_url

    def get_payload(self) -> dict[str, Any]:
        self.payload_attrs = {
            "prompt": self.prompt,
            "resolution": self.resolution,
            "length": self.length,
        }
        if not self.is_text_only:
            self.payload_attrs["image"] = self.image_url
        if self.image_tail:
            self.payload_attrs["imageTail"] = self.image_tail
        if self.negative_prompt:
            self.payload_attrs["negativePrompt"] = self.negative_prompt
        if self.seed is not None:
            self.payload_attrs["seed"] = self.seed
        if self.audio_url:
            self.payload_attrs["audioUrl"] = self.audio_url
        return {"input": self.payload_attrs}


class Wan30VideoGenerator(BaseVideoGenerator):
    """
    Alibaba Wan 3.0 (wanx/wan-v3-0) video generator.

    Enabled for API access as of 2026-09-18 (previously returned 403 "This
    model is not enabled for API access" as of 2026-08-25). resolution
    ("480P"/"720P"/"1080P") and length (2-30) enums, and generateAudio's
    boolean type, are all confirmed directly from the live API's validation
    error responses. numOutputs's field name is still inferred/unconfirmed —
    no sibling Pollo model in this codebase exposes an output-count field on
    a direct (non-ref2video) endpoint to compare against, and probing it
    further risks triggering a real (billed) generation rather than a
    validation error. The live API also validates an aspectRatio enum on
    the text-only branch, but it's intentionally omitted here per product
    spec.
    """

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(2, 31))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480P", "720P", "1080P")
    VALID_NUM_OUTPUTS: ClassVar[tuple] = (1, 2, 3, 4)

    resolution: str
    length: int
    generate_audio: bool
    num_outputs: int

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/wanx/wan-v3-0"
        self.resolution = kwargs.get("resolution") or os.getenv("RESOLUTION", "1080P")
        self.length = self._get_valid_length(str(kwargs.get("length") or os.getenv("LENGTH", "5")), default=5)
        self.generate_audio = (
            kwargs.get("generate_audio")
            if kwargs.get("generate_audio") is not None
            else _parse_bool_env("GENERATE_AUDIO", True)
        )
        num_outputs = kwargs.get("num_outputs")
        if num_outputs is None:
            env_val = os.getenv("NUM_OUTPUTS")
            num_outputs = int(env_val) if env_val else 1
        self.num_outputs = max(1, min(4, int(num_outputs)))

    def get_payload(self) -> dict[str, Any]:
        self.payload_attrs = {
            "prompt": self.prompt,
            "resolution": self.resolution,
            "length": self.length,
            "generateAudio": self.generate_audio,
            "numOutputs": self.num_outputs,
        }
        if not self.is_text_only:
            self.payload_attrs["image"] = self.image_url
        return {"input": self.payload_attrs}


class Wan30PrimeVideoGenerator(Wan30VideoGenerator):
    """
    Alibaba Wan 3.0 Prime — LEGACY endpoint (wanx/wan-v3-0-prime).

    Confirmed live via direct probe on 2026-09-18: the slug exists (unlike
    several other guessed "-prime"/"-pro"/"-turbo" variants, which 404) and
    its validation error responses show the exact same schema as
    wan-v3-0 — resolution ("480P"/"720P"/"1080P"), length (2-30), and
    generateAudio (boolean) enums/types are identical. Same numOutputs
    caveat as the base class applies.

    This turned out to be Pollo's pre-v1 "legacy" endpoint for the same
    model docs.pollo.ai/alibaba/wan-v3-0-prime describes — see
    Wan30PrimeVideoGeneratorV1 below for the current one docs.pollo.ai
    actually points to. Kept as a fallback per product decision (toggled
    via "legacy mode" in the web UI) in case the v1 endpoint misbehaves.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/wanx/wan-v3-0-prime"


class Pollo20VideoGeneratorV1(BaseV1VideoGenerator):
    """
    Pollo 2.0 — v1 API (pollo-ai/pollo-v2/video).

    Confirmed from Pollo's OpenAPI spec: duration enum (5, 10) and
    resolution enum ("480p"/"720p"/"1080p") are unchanged from the legacy
    endpoint. webSearch does NOT exist in the v1 schema (dropped — legacy
    Pollo20VideoGenerator has it, this doesn't). seed and refs are new
    capabilities the legacy endpoint didn't have. No imageTail, mode, or
    negativePrompt/audio fields.
    """

    V1_PROVIDER: ClassVar[str] = "pollo-ai"
    V1_MODEL: ClassVar[str] = "pollo-v2"

    VALID_LENGTHS: ClassVar[tuple] = (5, 10)
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p", "1080p")
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "9:16", "4:3", "3:4", "1:1")
    DEFAULT_RESOLUTION: ClassVar[str] = "480p"

    HAS_SEED: ClassVar[bool] = True
    HAS_GENERATE_AUDIO: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    # Ref branch: image refs only, and its own duration/resolution enums.
    REF_TYPES: ClassVar[tuple] = ("image",)
    MAX_REFS: ClassVar[int] = 7
    REF_VALID_LENGTHS: ClassVar[tuple] = tuple(range(1, 9))
    REF_VALID_RESOLUTIONS: ClassVar[tuple] = ("540p", "720p", "1080p")


class Pollo25VideoGeneratorV1(BaseV1VideoGenerator):
    """
    Pollo 2.5 — v1 API (pollo-ai/pollo-v2-5/video).

    Confirmed from Pollo's OpenAPI spec: duration enum (4,5,6,7,8,9,10,11,
    12,15) and resolution enum ("720p"/"1080p") are unchanged from the
    legacy endpoint. Gains a new "mode" field (enum "basic"/"pro", default
    "basic") that the legacy endpoint doesn't have. No seed, webSearch,
    imageTail, or refs (no Reference-To-Video branch exists for this
    model in the spec).
    """

    V1_PROVIDER: ClassVar[str] = "pollo-ai"
    V1_MODEL: ClassVar[str] = "pollo-v2-5"

    VALID_LENGTHS: ClassVar[tuple] = (4, 5, 6, 7, 8, 9, 10, 11, 12, 15)
    VALID_RESOLUTIONS: ClassVar[tuple] = ("720p", "1080p")
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "9:16")
    DEFAULT_RESOLUTION: ClassVar[str] = "720p"

    HAS_GENERATE_AUDIO: ClassVar[bool] = True
    HAS_MODE: ClassVar[bool] = True

    mode: str | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode = kwargs.get("mode") or os.getenv("MODE", "basic")


class PolloDance20VideoGeneratorV1(BaseV1VideoGenerator):
    """
    Pollo Dance 2.0 — v1 API (pollo-ai/pollo-dance-2-0/video).

    Confirmed from Pollo's OpenAPI spec: duration range (4-30... actually
    4-15, matches legacy's range(4,16) exactly) and resolution enum
    ("480p"/"720p"/"1080p") are unchanged from the legacy endpoint.
    seed, imageTail, webSearch, and generateAudio all carry over from the
    legacy schema; refs are now supported directly on this endpoint
    instead of needing the separate pollodanceref legacy endpoint.

    Unlike most v1 image-to-video branches, this model's image branch DOES
    accept aspectRatio (enum matches the text branch, including "adaptive";
    server-side default "16:9" if omitted) — confirmed from the spec, hence
    HAS_ASPECT_RATIO_ON_IMAGE.
    """

    V1_PROVIDER: ClassVar[str] = "pollo-ai"
    V1_MODEL: ClassVar[str] = "pollo-dance-2-0"

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p", "1080p")
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive")
    DEFAULT_RESOLUTION: ClassVar[str] = "480p"

    HAS_SEED: ClassVar[bool] = True
    HAS_GENERATE_AUDIO: ClassVar[bool] = True
    HAS_WEB_SEARCH: ClassVar[bool] = True
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    MAX_REFS: ClassVar[int] = 13
    REF_HAS_SEED: ClassVar[bool] = False
    HAS_ASPECT_RATIO_ON_IMAGE: ClassVar[bool] = True


class PolloDance20FastVideoGeneratorV1(PolloDance20VideoGeneratorV1):
    """Fast variant — v1 API (pollo-ai/pollo-dance-2-0-fast/video). Same schema, minus 1080p resolution."""

    V1_MODEL: ClassVar[str] = "pollo-dance-2-0-fast"
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p")


class Pollo30VideoGeneratorV1(PolloDance20VideoGeneratorV1):
    """
    Pollo 3.0 — v1 API (pollo-ai/pollo-v3-0/video).

    Confirmed from Pollo's OpenAPI spec (2026-10-07): the same three
    branches and fields as Pollo Dance 2.0 (seed, imageTail, webSearch,
    generateAudio, refs of up to 9 images / 3 videos / 3 audios, aspectRatio
    on the image branch incl. "adaptive"), plus a "4K" resolution, a seed on
    the ref branch too, and "mode" ("basic"/"pro"). 1080p and 4K require
    pro mode — basic only does 480p/720p — so the mode is picked from the
    resolution rather than offered separately.

    Not enabled for API access on our key yet (403 "This model is not
    enabled for API access", 2026-10-07), so MODEL_INFO marks it hidden.
    """

    V1_MODEL: ClassVar[str] = "pollo-v3-0"
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p", "1080p", "4K")
    REF_HAS_SEED: ClassVar[bool] = True
    HAS_MODE: ClassVar[bool] = True
    PRO_RESOLUTIONS: ClassVar[tuple] = ("1080p", "4K")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode = "pro" if self.resolution.upper() in {r.upper() for r in self.PRO_RESOLUTIONS} else "basic"


class Pollo30FastVideoGeneratorV1(PolloDance20VideoGeneratorV1):
    """
    Pollo 3.0 Fast — v1 API (pollo-ai/pollo-v3-0-fast/video).

    Confirmed from Pollo's OpenAPI spec (2026-10-07): Pollo Dance 2.0 Fast's
    schema (480p/720p, no mode, no seed on the ref branch) except that no
    branch offers the "adaptive" aspect ratio. The API currently answers
    400 "The model used to create this video is currently unavailable"
    (2026-10-07), so MODEL_INFO marks it hidden.
    """

    V1_MODEL: ClassVar[str] = "pollo-v3-0-fast"
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p")
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9")


class Seedance20VideoGeneratorV1(BaseV1VideoGenerator):
    """
    Seedance 2.0 — v1 API (bytedance/seedance-2-0/video).

    Confirmed from Pollo's OpenAPI spec: duration range 4-15 (matches
    legacy's range(4,16)) and resolution enum ("480p"/"720p"/"1080p"/"4K"
    — note the new "4K" option) are otherwise unchanged/expanded from the
    legacy endpoint. seed, imageTail, webSearch, generateAudio carry over;
    refs now supported directly instead of via the separate
    seedanceref legacy endpoint.

    Unlike most v1 image-to-video branches (and unlike its own successor,
    seedance-2-5 — see that class), this model's image branch DOES accept
    aspectRatio, same enum as the text branch minus "adaptive", server-side
    default "16:9" if omitted. Confirmed from the spec, hence
    HAS_ASPECT_RATIO_ON_IMAGE. Also inherited by the Fast/Mini subclasses
    below, whose image branches carry the same field.
    """

    V1_PROVIDER: ClassVar[str] = "bytedance"
    V1_MODEL: ClassVar[str] = "seedance-2-0"

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p", "1080p", "4K")
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9")
    DEFAULT_RESOLUTION: ClassVar[str] = "480p"

    HAS_SEED: ClassVar[bool] = True
    HAS_GENERATE_AUDIO: ClassVar[bool] = True
    HAS_WEB_SEARCH: ClassVar[bool] = True
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    MAX_REFS: ClassVar[int] = 15
    HAS_ASPECT_RATIO_ON_IMAGE: ClassVar[bool] = True


class Seedance20FastVideoGeneratorV1(Seedance20VideoGeneratorV1):
    """Fast variant — v1 API (bytedance/seedance-2-0-fast/video). Same schema, minus 1080p/4K resolution."""

    V1_MODEL: ClassVar[str] = "seedance-2-0-fast"
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p")


class Seedance20MiniVideoGeneratorV1(Seedance20VideoGeneratorV1):
    """Mini variant — v1 API (bytedance/seedance-2-0-mini/video). Same schema, minus 1080p/4K resolution."""

    V1_MODEL: ClassVar[str] = "seedance-2-0-mini"
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p")


class Seedance25VideoGeneratorV1(BaseV1VideoGenerator):
    """
    Seedance 2.5 — v1 API (bytedance/seedance-2-5/video).

    Confirmed from Pollo's OpenAPI spec: duration range 4-30 (matches
    legacy's range(4,31)) and resolution enum ("480p"/"720p"/"1080p") are
    unchanged from the legacy endpoint. aspectRatio adds "adaptive" as its
    default (matching legacy behavior of dropping aspectRatio from the
    payload — here we instead just let it default). seed, imageTail,
    webSearch, generateAudio carry over; refs now supported directly
    instead of via the separate seedanceref legacy endpoints.
    """

    V1_PROVIDER: ClassVar[str] = "bytedance"
    V1_MODEL: ClassVar[str] = "seedance-2-5"

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 31))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p", "1080p")
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive")
    DEFAULT_RESOLUTION: ClassVar[str] = "480p"

    HAS_SEED: ClassVar[bool] = True
    HAS_GENERATE_AUDIO: ClassVar[bool] = True
    HAS_WEB_SEARCH: ClassVar[bool] = True
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    MAX_REFS: ClassVar[int] = 50

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        if not kwargs.get("aspect_ratio") and not os.getenv("ASPECT_RATIO") and not os.getenv("RATIO"):
            self.aspect_ratio = "adaptive"


class MinimaxH3VideoGeneratorV1(BaseV1VideoGenerator):
    """
    MiniMax H3 (Hailuo 03) — v1 API (minimax/minimax-h3/video).

    Confirmed from Pollo's OpenAPI spec (2026-09-18): duration range 4-15
    (matches legacy's range(4,16)) and resolution enum is lowercase
    "480p"/"768p" plus uppercase "2K" as the top tier (same tiers as legacy,
    just lowercased below 2K). "minimax/hailuo-03/video" is the same schema
    but marked deprecated in the spec, so "minimax/minimax-h3/video" is used
    instead. No seed, webSearch, or generateAudio fields exist for this
    model (matches legacy, which also lacked seed/webSearch/generateAudio
    for MinimaxH3). imageTail and refs carry over from legacy; aspectRatio
    is new (legacy didn't expose it for this model).
    """

    V1_PROVIDER: ClassVar[str] = "minimax"
    V1_MODEL: ClassVar[str] = "minimax-h3"

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "768p", "2K")
    VALID_RATIOS: ClassVar[tuple] = ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
    DEFAULT_RESOLUTION: ClassVar[str] = "480p"

    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    MAX_REFS: ClassVar[int] = 15


class Wan27VideoGeneratorV1(BaseV1VideoGenerator):
    """
    Wan 2.7 — v1 API (alibaba/wan-v2-7/video) — note the provider slug
    changed from "wanx" (legacy) to "alibaba" (v1).

    Confirmed from Pollo's OpenAPI spec: duration range 2-15 (matches
    legacy's range(2,16)) but resolution enum is now lowercase
    "720p"/"1080p" (legacy: "720P"/"1080P"). negativePrompt and the
    audio-driven-generation "audio" field carry over from legacy (mapped
    here via HAS_NEGATIVE_PROMPT_AUDIO, same negative_prompt/audio_url
    kwargs as the legacy class). aspectRatio and refs are new capabilities
    the legacy endpoint didn't expose. No generateAudio, seed IS present
    (legacy also had it).
    """

    V1_PROVIDER: ClassVar[str] = "alibaba"
    V1_MODEL: ClassVar[str] = "wan-v2-7"

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(2, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("720p", "1080p")
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "1:1", "4:3", "3:4", "9:16")
    DEFAULT_RESOLUTION: ClassVar[str] = "720p"

    HAS_SEED: ClassVar[bool] = True
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    MAX_REFS: ClassVar[int] = 10
    HAS_NEGATIVE_PROMPT_AUDIO: ClassVar[bool] = True


class Wan30VideoGeneratorV1(BaseV1VideoGenerator):
    """
    Wan 3.0 — v1 API (alibaba/wan-v3-0/video) — note the provider slug
    changed from "wanx" (legacy) to "alibaba" (v1).

    Confirmed from Pollo's OpenAPI spec: duration range 2-30 (matches
    legacy's range(2,31)) but resolution enum is now lowercase
    "480p"/"720p"/"1080p" (legacy: "480P"/"720P"/"1080P"). generateAudio
    and seed carry over (seed is new vs. legacy — legacy's Wan30 had no
    seed field). numOutputs, which the legacy endpoint's docstring already
    flagged as an unconfirmed/inferred field name, does NOT exist anywhere
    in the v1 schema — it's dropped here rather than guessed again.
    aspectRatio and refs are new capabilities the legacy endpoint didn't
    expose (aside from refs going through a wholly separate ref2video URL).
    """

    V1_PROVIDER: ClassVar[str] = "alibaba"
    V1_MODEL: ClassVar[str] = "wan-v3-0"

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(2, 31))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("480p", "720p", "1080p")
    VALID_RATIOS: ClassVar[tuple] = ("adaptive", "16:9", "9:16", "4:3", "3:4", "1:1")
    DEFAULT_RESOLUTION: ClassVar[str] = "480p"

    HAS_SEED: ClassVar[bool] = True
    HAS_GENERATE_AUDIO: ClassVar[bool] = True
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_REFS: ClassVar[bool] = True
    # "file" = a document, "link" = a web page (at most one of the two).
    REF_TYPES: ClassVar[tuple] = ("image", "video", "audio", "file", "link")
    MAX_REFS: ClassVar[int] = 22

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        if not kwargs.get("aspect_ratio") and not os.getenv("ASPECT_RATIO") and not os.getenv("RATIO"):
            self.aspect_ratio = "adaptive"


class Wan30PrimeVideoGeneratorV1(Wan30VideoGeneratorV1):
    """
    Wan 3.0 Prime — v1 API (alibaba/wan-v3-0-prime/video). This is the
    model the user pointed at (docs.pollo.ai/alibaba/wan-v3-0-prime) that
    started this whole v1 migration. Confirmed from the OpenAPI spec to
    have an identical schema to wan-v3-0 v1, so it only overrides the
    model slug.
    """

    V1_MODEL: ClassVar[str] = "wan-v3-0-prime"


class PolloDanceRefVideoGenerator(BaseVideoGenerator):
    """
    Ref2Video generator using the pollodance-2-0/ref2video endpoint.

    Uses a refs array (1-13 references) of 4 types:
    - image:   { type, name, image (URL), order, avatarId? }
    - subject: { type, name, images [{url}] (1-3), subjectId }
    - video:   { type, name, video (URL), order }
    - audio:   { type, name, audio (URL), order }

    Supports:
    - duration: Video length (4-15s)
    - videoNum: Generate multiple videos (1-4)
    - imageMeta: Optional cropping/positioning metadata for refs
    - generateAudio: Generate audio track
    """

    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 16))
    VALID_RATIOS: ClassVar[tuple] = ("4:3", "3:4", "1:1", "16:9", "9:16", "21:9")
    VALID_REF_TYPES: ClassVar[tuple] = ("image", "subject", "video", "audio")

    refs: list[dict[str, Any]]
    aspect_ratio: str
    resolution: str
    duration: int
    generate_audio: bool
    video_num: int
    image_meta: list[dict[str, Any]] | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-dance-2-0/ref2video"
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "portrait")
        )
        self.resolution = kwargs.get("resolution") or os.getenv("RESOLUTION", "720p")
        self.duration = self._get_valid_length(
            str(kwargs.get("length") or kwargs.get("duration") or os.getenv("LENGTH", "10"))
        )
        self.generate_audio = (
            kwargs.get("generate_audio")
            if kwargs.get("generate_audio") is not None
            else _parse_bool_env("GENERATE_AUDIO", True)
        )
        self.video_num = kwargs.get("video_num") or int(os.getenv("VIDEO_NUM", "1"))
        if self.video_num < 1 or self.video_num > 4:
            self.video_num = 1

        # Build refs from kwargs or project files
        self.refs = kwargs.get("refs") or self._build_refs_from_inputs(kwargs)
        self.image_meta = kwargs.get("image_meta")

    def _build_refs_from_inputs(self, kwargs) -> list[dict[str, Any]]:
        """
        Build refs array from individual image URLs (backward-compatible).
        Also supports a refs.txt file in the project folder.
        """
        refs: list[dict[str, Any]] = []
        order = 1

        # Try loading from refs.txt in project folder
        refs_from_file = self._load_refs_file()
        if refs_from_file:
            return refs_from_file

        # Primary image as first ref
        if self.image_url:
            refs.append(
                {
                    "type": "image",
                    "name": "reference",
                    "image": self.image_url,
                    "order": order,
                }
            )
            order += 1

        # Subject URL as additional ref
        subject_url = kwargs.get("subject_url", _UNSET)
        if subject_url is _UNSET:
            subject_url = get_subject_url(self.project)
        if subject_url:
            refs.append(
                {
                    "type": "image",
                    "name": "subject",
                    "image": subject_url,
                    "order": order,
                }
            )
            order += 1

        return refs

    @staticmethod
    def _validate_ref(ref: dict[str, Any]) -> dict[str, Any] | None:
        """Validate and normalize a single ref dict for the API payload."""
        ref_type = ref.get("type", "image")
        name = str(ref.get("name", ""))[:20]

        if ref_type == "subject":
            # Subject refs need images array (1-3) and subjectId
            raw_images = ref.get("images", [])
            images = []
            for img in raw_images[:3]:
                url = img.get("url", "").strip() if isinstance(img, dict) else str(img).strip()
                if url:
                    images.append({"url": url})
            if not images:
                return None
            result = {
                "type": "subject",
                "name": name,
                "images": images,
                "subjectId": ref.get("subjectId", ""),
            }
            return result

        # image, video, audio all have a URL field + order
        # Accept either the type-specific key (image/video/audio) or generic "url"
        url = ref.get(ref_type) or ref.get("url") or ""
        url = str(url).strip()
        if not url:
            return None

        result = {
            "type": ref_type,
            "name": name,
            ref_type: url,  # "image": url, "video": url, or "audio": url
            "order": ref.get("order", 1),
        }
        # Optional avatarId for image type
        if ref_type == "image" and ref.get("avatarId"):
            result["avatarId"] = ref["avatarId"]

        return result

    def _load_refs_file(self) -> list[dict[str, Any]] | None:
        """Load refs from projects/{project}/refs.txt - one 'name|url' or plain URL per line."""
        refs_path = Path(f"projects/{self.project}/refs.txt")
        if not refs_path.exists():
            return None

        refs: list[dict[str, Any]] = []
        order = 1
        for line in refs_path.read_text().strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Support "name|url" or just "url"
            if "|" in line:
                name, url = line.split("|", 1)
                name = name.strip()[:20]
                url = url.strip()
            else:
                name = f"ref{order}"
                url = line
            refs.append(
                {
                    "type": "image",
                    "name": name,
                    "image": url,
                    "order": order,
                }
            )
            order += 1
            if order > 13:
                break
        return refs if refs else None

    @property
    def is_text_only(self) -> bool:
        """Ref2video always needs at least one ref."""
        return len(self.refs) == 0

    @property
    def is_video_edit(self) -> bool:
        """This is a ref-based generation, not a direct video edit."""
        return False

    def get_payload(self) -> dict[str, Any]:
        # Validate and normalize all refs
        validated_refs = []
        for ref in self.refs:
            validated = self._validate_ref(ref)
            if validated:
                validated_refs.append(validated)
        if len(validated_refs) > 13:
            validated_refs = validated_refs[:13]

        self.payload_attrs = {
            "prompt": self.prompt,
            "duration": self.duration,
            "resolution": self.resolution,
            "aspectRatio": self.aspect_ratio,
            "refs": validated_refs,
            "generateAudio": self.generate_audio,
            "videoNum": self.video_num,
        }

        if self.image_meta:
            self.payload_attrs["imageMeta"] = self.image_meta

        return {"input": self.payload_attrs}

    def build_download_metadata(self) -> dict[str, Any]:
        """Build metadata dict for download records."""
        meta: dict[str, Any] = {"payload": self.payload_attrs}
        meta["refs_count"] = len(self.refs)
        meta["ref_names"] = [r.get("name", "") for r in self.refs]
        meta["ref_types"] = [r.get("type", "image") for r in self.refs]
        return meta


class PolloDanceRefFastVideoGenerator(PolloDanceRefVideoGenerator):
    """Fast variant of the Ref2Video generator."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-dance-2-0-fast/ref2video"


class SeedanceRefVideoGenerator(PolloDanceRefVideoGenerator):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/bytedance/seedance-2-0/ref2video"


class SeedanceRefFastVideoGenerator(PolloDanceRefVideoGenerator):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/bytedance/seedance-2-0-fast/ref2video"


class SeedanceMiniRefVideoGenerator(PolloDanceRefVideoGenerator):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/bytedance/seedance-2-0-mini/ref2video"


class BaseV1ImageGenerator(BaseVideoGenerator):
    """
    Shared behavior for Pollo's v1 image-generation endpoints
    (https://pollo.ai/api/platform/v1/generation/{provider}/{model}/image).
    Confirmed from Pollo's OpenAPI spec (https://docs.pollo.ai/openapi.json,
    fetched 2026-09-18) — see BaseV1VideoGenerator's docstring for why the
    spec is used instead of live probing.

    Unlike the video endpoints, image endpoints take a plural "images"
    array (not a singular "imageUrl"/"image") for image-to-image mode, and
    none of the three v1 image models in this codebase (PolloJourney 8.2,
    Seedream 5.0 Lite, Nano Banana 2) expose maxImages, thinkingLevel, or
    responseFormat in their v1 schema even where the legacy endpoint had
    them — those fields are simply dropped for v1 subclasses rather than
    guessed at.
    """

    V1_PROVIDER: ClassVar[str] = ""
    V1_MODEL: ClassVar[str] = ""

    VALID_RATIOS: ClassVar[tuple] = ()
    VALID_RESOLUTIONS: ClassVar[tuple] = ()
    DEFAULT_RATIO_KEYWORD: ClassVar[str] = "square"
    HAS_SEED: ClassVar[bool] = False
    IMAGES_REQUIRED_FOR_IMAGE_TO_IMAGE: ClassVar[bool] = False
    # Image-to-image limits, per model's spec: whether it takes reference
    # images at all, how many (0 = no limit known), and whether aspectRatio
    # is still accepted alongside them (some follow the input image instead)
    ACCEPTS_IMAGES: ClassVar[bool] = True
    MAX_IMAGES: ClassVar[int] = 0
    ASPECT_RATIO_WITH_IMAGES: ClassVar[bool] = True

    aspect_ratio: str
    resolution: str | None
    seed: int | None
    images: list[str] | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_V1_BASE}/{self.V1_PROVIDER}/{self.V1_MODEL}/image"
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", self.DEFAULT_RATIO_KEYWORD)
        )
        resolution = kwargs.get("resolution") or os.getenv("RESOLUTION")
        self.resolution = resolution if resolution in self.VALID_RESOLUTIONS else None
        self.seed = (
            (kwargs.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None)) if self.HAS_SEED else None
        )
        self.images = kwargs.get("images") or None

    @property
    def is_text_only(self) -> bool:
        return self.image_url is None and not self.images

    def get_payload(self) -> dict[str, Any]:
        images = ([self.image_url] if self.image_url else []) + (self.images or [])
        if not self.ACCEPTS_IMAGES:
            images = []
        elif self.MAX_IMAGES:
            images = images[: self.MAX_IMAGES]

        input_payload: dict[str, Any] = {"prompt": self.prompt}
        if not images or self.ASPECT_RATIO_WITH_IMAGES:
            input_payload["aspectRatio"] = self.aspect_ratio
        if images:
            input_payload["images"] = images
        if self.resolution:
            input_payload["resolution"] = self.resolution
        if self.seed is not None:
            input_payload["seed"] = self.seed

        self.payload_attrs = input_payload
        return {"input": input_payload}


class PolloJourneyImageGenerator(BaseVideoGenerator):
    """
    Image generator using the Pollo Journey v8.2 model.

    Confirmed live via direct probe against pollojourney/pollojourney-v8-2-image:
    the slug follows the same "pollojourney/pollojourney-v8-2-image/image"
    pattern v7 used. aspectRatio enum (same seven values as v7) and resolution
    enum ("1K"/"2K", default "1K") are confirmed from the live API's
    validation error responses. Unlike v7, there's no documented "style"
    field, and image input goes through "images" only — there's no separate
    "imageUrl" for a single reference image.

    Two modes: Text-to-Image (prompt only) and Image-to-Image (images[],
    prompt optional).
    """

    VALID_RATIOS: ClassVar[tuple] = ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K")

    aspect_ratio: str
    resolution: str | None
    seed: int | None
    images: list[str] | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollojourney/pollojourney-v8-2-image/image"
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        resolution = kwargs.get("resolution") or os.getenv("RESOLUTION")
        self.resolution = resolution if resolution in self.VALID_RESOLUTIONS else None
        self.seed = kwargs.get("seed") or (int(os.getenv("SEED")) if os.getenv("SEED") else None)
        self.images = kwargs.get("images") or None

    @property
    def is_text_only(self) -> bool:
        return self.image_url is None and not self.images

    def get_payload(self) -> dict[str, Any]:
        images = ([self.image_url] if self.image_url else []) + (self.images or [])

        input_payload: dict[str, Any] = {
            "prompt": self.prompt,
            "aspectRatio": self.aspect_ratio,
        }
        if images:
            input_payload["images"] = images
        if self.resolution:
            input_payload["resolution"] = self.resolution
        if self.seed is not None:
            input_payload["seed"] = self.seed

        self.payload_attrs = input_payload
        return {"input": input_payload}


class PolloJourneyImageGeneratorV1(BaseV1ImageGenerator):
    """
    Pollo Journey 8.2 — v1 API (pollo-ai/pollojourney-v8-2-image/image).

    Confirmed from Pollo's OpenAPI spec: same aspectRatio (seven values,
    default "1:1") and resolution ("1K"/"2K", default "1K") enums as the
    legacy endpoint. seed carries over unchanged.
    """

    V1_PROVIDER: ClassVar[str] = "pollo-ai"
    V1_MODEL: ClassVar[str] = "pollojourney-v8-2-image"

    VALID_RATIOS: ClassVar[tuple] = ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K")
    HAS_SEED: ClassVar[bool] = True


class NanoBanana2ImageGenerator(BaseVideoGenerator):
    """Image generator using the Nano Banana 2 model.

    Supports text-to-image, image-to-image, and multi-image-to-image.
    """

    VALID_RATIOS: ClassVar[tuple] = ("1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K", "4K")
    VALID_THINKING_LEVELS: ClassVar[tuple] = ("minimal", "high")

    aspect_ratio: str
    resolution: str | None
    thinking_level: str | None
    max_images: int | None
    images: list[str] | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/google/nano-banana-2/image"
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        resolution = kwargs.get("resolution") or os.getenv("RESOLUTION")
        self.resolution = resolution if resolution in self.VALID_RESOLUTIONS else None
        thinking_level = kwargs.get("thinking_level") or os.getenv("THINKING_LEVEL")
        self.thinking_level = thinking_level if thinking_level in self.VALID_THINKING_LEVELS else None
        max_images = kwargs.get("max_images")
        if max_images is None:
            env_val = os.getenv("MAX_IMAGES")
            max_images = int(env_val) if env_val else None
        self.max_images = max(1, min(4, int(max_images))) if max_images is not None else None
        self.images = kwargs.get("images") or None

    @property
    def is_text_only(self) -> bool:
        return self.image_url is None and not self.images

    def get_payload(self) -> dict[str, Any]:
        input_payload: dict[str, Any] = {
            "prompt": self.prompt,
            "aspectRatio": self.aspect_ratio,
        }
        if self.images:
            input_payload["images"] = self.images
            if self.image_url:
                input_payload["imageUrl"] = self.image_url
        elif self.image_url:
            input_payload["imageUrl"] = self.image_url
        if self.resolution:
            input_payload["resolution"] = self.resolution
        if self.thinking_level:
            input_payload["thinkingLevel"] = self.thinking_level
        if self.max_images is not None:
            input_payload["maxImages"] = self.max_images

        self.payload_attrs = input_payload
        return {"input": input_payload}


class NanoBanana2ImageGeneratorV1(BaseV1ImageGenerator):
    """
    Nano Banana 2 — v1 API (google/nano-banana-2/image).

    Confirmed from Pollo's OpenAPI spec: aspectRatio gains four new
    ultra-wide/tall ratios ("1:4"/"4:1"/"8:1"/"1:8") vs. the legacy
    endpoint's ten. resolution replaces the legacy "1K"/"2K"/"4K" with
    "0.5K"/"1K"/"2K"/"4K" (new default tier "0.5K", not "1K"). thinkingLevel
    and maxImages do NOT exist in the v1 schema — dropped, matching
    BaseV1ImageGenerator's shared behavior of not guessing at fields
    the spec doesn't list. images (not imageUrl) is how a reference image
    is passed, and is REQUIRED for image-to-image per the spec (no
    seed field either).
    """

    V1_PROVIDER: ClassVar[str] = "google"
    V1_MODEL: ClassVar[str] = "nano-banana-2"

    VALID_RATIOS: ClassVar[tuple] = (
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
    )
    VALID_RESOLUTIONS: ClassVar[tuple] = ("0.5K", "1K", "2K", "4K")


class SeedreamImageGenerator(BaseVideoGenerator):
    """Image generator using the Seedream 5.0 Lite model.

    Supports text-to-image and image-to-image (single or multi-image reference).
    Returns 1–4 images per request. No seed or style fields.
    """

    VALID_RATIOS: ClassVar[tuple] = ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("2K", "3K", "4K")

    aspect_ratio: str
    resolution: str | None
    max_images: int | None
    images: list[str] | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/seedream/seedream-5-0-lite/image"
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        resolution = kwargs.get("resolution") or os.getenv("RESOLUTION")
        self.resolution = resolution if resolution in self.VALID_RESOLUTIONS else None
        max_images = kwargs.get("max_images")
        if max_images is None:
            env_val = os.getenv("MAX_IMAGES")
            max_images = int(env_val) if env_val else None
        self.max_images = max(1, min(4, int(max_images))) if max_images is not None else None
        self.images = kwargs.get("images") or None

    def get_payload(self) -> dict[str, Any]:
        input_payload: dict[str, Any] = {
            "prompt": self.prompt,
            "aspectRatio": self.aspect_ratio,
            "responseFormat": "url",
        }
        if self.images:
            input_payload["images"] = self.images
            if self.image_url:
                input_payload["imageUrl"] = self.image_url
        elif self.image_url:
            input_payload["imageUrl"] = self.image_url
        if self.resolution:
            input_payload["resolution"] = self.resolution
        if self.max_images is not None:
            input_payload["maxImages"] = self.max_images

        self.payload_attrs = input_payload
        return {"input": input_payload}


class SeedreamImageGeneratorV1(BaseV1ImageGenerator):
    """
    Seedream 5.0 Lite — v1 API (bytedance/seedream-5-0-lite/image) — note
    the provider slug changed from "seedream" (legacy) to "bytedance" (v1).

    Confirmed from Pollo's OpenAPI spec: same aspectRatio (eight values,
    default "1:1") and resolution ("2K"/"3K"/"4K", default "2K") enums as
    the legacy endpoint. maxImages and responseFormat do NOT exist in the
    v1 schema — dropped, matching BaseV1ImageGenerator's shared behavior
    of not guessing at fields the spec doesn't list. No seed field either.
    """

    V1_PROVIDER: ClassVar[str] = "bytedance"
    V1_MODEL: ClassVar[str] = "seedream-5-0-lite"

    VALID_RATIOS: ClassVar[tuple] = ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("2K", "3K", "4K")
    MAX_IMAGES: ClassVar[int] = 14


_SEEDREAM_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3")


class SeedreamFlashImageGeneratorV1(BaseV1ImageGenerator):
    """Seedream 5.0 Flash — v1 API (bytedance/seedream-5-0-flash/image).

    Not in Pollo's OpenAPI spec (2026-10-06) but served: an empty request
    answers 400, not 404. Fields confirmed from live validation errors (each
    probe carried an invalid aspectRatio, so none could generate): eight
    ratios incl. 21:9, resolution 1K/1.5K/2K, up to 10 reference images.
    seed/mode weren't rejected but aren't confirmed to do anything — left out.
    """

    V1_PROVIDER: ClassVar[str] = "bytedance"
    V1_MODEL: ClassVar[str] = "seedream-5-0-flash"
    VALID_RATIOS: ClassVar[tuple] = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "1.5K", "2K")
    MAX_IMAGES: ClassVar[int] = 10


class SeedreamProImageGeneratorV1(BaseV1ImageGenerator):
    """Seedream 5.0 Pro — v1 API (bytedance/seedream-5-0-pro/image). From the
    spec (2026-10-06): seven ratios, 1K/2K, up to 10 reference images."""

    V1_PROVIDER: ClassVar[str] = "bytedance"
    V1_MODEL: ClassVar[str] = "seedream-5-0-pro"
    VALID_RATIOS: ClassVar[tuple] = _SEEDREAM_RATIOS
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K")
    MAX_IMAGES: ClassVar[int] = 10


class PolloImage2ImageGenerator(BaseVideoGenerator):
    """
    Pollo Image 2.0 — legacy API only (pollo/pollo-image-v2/image).

    Pollo's OpenAPI spec (fetched 2026-10-05) also lists a v1 endpoint
    (pollo-ai/pollo-image-v2/image), but it answers "not enabled for API
    access" (2026-10-06), so there's no V1 class; MODEL_INFO marks this one
    legacy_only so it's offered outside legacy mode too.

    From the spec: text-to-image and image-to-image (up to 8 reference URLs
    in "images"), aspectRatio enum of nine values (default "1:1"),
    resolution "1K"/"2K"/"4K" (default "1K"), and mode
    fast/standard/professional (default standard). The spec says "Standard
    and fast modes only support 1K resolution", so asking for 2K/4K switches
    to professional rather than sending a combination Pollo rejects. The
    schema also lists imageUrl, guidance_scale, max_images, stream and
    response_format; they're left out (a single reference goes through
    images[], like Pollo Journey).
    """

    VALID_RATIOS: ClassVar[tuple] = ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "4:5", "5:4")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K", "4K")
    VALID_MODES: ClassVar[tuple] = ("fast", "standard", "professional")

    aspect_ratio: str
    resolution: str | None
    mode: str | None
    images: list[str] | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-image-v2/image"
        self.aspect_ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        resolution = kwargs.get("resolution") or os.getenv("RESOLUTION")
        self.resolution = resolution if resolution in self.VALID_RESOLUTIONS else None
        mode = kwargs.get("mode") or os.getenv("IMAGE_MODE")
        mode = mode if mode in self.VALID_MODES else None
        self.mode = "professional" if self.resolution and self.resolution != "1K" else mode
        self.images = kwargs.get("images") or None

    @property
    def is_text_only(self) -> bool:
        return self.image_url is None and not self.images

    def get_payload(self) -> dict[str, Any]:
        images = ([self.image_url] if self.image_url else []) + (self.images or [])

        input_payload: dict[str, Any] = {
            "prompt": self.prompt,
            "aspectRatio": self.aspect_ratio,
        }
        if images:
            input_payload["images"] = images
        if self.resolution:
            input_payload["resolution"] = self.resolution
        if self.mode:
            input_payload["mode"] = self.mode

        self.payload_attrs = input_payload
        return {"input": input_payload}


# ── Kling & Qwen image (v1) ─────────────────────────────────────────
# All confirmed from Pollo's OpenAPI spec (https://docs.pollo.ai/openapi.json,
# fetched 2026-10-06): each has a Text-To-Image and (except Qwen Image
# Flash) an Image-To-Image branch on one /image endpoint. negativePrompt
# (Qwen Image / Flash) is left out.

_KLING_IMAGE_RATIOS = ("1:1", "3:2", "2:3", "3:4", "4:3", "16:9", "9:16", "21:9")
_QWEN_IMAGE_RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16")


class KlingV3ImageGeneratorV1(BaseV1ImageGenerator):
    """Kling V3 Image (kling-ai/kling-v3-image/image): a single reference image, 1K/2K."""

    V1_PROVIDER: ClassVar[str] = "kling-ai"
    V1_MODEL: ClassVar[str] = "kling-v3-image"
    VALID_RATIOS: ClassVar[tuple] = _KLING_IMAGE_RATIOS
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K")
    MAX_IMAGES: ClassVar[int] = 1


class KlingV3OmniImageGeneratorV1(BaseV1ImageGenerator):
    """Kling V3 Omni image (kling-ai/kling-v3-omni/image): 1–10 reference
    images, 1K/2K/4K, plus an "auto" ratio (server default 16:9)."""

    V1_PROVIDER: ClassVar[str] = "kling-ai"
    V1_MODEL: ClassVar[str] = "kling-v3-omni"
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "auto")
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K", "4K")
    MAX_IMAGES: ClassVar[int] = 10


class QwenImageImageGenerator(BaseVideoGenerator):
    """
    Qwen Image — legacy API only (qwen/qwen-image/image).

    The spec also lists v1 qwen/qwen-image, but it answers 404 "Not found"
    (2026-10-06), so there's no V1 class; MODEL_INFO marks this one
    legacy_only. Legacy schema: Text-To-Image needs aspectRatio;
    Image-To-Image takes the reference as imageUrl (required) and has no
    aspectRatio. negativePrompt/style are left out.
    """

    VALID_RATIOS: ClassVar[tuple] = _QWEN_IMAGE_RATIOS
    VALID_RESOLUTIONS: ClassVar[tuple] = ()

    aspect_ratio: str
    images: list[str] | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/qwen/qwen-image/image"
        ratio = kwargs.get("aspect_ratio") or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        self.aspect_ratio = ratio if ratio in self.VALID_RATIOS else "1:1"
        self.images = kwargs.get("images") or None

    @property
    def is_text_only(self) -> bool:
        return self.image_url is None and not self.images

    def get_payload(self) -> dict[str, Any]:
        refs = ([self.image_url] if self.image_url else []) + (self.images or [])
        input_payload: dict[str, Any] = {"prompt": self.prompt}
        if refs:
            input_payload["imageUrl"] = refs[0]  # one reference; the image sets the shape
        else:
            input_payload["aspectRatio"] = self.aspect_ratio
        self.payload_attrs = input_payload
        return {"input": input_payload}


class QwenImage3ImageGeneratorV1(BaseV1ImageGenerator):
    """Qwen Image 3 (qwen/qwen-image-3/image): 1–3 reference images, 1K/2K.
    NB: answered 404 "Not found" for this account's API key on 2026-10-06,
    like a made-up model name; added at the user's request."""

    V1_PROVIDER: ClassVar[str] = "qwen"
    V1_MODEL: ClassVar[str] = "qwen-image-3"
    VALID_RATIOS: ClassVar[tuple] = _QWEN_IMAGE_RATIOS
    VALID_RESOLUTIONS: ClassVar[tuple] = ("1K", "2K")
    MAX_IMAGES: ClassVar[int] = 3


class QwenImage3ProImageGeneratorV1(QwenImage3ImageGeneratorV1):
    """Qwen Image 3 Pro (qwen/qwen-image-3-pro/image): same schema as Qwen Image 3 (same 404 caveat)."""

    V1_MODEL: ClassVar[str] = "qwen-image-3-pro"


class QwenImageFlashImageGeneratorV1(BaseV1ImageGenerator):
    """Qwen Image Flash (alibaba/pre-qwen-image-flash/image): text-to-image only."""

    V1_PROVIDER: ClassVar[str] = "alibaba"
    V1_MODEL: ClassVar[str] = "pre-qwen-image-flash"
    VALID_RATIOS: ClassVar[tuple] = _QWEN_IMAGE_RATIOS
    ACCEPTS_IMAGES: ClassVar[bool] = False


# ── Kling video (v1) ────────────────────────────────────────────────


class BaseKlingVideoGeneratorV1(BaseV1VideoGenerator):
    """
    Kling video — v1 API (kling-ai/<model>/video). Confirmed from Pollo's
    OpenAPI spec (https://docs.pollo.ai/openapi.json, fetched 2026-10-06).

    Most Kling models have no "resolution" field: quality is a "mode" tier
    (std/pro, plus 4K on V3/V3 Omni). With RESOLUTION_IS_MODE, the tiers are
    offered as this model's resolutions (so the existing Resolution menus
    on the Generate page and in chat can pick them) and the choice is sent
    as "mode". Every model's Image-To-Video branch takes no aspectRatio (the
    image sets it); Text-To-Video takes 16:9/9:16/1:1.

    Left out: negativePrompt, V2.1's "strength", and the Reference-To-Video
    branches of Video O1/V3 Omni (their own resolution/duration rules).
    """

    V1_PROVIDER: ClassVar[str] = "kling-ai"
    VALID_LENGTHS: ClassVar[tuple] = (5, 10)
    VALID_RATIOS: ClassVar[tuple] = ("16:9", "9:16", "1:1")
    DEFAULT_RESOLUTION: ClassVar[str] = ""  # leave the tier to Pollo's default
    RESOLUTION_IS_MODE: ClassVar[bool] = False
    MODE_ON_TEXT: ClassVar[bool] = True  # V2.5 Turbo's text branch has no mode
    TEXT_TO_VIDEO: ClassVar[bool] = True  # V2.1 is image-to-video only
    IMAGE_TAIL_NEEDS_PRO: ClassVar[bool] = False  # V2.5 Turbo: end frame only in pro mode
    NO_AUDIO_WITH_IMAGE_TAIL: ClassVar[bool] = False  # V2.6: end frame excludes audio

    def get_payload(self) -> dict[str, Any]:
        if self.is_text_only and not self.TEXT_TO_VIDEO:
            raise ValueError(f"{self.model_name} needs a source image (it has no text-to-video mode)")
        payload = super().get_payload()
        attrs = payload["input"]
        tier = attrs.pop("resolution", None)
        if tier in self.VALID_RESOLUTIONS:
            if not self.RESOLUTION_IS_MODE:
                attrs["resolution"] = tier
            elif self.MODE_ON_TEXT or not self.is_text_only:
                attrs["mode"] = tier
        if "imageTail" in attrs:
            if self.IMAGE_TAIL_NEEDS_PRO:
                attrs["mode"] = "pro"
            if self.NO_AUDIO_WITH_IMAGE_TAIL:
                attrs.pop("generateAudio", None)
        return payload


class KlingV21VideoGeneratorV1(BaseKlingVideoGeneratorV1):
    """Kling V2.1 (kling-v2-1): image-to-video only, std/pro, 5/10s."""

    V1_MODEL: ClassVar[str] = "kling-v2-1"
    VALID_RESOLUTIONS: ClassVar[tuple] = ("std", "pro")
    RESOLUTION_IS_MODE: ClassVar[bool] = True
    TEXT_TO_VIDEO: ClassVar[bool] = False


class KlingV21MasterVideoGeneratorV1(BaseKlingVideoGeneratorV1):
    """Kling V2.1 Master (kling-v2-1-master): 5/10s, no mode or end frame."""

    V1_MODEL: ClassVar[str] = "kling-v2-1-master"


class KlingV25TurboVideoGeneratorV1(BaseKlingVideoGeneratorV1):
    """Kling V2.5 Turbo (kling-v2-5-turbo): std/pro on image-to-video only;
    an end frame requires pro."""

    V1_MODEL: ClassVar[str] = "kling-v2-5-turbo"
    VALID_RESOLUTIONS: ClassVar[tuple] = ("std", "pro")
    RESOLUTION_IS_MODE: ClassVar[bool] = True
    MODE_ON_TEXT: ClassVar[bool] = False
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    IMAGE_TAIL_NEEDS_PRO: ClassVar[bool] = True


class KlingVideoO1VideoGeneratorV1(BaseKlingVideoGeneratorV1):
    """Kling Video O1 (kling-video-o1): 5/10s, end frame; no mode."""

    V1_MODEL: ClassVar[str] = "kling-video-o1"
    HAS_IMAGE_TAIL: ClassVar[bool] = True


class KlingV26VideoGeneratorV1(BaseKlingVideoGeneratorV1):
    """Kling V2.6 (kling-v2-6): 5/10s, audio, end frame — not both at once."""

    V1_MODEL: ClassVar[str] = "kling-v2-6"
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_GENERATE_AUDIO: ClassVar[bool] = True
    NO_AUDIO_WITH_IMAGE_TAIL: ClassVar[bool] = True


class KlingV3VideoGeneratorV1(BaseKlingVideoGeneratorV1):
    """Kling V3 (kling-v3): 3–15s, std/pro/4K, audio, end frame."""

    V1_MODEL: ClassVar[str] = "kling-v3"
    VALID_LENGTHS: ClassVar[tuple] = tuple(range(3, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("std", "pro", "4K")
    RESOLUTION_IS_MODE: ClassVar[bool] = True
    HAS_IMAGE_TAIL: ClassVar[bool] = True
    HAS_GENERATE_AUDIO: ClassVar[bool] = True


class KlingV3TurboVideoGeneratorV1(BaseKlingVideoGeneratorV1):
    """Kling V3 Turbo (kling-v3-turbo): 3–15s, real 720p/1080p resolutions; no mode/audio/end frame."""

    V1_MODEL: ClassVar[str] = "kling-v3-turbo"
    VALID_LENGTHS: ClassVar[tuple] = tuple(range(3, 16))
    VALID_RESOLUTIONS: ClassVar[tuple] = ("720p", "1080p")


class KlingV3OmniVideoGeneratorV1(KlingV3VideoGeneratorV1):
    """Kling V3 Omni (kling-v3-omni): as V3 (Pollo's default tier is pro, not std)."""

    V1_MODEL: ClassVar[str] = "kling-v3-omni"
