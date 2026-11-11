"""
Credit estimates from Pollo itself: every generation endpoint has an
".../estimate" twin (docs.pollo.ai/openapi.json, 2026-10-18) that takes the
same body as the generation request and returns its price without starting
a task. The Generate page asks while the form
changes, so answers are cached; the media URLs are placeholders (prices
depend on the settings, not on which image goes in), so nothing is
uploaded for an estimate. Checked 2026-10-18: they don't cost credits.
"""

import json
import logging
from typing import Any

import requests

from web.core.cache import MISS, TTLCache
from web.core.cloudflare import is_cloudflare_block

log = logging.getLogger(__name__)

# Stand-ins for the request's media: what's priced is that there is an
# image, end frame or reference, not what it shows (Pollo accepts these,
# checked 2026-10-18). Not for an extend's source video: Pollo reads its
# length to price it ("Failed to fetch video duration" otherwise).
PLACEHOLDERS = {
    "image": "https://example.com/estimate.png",
    "video": "https://example.com/estimate.mp4",
    "audio": "https://example.com/estimate.mp3",
}
CACHE_SECONDS = 600
TIMEOUT = 15

# A refusal is cached too (it won't change while the form does), so a cached
# None is a real answer — hence MISS to tell it from a miss.
_cache = TTLCache(CACHE_SECONDS, maxsize=1024)


def estimate(generator) -> dict | None:
    """{"credits": what it would cost, "full_credits": before any discount}
    for the generator's request, or None if Pollo can't say (no estimate
    endpoint for it, an error, or not reachable)."""
    url = getattr(generator, "estimate_url", None)
    if not url:
        return None
    payload = generator.get_payload()
    key = json.dumps([url, payload], sort_keys=True)
    hit = _cache.get(key, MISS)
    if hit is not MISS:
        return hit
    try:
        result, cacheable = _ask(url, payload, generator.api_key)
    except requests.RequestException:
        return None  # not reachable: ask again next time
    if cacheable:
        _cache.put(key, result)
    return result


def clear_cache() -> None:
    _cache.clear()


def _ask(url: str, payload: dict, api_key: str | None) -> tuple[dict | None, bool]:
    """(the estimate or None, whether the answer can be cached — a refusal
    can, a server hiccup or a Cloudflare block can't)."""
    headers = {"x-api-key": api_key or "", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    if is_cloudflare_block(resp) or resp.status_code >= 500:
        return None, False
    if resp.status_code != 200:
        log.warning("estimate %s answered HTTP %s: %s", url, resp.status_code, resp.text[:200])
        return None, True
    try:
        body = resp.json()
    except ValueError:
        return None, False
    return _credits(body.get("data", body) if isinstance(body, dict) else None), True


def _credits(data: Any) -> dict | None:
    """The price out of an estimate answer: `cost`, or `discountCost` when
    the account gets a discount. `totalCost` is accepted as an older spelling
    of the undiscounted price."""
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
