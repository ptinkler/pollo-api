"""
Venice (https://venice.ai) text, image and video models for chat mode.

Listed in the chat's catalogues as "venice/<model id>" and billed to the
Venice account (VENICE_API_KEY), alongside OpenRouter's and Pollo's models.

  • text   — POST /chat/completions (OpenAI-compatible, streamed; tools on
             models that support function calling)
  • image  — POST /image/generate, or /image/multi-edit when reference images
             are sent. Venice splits these into separate models
             ("seedream-v5-pro" / "seedream-v5-pro-edit"); one catalogue entry
             covers both and the right one is picked per request.
  • video  — POST /video/queue, then /video/retrieve until the MP4 comes back.
             Text-to-video and image-to-video are separate models too
             ("…-text-to-video…" / "…-image-to-video…"), paired the same way.

Safe mode is always off (Venice blurs adult content otherwise), and Venice's
own system prompt is never added to chats.

Video job ids are "venice:<model>:<queue_id>" — retrieve needs the model.
"""

import base64
import contextlib
import json
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from . import sse
from .openrouter import CHAT_TIMEOUT, IMAGE_TIMEOUT, OpenRouterError, _keepalive_socket_options

VENICE_BASE = os.getenv("VENICE_BASE_URL", "https://api.venice.ai/api/v1").rstrip("/")
PREFIX = "venice/"
JOB_PREFIX = "venice:"
CATALOGUE_TTL = 30 * 60
DEFAULT_TIMEOUT = httpx.Timeout(30)
# Video model families, by what they need from the chat (see _video_family)
VIDEO_FAMILIES = {
    "standard": "text → video, or animate an image",
    "reference": "reference images (characters, pins, attached images) → video",
    "frames": "first frame + last frame → video",
    "angles": "image → video with a camera move around the subject",
    "video": "the chat's latest video → a new video",
    "motion": "the chat's latest video's motion + an image → video",
    "upscale": "upscale the chat's latest video",
}
FAMILY_LABELS = {
    "reference": "refs→video",
    "frames": "first+last frame",
    "angles": "multi-angle",
    "video": "video→video",
    "motion": "motion control",
    "upscale": "upscale",
}
# Multi-angle models need a camera path; chat uses a slow quarter orbit
DEFAULT_CAMERA_TRAJECTORY = [
    {"time": 0, "azimuth": 0, "elevation": 0, "distance": 1},
    {"time": 1, "azimuth": 90, "elevation": 10, "distance": 1},
]

_client = httpx.Client(transport=httpx.HTTPTransport(socket_options=_keepalive_socket_options()))
_catalogue: dict[str, Any] = {"at": 0.0, "data": None}
_catalogue_lock = threading.Lock()
_balance: dict[str, Any] = {"usd": None}  # from the x-venice-balance-usd header on each call
_video_quotes: dict[str, float] = {}  # job id → quoted USD, recorded as its cost when done
_download_urls: dict[str, str] = {}  # job id → download link (private models)
_VIDEO_DIR = Path(tempfile.gettempdir()) / "venice-videos"
QUOTE_TTL = 24 * 3600
QUOTE_SECONDS = 5  # videos are priced (for sorting) at ~5s, lowest resolution
_quotes: dict[
    tuple, tuple[float, float | None]
] = {}  # (model, duration, resolution) → (when, USD)   # finished videos between retrieve and download


class VeniceError(OpenRouterError):
    """A Venice failure. Subclasses OpenRouterError so chat handles it the same way."""


