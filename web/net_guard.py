"""
SSRF guard for server-side fetches of URLs we don't fully control.

A provider's API response can hand us a URL to download (e.g. an image the
model generated). Before fetching, confirm it's a public http(s) address so a
crafted response can't point the server at loopback, the cloud metadata
endpoint, or the LAN.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class UnsafeURLError(ValueError):
    """The URL is not a fetchable public http(s) address."""


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local  # 169.254/16 incl. cloud metadata 169.254.169.254
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_public_url(url: str) -> None:
    """Raise UnsafeURLError unless *url* is http(s) and every address its host
    resolves to is public."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Cannot resolve host {host!r}: {exc}") from exc
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise UnsafeURLError(f"Host {host!r} resolves to non-public address {ip}")


def get_public(client: httpx.Client, url: str, *, timeout, max_redirects: int = 3) -> httpx.Response:
    """GET *url* with SSRF checks, following redirects manually so each hop's
    target is validated too (httpx's own redirect handling would skip that)."""
    for _ in range(max_redirects + 1):
        assert_public_url(url)
        resp = client.get(url, timeout=timeout, follow_redirects=False)
        if resp.is_redirect and "location" in resp.headers:
            url = str(resp.next_request.url) if resp.next_request else resp.headers["location"]
            continue
        return resp
    raise UnsafeURLError("Too many redirects")
