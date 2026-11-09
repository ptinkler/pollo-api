"""
Public hosting for local source media, for providers that only take a URL
(Pollo): the per-user preference picks the host (litterbox / tmpfiles /
self-host) and retention — see web/upload_settings.py. A primary host is tried
first, then the backup. Self-host serves the file from this instance itself
(web/public_media.py) instead of a third-party temp host.
"""

from pathlib import Path

import requests
from bs4 import BeautifulSoup

LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
TMPFILES_URL = "https://tmpfiles.org/api/v1/upload"
# Litterbox only offers these fixed retentions; map any requested span to the
# nearest. Keys are minutes.
_LITTERBOX_BUCKETS = {60: "1h", 720: "12h", 1440: "24h", 4320: "72h"}


def upload_image(filepath: Path) -> str:
    """Upload a source image to the user's configured host(s)."""
    return upload_file(filepath)


def upload_file(filepath: Path, prefs: dict | None = None) -> str:
    """Upload any source file to the configured public host and return its URL,
    trying the primary host then the backup. `prefs` defaults to the current
    user's resolved upload preferences (web/upload_settings.py)."""
    if prefs is None:
        from .upload_settings import current_upload_prefs

        prefs = current_upload_prefs()
    order = [prefs["primary"]]
    if prefs.get("backup") and prefs["backup"] != prefs["primary"]:
        order.append(prefs["backup"])
    errors: list[str] = []
    for host in order:
        try:
            url = _dispatch(host, filepath, prefs)
            print(f"[Upload] {host} succeeded: {url}")
            return url
        except ValueError as exc:
            print(f"[Upload] {host} failed ({exc}), trying next host…")
            errors.append(f"{host}: {exc}")
    raise ValueError("All upload hosts failed — " + "; ".join(errors))


def _dispatch(host: str, filepath: Path, prefs: dict) -> str:
    expiry = prefs.get("expiry_minutes", 60)
    if host == "litterbox":
        return _upload_to_litterbox(filepath, expiry)
    if host == "tmpfiles":
        return _upload_to_tmpfiles(filepath, expiry)
    if host == "selfhost":
        from .public_media import selfhost_url

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
        print(f"[Litterbox] Upload failed — timed out ({exc})")
        raise ValueError("Litterbox upload timed out — cycle VPN if blocked") from exc
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as exc:
        print(f"[Litterbox] Upload failed — {type(exc).__name__}: {exc}")
        raise ValueError(f"Litterbox upload failed — {type(exc).__name__}: {exc}") from exc
    if resp.status_code != 200 or not resp.text.startswith("https://"):
        err = _http_failure("Litterbox", resp)
        print(f"[Litterbox] {err}")
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