def get_api_key() -> str:
    return os.getenv("VENICE_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(get_api_key())


def is_venice(model_id: str | None) -> bool:
    return bool(model_id and model_id.startswith(PREFIX))


def is_venice_job(job_id: str | None) -> bool:
    return bool(job_id and job_id.startswith(JOB_PREFIX))


def _headers() -> dict[str, str]:
    key = get_api_key()
    if not key:
        raise VeniceError("VENICE_API_KEY is not set on the server", 503)
    return {"Authorization": f"Bearer {key}"}


def _note_balance(resp: httpx.Response) -> None:
    value = resp.headers.get("x-venice-balance-usd")
    if value:
        with contextlib.suppress(ValueError):
            _balance["usd"] = float(value)


def _raise_for_response(resp: httpx.Response) -> None:
    _note_balance(resp)
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
        err = body.get("error") or body.get("message") or body
        message = err.get("message") if isinstance(err, dict) else str(err)
        details = body.get("details") if isinstance(body, dict) else None
        if details and isinstance(details, (dict, list)):
            message = f"{message}: {json.dumps(details)[:300]}"
    except (ValueError, AttributeError):
        message = resp.text[:500]
    raise VeniceError(f"Venice: {message or f'HTTP {resp.status_code}'}", resp.status_code)


def _request(method: str, path: str, *, timeout=DEFAULT_TIMEOUT, waiting_for: str = "response", **kw) -> httpx.Response:
    start = time.monotonic()
    try:
        resp = _client.request(method, f"{VENICE_BASE}{path}", headers=_headers(), timeout=timeout, **kw)
    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError, httpx.ConnectError) as e:
        raise VeniceError(
            f"The connection to Venice dropped after {round(time.monotonic() - start)}s waiting "
            f"for the {waiting_for} ({type(e).__name__}). It may still have been billed."
        ) from e
    except httpx.TimeoutException as e:
        raise VeniceError(f"Venice didn't answer in time ({type(e).__name__})", 504) from e
    _raise_for_response(resp)
    return resp


def _data_url(path: Path) -> str:
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode()}"


# ── Catalogue ───────────────────────────────────────────────────────


def _fetch_models(kind: str) -> list[dict]:
    return [
        m
        for m in _request("GET", "/models", params={"type": kind}).json().get("data", [])
        if not (m.get("model_spec") or {}).get("offline")
    ]


def _usd(price) -> float | None:
    if isinstance(price, dict):
        price = price.get("usd")
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return None


def _seconds(values) -> list[int]:
    out = []
    for v in values or []:
        with contextlib.suppress(ValueError):  # "auto", "1 gen" — not a length chat can ask for
            out.append(int(str(v).lower().rstrip("s")))
    return sorted(set(out))


def _uncensored(*models: dict | None) -> bool | None:
    """Venice's own "uncensored" flag on a model (on any of a pair)."""
    return any((m.get("model_spec") or {}).get("uncensored") for m in models if m) or None


def _privacy(*models: dict | None) -> str | None:
    """Venice's privacy level: "private" (Venice's own servers, nothing kept)
    or "anonymized" (a third-party provider, sent without your identity).
    A pair is only as private as its less private half."""
    levels = {(m.get("model_spec") or {}).get("privacy") for m in models if m} - {None}
    return "anonymized" if "anonymized" in levels else ("private" if levels else None)


def _edit_model_for(image_id: str, edit_ids: set[str]) -> str | None:
    """Venice's edit twin of an image model: "x" → "x-edit", or with "-image"
    dropped ("grok-imagine-image-quality" → "grok-imagine-quality-edit")."""
    for candidate in (f"{image_id}-edit", image_id.replace("-image", "", 1) + "-edit"):
        if candidate in edit_ids:
            return candidate
    return None


