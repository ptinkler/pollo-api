"""
Public hosting for local source media, for providers that only take a URL
(Pollo): the per-user preference picks the host (litterbox / tmpfiles /
self-host) and retention — see web/upload_settings.py. A primary host is tried
first, then the backup. Self-host serves the file from this instance itself
(web/public_media.py) instead of a third-party temp host.
"""

import logging
import threading
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .public_media import selfhost_url
from .upload_settings import current_upload_prefs

log = logging.getLogger(__name__)

LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
TMPFILES_URL = "https://tmpfiles.org/api/v1/upload"
# Litterbox only offers these fixed retentions; map any requested span to the
# nearest. Keys are minutes.
_LITTERBOX_BUCKETS = {60: "1h", 720: "12h", 1440: "24h", 4320: "72h"}

# A retry (or a second model on the same source media) re-runs the whole submit
# and would otherwise re-upload the same local file — pure wasted bandwidth,
# since the hosted URL is still live. Remember each successful upload keyed by
# (file identity, host, requested span) and reuse it until shortly before it
# expires. In-memory and per-process, so it helps the common case (consecutive
# retries on the same worker) without any shared state; a cold worker just
# re-uploads. Keyed on size+mtime so editing the file forces a fresh upload.
_url_cache: dict[tuple, tuple[str, float]] = {}
_url_cache_lock = threading.Lock()
# Stop handing out a cached URL this long before it truly lapses, so Pollo never
# fetches one that dies mid-job: 10% of the span, capped at 5 minutes.
_CACHE_MARGIN_FRAC = 0.1
_CACHE_MARGIN_MAX_S = 300
_URL_CACHE_MAX = 256  # bound the dict; prune expired first, then oldest


def _cache_key(filepath: Path, host: str, expiry_minutes: int) -> tuple | None:
    """A cache key identifying this exact file content for this host/span, or
    None when the file can't be stat'd (then it just isn't cached)."""
    try:
        st = Path(filepath).stat()
    except OSError:
        return None
    return (str(Path(filepath).resolve()), st.st_size, st.st_mtime_ns, host, expiry_minutes)


def _cached_url(key: tuple | None) -> str | None:
    if key is None:
        return None
    with _url_cache_lock:
        hit = _url_cache.get(key)
        if hit and hit[1] > time.time():
            return hit[0]
        if hit:  # lapsed — drop it
            _url_cache.pop(key, None)
    return None


def _store_url(key: tuple | None, url: str, expiry_minutes: int) -> None:
    if key is None:
        return
    lifetime = max(expiry_minutes, 1) * 60
    good_until = time.time() + lifetime - min(_CACHE_MARGIN_MAX_S, lifetime * _CACHE_MARGIN_FRAC)
    with _url_cache_lock:
        now = time.time()
        for k in [k for k, (_, exp) in _url_cache.items() if exp <= now]:
            _url_cache.pop(k, None)
        if len(_url_cache) >= _URL_CACHE_MAX:  # still full — evict the soonest-to-expire
            _url_cache.pop(min(_url_cache, key=lambda k: _url_cache[k][1]), None)
        _url_cache[key] = (url, good_until)


def upload_file(filepath: Path, prefs: dict | None = None) -> str:
    """Upload any source file to the configured public host and return its URL,
    trying the primary host then the backup. `prefs` defaults to the current
    user's resolved upload preferences (web/upload_settings.py). A still-live
    URL from an earlier upload of the same file+host is reused instead of
    re-uploading (see the cache above)."""
    if prefs is None:
        prefs = current_upload_prefs()
    expiry = prefs.get("expiry_minutes", 60)
    order = [prefs["primary"]]
    if prefs.get("backup") and prefs["backup"] != prefs["primary"]:
        order.append(prefs["backup"])
    errors: list[str] = []
    for host in order:
        key = _cache_key(filepath, host, expiry)
        cached = _cached_url(key)
        if cached:
            log.info("%s: reused still-live URL, no re-upload: %s", host, cached)
            return cached
        try:
            url = _dispatch(host, filepath, prefs)
            _verify_served(host, url, filepath)
            _store_url(key, url, expiry)
            log.info("%s: uploaded %s", host, url)
            return url
        except ValueError as exc:
            log.warning("%s failed (%s), trying the next host", host, exc)
            errors.append(f"{host}: {exc}")
    raise ValueError("All upload hosts failed — " + "; ".join(errors))


