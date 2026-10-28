"""
Multi-provider video/image generation for the Generate page (web/api.py).

The Generate page is built on Pollo's img2vid generators (bare model keys like
"pollodance20"). This module lets it ALSO use the chat's providers — Pollo
(v1, "pollo/..."), Venice ("venice/...") and OpenRouter ("vendor/model") — by
reusing the exact uniform layer the chat uses: list_*, submit_video,
generate_image, get_video, download_video, is_*_job. Provider models always
carry a "/" in their id, which is how the Generate page tells them apart from
its own bare-key Pollo models.
"""

import base64
import contextlib
import mimetypes
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from . import openrouter, pollo_chat, venice_chat
from .uploads import safe_filename

VIDEO_POLL_INTERVAL = 10  # seconds between polls
VIDEO_POLL_TIMEOUT = 30 * 60  # give up after 30 min
VIDEO_MAX_POLL_ERRORS = 6  # consecutive poll errors before failing


def is_provider_model(model: str | None) -> bool:
    """A chat-provider model id (Pollo v1 "pollo/…", Venice "venice/…", or an
    OpenRouter "vendor/model"). The Generate page's own Pollo img2vid models
    are bare keys with no slash."""
    return "/" in (model or "")


def _provider(model_or_job: str):
    """The provider module that owns a model id or a job id."""
    if pollo_chat.is_pollo(model_or_job) or pollo_chat.is_pollo_job(model_or_job):
        return pollo_chat
    if venice_chat.is_venice(model_or_job) or venice_chat.is_venice_job(model_or_job):
        return venice_chat
    return openrouter


# ── Model lists (the same ones the chat shows) ──────────────────────


def list_video_models() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fn in (pollo_chat.list_video_models, lambda: venice_chat.list_models("video"), openrouter.list_video_models):
        # A provider that isn't configured/reachable is just skipped
        with contextlib.suppress(Exception):
            out += fn() or []
    return out


def list_image_models() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fn in (pollo_chat.list_image_models, lambda: venice_chat.list_models("image"), openrouter.list_image_models):
        with contextlib.suppress(Exception):  # unconfigured/unreachable provider is skipped
            out += fn() or []
    return out


# ── Local file helpers ──────────────────────────────────────────────


def local_path(assets_path: Path, ref: str | None) -> Path | None:
    """Resolve a Generate-page media reference to a local file: a "local:<file>"
    in the project assets, or an http(s) URL downloaded into the assets."""
    if not ref:
        return None
    if ref.startswith("local:"):
        path = assets_path / safe_filename(ref[len("local:") :])
        return path if path.is_file() else None
    if ref.startswith(("http://", "https://")):
        suffix = Path(ref.split("?", 1)[0]).suffix or ".bin"
        dest = assets_path / f"src-{uuid.uuid4().hex[:12]}{suffix}"
        with requests.get(ref, stream=True, timeout=(8, 60)) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        return dest
    return None


def _data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


# ── Submit (dispatch to the provider, like chat._submit_video) ──────


def submit_video(
    model: str,
    prompt: str,
    first_frame: Path | None = None,
    source_video: Path | None = None,
    refs: list[Path] | None = None,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    generate_audio: bool | None = None,
    mode: str | None = None,
) -> dict:
    """Start a video job on the model's provider; returns {"id", "params"}."""
    prompt = prompt or " "  # some generators read a project prompt file on empty
    if venice_chat.is_venice(model):
        return venice_chat.submit_video(
            model,
            prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            generate_audio=generate_audio,
            first_frame=first_frame,
            refs=refs,
            source_video=source_video,
        )
    if pollo_chat.is_pollo(model):
        return pollo_chat.submit_video(
            model,
            prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            generate_audio=generate_audio,
            first_frame=first_frame,
            source_video=source_video,
            mode=mode,
        )
    return openrouter.submit_video(
        model,
        prompt,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        generate_audio=generate_audio,
        first_frame=_data_url(first_frame) if first_frame else None,
    )


# ── Run a provider video job in the Generate page's job DB ──────────


def run_video(job_id: str, model: str, submit_kwargs: dict, assets_path: Path, get_db) -> None:
    """Background: submit to the provider, poll to completion, download the
    MP4 into the project assets and mark the job done — reusing the chat's
    uniform get_video/download_video. `get_db` is api.get_db (a factory)."""
    db = get_db()
    try:
        db.update_job(job_id, status="sending", message="Sending request to the provider...")
        job = submit_video(model, **submit_kwargs)
        provider_job_id = job["id"]
        source = _provider(provider_job_id)
        db.update_job(job_id, status="processing", task_id=provider_job_id, message="Processing...")

        deadline = time.time() + VIDEO_POLL_TIMEOUT
        errors = 0
        while time.time() < deadline:
            time.sleep(VIDEO_POLL_INTERVAL)
            try:
                res = source.get_video(provider_job_id)
                errors = 0
            except Exception as e:  # noqa: BLE001 — transient network/VPN hiccups
                errors += 1
                if errors >= VIDEO_MAX_POLL_ERRORS:
                    db.update_job(job_id, status="error", message=f"Polling failed: {e}")
                    return
                continue

            status = res.get("status")
            if status == "completed":
                db.update_job(job_id, status="downloading", message="Downloading video...")
                name = f"gen-{uuid.uuid4().hex[:12]}.mp4"
                source.download_video(provider_job_id, assets_path / name)
                db.update_job(
                    job_id,
                    status="done",
                    message="Video ready!",
                    video_path=str(assets_path / name),
                    credits_used=res.get("credits"),
                )
                return
            if status in ("failed", "cancelled", "expired"):
                db.update_job(job_id, status="error", message=res.get("error") or f"Video {status}")
                return
        db.update_job(job_id, status="error", message="Timed out waiting for video")
    except Exception as e:  # noqa: BLE001 — surface any failure on the job
        db.update_job(job_id, status="error", message=str(e))


def start_video(job_id: str, model: str, submit_kwargs: dict, assets_path: Path, get_db) -> None:
    threading.Thread(
        target=run_video, args=(job_id, model, submit_kwargs, assets_path, get_db), daemon=True, name=f"gen-{job_id}"
    ).start()