def _build_catalogue() -> dict[str, Any]:
    text = []
    for m in _fetch_models("text"):
        spec = m.get("model_spec") or {}
        caps = spec.get("capabilities") or {}
        pricing = spec.get("pricing") or {}
        prompt_price, completion_price = _usd(pricing.get("input")), _usd(pricing.get("output"))
        text.append(
            {
                "id": PREFIX + m["id"],
                "name": f"Venice: {spec.get('name') or m['id']}",
                "context_length": spec.get("availableContextTokens") or m.get("context_length"),
                "input_modalities": ["text", "image"] if caps.get("supportsVision") else ["text"],
                "supports_tools": bool(caps.get("supportsFunctionCalling")),
                "uncensored": _uncensored(m),
                "privacy": _privacy(m),
                # Venice prices per million tokens; the picker expects per token
                "prompt_price": prompt_price / 1e6 if prompt_price is not None else None,
                "completion_price": completion_price / 1e6 if completion_price is not None else None,
                "created": m.get("created"),
            }
        )

    edits = {m["id"]: m for m in _fetch_models("inpaint")}
    image, paired = [], set()
    for m in _fetch_models("image"):
        spec = m.get("model_spec") or {}
        c = spec.get("constraints") or {}
        edit_id = _edit_model_for(m["id"], set(edits))
        if edit_id:
            paired.add(edit_id)
        image.append(
            {
                "id": PREFIX + m["id"],
                "name": f"Venice: {spec.get('name') or m['id']}",
                "input_modalities": ["text", "image"] if edit_id else ["text"],
                "uncensored": _uncensored(m, edits.get(edit_id)),
                "privacy": _privacy(m, edits.get(edit_id)),
                "aspect_ratios": c.get("aspectRatios"),
                "resolutions": c.get("resolutions"),
                "created": m.get("created"),
                "conversational": False,
                "_generate": m["id"],
                "_edit": edit_id,
                "_max_refs": ((edits[edit_id].get("model_spec") or {}).get("constraints") or {}).get("maxInputImages")
                if edit_id
                else None,
                "price": _price_tag(
                    _image_price(spec.get("pricing") or {}, "generation", None, c.get("defaultResolution")),
                    c.get("defaultResolution"),
                ),
                "_pricing": ("generation", spec.get("pricing") or {}, c.get("defaultResolution")),
                "_edit_pricing": (
                    "inpaint",
                    (edits[edit_id].get("model_spec") or {}).get("pricing") or {},
                    ((edits[edit_id].get("model_spec") or {}).get("constraints") or {}).get("defaultResolution"),
                )
                if edit_id
                else None,
            }
        )
    # Edit models with no text-to-image twin: they only work on a reference image
    for edit_id, m in edits.items():
        if edit_id in paired:
            continue
        spec = m.get("model_spec") or {}
        c = spec.get("constraints") or {}
        image.append(
            {
                "id": PREFIX + edit_id,
                "name": f"Venice: {spec.get('name') or edit_id} (edit only)",
                "input_modalities": ["text", "image"],
                "uncensored": _uncensored(m),
                "privacy": _privacy(m),
                "aspect_ratios": c.get("aspectRatios"),
                "resolutions": c.get("resolutions"),
                "created": m.get("created"),
                "conversational": False,
                "_generate": None,
                "_edit": edit_id,
                "_max_refs": c.get("maxInputImages"),
                "price": _price_tag(
                    _image_price(spec.get("pricing") or {}, "inpaint", None, c.get("defaultResolution")),
                    c.get("defaultResolution"),
                ),
                "_pricing": None,
                "_edit_pricing": ("inpaint", spec.get("pricing") or {}, c.get("defaultResolution")),
            }
        )

    # Plain models: pair "…-text-to-video…" with "…-image-to-video…" under
    # one entry. Every other family is listed as it is.
    groups: dict[str, dict[str, dict]] = {}
    video = []
    for m in _fetch_models("video"):
        family = _video_family(m)
        if family == "standard":
            mtype = ((m.get("model_spec") or {}).get("constraints") or {}).get("model_type")
            key = m["id"].replace("text-to-video", "*").replace("image-to-video", "*")
            groups.setdefault(key, {})[mtype] = m
        else:
            video.append(_video_entry(family, m, None))
    for pair in groups.values():
        t2v, i2v = pair.get("text-to-video"), pair.get("image-to-video")
        video.append(_video_entry("standard", t2v, i2v))
    _price_videos(video)
    for m in text:
        m["price"] = (
            _price_tag(m["completion_price"] * 1e6, "per 1M output tokens")
            if m.get("completion_price") is not None
            else None
        )
    return {"text": _by_price(text), "image": _by_price(image), "video": _by_price(video)}


def _by_price(models: list[dict]) -> list[dict]:
    """Uncensored first (as the user asked), then cheapest first; unpriced last."""

    def key(m):
        usd = (m.get("price") or {}).get("usd")
        return (not m.get("uncensored"), usd is None, usd or 0, m["name"].lower())

    return sorted(models, key=key)


def _price_tag(usd: float | None, basis: str | None = None) -> dict | None:
    return {"usd": round(usd, 4), "basis": basis or ""} if usd is not None else None


