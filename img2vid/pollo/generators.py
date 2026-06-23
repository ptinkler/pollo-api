import requests
import os
from typing import Any, ClassVar
from pathlib import Path
from PIL import Image
from ..common.get_inputs import get_prompt, get_image_url, get_image_path, get_subject_url
from ..common.cloudflare import is_cloudflare_block
from ..common.config import POLLO_API_BASE, POLLO_API_TIMEOUT

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
            if hasattr(cls, 'VALID_LENGTHS') and cls.VALID_LENGTHS:
                if length in cls.VALID_LENGTHS:
                    return length
            else:
                return length
        except (ValueError, TypeError):
            pass
        return default

    def __init__(self, **kwargs) -> None:
        self.api_key = kwargs.get('api_key') or os.getenv("POLLO_API_KEY")
        self.project = kwargs.get('project') or os.getenv("PROJECT", "default")
        self.prompt = kwargs.get('prompt') or get_prompt(self.project)
        self.image_url = kwargs.get('image_url', _UNSET)
        if self.image_url is _UNSET:
            self.image_url = get_image_url(self.project)
        self.image_path = get_image_path(self.project) if not kwargs.get('image_url') else None
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
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        try:
            resp = requests.request("POST", self.model_url, json=payload, headers=headers, timeout=POLLO_API_TIMEOUT)
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"Cannot reach API ({self.model_url}) — VPN/network may be down: {e}"
            ) from e
        except requests.exceptions.Timeout as e:
            raise ConnectionError(
                f"API request timed out ({self.model_url}) — VPN/network may be slow: {e}"
            ) from e

        if is_cloudflare_block(resp):
            raise ConnectionError(
                f"Cloudflare blocked the request (HTTP {resp.status_code}). "
                "Check your VPN — you may need to enable it, switch regions, or your IP is flagged."
            )
        return resp

    def build_download_metadata(self) -> dict[str, Any]:
        """Build metadata dict for download records."""
        return {"payload": self.payload_attrs}


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
        self.aspect_ratio = kwargs.get('aspect_ratio') or self.get_aspect_ratio(os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "portrait"))
        self.resolution = kwargs.get('resolution') or os.getenv("RESOLUTION", "480p")
        self.length = self._get_valid_length(str(kwargs.get('length') or os.getenv("LENGTH", "10")))
        self.generate_audio = kwargs.get('generate_audio') if kwargs.get('generate_audio') is not None else _parse_bool_env("GENERATE_AUDIO", True)
        self.web_search = kwargs.get('web_search') if kwargs.get('web_search') is not None else _parse_bool_env("WEBSEARCH", False)

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


class PolloDance20VideoGenerator(Pollo20VideoGenerator):
    VALID_LENGTHS: ClassVar[tuple] = tuple(range(4, 16))
    VALID_RATIOS: ClassVar[tuple] = ("4:3", "3:4", "1:1", "16:9", "9:16", "21:9")

    seed: int | None
    image_tail: str | None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollo/pollo-dance-2-0"
        self.aspect_ratio = self.get_aspect_ratio_from_image() or self.aspect_ratio
        self.seed = kwargs.get('seed') or (int(os.getenv("SEED")) if os.getenv("SEED") else None)
        self.image_tail = kwargs.get('image_tail') or os.getenv("IMAGE_TAIL")

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
        self.aspect_ratio = kwargs.get('aspect_ratio') or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "portrait")
        )
        self.resolution = kwargs.get('resolution') or os.getenv("RESOLUTION", "720p")
        self.duration = self._get_valid_length(
            str(kwargs.get('length') or kwargs.get('duration') or os.getenv("LENGTH", "10"))
        )
        self.generate_audio = (
            kwargs.get('generate_audio')
            if kwargs.get('generate_audio') is not None
            else _parse_bool_env("GENERATE_AUDIO", True)
        )
        self.video_num = kwargs.get('video_num') or int(os.getenv("VIDEO_NUM", "1"))
        if self.video_num < 1 or self.video_num > 4:
            self.video_num = 1

        # Build refs from kwargs or project files
        self.refs = kwargs.get('refs') or self._build_refs_from_inputs(kwargs)
        self.image_meta = kwargs.get('image_meta')

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
            refs.append({
                "type": "image",
                "name": "reference",
                "image": self.image_url,
                "order": order,
            })
            order += 1

        # Subject URL as additional ref
        subject_url = kwargs.get('subject_url', _UNSET)
        if subject_url is _UNSET:
            subject_url = get_subject_url(self.project)
        if subject_url:
            refs.append({
                "type": "image",
                "name": "subject",
                "image": subject_url,
                "order": order,
            })
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
            refs.append({
                "type": "image",
                "name": name,
                "image": url,
                "order": order,
            })
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


class PolloJourneyImageGenerator(BaseVideoGenerator):
    """Image generator using the Pollo Journey v7 model.

    Supports three modes determined by which inputs are provided:
    - Text-to-Image: prompt only (+ optional style)
    - Image-to-Image: prompt + imageUrl
    - Multi-Image-to-Image: prompt + images[] (+ optional imageUrl)
    """
    VALID_RATIOS: ClassVar[tuple] = ("1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16")

    aspect_ratio: str
    seed: int | None
    images: list[str] | None
    style: str

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_url = f"{POLLO_API_BASE}/pollojourney/pollojourney-v7-image/image"
        self.aspect_ratio = kwargs.get('aspect_ratio') or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        self.seed = kwargs.get('seed') or (int(os.getenv("SEED")) if os.getenv("SEED") else None)
        self.images = kwargs.get('images') or None
        self.style = kwargs.get('style') or os.getenv("STYLE", "")

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
        else:
            if self.style:
                input_payload["style"] = self.style
        if self.seed is not None:
            input_payload["seed"] = self.seed

        self.payload_attrs = input_payload
        return {"input": input_payload}


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
        self.aspect_ratio = kwargs.get('aspect_ratio') or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        resolution = kwargs.get('resolution') or os.getenv("RESOLUTION")
        self.resolution = resolution if resolution in self.VALID_RESOLUTIONS else None
        thinking_level = kwargs.get('thinking_level') or os.getenv("THINKING_LEVEL")
        self.thinking_level = thinking_level if thinking_level in self.VALID_THINKING_LEVELS else None
        max_images = kwargs.get('max_images')
        if max_images is None:
            env_val = os.getenv("MAX_IMAGES")
            max_images = int(env_val) if env_val else None
        self.max_images = max(1, min(4, int(max_images))) if max_images is not None else None
        self.images = kwargs.get('images') or None

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
        self.aspect_ratio = kwargs.get('aspect_ratio') or self.get_aspect_ratio(
            os.getenv("ASPECT_RATIO") or os.getenv("RATIO", "square")
        )
        resolution = kwargs.get('resolution') or os.getenv("RESOLUTION")
        self.resolution = resolution if resolution in self.VALID_RESOLUTIONS else None
        max_images = kwargs.get('max_images')
        if max_images is None:
            env_val = os.getenv("MAX_IMAGES")
            max_images = int(env_val) if env_val else None
        self.max_images = max(1, min(4, int(max_images))) if max_images is not None else None
        self.images = kwargs.get('images') or None

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
