"""
Pollo image models for chat mode.

Chat's generate_image tool normally runs on OpenRouter image models. This
module lets it run on Pollo's image models too, reusing the same generator
classes the Generate page uses. They're listed in the chat's image catalogue
as "pollo/<generator key>" (e.g. "pollo/seedreamv1").

Pollo bills in credits, not dollars, so a Pollo image records `credits` on
its media item rather than adding to the OpenRouter `cost`.
"""
import os
import time
from pathlib import Path
from typing import Any

import requests

from img2vid.common.get_task import get_task_status
from img2vid.pollo.generators import ERROR_STATUSES, SUCCESS_STATUSES
from img2vid.pollo.pollo_img2vid import IMAGE_GENERATORS_V1, get_image_generator

from .openrouter import OpenRouterError

PREFIX = "pollo/"
POLL_INTERVAL = 4
POLL_TIMEOUT = 10 * 60
MAX_POLL_ERRORS = 6
DOWNLOAD_TIMEOUT = 120


def is_configured() -> bool:
    return bool(os.getenv("POLLO_API_KEY"))


def is_pollo(model_id: str | None) -> bool:
    return bool(model_id and model_id.startswith(PREFIX))


def _web_api():
    # web.api imports this package's chat router, so import it lazily
    from . import api
    return api


def list_image_models() -> list[dict[str, Any]]:
    """Pollo's v1 image models, shaped like openrouter.list_image_models()."""
    if not is_configured():
        return []
    info = _web_api().MODEL_INFO
    return [{
        "id": PREFIX + key,
        "name": f"Pollo: {info.get(key, {}).get('label') or key}",
        "input_modalities": ["text", "image"],   # all take reference images
        "aspect_ratios": list(cls.VALID_RATIOS) or None,
        "resolutions": list(cls.VALID_RESOLUTIONS) or None,
        "created": None,
        "conversational": False,
    } for key, cls in IMAGE_GENERATORS_V1.items()]


def generate_image(model_id: str, prompt: str, aspect_ratio: str | None = None,
                   resolution: str | None = None,
                   ref_paths: list[Path] | None = None) -> tuple[list[tuple[bytes, str]], int | None]:
    """Generate on Pollo and wait for the result. Returns ([(bytes, media type)], credits).
    Reference images are uploaded to a temporary public host first (Pollo
    only takes URLs), the same way the Generate page sends local images."""
    if not is_configured():
        raise OpenRouterError("POLLO_API_KEY is not set on the server")
    key = model_id[len(PREFIX):]
    cls = IMAGE_GENERATORS_V1.get(key)
    if not cls:
        raise OpenRouterError(f"Unknown Pollo image model: {key}")
    if aspect_ratio not in cls.VALID_RATIOS:
        aspect_ratio = None   # the generator falls back to 1:1
    try:
        images = [_web_api()._upload_image(p) for p in ref_paths or []]
    except ValueError as e:
        raise OpenRouterError(f"Couldn't upload the reference image for Pollo: {e}") from e

    generator = get_image_generator(
        key, api_key=os.getenv("POLLO_API_KEY"), project="chat", prompt=prompt, image_url=None,
        aspect_ratio=aspect_ratio, resolution=resolution, images=images or None,
    )
    task_id = _submit(generator)
    urls, credits = _wait(task_id, generator.api_key)
    return [_download(u) for u in urls], credits


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


def _wait(task_id: str, api_key: str) -> tuple[list[str], int | None]:
    """Poll the task until every image is done (or one fails)."""
    deadline = time.time() + POLL_TIMEOUT
    errors = 0
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            results = get_task_status(task_id, api_key)
        except Exception as e:  # noqa: BLE001 — transient network/VPN hiccups
            results = [("error_transient", str(e), None, None)]
        status, fail_msg = results[0][0], results[0][1]
        if status in ("cloudflare_blocked", "error_transient") or (
                status == "error" and (fail_msg or "").startswith("HTTP ")):
            errors += 1
            if errors >= MAX_POLL_ERRORS:
                raise OpenRouterError(f"Pollo: polling failed — {fail_msg}")
            continue
        errors = 0
        if status in ERROR_STATUSES:
            raise OpenRouterError(f"Pollo: {fail_msg or 'generation failed'}")
        if all(r[0] in SUCCESS_STATUSES for r in results):
            urls = [r[2] for r in results if r[2]]
            if not urls:
                raise OpenRouterError("Pollo finished but returned no image")
            credits = sum(r[3] for r in results if r[3] is not None) or None
            return urls, credits
    raise OpenRouterError("Pollo: timed out waiting for the image")


def _download(url: str) -> tuple[bytes, str]:
    try:
        resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OpenRouterError(f"Couldn't download the Pollo image: {e}") from e
    media_type = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip()
    return resp.content, media_type
