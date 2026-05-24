"""Cloudflare challenge/block detection utilities."""
import requests

# Markers found in Cloudflare challenge pages
_CF_MARKERS = ("just a moment", "cloudflare", "cf-browser-verification", "challenge-platform")


def is_cloudflare_block(response: requests.Response) -> bool:
    """Detect if a response is a Cloudflare challenge/block page."""
    if response.status_code not in (403, 503):
        return False
    body = (response.text or "").lower()
    return any(marker in body for marker in _CF_MARKERS)