# A host can accept the upload and still not serve the file to a plain HTTP
# client — a temp host hands an interstitial page to anything that doesn't look
# like a browser, say. The provider then fetches HTML where a video should be
# and rejects it ("Invalid video_url") *after* charging for the job, so the URL
# is checked here instead, and a host that doesn't serve it falls through to
# the backup. Self-hosting is skipped: this instance can reach itself whatever
# the outside world sees.
_VERIFY_HOSTS = ("litterbox", "tmpfiles")
_VERIFY_TIMEOUT = (8, 15)


def _verify_served(host: str, url: str, filepath: Path) -> None:
    if host not in _VERIFY_HOSTS:
        return
    try:
        resp = requests.get(url, stream=True, timeout=_VERIFY_TIMEOUT, headers={"Range": "bytes=0-0"})
        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        resp.close()
    except requests.RequestException as exc:
        raise ValueError(f"hosted file isn't reachable ({type(exc).__name__})") from exc
    if resp.status_code not in (200, 206):
        raise ValueError(f"hosted file answered HTTP {resp.status_code}")
    # Only an HTML answer is treated as wrong: hosts serve files as all sorts of
    # octet-stream/text types, and rejecting those would break working uploads.
    if content_type in ("text/html", "application/xhtml+xml"):
        raise ValueError(f"hosted file served a web page, not {filepath.suffix.lstrip('.') or 'the file'}")


def _dispatch(host: str, filepath: Path, prefs: dict) -> str:
    expiry = prefs.get("expiry_minutes", 60)
    if host == "litterbox":
        return _upload_to_litterbox(filepath, expiry)
    if host == "tmpfiles":
        return _upload_to_tmpfiles(filepath, expiry)
    if host == "selfhost":
        return selfhost_url(filepath, prefs.get("selfhost_base", ""), ttl_seconds=expiry * 60)
    raise ValueError(f"Unknown upload host {host!r}")


def _http_failure(service: str, resp: requests.Response) -> ValueError:
    body = resp.text[:200].strip()
    return ValueError(f"{service} upload failed — HTTP {resp.status_code}" + (f" — {body}" if body else ""))


def _litterbox_time(expiry_minutes: int) -> str:
    """Litterbox's retention label (1h/12h/24h/72h) nearest to the request."""
    return _LITTERBOX_BUCKETS[min(_LITTERBOX_BUCKETS, key=lambda v: abs(v - expiry_minutes))]


def _upload_to_litterbox(filepath: Path, expiry_minutes: int = 60) -> str:
    """Upload a file to litterbox.catbox.moe and return the public URL.
    Fails fast (no retry) so VPN/Cloudflare blocks surface immediately."""
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                LITTERBOX_URL,
                data={"reqtype": "fileupload", "time": _litterbox_time(expiry_minutes)},
                files={"fileToUpload": (filepath.name, f)},
                timeout=(8, 15),  # (connect, read) — read is server response time only, not upload duration
            )
    except requests.exceptions.Timeout as exc:
        log.warning("litterbox upload timed out (%s)", exc)
        raise ValueError("Litterbox upload timed out — cycle VPN if blocked") from exc
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as exc:
        log.warning("litterbox upload failed — %s: %s", type(exc).__name__, exc)
        raise ValueError(f"Litterbox upload failed — {type(exc).__name__}: {exc}") from exc
    if resp.status_code != 200 or not resp.text.startswith("https://"):
        err = _http_failure("Litterbox", resp)
        log.warning("%s", err)
        raise err
    return resp.text.strip()


def _upload_to_tmpfiles(filepath: Path, expiry_minutes: int = 60) -> str:
    """Upload a file to tmpfiles.org and return its direct download URL.
    (tmpfiles honors its own retention; we pass the requested span as a hint.)"""
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                TMPFILES_URL,
                data={"expire": expiry_minutes * 60},
                files={"file": (filepath.name, f)},
                timeout=(8, 30),
            )
        if resp.status_code != 200:
            raise _http_failure("tmpfiles.org", resp)
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(f"tmpfiles.org upload failed — {data}")
        return _tmpfiles_direct_url(data["data"]["url"])
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 — any failure falls back to litterbox
        raise ValueError(f"tmpfiles.org upload failed — {exc}") from exc


def _tmpfiles_direct_url(page_url: str) -> str:
    """tmpfiles.org's dl/ URLs need a {timestamp}.{hash} segment the upload
    API doesn't return, so scrape it from the file's HTML page."""
    page = requests.get(page_url, timeout=(8, 30))
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    link = soup.find("a", class_="download") or soup.find("img", id="img_preview")
    direct_url = (link.get("href") or link.get("src")) if link else None
    if not direct_url:
        raise ValueError(f"tmpfiles.org upload succeeded but no direct download link found on {page_url}")
    return direct_url
