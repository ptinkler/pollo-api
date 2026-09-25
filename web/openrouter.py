"""
Thin OpenRouter client (https://openrouter.ai/docs) used by the chat mode.

Covers the three surfaces chat needs:
  • text   — POST /chat/completions (SSE streaming, tool calls)
  • image  — POST /images           (synchronous, base64 results)
  • video  — POST /videos           (async job: submit → poll → download /content)

Request/response shapes were taken from https://openrouter.ai/openapi.json,
not by probing the live API (probes cost real money).
"""
import base64
import json
import os
from pathlib import Path
from typing import Any, Iterator

import httpx

# Overridable so a local fake can stand in during manual testing
OPENROUTER_BASE = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
CHAT_TIMEOUT = httpx.Timeout(connect=15, read=300, write=60, pool=15)
IMAGE_TIMEOUT = httpx.Timeout(connect=15, read=600, write=120, pool=15)
DEFAULT_TIMEOUT = httpx.Timeout(30)


class OpenRouterError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def get_api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(get_api_key())


def _headers() -> dict[str, str]:
    key = get_api_key()
    if not key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured", 503)
    return {
        "Authorization": f"Bearer {key}",
        # Optional attribution headers — shown on openrouter.ai activity pages
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://github.com/ptinkler/pollo-api"),
        "X-Title": "Pollo Chat",
    }


def _raise_for_response(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
        err = body.get("error") or {}
        message = err.get("message") if isinstance(err, dict) else str(err)
        # Provider errors carry the upstream message in metadata.raw and the
        # upstream's name in metadata.provider_name. Naming the provider
        # matters: e.g. Google's "API key not valid" refers to a BYOK key set
        # in OpenRouter, not to OPENROUTER_API_KEY.
        meta = (err.get("metadata") or {}) if isinstance(err, dict) else {}
        raw = meta.get("raw")
        if raw and isinstance(raw, str) and raw not in (message or ""):
            message = f"{message}: {raw[:300]}"
        provider = meta.get("provider_name")
        if provider and isinstance(provider, str) and provider not in (message or ""):
            message = f"[{provider}] {message}"
    except (ValueError, AttributeError):
        message = resp.text[:500]
    raise OpenRouterError(message or f"HTTP {resp.status_code}", resp.status_code)


def _get(path: str, params: dict | None = None) -> dict:
    resp = httpx.get(f"{OPENROUTER_BASE}{path}", headers=_headers(), params=params, timeout=DEFAULT_TIMEOUT)
    _raise_for_response(resp)
    return resp.json()


# ── Model catalogues ────────────────────────────────────────────────

def list_text_models() -> list[dict[str, Any]]:
    data = _get("/models", {"output_modalities": "text"}).get("data", [])
    models = []
    for m in data:
        arch = m.get("architecture") or {}
        pricing = m.get("pricing") or {}
        params = m.get("supported_parameters") or []
        models.append({
            "id": m["id"],
            "name": m.get("name") or m["id"],
            "context_length": m.get("context_length"),
            "input_modalities": arch.get("input_modalities") or ["text"],
            "supports_tools": "tools" in params,
            "prompt_price": pricing.get("prompt"),
            "completion_price": pricing.get("completion"),
            "created": m.get("created"),
        })
    return models


def list_image_models() -> list[dict[str, Any]]:
    data = _get("/images/models").get("data", [])
    models = []
    for m in data:
        arch = m.get("architecture") or {}
        params = m.get("supported_parameters") or {}
        models.append({
            "id": m["id"],
            "name": m.get("name") or m["id"],
            "input_modalities": arch.get("input_modalities") or ["text"],
            "aspect_ratios": (params.get("aspect_ratio") or {}).get("values"),
            "resolutions": (params.get("resolution") or {}).get("values"),
            "created": m.get("created"),
        })
    return models


def list_video_models() -> list[dict[str, Any]]:
    data = _get("/videos/models").get("data", [])
    models = []
    for m in data:
        # Upscalers share this catalogue but can't generate from a prompt
        if m.get("upscale_factor") or m.get("creativity"):
            continue
        models.append({
            "id": m["id"],
            "name": m.get("name") or m["id"],
            "durations": m.get("supported_durations"),
            "resolutions": m.get("supported_resolutions"),
            "aspect_ratios": m.get("supported_aspect_ratios"),
            "frame_images": m.get("supported_frame_images") or [],
            "generate_audio": m.get("generate_audio"),
            "created": m.get("created"),
        })
    return models


# ── Text ────────────────────────────────────────────────────────────

def stream_chat(model: str, messages: list[dict], tools: list[dict] | None = None,
                session_id: str | None = None) -> Iterator[dict]:
    """Yield parsed chat.completion.chunk dicts. Raises OpenRouterError on
    pre-stream HTTP errors and on mid-stream error chunks."""
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,  # usage (incl. cost) always arrives on the final chunk
    }
    if tools:
        body["tools"] = tools
    if session_id:
        body["session_id"] = session_id

    with httpx.stream("POST", f"{OPENROUTER_BASE}/chat/completions", headers=_headers(),
                      json=body, timeout=CHAT_TIMEOUT) as resp:
        if resp.status_code >= 400:
            resp.read()
            _raise_for_response(resp)
        for line in resp.iter_lines():
            # Blank separators and ": OPENROUTER PROCESSING" keep-alives
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                err = chunk["error"]
                raise OpenRouterError(err.get("message") if isinstance(err, dict) else str(err))
            yield chunk


