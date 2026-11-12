"""Thin OpenRouter client (https://openrouter.ai/docs) used by the chat mode.

Covers the three surfaces chat needs:
  • text   — POST /chat/completions (SSE streaming, tool calls)
  • image  — POST /images           (streamed SSE, base64 results)
  • video  — POST /videos           (async job: submit → poll → download /content)

Request/response shapes were taken from https://openrouter.ai/openapi.json,
not by probing the live API (probes cost real money).
"""

import base64
import json
import os
import socket
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import httpx

from web import keyctx, net_guard, request_log, sse
from web.types import ChatChunk, JsonValue, VideoJob

# Overridable so a local fake can stand in during manual testing
OPENROUTER_BASE = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
CHAT_TIMEOUT = httpx.Timeout(connect=15, read=300, write=60, pool=15)
IMAGE_TIMEOUT = httpx.Timeout(connect=15, read=600, write=120, pool=15)
DEFAULT_TIMEOUT = httpx.Timeout(30)


class OpenRouterError(Exception):
    """An error returned or raised by an OpenRouter request."""

    def __init__(self, message: str, status: int | None = None) -> None:
        """Carry the message plus the HTTP status, when the call got that far."""
        super().__init__(message)
        self.status = status


def keepalive_socket_options() -> list[tuple[int, int, int]]:
    """Enable TCP keepalive probes every 5 seconds while a request waits.

    Image and video calls can sit silent for a minute or more
    (Seedream 5.0 Pro with references:
    ~2 min), and some networks — VPNs, NAT routers, NAS/Docker hosts — drop
    connections idle that long, surfacing as httpx.RemoteProtocolError
    "Server disconnected without sending a response".

    NB: observed cuts at ~62s on both OpenRouter and Venice through the
    Surfshark/gluetun tunnel suggest the VPN ignores these keepalive ACKs
    (they carry no payload) and times out on idle *data*. If so, tightening
    the interval won't help and the fix is at the VPN layer.
    """
    options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    for name, value in (("TCP_KEEPIDLE", 5), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 8)):
        if hasattr(socket, name):  # Linux names; other platforms keep OS defaults
            options.append((socket.IPPROTO_TCP, getattr(socket, name), value))
    return options


# One shared, thread-safe client so every OpenRouter connection gets keepalive
_client = httpx.Client(transport=httpx.HTTPTransport(socket_options=keepalive_socket_options()))


@contextmanager
def _connection_guard(waiting_for: str) -> Generator[None]:
    """Translate dropped connections into errors that identify the wait duration."""
    start = time.monotonic()
    try:
        yield
    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError) as e:
        waited = round(time.monotonic() - start)
        raise OpenRouterError(  # noqa: TRY003
            f"The connection to OpenRouter dropped after {waited}s waiting for the {waiting_for} "
            f"({type(e).__name__}) — usually a network/VPN closing idle connections. "
            "It may still have been billed: check OpenRouter's activity before retrying."
        ) from e


def get_api_key() -> str:
    """Return the configured OpenRouter API key, or an empty string."""
    return keyctx.provider_key("openrouter") or ""


def is_configured() -> bool:
    """Return whether an OpenRouter API key is configured."""
    return bool(get_api_key())


NAME = "openrouter"


