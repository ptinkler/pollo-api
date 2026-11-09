"""
Pollo image and video models for chat mode.

Chat's generate_image / generate_video tools normally run on OpenRouter
models. This module lets them run on Pollo's v1 models too (plus legacy
models that have no working v1 endpoint), reusing the
generator classes the Generate page uses. They're listed in the chat's
catalogues as "pollo/<generator key>" (e.g. "pollo/seedreamv1",
"pollo/seedance20fastv1") and bill the signed-in user's Pollo account (their per-user Pollo key).

Images are generated synchronously, like OpenRouter's. Videos mirror
openrouter.submit_video / get_video / download_video, with job ids prefixed
"pollo:" so chat's background video poller knows which API to ask.

Pollo bills in credits, not dollars, so Pollo media records `credits` on
its media item rather than adding to the OpenRouter `cost`.
"""

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from PIL import Image

from web.core.config import POLLO_API_TIMEOUT, POLLO_API_V1_BASE
from web.core.get_task import get_task_status

from .. import image_hosts, keyctx, request_log
from . import pollo_estimate
from .openrouter import OpenRouterError
from .pollo_engine import (
    AUDIO_GENERATORS,
    ERROR_STATUSES,
    GENERATORS_LEGACY,
    GENERATORS_V1,
    IMAGE_GENERATORS,
    IMAGE_GENERATORS_V1,
    SUCCESS_STATUSES,
    closest_aspect_ratio,
)
from .pollo_engine import audio_generator as get_audio_generator
from .pollo_engine import image_generator as get_image_generator
from .pollo_engine import video_generator as get_video_generator
from .pollo_models import MODEL_INFO

POLLO_PLATFORM_BASE = POLLO_API_V1_BASE.split("/v1/")[0]


class PolloError(OpenRouterError):
    """A Pollo failure. Subclasses OpenRouterError so chat handles it the
    same way — except moderation detection: Pollo answers 403 for "This model
    is not enabled for API access", which isn't a content block."""


PREFIX = "pollo/"
JOB_PREFIX = "pollo:"
FOLLOW_IMAGE_RATIOS = ("adaptive", "auto")  # values meaning "match the input image"
POLL_INTERVAL = 4
POLL_TIMEOUT = 10 * 60
MAX_POLL_ERRORS = 6
DOWNLOAD_TIMEOUT = 120


def is_configured() -> bool:
    return bool(keyctx.provider_key("pollo"))


NAME = "pollo"
REF_MAX_IMAGES = 9  # reference images a ref2video request carries


def list_models(kind: str, refresh: bool = False) -> list[dict]:
    """Uniform provider interface. Pollo has no text models; image/video lists
    are already key-gated (empty without a Pollo key)."""
    if kind == "image":
        return list_image_models()
    if kind == "video":
        return list_video_models()
    if kind == "audio":
        return list_audio_models()
    return []


def is_pollo(model_id: str | None) -> bool:
    return bool(model_id and model_id.startswith(PREFIX))


def is_pollo_job(job_id: str | None) -> bool:
    return bool(job_id and job_id.startswith(JOB_PREFIX))


def _image_generators() -> dict:
    """The v1 image models, plus legacy models with no working v1 endpoint
    (MODEL_INFO "legacy_only", e.g. Pollo Image 2.0)."""
    info = MODEL_INFO
    return {
        **IMAGE_GENERATORS_V1,
        **{key: cls for key, cls in IMAGE_GENERATORS.items() if info.get(key, {}).get("legacy_only")},
    }


def _catalogue(generators: dict) -> list[tuple[str, type, dict]]:
    """(key, class, MODEL_INFO entry) for each model the Generate page doesn't mark deprecated."""
    if not is_configured():
        return []
    info = MODEL_INFO
    return [(key, cls, info.get(key, {})) for key, cls in generators.items() if not info.get(key, {}).get("deprecated")]