# ── Image ───────────────────────────────────────────────────────────

def generate_image(model: str, prompt: str, aspect_ratio: str | None = None,
                   resolution: str | None = None, input_images: list[str] | None = None,
                   session_id: str | None = None) -> tuple[list[tuple[bytes, str]], float | None]:
    """Returns ([(image_bytes, media_type), ...], cost_usd)."""
    body: dict[str, Any] = {"model": model, "prompt": prompt}
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution
    if input_images:
        body["input_references"] = [{"type": "image_url", "image_url": {"url": u}} for u in input_images]
    if session_id:
        body["session_id"] = session_id

    resp = httpx.post(f"{OPENROUTER_BASE}/images", headers=_headers(), json=body, timeout=IMAGE_TIMEOUT)
    _raise_for_response(resp)
    data = resp.json()
    images = [
        (base64.b64decode(item["b64_json"]), item.get("media_type") or "image/png")
        for item in data.get("data", []) if item.get("b64_json")
    ]
    if not images:
        raise OpenRouterError("Image model returned no images")
    return images, (data.get("usage") or {}).get("cost")


# ── Video ───────────────────────────────────────────────────────────

def submit_video(model: str, prompt: str, duration: int | None = None,
                 aspect_ratio: str | None = None, resolution: str | None = None,
                 first_frame: str | None = None, generate_audio: bool | None = None,
                 session_id: str | None = None) -> dict:
    """Start a video job. Returns {"id", "polling_url", "status"}."""
    body: dict[str, Any] = {"model": model, "prompt": prompt}
    if duration:
        body["duration"] = duration
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution
    if first_frame:
        body["frame_images"] = [{"type": "image_url", "image_url": {"url": first_frame},
                                 "frame_type": "first_frame"}]
    if generate_audio is not None:
        body["generate_audio"] = generate_audio
    if session_id:
        body["session_id"] = session_id

    resp = httpx.post(f"{OPENROUTER_BASE}/videos", headers=_headers(), json=body, timeout=IMAGE_TIMEOUT)
    _raise_for_response(resp)
    return resp.json()


def get_video(job_id: str) -> dict:
    """Status: pending | in_progress | completed | failed | cancelled | expired."""
    return _get(f"/videos/{job_id}")


def download_video(job_id: str, dest: Path, index: int = 0) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", f"{OPENROUTER_BASE}/videos/{job_id}/content", headers=_headers(),
                      params={"index": index}, timeout=IMAGE_TIMEOUT, follow_redirects=True) as resp:
        if resp.status_code >= 400:
            resp.read()
            _raise_for_response(resp)
        with open(tmp, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)
