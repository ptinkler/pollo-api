"""
Credit estimates from Pollo itself: every v1 endpoint has an ".../estimate"
twin and most legacy ones a ".../validate" twin (docs.pollo.ai/openapi.json,
2026-10-18) that take the same body as the generation request and return
its price without starting a task. The Generate page asks while the form
changes, so answers are cached; the media URLs are placeholders (prices
depend on the settings, not on which image or video goes in), so nothing
is uploaded for an estimate.
"""

import json
import threading
import time
from typing import Any

import requests

from img2vid.common.cloudflare import is_cloudflare_block

# Stand-ins for the request's media: what's priced is that there is an
# image, end frame, reference or source video, not what it shows
PLACEHOLDERS = {
    "image": "https://example.com/estimate.png",
    "video": "https://example.com/estimate.mp4",
    "audio": "https://example.com/estimate.mp3",
}
CACHE_SECONDS = 600
TIMEOUT = 15

_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()


def estimate(generator) -> dict | None:
    """{"credits": what it would cost, "full_credits": before any discount}
    for the generator's request, or None if Pollo can't say (no estimate
    endpoint for it, an error, or not reachable)."""
    url = getattr(generator, "estimate_url", None)
    if not url:
        return None
    payload = generator.get_payload()
    key = json.dumps([url, payload], sort_keys=True)
    with _lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        result, cacheable = _ask(url, payload, generator.api_key)
    except requests.RequestException:
        return None  # not reachable: ask again next time
    if cacheable:
        with _lock:
            _cache[key] = (time.monotonic(), result)
    return result


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _ask(url: str, payload: dict, api_key: str | None) -> tuple[dict | None, bool]:
    """(the estimate or None, whether the answer can be cached — a refusal
    can, a server hiccup or a Cloudflare block can't)."""
    headers = {"x-api-key": api_key or "", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    if is_cloudflare_block(resp) or resp.status_code >= 500:
        return None, False
    if resp.status_code != 200:
        print(f"[Estimate] {url} answered HTTP {resp.status_code}: {resp.text[:200]}")
        return None, True
    try:
        body = resp.json()
    except ValueError:
        return None, False
    return _credits(body.get("data", body) if isinstance(body, dict) else None), True


def _credits(data: Any) -> dict | None:
    """The price from an estimate (v1: cost/discountCost) or validate
    (legacy: cost/totalCost) answer."""
    if not isinstance(data, dict):
        return None
    full = _number(data.get("totalCost")) if data.get("totalCost") is not None else _number(data.get("cost"))
    discounted = _number(data.get("discountCost"))
    if full is None and discounted is None:
        return None
    credits = discounted if discounted is not None else full
    return {"credits": credits, "full_credits": full if full is not None else credits}


def _number(value: Any) -> int | float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return int(n) if n.is_integer() else round(n, 2)