def _json_object(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {}
    return cast("dict[str, JsonValue]", value)


def _json_objects(value: object) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [cast("dict[str, JsonValue]", item) for item in items if isinstance(item, dict)]


def _strings(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _cost(value: JsonValue) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def list_models(kind: str, refresh: bool = False) -> list[dict[str, JsonValue]]:  # noqa: ARG001 — provider interface
    """Uniform provider interface: text/image/video models (empty without a key)."""
    if not is_configured():
        return []
    lister = {"text": list_text_models, "image": list_image_models, "video": list_video_models}.get(kind)
    return lister() if lister else []  # no audio models here


def _headers() -> dict[str, str]:
    key = get_api_key()
    if not key:
        raise OpenRouterError("No OpenRouter API key set — add one in Settings → Keys", 503)  # noqa: TRY003
    return {
        "Authorization": f"Bearer {key}",
        # App attribution (https://openrouter.ai/docs/app-attribution). The URL
        # is deliberately generic — OpenRouter needs one to create the app and
        # accepts localhost with a title — so the app isn't linkable to anyone.
        # Visibility only applies when the app is first created.
        "HTTP-Referer": "http://localhost",
        "X-OpenRouter-Title": "Pollo Chat",
        "X-OpenRouter-App-Visibility": "hidden",
    }


def _raise_for_response(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        body = cast("object", resp.json())
        if not isinstance(body, dict):
            message = resp.text[:500]
        else:
            body_obj = _json_object(cast("object", body))
            err = body_obj.get("error") or {}
            err_obj = _json_object(cast("object", err))
            error_message = err_obj.get("message")
            message = error_message if isinstance(error_message, str) else str(err)
            # Provider errors carry the upstream message in metadata.raw and
            # the upstream's name in metadata.provider_name.
            meta = _json_object(err_obj.get("metadata") or {}) if isinstance(err, dict) else {}
            raw = meta.get("raw")
            if isinstance(raw, str) and raw not in message:
                message = f"{message}: {raw[:300]}"
            provider = meta.get("provider_name")
            if isinstance(provider, str) and provider not in message:
                message = f"[{provider}] {message}"
    except (ValueError, AttributeError):
        message = resp.text[:500]
    raise OpenRouterError(message or f"HTTP {resp.status_code}", resp.status_code)


def _get(path: str, params: dict[str, str] | None = None) -> dict[str, JsonValue]:
    resp = _client.get(f"{OPENROUTER_BASE}{path}", headers=_headers(), params=params, timeout=DEFAULT_TIMEOUT)
    _raise_for_response(resp)
    data = cast("object", resp.json())
    if not isinstance(data, dict):
        raise OpenRouterError("OpenRouter returned an invalid JSON object")  # noqa: TRY003
    return cast("dict[str, JsonValue]", data)


def get_credits() -> dict[str, float]:
    """Return the account's total, used, and remaining credits in dollars.

    This is distinct from GET /key, which reports only this key's spending limit.
    """
    data = _json_object(cast("object", _get("/credits").get("data") or {}))
    total_value, used_value = data.get("total_credits"), data.get("total_usage")
    total = float(total_value) if isinstance(total_value, int | float | str) else 0.0
    used = float(used_value) if isinstance(used_value, int | float | str) else 0.0
    return {"total_credits": total, "total_usage": used, "remaining": round(total - used, 4)}


def list_text_models() -> list[dict[str, JsonValue]]:
    """Return OpenRouter text models and their supported capabilities."""
    data = _json_objects(_get("/models", {"output_modalities": "text"}).get("data", []))
    models: list[dict[str, JsonValue]] = []
    for m in data:
        model_id = m.get("id")
        if not isinstance(model_id, str):
            continue
        arch = _json_object(m.get("architecture") or {})
        pricing = _json_object(m.get("pricing") or {})
        params = _strings(m.get("supported_parameters") or [])
        models.append(
            {
                "id": model_id,
                "name": m.get("name") or model_id,
                "context_length": m.get("context_length"),
                "input_modalities": arch.get("input_modalities") or ["text"],
                "supports_tools": "tools" in params,
                "prompt_price": pricing.get("prompt"),
                "completion_price": pricing.get("completion"),
                "created": m.get("created"),
            }
        )
    return models


def list_image_models() -> list[dict[str, JsonValue]]:
    """Return image API models and chat models that can also produce images.

    Conversational models are marked as such and can receive the whole
    conversation, as the Gemini app does, instead of a lone prompt.
    """
    data = _json_objects(_get("/images/models").get("data", []))
    models: list[dict[str, JsonValue]] = []
    for m in data:
        model_id = m.get("id")
        if not isinstance(model_id, str):
            continue
        arch = _json_object(m.get("architecture") or {})
        params = _json_object(m.get("supported_parameters") or {})
        models.append(
            {
                "id": model_id,
                "name": m.get("name") or model_id,
                "input_modalities": arch.get("input_modalities") or ["text"],
                "aspect_ratios": _json_object(params.get("aspect_ratio") or {}).get("values"),
                "resolutions": _json_object(params.get("resolution") or {}).get("values"),
                "created": m.get("created"),
                "conversational": False,
            }
        )
    by_id = {str(m["id"]): m for m in models}
    for m in _json_objects(_get("/models", {"output_modalities": "image"}).get("data", [])):
        model_id = m.get("id")
        if not isinstance(model_id, str):
            continue
        arch = _json_object(m.get("architecture") or {})
        if not {"text", "image"} <= set(_strings(arch.get("output_modalities") or [])):
            continue
        if model_id.startswith("openrouter/"):
            continue  # general-purpose routers (openrouter/auto), not image models
        if model_id in by_id:
            by_id[model_id]["conversational"] = True
        else:
            models.append(
                {
                    "id": model_id,
                    "name": m.get("name") or model_id,
                    "input_modalities": arch.get("input_modalities") or ["text"],
                    "aspect_ratios": None,
                    "resolutions": None,
                    "created": m.get("created"),
                    "conversational": True,
                }
            )
    return models


def list_video_models() -> list[dict[str, JsonValue]]:
    """Return OpenRouter video models that can generate videos from prompts."""
    data = _json_objects(_get("/videos/models").get("data", []))
    models: list[dict[str, JsonValue]] = []
    for m in data:
        # Upscalers share this catalogue but can't generate from a prompt
        if m.get("upscale_factor") or m.get("creativity"):
            continue
        model_id = m.get("id")
        if not isinstance(model_id, str):
            continue
        models.append(
            {
                "id": model_id,
                "name": m.get("name") or model_id,
                "durations": m.get("supported_durations"),
                "resolutions": m.get("supported_resolutions"),
                "aspect_ratios": m.get("supported_aspect_ratios"),
                "frame_images": m.get("supported_frame_images") or [],
                "generate_audio": m.get("generate_audio"),
                "created": m.get("created"),
            }
        )
    return models


def stream_chat(
    model: str,
    messages: list[dict[str, JsonValue]],
    tools: list[dict[str, JsonValue]] | None = None,
    session_id: str | None = None,
    max_seconds: float | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[ChatChunk]:
    """Yield parsed chat-completion chunks.

    Raises OpenRouterError on pre-stream HTTP errors and on mid-stream error
    chunks.

    OpenRouter sends ": OPENROUTER PROCESSING" keep-alives while a provider
    is slow, and each one resets httpx's read timeout — so a stalled upstream
    would otherwise hang forever. `max_seconds` caps the whole call and
    `should_stop` is polled on every line (keep-alives included), so a
    cancel is noticed within seconds even when no tokens are flowing.
    """
    body: dict[str, JsonValue] = {
        "model": model,
        "messages": messages,
        "stream": True,  # usage (incl. cost) always arrives on the final chunk
    }
    if tools:
        body["tools"] = tools
    if session_id:
        body["session_id"] = session_id

    with (
        request_log.logged("openrouter", "POST", "/chat/completions", body) as outcome,
        _client.stream(
            "POST", f"{OPENROUTER_BASE}/chat/completions", headers=_headers(), json=body, timeout=CHAT_TIMEOUT
        ) as resp,
    ):
        outcome["status"] = resp.status_code
        if resp.status_code >= 400:
            resp.read()
            outcome["response"] = request_log.response_of(resp)
            _raise_for_response(resp)
        chunks = sse.chat_chunks(resp.iter_lines(), OpenRouterError, max_seconds, should_stop)
        yield from request_log.chat_reply(chunks, outcome)


def generate_image(
    model: str,
    prompt: str,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    input_images: list[str] | None = None,
    session_id: str | None = None,
) -> tuple[list[tuple[bytes, str]], float | None]:
    """Generate images and return their bytes, media types, and USD cost."""
    body: dict[str, JsonValue] = {"model": model, "prompt": prompt}
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution
    if input_images:
        body["input_references"] = [{"type": "image_url", "image_url": {"url": u}} for u in input_images]
    if session_id:
        body["session_id"] = session_id

    # Streamed so the connection carries traffic while the image renders:
    # a silent request was cut at exactly 60s by something between us and
    # OpenRouter (TCP keepalive didn't help). Streaming only helps if bytes
    # actually flow before 60s, so we also ask for partial-image frames —
    # without them the stream stays silent until the render is done and a slow
    # model (Seedream ~2 min) is still cut at 60s. Only the final image is kept.
    # OpenRouter rejects streaming for image-to-image (edit) requests, so
    # only stream plain text-to-image — edits come back as plain JSON.
    if not input_images:
        body["stream"] = True
        body["partial_images"] = 2  # keepalive previews; ignored if unsupported
    with (
        request_log.logged("openrouter", "POST", "/images", body) as outcome,
        _connection_guard("image"),
        _client.stream(
            "POST", f"{OPENROUTER_BASE}/images", headers=_headers(), json=body, timeout=IMAGE_TIMEOUT
        ) as resp,
    ):
        outcome["status"] = resp.status_code
        if resp.status_code >= 400:
            resp.read()
            outcome["response"] = request_log.response_of(resp)
            _raise_for_response(resp)
        if "text/event-stream" not in resp.headers.get("content-type", ""):
            resp.read()  # a provider that doesn't stream answers with plain JSON
            outcome["response"] = request_log.response_of(resp)
            return _images_from_json(_json_object(cast("object", resp.json())))
        images, cost = _images_from_stream(resp.iter_lines())
        outcome["response"] = {"images": [t for _, t in images], "cost": cost}
        return images, cost


def _images_from_json(data: dict[str, JsonValue]) -> tuple[list[tuple[bytes, str]], float | None]:
    images: list[tuple[bytes, str]] = []
    for item in _json_objects(data.get("data", [])):
        encoded = item.get("b64_json")
        if not isinstance(encoded, str):
            continue
        media_type = item.get("media_type")
        images.append((base64.b64decode(encoded), media_type if isinstance(media_type, str) else "image/png"))
    if not images:
        raise OpenRouterError("Image model returned no images")  # noqa: TRY003
    usage = _json_object(cast("object", data.get("usage") or {}))
    return images, _cost(usage.get("cost"))


def _images_from_stream(lines: Iterator[str]) -> tuple[list[tuple[bytes, str]], float | None]:
    """Extract completed images from an /images SSE stream, skipping previews and keep-alives."""
    images: list[tuple[bytes, str]] = []
    cost = None
    event = ""
    for line in lines:
        if line.startswith("event:"):
            event = line[6:].strip()
            continue
        if not line.startswith("data:"):
            if not line:
                event = ""
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = _json_object(cast("object", json.loads(payload)))
        except json.JSONDecodeError:
            continue
        image, parsed_cost = _completed_image(chunk, event)
        if image:
            images.append(image)
        if parsed_cost is not None:
            cost = parsed_cost
    if not images:
        raise OpenRouterError("Image model returned no images")  # noqa: TRY003
    return images, cost


def _completed_image(chunk: dict[str, JsonValue], event: str) -> tuple[tuple[bytes, str] | None, float | None]:
    kind = chunk.get("type") or event
    if not isinstance(kind, str):
        kind = event
    err = chunk.get("error")
    if kind == "error" or err:
        detail = err or chunk
        message = _json_object(cast("object", detail)).get("message")
        raise OpenRouterError(message if isinstance(message, str) else str(detail) or "Image generation failed")
    encoded = chunk.get("b64_json")
    if not kind.endswith("completed") or not isinstance(encoded, str):
        return None, None
    media_type = chunk.get("media_type")
    image = (base64.b64decode(encoded), media_type if isinstance(media_type, str) else "image/png")
    usage = _json_object(cast("object", chunk.get("usage") or {}))
    return image, _cost(usage.get("cost"))


def generate_image_chat(
    model: str,
    messages: list[dict[str, JsonValue]],
    aspect_ratio: str | None = None,
    session_id: str | None = None,
) -> tuple[list[tuple[bytes, str]], float | None]:
    """Generate images with a conversational model using chat context.

    Returns image bytes and media types, plus the cost in USD.
    """
    body: dict[str, JsonValue] = {"model": model, "messages": messages, "modalities": ["image", "text"]}
    if aspect_ratio:
        body["image_config"] = {"aspect_ratio": aspect_ratio}
    if session_id:
        body["session_id"] = session_id
    with request_log.logged("openrouter", "POST", "/chat/completions", body) as outcome:
        with _connection_guard("image"):
            resp = _client.post(
                f"{OPENROUTER_BASE}/chat/completions", headers=_headers(), json=body, timeout=IMAGE_TIMEOUT
            )
        outcome["status"] = resp.status_code
        outcome["response"] = request_log.response_of(resp)
        _raise_for_response(resp)
    data = _json_object(cast("object", resp.json()))
    choices = _json_objects(data.get("choices") or [])
    message = _json_object(cast("object", choices[0].get("message") or {})) if choices else {}
    images: list[tuple[bytes, str]] = []
    for part in _json_objects(message.get("images") or []):
        image_url = _json_object(cast("object", part.get("image_url") or {}))
        url_value = image_url.get("url")
        url = url_value if isinstance(url_value, str) else ""
        if url.startswith("data:"):
            header, _, b64 = url.partition(",")
            images.append((base64.b64decode(b64), header[5:].split(";")[0] or "image/png"))
        elif url:
            # Provider-supplied URL — guard against SSRF (loopback/metadata/LAN).
            try:
                r = net_guard.get_public(_client, url, timeout=IMAGE_TIMEOUT)
            except net_guard.UnsafeURLError as exc:
                raise OpenRouterError(f"Refusing to fetch unsafe image URL: {exc}") from exc  # noqa: TRY003
            r.raise_for_status()
            content_type = cast("object", r.headers.get("content-type", "image/png"))
            images.append((r.content, content_type.split(";")[0] if isinstance(content_type, str) else "image/png"))
    if not images:
        # e.g. the model declined — its text says why
        content = message.get("content")
        said = content.strip() if isinstance(content, str) else ""
        raise OpenRouterError("The image model returned no image" + (f": {said[:300]}" if said else ""))
    usage = _json_object(cast("object", data.get("usage") or {}))
    return images, _cost(usage.get("cost"))


def submit_video(
    model: str,
    prompt: str,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    first_frame: str | None = None,
    generate_audio: bool | None = None,
    session_id: str | None = None,
) -> VideoJob:
    """Start a video job. Returns {"id", "polling_url", "status"}."""
    body: dict[str, JsonValue] = {"model": model, "prompt": prompt}
    if duration:
        body["duration"] = duration
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution
    if first_frame:
        body["frame_images"] = [{"type": "image_url", "image_url": {"url": first_frame}, "frame_type": "first_frame"}]
    if generate_audio is not None:
        body["generate_audio"] = generate_audio
    if session_id:
        body["session_id"] = session_id

    with request_log.logged("openrouter", "POST", "/videos", body) as outcome:
        with _connection_guard("video job to start"):
            resp = _client.post(f"{OPENROUTER_BASE}/videos", headers=_headers(), json=body, timeout=IMAGE_TIMEOUT)
        outcome["status"] = resp.status_code
        outcome["response"] = request_log.response_of(resp)
        _raise_for_response(resp)
    result = _json_object(cast("object", resp.json()))
    job_id = result.get("id")
    if not isinstance(job_id, str):
        raise OpenRouterError("OpenRouter returned an invalid video job")  # noqa: TRY003
    return cast("VideoJob", result)


def get_video(job_id: str) -> dict[str, JsonValue]:
    """Status: pending | in_progress | completed | failed | cancelled | expired."""
    return _get(f"/videos/{job_id}")


def download_video(job_id: str, dest: Path, index: int = 0) -> None:
    """Download a completed video job to ``dest``."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _client.stream(
        "GET",
        f"{OPENROUTER_BASE}/videos/{job_id}/content",
        headers=_headers(),
        params={"index": index},
        timeout=IMAGE_TIMEOUT,
        follow_redirects=True,
    ) as resp:
        if resp.status_code >= 400:
            resp.read()
            _raise_for_response(resp)
        with tmp.open("wb") as f:
            f.writelines(resp.iter_bytes())
    tmp.replace(dest)