def _image_price(pricing: dict, key: str, resolution: str | None, default_res: str | None) -> float | None:
    """One image's USD price: the resolution's tier if priced that way, else the flat price."""
    tiers = pricing.get("resolutions") or {}
    for res in (resolution, None, default_res):
        if res is None:
            flat = _usd(pricing.get(key))
            if flat is not None:
                return flat
        elif res in tiers and _usd(tiers[res]) is not None:
            return _usd(tiers[res])
    prices = [p for p in (_usd(v) for v in tiers.values()) if p is not None]
    return min(prices) if prices else None


def _res_rank(res: str) -> int:
    """Rough vertical pixels, to find a model's lowest resolution ("480p", "768P", "2K", "4k")."""
    s = str(res).lower()
    if m := re.match(r"(\d+)p", s):
        return int(m.group(1))
    return {"1k": 1080, "2k": 1440, "4k": 2160}.get(s, 10_000)


def _price_videos(video: list[dict]) -> None:
    """Set each video entry's price from Venice's (free) quote endpoint, at
    ~5s and its lowest resolution. Quotes are cached for a day; models that
    work on a chat video (length unknown up front) stay unpriced."""
    jobs = []
    for m in video:
        if m["video_input"]:
            m["price"] = None
            continue
        model = m["_text"] or m["_image"]
        c = m["_constraints"]["text" if m["_text"] else "image"]
        seconds = _seconds(c.get("durations"))
        duration = min(seconds, key=lambda d: (abs(d - QUOTE_SECONDS), d)) if seconds else None
        res = min(c.get("resolutions") or [], key=_res_rank, default=None)
        jobs.append((m, model, duration, res))

    def quote(job):
        _, model, duration, res = job
        key = (model, duration, res)
        cached = _quotes.get(key)
        if cached and time.time() - cached[0] < QUOTE_TTL:
            return cached[1]
        body = {"model": model, "duration": f"{duration}s" if duration else "auto"}
        if res:
            body["resolution"] = res
        try:
            usd = _usd(_request("POST", "/video/quote", json=body).json().get("quote"))
        except VeniceError:
            usd = None
        _quotes[key] = (time.time(), usd)
        return usd

    with ThreadPoolExecutor(max_workers=8) as pool:
        for (m, _, duration, res), usd in zip(jobs, pool.map(quote, jobs), strict=False):
            basis = " · ".join(x for x in (f"{duration}s" if duration else "", res or "") if x)
            m["price"] = _price_tag(usd, basis)


def _video_family(m: dict) -> str:
    mid = m["id"]
    mtype = ((m.get("model_spec") or {}).get("constraints") or {}).get("model_type")
    if "reference-to-video" in mid:
        return "reference"
    if "first-last-frame" in mid or "transition" in mid:
        return "frames"
    if "multi-angle" in mid:
        return "angles"
    if "upscale" in mid:
        return "upscale"
    if "motion-control" in mid:
        return "motion"
    if mtype == "video":
        return "video"
    return "standard"


def _video_entry(family: str, main: dict | None, i2v: dict | None) -> dict:
    """One catalogue entry. For "standard", main is the text-to-video model
    (None if there's only an image-to-video one) and i2v its twin."""
    first = main or i2v
    spec = first.get("model_spec") or {}
    c = spec.get("constraints") or {}
    name = f"Venice: {spec.get('name') or first['id']}"
    if family == "standard" and not main:
        name += " (image→video only)"
    elif family != "standard":
        name += f" ({FAMILY_LABELS[family]})"
    frames = {
        "standard": ["first_frame"] if i2v else [],
        "frames": ["first_frame", "last_frame"],
        "angles": ["first_frame"],
        "motion": ["first_frame"],
    }.get(family, [])
    return {
        "id": PREFIX + first["id"],
        "name": name,
        "family": family,
        "family_hint": VIDEO_FAMILIES[family],
        "durations": _seconds(c.get("durations")) or None,
        "resolutions": c.get("resolutions") or None,
        "aspect_ratios": c.get("aspect_ratios") or None,
        "frame_images": frames,
        "reference_images": family == "reference",
        "video_input": family in ("video", "motion", "upscale"),
        "uncensored": _uncensored(main, i2v),
        "privacy": _privacy(main, i2v),
        "generate_audio": bool(c.get("audio_configurable")),
        "created": first.get("created"),
        "_text": main["id"] if main and family == "standard" else None,
        "_image": i2v["id"] if i2v else (None if family == "standard" else first["id"]),
        "_constraints": {
            k: (v.get("model_spec") or {}).get("constraints") or {} for k, v in (("text", main), ("image", i2v)) if v
        }
        if family == "standard"
        else {"image": c},
    }


