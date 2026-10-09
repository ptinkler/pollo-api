"""
Temporary public hosting for local images, for providers that only take an
image URL (Pollo): tmpfiles.org, falling back to litterbox.catbox.moe.
"""

from pathlib import Path

import requests
from bs4 import BeautifulSoup

HOSTED_SECONDS = 3600  # how long an uploaded image stays up (both hosts)
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
LITTERBOX_EXPIRY = "1h"  # litterbox's name for HOSTED_SECONDS: 1h, 12h, 24h or 72h
TMPFILES_URL = "https://tmpfiles.org/api/v1/upload"


def upload_image(filepath: Path) -> str:
    """Upload a file to tmpfiles.org, falling back to litterbox if that fails."""
    try:
        url = _upload_to_tmpfiles(filepath)
        print(f"[Upload] tmpfiles.org succeeded: {url}")
        return url
    except ValueError as primary_exc:
        print(f"[Upload] tmpfiles.org failed ({primary_exc}), trying litterbox…")
        try:
            return _upload_to_litterbox(filepath)
        except ValueError as fallback_exc:
            raise ValueError(
                f"All upload hosts failed — tmpfiles: {primary_exc}; litterbox: {fallback_exc}"
            ) from fallback_exc


def _http_failure(service: str, resp: requests.Response) -> ValueError:
    body = resp.text[:200].strip()
    return ValueError(f"{service} upload failed — HTTP {resp.status_code}" + (f" — {body}" if body else ""))


def _upload_to_litterbox(filepath: Path) -> str:
    """Upload a file to litterbox.catbox.moe and return the public URL.
    Fails fast (no retry) so VPN/Cloudflare blocks surface immediately."""
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                LITTERBOX_URL,
                data={"reqtype": "fileupload", "time": LITTERBOX_EXPIRY},
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


def _upload_to_tmpfiles(filepath: Path) -> str:
    """Upload a file to tmpfiles.org and return its direct download URL."""
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                TMPFILES_URL, data={"expire": HOSTED_SECONDS}, files={"file": (filepath.name, f)}, timeout=(8, 30)
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
