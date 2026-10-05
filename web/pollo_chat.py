"""
Pollo image and video models for chat mode.

Chat's generate_image / generate_video tools normally run on OpenRouter
models. This module lets them run on Pollo's v1 models too, reusing the
generator classes the Generate page uses. They're listed in the chat's
catalogues as "pollo/<generator key>" (e.g. "pollo/seedreamv1",
"pollo/seedance20fastv1") and bill the Pollo account (POLLO_API_KEY).

Images are generated synchronously, like OpenRouter's. Videos mirror
openrouter.submit_video / get_video / download_video, with job ids prefixed
"pollo:" so chat's background video poller knows which API to ask.

Pollo bills in credits, not dollars, so Pollo media records `credits` on
its media item rather than adding to the OpenRouter `cost`.
"""
import os
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from img2vid.common.get_task import get_task_status
from img2vid.pollo.generators import ERROR_STATUSES, SUCCESS_STATUSES, BaseVideoGenerator
from img2vid.pollo.pollo_img2vid import (GENERATORS_V1, IMAGE_GENERATORS_V1, get_image_generator,
                                         get_video_generator)

from .openrouter import OpenRouterError

PREFIX = "pollo/"
JOB_PREFIX = "pollo:"
FOLLOW_IMAGE_RATIOS = ("adaptive", "auto")   # values meaning "match the input image"
POLL_INTERVAL = 4
POLL_TIMEOUT = 10 * 60
MAX_POLL_ERRORS = 6
DOWNLOAD_TIMEOUT = 120


def is_configured() -> bool:
    return bool(os.getenv("POLLO_API_KEY"))


def is_pollo(model_id: str | None) -> bool:
    return bool(model_id and model_id.startswith(PREFIX))


def is_pollo_job(job_id: str | None) -> bool:
    return bool(job_id and job_id.startswith(JOB_PREFIX))


def _web_api():
    # web.api imports this package's chat router, so import it lazily
    from . import api
    return api


def _catalogue(generators: dict) -> list[tuple[str, type, dict]]:
    """(key, class, MODEL_INFO entry) for each model the Generate page doesn't mark deprecated."""
    if not is_configured():
        return []
    info = _web_api().MODEL_INFO
    return [(key, cls, info.get(key, {})) for key, cls in generators.items()
            if not info.get(key, {}).get("deprecated")]


def list_image_models() -> list[dict[str, Any]]:
    """Pollo's v1 image models, shaped like openrouter.list_image_models()."""
    return [{
        "id": PREFIX + key,
        "name": f"Pollo: {meta.get('label') or key}",
        "input_modalities": ["text", "image"],   # all take reference images
        "aspect_ratios": list(cls.VALID_RATIOS) or None,
        "resolutions": list(cls.VALID_RESOLUTIONS) or None,
        "created": None,
        "conversational": False,
    } for key, cls, meta in _catalogue(IMAGE_GENERATORS_V1)]


def list_video_models() -> list[dict[str, Any]]:
    """Pollo's v1 video models, shaped like openrouter.list_video_models()."""
    return [{
        "id": PREFIX + key,
        "name": f"Pollo: {meta.get('label') or key}",
        "durations": meta.get("lengths") or list(cls.VALID_LENGTHS) or None,
        "resolutions": meta.get("resolutions") or list(cls.VALID_RESOLUTIONS) or None,
        "aspect_ratios": meta.get("ratios") or list(cls.VALID_RATIOS) or None,
        "frame_images": ["first_frame"],          # all animate a source image
        "generate_audio": "generate_audio" in meta.get("options", []),
        "created": None,
    } for key, cls, meta in _catalogue(GENERATORS_V1)]


def _generator_key(model_id: str, generators: dict) -> str:
    if not is_configured():
        raise OpenRouterError("POLLO_API_KEY is not set on the server")
    key = model_id[len(PREFIX):]
    if key not in generators:
        raise OpenRouterError(f"Unknown Pollo model: {key}")
    return key


def _upload(path: Path) -> str:
    try:
        return _web_api()._upload_image(path)
    except ValueError as e:
        raise OpenRouterError(f"Couldn't upload the image for Pollo: {e}") from e