def _get_catalogue(refresh: bool = False) -> dict[str, Any]:
    with _catalogue_lock:
        if refresh or not _catalogue["data"] or time.time() - _catalogue["at"] > CATALOGUE_TTL:
            _catalogue.update(at=time.time(), data=_build_catalogue())
        return _catalogue["data"]


def _public(models: list[dict]) -> list[dict]:
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in models]


def list_models(kind: str, refresh: bool = False) -> list[dict[str, Any]]:
    """Venice's models of one kind (text | image | video), shaped like openrouter.list_*_models()."""
    if not is_configured():
        return []
    return _public(_get_catalogue(refresh)[kind])


def _entry(kind: str, model_id: str) -> dict:
    entry = next((m for m in _get_catalogue()[kind] if m["id"] == model_id), None)
    if not entry:
        raise VeniceError(f"Unknown Venice {kind} model: {model_id[len(PREFIX) :]}")
    return entry


def model_info(kind: str, model_id: str) -> dict[str, Any]:
    """One model's public catalogue entry (raises VeniceError if unknown)."""
    return _public([_entry(kind, model_id)])[0]


def get_balance() -> float | None:
    """The account's USD balance: the billing endpoint if this key may read
    it, else the balance Venice reported on the latest call."""
    try:
        data = _request("GET", "/billing/balance").json()
        usd = (data.get("balances") or {}).get("usd")
        if usd is not None:
            _balance["usd"] = float(usd)
    except VeniceError:
        if _balance["usd"] is None:
            with contextlib.suppress(VeniceError):
                _request("GET", "/api_keys/rate_limits")  # every response carries the balance header
    return _balance["usd"]


# ── Text ────────────────────────────────────────────────────────────


def stream_chat(
    model_id: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    session_id: str | None = None,
    max_seconds: float | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[dict]:
    """Like openrouter.stream_chat: yields chat.completion.chunk dicts, with
    usage.cost in USD (from Venice's cost, or tokens × the model's prices)."""
    body: dict[str, Any] = {
        "model": model_id[len(PREFIX) :],
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "venice_parameters": {"include_venice_system_prompt": False},
    }
    if tools:
        body["tools"] = tools
    start = time.monotonic()
    try:
        with _client.stream(
            "POST", f"{VENICE_BASE}/chat/completions", headers=_headers(), json=body, timeout=CHAT_TIMEOUT
        ) as resp:
            if resp.status_code >= 400:
                resp.read()
            _raise_for_response(resp)
            for chunk in sse.chat_chunks(resp.iter_lines(), _stream_error, max_seconds, should_stop):
                usage = chunk.get("usage")
                if usage:
                    chunk["usage"] = {**usage, "cost": _chat_cost(model_id, usage, chunk.get("cost"))}
                yield chunk
    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError) as e:
        raise VeniceError(
            f"The connection to Venice dropped after {round(time.monotonic() - start)}s ({type(e).__name__})"
        ) from e


def _stream_error(message: str, status: int | None) -> VeniceError:
    """A stream failure: the time cap as it is, an error chunk labelled as Venice's."""
    return VeniceError(message if status else f"Venice: {message}", status)


def _chat_cost(model_id: str, usage: dict, top_level_cost=None) -> float | None:
    cost = _usd(usage.get("cost")) if usage.get("cost") is not None else _usd(top_level_cost)
    if cost is not None:
        return cost
    try:
        info = _entry("text", model_id)
    except VeniceError:
        return None
    if info.get("prompt_price") is None or info.get("completion_price") is None:
        return None
    return round(
        (usage.get("prompt_tokens") or 0) * info["prompt_price"]
        + (usage.get("completion_tokens") or 0) * info["completion_price"],
        6,
    )


# ── Image ───────────────────────────────────────────────────────────


def _check_violation(resp: httpx.Response) -> None:
    """Venice flags images that break its terms (x-venice-is-content-violation);
    what comes back then isn't the picture asked for."""
    if (resp.headers.get("x-venice-is-content-violation") or "").lower() == "true":
        raise VeniceError(
            "Blocked by Venice's content filter (it flagged the image as a content violation)", status=403
        )