def list_image_models() -> list[dict[str, Any]]:
    """Pollo's v1 image models, shaped like openrouter.list_image_models()."""
    return [
        {
            "id": PREFIX + key,
            "name": f"Pollo: {meta.get('label') or key}",
            "input_modalities": ["text", "image"] if getattr(cls, "ACCEPTS_IMAGES", True) else ["text"],
            "max_refs": getattr(cls, "MAX_IMAGES", 0) or None,  # reference images it takes (None = unknown)
            "aspect_ratios": list(cls.VALID_RATIOS) or None,
            "resolutions": list(cls.VALID_RESOLUTIONS) or None,
            "tool": meta.get("tool") or None,  # a source image in, a result out (no prompt)
            "no_prompt": bool(meta.get("tool")),
            "created": None,
            "conversational": False,
            # Not enabled for this key — listed only behind "Show hidden"
            "hidden": meta.get("hidden") or None,
        }
        for key, cls, meta in _catalogue(_image_generators())
    ]


def list_video_models() -> list[dict[str, Any]]:
    """Pollo's v1 video models, shaped like openrouter.list_video_models()."""
    out = []
    for key, cls, meta in _catalogue(_video_generators()):
        # Motion models work on a source video + one reference image, so it has no
        # duration/resolution/aspect ratio (the source video sets those). Extend
        # continues a source video too, but the user picks the added duration
        # and resolution — it takes no image and no aspect ratio.
        typ = meta.get("type")
        recast = typ in _IMAGE_AND_VIDEO  # a reference image + a source video
        no_image = typ in _VIDEO_ONLY  # source-video families that take no first frame
        lipsync = typ == "lipsync"  # drive a portrait with an audio track
        # only the plain generators carry their own duration / aspect ratio;
        # the source-video / audio families derive the length from their input.
        # Extend alone lets the user pick the added duration.
        derived = recast or lipsync or no_image
        own_duration = not derived or typ == "extend"
        own_ratio = not derived
        out.append(
            {
                "id": PREFIX + key,
                "name": f"Pollo: {meta.get('label') or key}",
                "type": typ,
                "durations": (meta.get("lengths") or list(cls.VALID_LENGTHS) or None) if own_duration else None,
                "no_prompt": typ in _NO_PROMPT,  # the source file is the whole input
                "resolutions": None if recast else (meta.get("resolutions") or list(cls.VALID_RESOLUTIONS) or None),
                "aspect_ratios": (meta.get("ratios") or list(cls.VALID_RATIOS) or None) if own_ratio else None,
                # recast/lipsync: the reference image rides on first_frame; extend/edit take none
                "frame_images": [] if no_image else ["first_frame"],
                "audio_input": lipsync,  # takes an uploaded audio track (lip sync)
                # ref2video models take several named reference images
                "reference_images": meta.get("type") == "ref",
                "max_refs": REF_MAX_IMAGES if meta.get("type") == "ref" else None,
                # v1 reference-to-video branch (image/video/audio refs, [@name]
                # mentions): the allowed types, total cap and per-type limits.
                "ref_mode": meta.get("ref_mode") or None,
                "video_input": bool(meta.get("video_input")),
                "modes": meta.get("modes") or None,
                "generate_audio": "generate_audio" in meta.get("options", []),
                "created": None,
                "hidden": meta.get("hidden") or None,
            }
        )
    return out


def list_audio_models() -> list[dict[str, Any]]:
    """Pollo's speech and music models. `options` says which inputs the UI offers."""
    return [
        {
            "id": PREFIX + key,
            "name": f"Pollo: {meta.get('label') or key}",
            "type": meta.get("type"),
            "options": meta.get("options") or [],
            "audio_input": bool(meta.get("audio_input")),  # takes a reference clip (voice cloning)
            "created": None,
            "hidden": meta.get("hidden") or None,
        }
        for key, cls, meta in _catalogue(AUDIO_GENERATORS)
    ]