def generate_image(model_id: str, prompt: str, aspect_ratio: str | None = None,
                   resolution: str | None = None,
                   ref_paths: list[Path] | None = None) -> tuple[list[tuple[bytes, str]], int | None]:
    """Generate on Pollo and wait for the result. Returns ([(bytes, media type)], credits).
    Reference images are uploaded to a temporary public host first (Pollo
    only takes URLs), the same way the Generate page sends local images."""
    key = _generator_key(model_id, IMAGE_GENERATORS_V1)
    if aspect_ratio not in IMAGE_GENERATORS_V1[key].VALID_RATIOS:
        aspect_ratio = None   # the generator falls back to 1:1
    images = [_upload(p) for p in ref_paths or []]

    generator = get_image_generator(
        key, api_key=os.getenv("POLLO_API_KEY"), project="chat", prompt=prompt, image_url=None,
        aspect_ratio=aspect_ratio, resolution=resolution, images=images or None,
    )
    task = _wait(_submit(generator))
    return [_download(u) for u in task["urls"]], task["credits"]


def submit_video(model_id: str, prompt: str, duration: int | None = None, aspect_ratio: str | None = None,
                 resolution: str | None = None, generate_audio: bool | None = None,
                 first_frame: Path | None = None) -> dict:
    """Start a Pollo video job. Returns {"id": "pollo:<taskId>"}, like openrouter.submit_video.
    A first frame is uploaded to a temporary public host first (Pollo only takes URLs)."""
    key = _generator_key(model_id, GENERATORS_V1)
    ratios = _web_api().MODEL_INFO.get(key, {}).get("ratios") or list(GENERATORS_V1[key].VALID_RATIOS)
    if aspect_ratio not in ratios:
        aspect_ratio = None
    if first_frame and not aspect_ratio:
        # Some models (Seedance 2.0, Pollo Dance 2.0) take aspectRatio on the
        # image branch too, and the generator's fallback is 9:16 — so frame
        # the video like the image instead
        aspect_ratio = _ratio_for_image(first_frame, ratios)
    generator = get_video_generator(
        key, api_key=os.getenv("POLLO_API_KEY"), project="chat", prompt=prompt,
        image_url=_upload(first_frame) if first_frame else None,
        aspect_ratio=aspect_ratio, resolution=resolution, length=duration, generate_audio=generate_audio,
    )
    return {"id": JOB_PREFIX + _submit(generator)}


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
    return BaseVideoGenerator.get_closest_aspect_ratio(width, height, numeric)


def get_video(job_id: str) -> dict:
    """The job in openrouter.get_video's shape: status completed | failed |
    in_progress, plus "error", and "credits" once done. Transient poll
    failures raise, so the poller's error budget handles them."""
    task = _task_state(job_id[len(JOB_PREFIX):])
    if task["status"] == "transient":
        raise OpenRouterError(task["error"])
    return task


def download_video(job_id: str, dest: Path, index: int = 0) -> None:
    task = get_video(job_id)
    if task["status"] != "completed":
        raise OpenRouterError(f"Pollo video isn't ready ({task['status']})")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with requests.get(task["urls"][index], stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
    except requests.RequestException as e:
        raise OpenRouterError(f"Couldn't download the Pollo video: {e}") from e
    tmp.replace(dest)


def _submit(generator) -> str:
    try:
        resp = generator.send_request()
    except ConnectionError as e:
        raise OpenRouterError(str(e)) from e
    try:
        body = resp.json()
    except ValueError:
        raise OpenRouterError(f"Pollo returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}", resp.status_code)
    task_id = (body.get("data") or {}).get("taskId") if isinstance(body.get("data"), dict) else None
    if not task_id:
        issues = (body.get("data") or {}).get("issues") if isinstance(body.get("data"), dict) else None
        detail = "; ".join(i.get("message", "") for i in issues or []) or body.get("message")
        raise OpenRouterError(f"Pollo: {detail or f'request failed (HTTP {resp.status_code})'}", resp.status_code)
    return task_id


def _task_state(task_id: str) -> dict:
    """One status check: {"status": completed | failed | in_progress |
    transient, "error", "urls", "credits"}. "transient" = Cloudflare/network/
    HTTP trouble worth retrying, not a verdict on the generation."""
    try:
        results = get_task_status(task_id, os.getenv("POLLO_API_KEY"))
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
    return {"status": "completed", "urls": urls,
            "credits": sum(r[3] for r in results if r[3] is not None) or None}


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
                raise OpenRouterError(f"{task['error']} (polling gave up)")
            continue
        errors = 0
        if task["status"] == "failed":
            raise OpenRouterError(task["error"])
        if task["status"] == "completed":
            return task
    raise OpenRouterError("Pollo: timed out waiting for the image")


def _download(url: str) -> tuple[bytes, str]:
    try:
        resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OpenRouterError(f"Couldn't download the Pollo image: {e}") from e
    media_type = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip()
    return resp.content, media_type