def generate_image(
    model_id: str,
    prompt: str,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    ref_paths: list[Path] | None = None,
) -> tuple[list[tuple[bytes, str]], float | None, dict]:
    """Returns ([(bytes, media type)], cost in USD (from the catalogue's price),
    the settings actually sent). With reference images it runs the model's
    edit twin; without, the text-to-image model."""
    info = _entry("image", model_id)
    aspect_ratio = _snap(aspect_ratio, info.get("aspect_ratios") or [])
    resolution = _snap(resolution, info.get("resolutions") or [])
    size = {k: v for k, v in (("aspect_ratio", aspect_ratio), ("resolution", resolution)) if v}
    sent: dict[str, Any] = {"aspect_ratio": aspect_ratio, "resolution": resolution}
    refs = [p for p in ref_paths or [] if p.is_file()]
    if refs and info["_edit"]:
        refs = refs[: info.get("_max_refs") or 1]
        images, cost = _edit_image(info, prompt, refs, size)
        return images, cost, {**sent, "refs_used": len(refs)}
    if not info["_generate"]:
        raise VeniceError("This Venice model only edits images: attach, pin or reference an image first")
    return *_new_image(info, prompt, size), sent


def _edit_image(info: dict, prompt: str, refs: list[Path], size: dict) -> tuple[list[tuple[bytes, str]], float | None]:
    body = {
        "modelId": info["_edit"],
        "prompt": prompt,
        "safe_mode": False,
        "images": [_data_url(p) for p in refs],
        **size,
    }
    resp = _request("POST", "/image/multi-edit", json=body, timeout=IMAGE_TIMEOUT, waiting_for="image")
    _check_violation(resp)
    media_type = (resp.headers.get("content-type") or "image/png").split(";")[0].strip()
    if not media_type.startswith("image/"):
        raise VeniceError("Venice returned no image")
    key, pricing, default_res = info["_edit_pricing"]
    return [(resp.content, media_type)], _image_price(pricing, key, size.get("resolution"), default_res)


def _new_image(info: dict, prompt: str, size: dict) -> tuple[list[tuple[bytes, str]], float | None]:
    body = {
        "model": info["_generate"],
        "prompt": prompt,
        "safe_mode": False,
        "hide_watermark": True,
        "format": "png",
        **size,
    }
    resp = _request("POST", "/image/generate", json=body, timeout=IMAGE_TIMEOUT, waiting_for="image")
    _check_violation(resp)
    images = [(base64.b64decode(b64), "image/png") for b64 in resp.json().get("images") or [] if b64]
    if not images:
        raise VeniceError("Venice returned no image")
    key, pricing, default_res = info["_pricing"]
    return images, _image_price(pricing, key, size.get("resolution"), default_res)


# ── Video ───────────────────────────────────────────────────────────

MAX_VIDEO_REFS = 30
QUOTED_FIELDS = ("model", "duration", "aspect_ratio", "resolution", "audio", "upscale_factor")


def _snap(value, allowed: list):
    """value if allowed (or nothing is known), else None."""
    return value if value and (not allowed or value in allowed) else None