def list_voices(page: int = 1, page_size: int = 50, **filters: str) -> dict[str, Any]:
    """Pollo's official TTS voices ({"voices": [...], "total"}). A free GET."""
    params = {"page": page, "pageSize": page_size, **{k: v for k, v in filters.items() if v}}
    try:
        resp = requests.get(
            f"{POLLO_PLATFORM_BASE}/config/voice/items",
            params=params,
            headers={"x-api-key": keyctx.provider_key("pollo")},
            timeout=POLLO_API_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise PolloError(f"Couldn't load Pollo's voice list: {e}") from e
    keep = ("voiceId", "voiceName", "sampleAudio", "language", "gender", "age", "voiceStyle", "accent", "engineCode")
    voices = [{k: v.get(k) for k in keep} for v in body.get("data") or []]
    return {"voices": voices, "total": body.get("total", len(voices))}


def submit_audio(model_id: str, prompt: str, source_audio: Path | None = None, **opts: Any) -> dict:
    """Start a speech / music job. Returns {"id": "pollo:<task>", "params": the
    settings actually sent}, like submit_video."""
    key = _generator_key(model_id, AUDIO_GENERATORS)
    if MODEL_INFO.get(key, {}).get("audio_input"):
        if not source_audio:
            raise PolloError("Voice cloning needs a reference clip — upload an audio file")
        opts["voice_ref_url"] = _upload_audio(source_audio)
    try:
        generator = get_audio_generator(
            key, api_key=keyctx.provider_key("pollo"), project="chat", prompt=prompt, **opts
        )
        generator.get_payload()
    except ValueError as e:
        raise PolloError(str(e)) from e
    task_id = _submit(generator)
    return {"id": JOB_PREFIX + task_id, "params": dict(generator.payload_attrs)}


def _video_generators() -> dict:
    """The v1 video models selectable in the picker — text/image-to-video plus
    the source-video families (extend, motion…) — and legacy ref2video."""
    return {
        **GENERATORS_V1,
        # ref2video (several reference images) only exists on the legacy API
        **{key: cls for key, cls in GENERATORS_LEGACY.items() if MODEL_INFO.get(key, {}).get("type") == "ref"},
    }


def _generator_key(model_id: str, generators: dict) -> str:
    if not is_configured():
        raise PolloError("No Pollo API key set — add one in Settings → Keys")
    key = model_id[len(PREFIX) :]
    if key not in generators:
        raise PolloError(f"Unknown Pollo model: {key}")
    return key


def _upload(path: Path) -> str:
    try:
        return image_hosts.upload_image(path)
    except ValueError as e:
        raise PolloError(f"Couldn't upload the image for Pollo: {e}") from e


def _upload_video(path: Path) -> str:
    """Upload a source video to the user's configured host (Pollo only takes
    URLs). The host/retention come from the user's upload preferences."""
    try:
        return image_hosts.upload_file(path)
    except ValueError as e:
        raise PolloError(f"Couldn't upload the video for Pollo: {e}") from e


def _upload_audio(path: Path) -> str:
    """Upload a lip-sync audio track to the user's configured host (Pollo only
    takes URLs)."""
    try:
        return image_hosts.upload_file(path)
    except ValueError as e:
        raise PolloError(f"Couldn't upload the audio for Pollo: {e}") from e


def _upload_ref_item(item: dict) -> dict:
    """Upload one reference element (image / video / audio) and return it as a
    Pollo ref: {url, name, type}. The upload URL is cached and reused across
    retries (web/image_hosts.py), so re-rendering doesn't re-upload."""
    typ = item.get("type") or "image"
    path = item["path"]
    url = _upload_video(path) if typ == "video" else _upload_audio(path) if typ == "audio" else _upload(path)
    ref: dict[str, Any] = {"url": url, "type": typ}
    if item.get("name"):
        ref["name"] = item["name"]
    return ref


def _submit_ref_video_job(
    key: str,
    *,
    prompt: str,
    ref_items: list[dict],
    aspect_ratio: str | None,
    resolution: str | None,
    duration: int | None,
    generate_audio: bool | None,
) -> dict:
    """Reference-to-video: a named list of image/video/audio refs the prompt
    mentions as [@name] (Kling 4.0 / Flash / 3.0 Omni, MiniMax H3…). The engine
    routes to the refs branch whenever `refs` is present (_generic_payload)."""
    refs = [_upload_ref_item(ri) for ri in ref_items]
    generator = get_video_generator(
        key,
        api_key=keyctx.provider_key("pollo"),
        project="chat",
        prompt=prompt,
        image_url=None,
        refs=refs,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        length=duration,
        generate_audio=generate_audio,
    )
    task_id = _submit(generator)
    return {"id": JOB_PREFIX + task_id, "params": _sent_params(generator)}


def generate_image(
    model_id: str,
    prompt: str,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    ref_paths: list[Path] | None = None,
) -> tuple[list[tuple[bytes, str]], int | None, dict]:
    """Generate on Pollo and wait for the result. Returns ([(bytes, media
    type)], credits, the settings actually sent — see _sent_params).
    Reference images are uploaded to a temporary public host first (Pollo
    only takes URLs), the same way the Generate page sends local images."""
    generators = _image_generators()
    key = _generator_key(model_id, generators)
    if aspect_ratio not in generators[key].VALID_RATIOS:
        aspect_ratio = None  # the generator falls back to 1:1
    images = [_upload(p) for p in ref_paths or []]

    generator = get_image_generator(
        key,
        api_key=keyctx.provider_key("pollo"),
        project="chat",
        prompt=prompt,
        image_url=None,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        images=images or None,
    )
    task = _wait(_submit(generator))
    sent = _sent_params(generator)
    return (
        [_download(u) for u in task["urls"]],
        task["credits"],
        {"aspect_ratio": sent["aspect_ratio"], "resolution": sent["resolution"]},
    )


# "needs a source video" label per source-video family (preserves wording)
_SRC_VIDEO_NEEDS = {
    "faceswap": "Face swap",
    "bgremove": "Background removal",
    "subtitle_remove": "Subtitle removal",
    "motion": "Motion",
    "extend": "Extending",
    "video_edit": "Editing",
    "upscale": "Upscaling",
}
# families that animate a reference image with a source video (image + video)
_IMAGE_AND_VIDEO = ("motion", "faceswap")
# families that work on a source video alone (no image)
_VIDEO_ONLY = ("extend", "video_edit", "upscale", "bgremove", "subtitle_remove")
# families that run with no prompt text
_NO_PROMPT = ("upscale", "bgremove", "subtitle_remove", "faceswap", "motion")
# families whose enhancement mode the user can pick
_TAKES_MODE = ("motion", "upscale", "subtitle_remove")


def _submit_source_video_job(
    key: str,
    typ: str | None,
    *,
    prompt: str,
    source_video: Path | None,
    first_frame: Path | None,
    resolution: str | None,
    duration: int | None,
    generate_audio: bool | None,
    mode: str | None,
) -> dict | None:
    """Submit a job for a family that works on a source video — Motion
    (video + reference image + mode), Extend (video, adds duration) or Video Edit
    (video + instruction prompt) or Upscale (video + scale/mode). Returns the job dict, or None if `typ` isn't one
    of those (so the caller falls through to the image/text path)."""
    if typ not in (*_IMAGE_AND_VIDEO, *_VIDEO_ONLY):
        return None
    if not source_video:
        raise PolloError(f"{_SRC_VIDEO_NEEDS[typ]} needs a source video")
    if typ in _IMAGE_AND_VIDEO and not first_frame:
        raise PolloError(f"{_SRC_VIDEO_NEEDS[typ]} needs a reference image")
    if typ == "video_edit" and not (prompt or "").strip():
        raise PolloError("Editing needs an instruction prompt")
    # The source video goes to the host that takes larger files; both are URLs.
    kw: dict[str, Any] = {
        "api_key": keyctx.provider_key("pollo"),
        "project": "chat",
        "prompt": prompt,
        "video_url": _upload_video(source_video),
    }
    if typ in _IMAGE_AND_VIDEO:  # the reference / face image rides along
        kw.update(image_url=_upload(first_frame), mode=mode)
    else:
        kw.update(image_url=None, resolution=resolution)
        if typ in _TAKES_MODE:  # resolution carries the one pick (scale / language); mode the rest
            kw.update(mode=mode)
        if typ == "extend":  # extend lets the user pick added duration + audio
            kw.update(length=duration, generate_audio=generate_audio)
    generator = get_video_generator(key, **kw)
    task_id = _submit(generator)
    return {"id": JOB_PREFIX + task_id, "params": _sent_params(generator)}


def submit_video(
    model_id: str,
    prompt: str,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    generate_audio: bool | None = None,
    first_frame: Path | None = None,
    source_video: Path | None = None,
    source_audio: Path | None = None,
    mode: str | None = None,
    refs: list[Path] | None = None,
    ref_items: list[dict] | None = None,
) -> dict:
    """Start a Pollo video job. Returns {"id": "pollo:<taskId>", "params": the
    settings actually sent}, shaped like openrouter.submit_video's result.
    A first frame is uploaded to a temporary public host first (Pollo only takes URLs).
    `ref_items` (named image/video/audio refs — {path, name, type}) routes a
    ref_mode model to its reference-to-video branch, superseding first_frame."""
    key = _generator_key(model_id, _video_generators())
    typ = MODEL_INFO.get(key, {}).get("type")
    if ref_items and MODEL_INFO.get(key, {}).get("ref_mode"):
        return _submit_ref_video_job(
            key,
            prompt=prompt,
            ref_items=ref_items,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration=duration,
            generate_audio=generate_audio,
        )
    if typ == "lipsync":
        # Lip sync: a reference image (first frame) driven by an uploaded audio
        # track. Both are uploaded to public URLs.
        if not first_frame:
            raise PolloError("Lip sync needs a reference image")
        if not source_audio:
            raise PolloError("Lip sync needs an audio file")
        generator = get_video_generator(
            key,
            api_key=keyctx.provider_key("pollo"),
            project="chat",
            prompt=prompt,
            image_url=_upload(first_frame),
            audio_url=_upload_audio(source_audio),
            resolution=resolution,
        )
        task_id = _submit(generator)
        return {"id": JOB_PREFIX + task_id, "params": _sent_params(generator)}
    job = _submit_source_video_job(
        key,
        typ,
        prompt=prompt,
        source_video=source_video,
        first_frame=first_frame,
        resolution=resolution,
        duration=duration,
        generate_audio=generate_audio,
        mode=mode,
    )
    if job is not None:
        return job
    if typ == "ref":
        # ref2video: every reference image (the first frame too) becomes a named
        # "Image N" reference the prompt can mention, like Pollo's own site
        files = list(dict.fromkeys([*([first_frame] if first_frame else []), *(refs or [])]))[:REF_MAX_IMAGES]
        generator = get_video_generator(
            key,
            api_key=keyctx.provider_key("pollo"),
            project="chat",
            prompt=prompt,
            image_url=None,
            refs=[
                {"type": "image", "name": f"Image {i}", "image": _upload(p), "order": i} for i, p in enumerate(files, 1)
            ],
            aspect_ratio=aspect_ratio if aspect_ratio in (MODEL_INFO[key].get("ratios") or []) else None,
            resolution=resolution,
            length=duration,
            generate_audio=generate_audio,
        )
        task_id = _submit(generator)
        return {"id": JOB_PREFIX + task_id, "params": _sent_params(generator)}
    ratios = MODEL_INFO.get(key, {}).get("ratios") or list(GENERATORS_V1[key].VALID_RATIOS)
    if aspect_ratio not in ratios:
        aspect_ratio = None
    if first_frame and not aspect_ratio:
        # Some models (Seedance 2.0, Pollo Dance 2.0) take aspectRatio on the
        # image branch too, and the generator's fallback is 9:16 — so frame
        # the video like the image instead
        aspect_ratio = _ratio_for_image(first_frame, ratios)
    generator = get_video_generator(
        key,
        api_key=keyctx.provider_key("pollo"),
        project="chat",
        prompt=prompt,
        image_url=_upload(first_frame) if first_frame else None,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        length=duration,
        generate_audio=generate_audio,
    )
    task_id = _submit(generator)
    return {"id": JOB_PREFIX + task_id, "params": _sent_params(generator)}


def estimate_cost(
    model_id: str,
    kind: str,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    generate_audio: bool | None = None,
    n_images: int = 0,
    prompt: str = "",
    audio: dict[str, Any] | None = None,
) -> dict | None:
    """Pollo's own price for a request ({"credits", "full_credits"}), or None if
    it can't say (a ref2video model has no estimate endpoint; errors). Free, and
    nothing is uploaded: stand-in URLs are priced the same as real ones."""
    try:
        if kind == "audio":
            key = _generator_key(model_id, AUDIO_GENERATORS)
            generator = get_audio_generator(
                key,
                api_key=keyctx.provider_key("pollo"),
                project="chat",
                prompt=prompt or "estimate",
                voice_ref_url=pollo_estimate.PLACEHOLDERS["audio"],
                **(audio or {}),
            )
        elif kind == "image":
            generators = _image_generators()
            key = _generator_key(model_id, generators)
            generator = get_image_generator(
                key,
                api_key=keyctx.provider_key("pollo"),
                project="chat",
                prompt="estimate",
                image_url=None,
                aspect_ratio=aspect_ratio if aspect_ratio in generators[key].VALID_RATIOS else None,
                resolution=resolution,
                images=[pollo_estimate.PLACEHOLDERS["image"]] * n_images or None,
            )
        else:
            key = _generator_key(model_id, _video_generators())
            ratios = MODEL_INFO.get(key, {}).get("ratios") or list(_video_generators()[key].VALID_RATIOS)
            generator = get_video_generator(
                key,
                api_key=keyctx.provider_key("pollo"),
                project="chat",
                prompt="estimate",
                image_url=pollo_estimate.PLACEHOLDERS["image"] if n_images else None,
                # source-file models (upscale, tools…) price from stand-in files
                video_url=pollo_estimate.PLACEHOLDERS["video"] if MODEL_INFO.get(key, {}).get("video_input") else None,
                aspect_ratio=aspect_ratio if aspect_ratio in ratios else None,
                resolution=resolution,
                length=duration,
                generate_audio=generate_audio,
            )
        return pollo_estimate.estimate(generator)
    except Exception:  # noqa: BLE001 — an estimate is a nicety; never fail the composer over it
        return None


def _sent_params(generator) -> dict[str, Any]:
    """What the generator actually sent, in chat's param names — so the UI
    shows the real settings, including defaults the generator filled in. A
    None means the field wasn't sent (e.g. no aspectRatio when animating an
    image: the image sets it). Kling's quality tier ("mode") shows as the
    resolution, the way it's picked."""
    attrs = generator.payload_attrs or {}
    return {
        "aspect_ratio": attrs.get("aspectRatio"),
        "resolution": attrs.get("resolution") or attrs.get("mode"),
        "duration": attrs.get("duration") or attrs.get("length"),
        "generate_audio": attrs.get("generateAudio"),
    }


def _ratio_for_image(path: Path, ratios: list[str]) -> str | None:
    """The model's "follow the image" ratio if it has one, else its closest ratio to the image's shape."""
    follow = next((r for r in ratios if r in FOLLOW_IMAGE_RATIOS), None)
    if follow:
        return follow
    numeric = tuple(r for r in ratios if ":" in r)
    if not numeric:
        return None
    with Image.open(path) as img:
        width, height = img.size
    return closest_aspect_ratio(width, height, numeric)


def get_video(job_id: str) -> dict:
    """The job in openrouter.get_video's shape: status completed | failed |
    in_progress, plus "error", and "credits" once done. Transient poll
    failures raise, so the poller's error budget handles them."""
    task = _task_state(job_id[len(JOB_PREFIX) :])
    if task["status"] == "transient":
        raise PolloError(task["error"])
    return task


def download_video(job_id: str, dest: Path, index: int = 0) -> None:
    task = get_video(job_id)
    if task["status"] != "completed":
        raise PolloError(f"Pollo video isn't ready ({task['status']})")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with requests.get(task["urls"][index], stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
    except requests.RequestException as e:
        raise PolloError(f"Couldn't download the Pollo video: {e}") from e
    tmp.replace(dest)


def _submit(generator) -> str:
    path = urlsplit(getattr(generator, "model_url", None) or "").path
    model = path.rstrip("/").rsplit("/", 1)[-1] or None
    with request_log.logged("pollo", "POST", path, _payload(generator), model=model) as outcome:
        return _submit_logged(generator, outcome)


def _payload(generator) -> Any:
    """What the generator will send (None if it refuses to build one)."""
    try:
        return generator.get_payload()
    except Exception:  # noqa: BLE001 — send_request reports the real problem
        return None


def _submit_logged(generator, outcome: dict) -> str:
    try:
        resp = generator.send_request()
    except (ConnectionError, ValueError) as e:
        # ValueError: the generator refused the request (e.g. an
        # image-to-video-only model with no image) — nothing was sent
        raise PolloError(f"Pollo: {e}") from e
    outcome["status"] = resp.status_code
    outcome["response"] = request_log.response_of(resp)
    try:
        body = resp.json()
    except ValueError:
        raise PolloError(
            f"Pollo returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}", resp.status_code
        ) from None
    task_id = (body.get("data") or {}).get("taskId") if isinstance(body.get("data"), dict) else None
    if not task_id and resp.status_code == 404 and body.get("message") == "Not found":
        raise PolloError(
            "Pollo: this model isn't available to your API key (404 Not found) — "
            "it may not be enabled for API access yet",
            404,
        )
    if not task_id:
        issues = (body.get("data") or {}).get("issues") if isinstance(body.get("data"), dict) else None
        detail = "; ".join(i.get("message", "") for i in issues or []) or body.get("message")
        raise PolloError(f"Pollo: {detail or f'request failed (HTTP {resp.status_code})'}", resp.status_code)
    return task_id


def _task_state(task_id: str) -> dict:
    """One status check: {"status": completed | failed | in_progress |
    transient, "error", "urls", "credits"}. "transient" = Cloudflare/network/
    HTTP trouble worth retrying, not a verdict on the generation."""
    try:
        results = get_task_status(task_id, keyctx.provider_key("pollo"))
    except Exception as e:  # noqa: BLE001 — network/VPN hiccups
        return {"status": "transient", "error": f"Pollo: {e}"}
    status, fail_msg = results[0][0], results[0][1]
    if status == "cloudflare_blocked" or (status == "error" and (fail_msg or "").startswith("HTTP ")):
        return {"status": "transient", "error": f"Pollo: {fail_msg}"}
    if status in ERROR_STATUSES:
        return {"status": "failed", "error": f"Pollo: {fail_msg or 'generation failed'}"}
    if not all(r[0] in SUCCESS_STATUSES for r in results):
        return {"status": "in_progress"}
    urls = [r[2] for r in results if r[2]]
    if not urls:
        return {"status": "failed", "error": "Pollo finished but returned no file"}
    return {"status": "completed", "urls": urls, "credits": sum(r[3] for r in results if r[3] is not None) or None}


def _wait(task_id: str) -> dict:
    """Poll an image task until it's done (or fails)."""
    deadline = time.time() + POLL_TIMEOUT
    errors = 0
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        task = _task_state(task_id)
        if task["status"] == "transient":
            errors += 1
            if errors >= MAX_POLL_ERRORS:
                raise PolloError(f"{task['error']} (polling gave up)")
            continue
        errors = 0
        if task["status"] == "failed":
            raise PolloError(task["error"])
        if task["status"] == "completed":
            return task
    raise PolloError("Pollo: timed out waiting for the image")


def _download(url: str) -> tuple[bytes, str]:
    try:
        resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise PolloError(f"Couldn't download the Pollo image: {e}") from e
    media_type = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip()
    return resp.content, media_type