def submit_video(
    model_id: str,
    prompt: str,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    generate_audio: bool | None = None,
    first_frame: Path | None = None,
    last_frame: Path | None = None,
    refs: list[Path] | None = None,
    source_video: Path | None = None,
) -> dict:
    """Queue a video. Returns {"id": "venice:<model>:<queue_id>", "params":
    the settings actually sent}, like openrouter.submit_video.

    What's used depends on the model's family: reference models take `refs`
    (the first frame joins them if there are none), first/last-frame models
    both frames, video models `source_video` (motion control also an image)."""
    info = _entry("video", model_id)
    family = info.get("family", "standard")
    model, c = _video_model(info, family, first_frame)
    frames = _VideoFrames(first_frame, last_frame, [p for p in refs or [] if p.is_file()], source_video)
    inputs, sent, image_used = _VIDEO_INPUTS.get(family, _standard_inputs)(frames)
    body: dict[str, Any] = {"model": model, "prompt": prompt, **inputs}
    if family == "angles":
        body["camera_trajectory"] = DEFAULT_CAMERA_TRAJECTORY

    duration, body["duration"] = _video_duration(c, duration)
    resolution = _video_resolution(body, family, c, resolution)
    aspect_ratio = _snap(aspect_ratio, c.get("aspect_ratios") or [])
    if image_used and not c.get("aspect_ratios"):
        aspect_ratio = None  # the image sets the shape
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if c.get("audio_configurable") and generate_audio is not None:
        body["audio"] = bool(generate_audio)

    quote = _video_quote(body)
    data = _request("POST", "/video/queue", json=body, timeout=IMAGE_TIMEOUT, waiting_for="video job to start").json()
    if not data.get("queue_id"):
        raise VeniceError("Venice didn't return a job id")
    job_id = f"{JOB_PREFIX}{model}:{data['queue_id']}"
    if data.get("download_url"):
        _download_urls[job_id] = data["download_url"]
    if quote is not None:
        _video_quotes[job_id] = quote
    audio = body.get("audio", bool(c.get("audio")) or None)
    return {
        "id": job_id,
        "params": {
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "generate_audio": audio,
            **sent,
        },
    }


def _video_model(info: dict, family: str, first_frame: Path | None) -> tuple[str, dict]:
    """(the Venice model to run, its constraints): standard families pair a
    text-to-video model with an image-to-video one; the rest have one model."""
    if family != "standard":
        return info["_image"], info["_constraints"]["image"]
    model = info["_image"] if first_frame else info["_text"]
    if not model:
        raise VeniceError(
            "This Venice model needs an image to animate"
            if not first_frame
            else "This Venice model can't animate an image — pick an image→video model"
        )
    return model, info["_constraints"]["image" if first_frame else "text"]


class _VideoFrames:
    def __init__(self, first: Path | None, last: Path | None, refs: list[Path], source_video: Path | None):
        self.first, self.last, self.refs, self.source_video = first, last, refs, source_video


# Each family's inputs: (body fields, settings to report, whether an image sets the shape)
VideoInputs = tuple[dict[str, Any], dict[str, Any], bool]


def _reference_inputs(f: _VideoFrames) -> VideoInputs:
    refs = (f.refs or ([f.first] if f.first else []))[:MAX_VIDEO_REFS]
    if not refs:
        raise VeniceError(
            "This Venice model makes a video from reference images: attach a character, "
            "pin an image or attach one first"
        )
    return {"reference_image_urls": [_data_url(p) for p in refs]}, {"refs_used": len(refs)}, False


def _frames_inputs(f: _VideoFrames) -> VideoInputs:
    if not (f.first and f.last):
        raise VeniceError(
            "This Venice model needs a first and a last frame: attach two images "
            "(the first is the start, the second the end)"
        )
    return {"image_url": _data_url(f.first), "end_image_url": _data_url(f.last)}, {}, True


def _source_video_inputs(f: _VideoFrames) -> VideoInputs:
    if not f.source_video or not f.source_video.is_file():
        raise VeniceError(
            "This Venice model works on a video: make or keep a video in this chat first (it uses the latest one)"
        )
    return {"video_url": _data_url(f.source_video)}, {"source_video": f.source_video.name}, False


def _motion_inputs(f: _VideoFrames) -> VideoInputs:
    body, sent, _ = _source_video_inputs(f)
    image = f.first or (f.refs[0] if f.refs else None)
    if not image:
        raise VeniceError("Motion control needs an image of who should move: attach or pin one")
    return {**body, "image_url": _data_url(image)}, sent, True


def _standard_inputs(f: _VideoFrames) -> VideoInputs:
    """Standard image→video and multi-angle: the first frame, if any."""
    return ({"image_url": _data_url(f.first)}, {}, True) if f.first else ({}, {}, False)


_VIDEO_INPUTS = {
    "reference": _reference_inputs,
    "frames": _frames_inputs,
    "video": _source_video_inputs,
    "upscale": _source_video_inputs,
    "motion": _motion_inputs,
}


def _video_duration(c: dict, duration: int | None) -> tuple[int | None, str]:
    """(the duration in seconds, or None, the value to send): snapped to the
    nearest allowed length (5s when unset); else the model's own setting."""
    allowed = c.get("durations") or []
    seconds = _seconds(allowed)
    if not seconds:
        return None, allowed[0] if allowed else "auto"  # e.g. "Auto": follows the source video
    if not duration or duration not in seconds:
        target = duration or 5
        duration = min(seconds, key=lambda d: (abs(d - target), d))
    return duration, f"{duration}s"


def _video_resolution(body: dict, family: str, c: dict, resolution: str | None) -> str | None:
    """Put the resolution (an upscale's factor) on the body; the setting to report."""
    if family == "upscale":
        body["upscale_factor"] = {"2x": 2, "4x": 4}.get(str(resolution).lower()) or 2
        return f"{body['upscale_factor']}x"
    resolution = _snap(resolution, c.get("resolutions") or [])
    if resolution:
        body["resolution"] = resolution
    return resolution


def _video_quote(body: dict) -> float | None:
    """What Venice says the video will cost — nice to show, not needed to generate."""
    try:
        return _usd(
            _request("POST", "/video/quote", json={k: v for k, v in body.items() if k in QUOTED_FIELDS})
            .json()
            .get("quote")
        )
    except VeniceError:
        return None


def _split_job(job_id: str) -> tuple[str, str]:
    model, _, queue_id = job_id[len(JOB_PREFIX) :].rpartition(":")
    return model, queue_id


def _video_file(job_id: str) -> Path:
    return _VIDEO_DIR / f"{_split_job(job_id)[1]}.mp4"


def get_video(job_id: str) -> dict:
    """The job in openrouter.get_video's shape (status completed | failed |
    in_progress, "error", "usage"). Venice hands the finished MP4 straight
    back from retrieve, so it's kept until download_video collects it.
    Network trouble and 5xx raise, for the poller's error budget."""
    if _video_file(job_id).is_file():
        return {"status": "completed", "usage": {"cost": _video_quotes.get(job_id)}}
    model, queue_id = _split_job(job_id)
    start = time.monotonic()
    try:
        with _client.stream(
            "POST",
            f"{VENICE_BASE}/video/retrieve",
            headers=_headers(),
            json={"model": model, "queue_id": queue_id},
            timeout=IMAGE_TIMEOUT,
        ) as resp:
            if resp.status_code >= 500 or resp.status_code == 429:
                resp.read()
                raise VeniceError(f"Venice: HTTP {resp.status_code} while checking the video")
            if resp.status_code >= 400:
                resp.read()
                try:
                    _raise_for_response(resp)
                except VeniceError as e:
                    return {"status": "failed", "error": str(e)}
            if (resp.headers.get("content-type") or "").startswith("video/"):
                _VIDEO_DIR.mkdir(parents=True, exist_ok=True)
                part = _video_file(job_id).with_suffix(".part")
                with open(part, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
                part.replace(_video_file(job_id))
                return {"status": "completed", "usage": {"cost": _video_quotes.get(job_id)}}
            resp.read()
            _note_balance(resp)
            data = resp.json()
    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError, httpx.ConnectError) as e:
        raise VeniceError(
            f"Venice connection dropped after {round(time.monotonic() - start)}s ({type(e).__name__})"
        ) from e
    status = str(data.get("status") or "").upper()
    if status in ("FAILED", "ERROR", "CANCELLED"):
        return {"status": "failed", "error": f"Venice: {data.get('error') or data.get('message') or 'video failed'}"}
    if status == "COMPLETED" and job_id in _download_urls:
        return {"status": "completed", "usage": {"cost": _video_quotes.get(job_id)}}
    return {"status": "in_progress"}


def download_video(job_id: str, dest: Path, index: int = 0) -> None:
    src = _video_file(job_id)
    if not src.is_file():
        url = _download_urls.get(job_id)
        if url:  # private models hand back a short-lived download link instead
            tmp = dest.with_suffix(dest.suffix + ".part")
            with _client.stream("GET", url, timeout=IMAGE_TIMEOUT, follow_redirects=True) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    raise VeniceError(f"Couldn't download the Venice video (HTTP {resp.status_code})")
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
            tmp.replace(dest)
            return
        if get_video(job_id)["status"] != "completed" or not src.is_file():
            raise VeniceError("The Venice video isn't ready")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dest)  # the temp dir may be on another filesystem
