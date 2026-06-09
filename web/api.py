"""
Pollo Video Generator — API Backend (FastAPI)

Run:  python web/app.py   (from the pollo root directory)
"""
import os
import sys
import json
import shutil
import uuid
import threading
import hashlib
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Optional, TypedDict
from contextlib import asynccontextmanager

import requests as _requests
import io as _io
from PIL import Image as _PILImage
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Cookie, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import cv2
import uvicorn

# ── Bootstrap ───────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent.resolve()
WEB_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)
load_dotenv(override=True)

from img2vid.pollo.pollo_img2vid import get_video_generator, GENERATORS
from img2vid.pollo.generators import SUCCESS_STATUSES, ERROR_STATUSES
from img2vid.common.get_task import get_task_status, get_credit_balance
from img2vid.common.download import download_video, download_image, get_filename_from_url
from img2vid.common.metadata import get_db

# ── Authentication ───────────────────────────────────────────────────
from .auth import verify_api_key, is_auth_enabled, get_api_keys


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: resume polling for any jobs stuck in processing
    startup_resume_jobs()
    yield
    # Shutdown: nothing to do


app = FastAPI(title="Pollo Video Generator API", lifespan=lifespan)

# CORS - allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                    "https://localhost:5173", "https://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Constants ───────────────────────────────────────────────────────
MODEL_INFO = {
    "pollodance20": {
        "label": "Pollo Dance 2.0", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
    },
    "pollodance20fast": {
        "label": "Pollo Dance 2.0 Fast", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
    },
    "pollo20": {
        "label": "Pollo 2.0", "type": "img2vid",
        "lengths": [5, 10],
        "ratios": ["9:16", "16:9"],
        "options": ["generate_audio", "web_search"],
    },
    "pollodanceref": {
        "label": "Pollo Dance Ref", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
    },
    "pollodancereffast": {
        "label": "Pollo Dance Ref Fast", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
    },
    "seedance20": {
        "label": "Seedance 2.0", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
    },
    "seedance20fast": {
        "label": "Seedance 2.0 Fast", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
    },
    "seedanceref": {
        "label": "Seedance Ref", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
    },
    "seedancereffast": {
        "label": "Seedance Ref Fast", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
    },
}

# Support external data directory via env var (same as metadata.py)
_data_dir_env = os.environ.get("POLLO_DATA_DIR")
print(f"📁 POLLO_DATA_DIR env var: {_data_dir_env or '(not set, using local)'}")
POLLO_ROOT = Path(_data_dir_env) if _data_dir_env else ROOT_DIR
ASSETS_DIR = POLLO_ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Thumbnail cache directory (for video frame caching)
# Stored in data directory to keep all data together
THUMB_CACHE_DIR = POLLO_ROOT / "cache" / "thumbnails"
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Polling retry constants — used by run_generation() and resume_polling_job()
MAX_POLL_ERRORS = 6          # give up after this many consecutive failures (~3 min)
POLL_BACKOFF_BASE = 10       # base sleep between polls (seconds)
POLL_BACKOFF_MAX = 60        # max backoff on transient errors
STALE_JOB_SECONDS = 180      # consider a non-terminal job stale after 3 min of no updates

# Sending retry behaviour for initial POST to API — helps when VPN/gluetun causes
# intermittent 5xx/502 responses but the remote task may still have been created.
SEND_RETRIES = 3             # number of attempts for initial send (counting first)
SEND_RETRY_BACKOFF = 2      # seconds between send retries (simple linear backoff)

# Litterbox (temporary image hosting for source uploads)
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
LITTERBOX_EXPIRY = "1h"  # 1h, 12h, 24h, 72h
SOURCE_IMAGE_MAX_SIZE = 20 * 1024 * 1024  # 20 MB

print(f"📁 Pollo root: {POLLO_ROOT}")
print(f"📁 Assets directory: {ASSETS_DIR}")
print(f"📁 Data directory: {POLLO_ROOT / 'data'}")
print(f"📁 Thumbnail cache (frames): {THUMB_CACHE_DIR}")
print("📁 Project thumbnails will be saved to: ASSETS_DIR/<project>/thumb.jpg")


# ── In-Memory TTL Cache ─────────────────────────────────────────────
class TTLCache:
    """Simple in-memory cache with TTL expiration."""
    def __init__(self, default_ttl: float = 30.0):
        self._cache: dict = {}
        self._timestamps: dict = {}
        self._ttls: dict = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._cache:
                return None
            ttl = self._ttls.get(key, self._default_ttl)
            if time.time() - self._timestamps[key] > ttl:
                del self._cache[key]
                del self._timestamps[key]
                self._ttls.pop(key, None)
                return None
            return self._cache[key]

    def set(self, key: str, value: Any, ttl: float | None = None):
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            if ttl is not None:
                self._ttls[key] = ttl
            else:
                self._ttls.pop(key, None)  # use default

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._ttls.clear()


# Cache instances — ONLY for immutable lookups (slug→folder never changes once created)
_project_lookup_cache = TTLCache(default_ttl=120.0)  # Project slug -> assets_folder lookups (for file serving)


def _get_project_assets_folder(slug: str) -> str | None:
    """Get assets folder for a project slug with caching."""
    cache_key = f"project:{slug}"
    cached = _project_lookup_cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__NOT_FOUND__" else None

    db = get_db()
    proj = db.get_project_by_slug(slug)
    if proj:
        _project_lookup_cache.set(cache_key, proj.assets_folder)
        return proj.assets_folder
    else:
        _project_lookup_cache.set(cache_key, "__NOT_FOUND__")
        return None


def _invalidate_project_caches():
    """Invalidate all project-related caches."""
    _project_lookup_cache.clear()


# ── Pydantic Models ─────────────────────────────────────────────────

class JobArchivedResult(TypedDict):
    archived: bool
    job_id: str


class ProjectArchivedResult(TypedDict):
    archived: bool
    slug: str


class GenerateRequest(BaseModel):
    model: str = "pollodance20"
    project: str | None = None  # project slug
    prompt: str
    image_url: str | None = None
    video_url: str | None = None
    subject_url: str | None = None
    audio_url: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    length: int | None = None
    generate_audio: bool | None = None
    web_search: bool | None = None
    image_tail: str | None = None
    seed: int | None = None
    refs: list | None = None  # ref2video: array of {type, name, image, order, avatarId?}
    video_num: int | None = None  # ref2video: 1-4
    image_meta: list | None = None  # ref2video: array of {url, order, name?, cropper?}


class BulkMoveRequest(BaseModel):
    job_ids: list[str]
    target_project: str


class ProjectCreate(BaseModel):
    name: str  # Display name
    prompt: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    subject_url: str | None = None
    audio_url: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None  # Rename display name
    prompt: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    subject_url: str | None = None
    audio_url: str | None = None


class VpnCountryRequest(BaseModel):
    country: str


class LoginRequest(BaseModel):
    key: str


# ── Auth Routes ─────────────────────────────────────────────────────

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


@app.post("/api/auth/login")
async def api_auth_login(data: LoginRequest, response: Response, request: Request):
    key = data.key.strip()
    auth_keys = get_api_keys()
    if auth_keys and key not in auth_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    is_https = request.headers.get("x-forwarded-proto", "").lower() == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=key,
        httponly=True,
        samesite="strict",
        secure=is_https,
        max_age=COOKIE_MAX_AGE,
    )
    return {"ok": True}


@app.post("/api/auth/logout")
async def api_auth_logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, samesite="strict")
    return {"ok": True}


@app.get("/api/auth/status")
async def api_auth_status(session: Optional[str] = Cookie(None)):
    enabled = is_auth_enabled()
    if not enabled:
        return {"enabled": False, "authenticated": True}
    authenticated = session is not None and session.strip() in get_api_keys()
    return {"enabled": True, "authenticated": authenticated}


# ── Background worker ──────────────────────────────────────────────

def _poll_task(job_id: str, task_id: str, api_key: str,
               on_poll: Callable[[], bool] | None = None) -> list[tuple[str, str | None, str | None, int | None]] | None:
    """Poll a task until completion, handling retries and backoff.

    *on_poll* is called before each sleep so callers can inject extra
    checks (e.g. detecting that another thread already resolved the job).
    It should return ``True`` to abort polling early.

    Returns the final *results* list on success, or ``None`` if the job
    was marked as error (the DB is updated inline).
    """
    db = get_db()
    consecutive_errors = 0

    while True:
        sleep_time = min(POLL_BACKOFF_BASE * (2 ** consecutive_errors),
                         POLL_BACKOFF_MAX)
        time.sleep(sleep_time)

        if on_poll and on_poll():
            return None  # Caller requested early abort

        # Touch updated_at each poll cycle to prevent stale-job recovery
        db.update_job(job_id, message=f"Task {task_id} processing...")

        try:
            results = get_task_status(task_id, api_key)
        except Exception as poll_exc:
            consecutive_errors += 1
            msg = (f"Poll error ({consecutive_errors}/{MAX_POLL_ERRORS}): "
                   f"{poll_exc}")
            print(f"[Job {job_id}] {msg}")
            db.update_job(job_id,
                          message=f"Task {task_id} — retrying after "
                                  f"transient error ({consecutive_errors}/"
                                  f"{MAX_POLL_ERRORS})...")
            if consecutive_errors >= MAX_POLL_ERRORS:
                db.update_job(job_id, status="error",
                              message=f"Polling failed after "
                                      f"{MAX_POLL_ERRORS} retries: "
                                      f"{poll_exc}")
                return None
            continue

        api_status, fail_msg, url, _credits = results[0]
        print(f"[Job {job_id}] Poll result: status={api_status}, url={url}")

        # Cloudflare block is transient — retry like a network error
        if api_status == "cloudflare_blocked":
            consecutive_errors += 1
            print(f"[Job {job_id}] Cloudflare blocked "
                  f"({consecutive_errors}/{MAX_POLL_ERRORS})")
            db.update_job(job_id,
                          message=f"Task {task_id} — Cloudflare block, "
                                  f"retrying ({consecutive_errors}/"
                                  f"{MAX_POLL_ERRORS})...")
            if consecutive_errors >= MAX_POLL_ERRORS:
                db.update_job(job_id, status="error",
                              message=fail_msg or "Cloudflare blocked "
                                      "after max retries")
                return None
            continue

        # Reset consecutive error counter on any successful poll
        consecutive_errors = 0

        if api_status in ERROR_STATUSES:
            db.update_job(job_id, status="error",
                          message=fail_msg or "Generation failed")
            return None

        # For multi-video (videoNum > 1), wait until all are done
        if api_status in SUCCESS_STATUSES:
            all_done = all(r[0] in SUCCESS_STATUSES for r in results)
            if all_done:
                return results


def run_generation(job_id: str, model: str, kwargs: dict):
    """Run video generation in a background thread, updating the DB."""
    db = get_db()
    try:
        db.update_job(job_id, status="creating", message="Creating generator...")
        generator = get_video_generator(model, **kwargs)
        project = generator.project

        # Download source image for img2vid if needed
        if not generator.is_text_only and not (hasattr(generator, "is_video_edit") and generator.is_video_edit):
            if not generator.image_url:
                if not (hasattr(generator, "refs") and generator.refs):
                    db.update_job(job_id, status="error",
                                  message="image_url is required for image-to-video generation but was not provided")
                    return
            else:
                download_image(generator.image_url, project)

        db.update_job(job_id, status="sending", message="Sending request to API...")

        # Attempt to send the initial request with a few retries for 5xx or transient
        # errors. The Pollo API may occasionally return 502/5xx while still creating
        # a remote task; in that case the response JSON sometimes contains a
        # taskId even though the HTTP status is not 200. We try a few times and
        # accept a response that contains a taskId.
        response = None
        resp_json = None
        last_exc: Exception | None = None
        for attempt in range(SEND_RETRIES):
            try:
                response = generator.send_request()
            except ConnectionError as exc:
                # Network-level issue (VPN down, Cloudflare, timeout) — retry a few times
                last_exc = exc
                db.update_job(job_id, message=f"Send attempt {attempt+1}/{SEND_RETRIES} failed: {exc}")
                if attempt < SEND_RETRIES - 1:
                    time.sleep(SEND_RETRY_BACKOFF)
                    continue
                else:
                    db.update_job(job_id, status="error", message=str(exc))
                    return

            # Try to parse JSON if present
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None

            # If we got a 200+SUCCESS response, proceed
            if response.status_code == 200 and resp_json and resp_json.get("code") == "SUCCESS":
                break

            # If non-200 but JSON includes a taskId, accept it and continue
            if resp_json and isinstance(resp_json.get("data"), dict) and resp_json.get("data", {}).get("taskId"):
                break

            # If server 5xx, retry a few times
            if 500 <= response.status_code < 600 and attempt < SEND_RETRIES - 1:
                db.update_job(job_id, message=f"API responded HTTP {response.status_code}, retrying ({attempt+1}/{SEND_RETRIES})...")
                time.sleep(SEND_RETRY_BACKOFF)
                continue

            # Otherwise, break and handle as an error below
            break

        if response is None:
            # Shouldn't happen due to above handling, but guard anyway
            db.update_job(job_id, status="error", message=str(last_exc or "No response from API"))
            return

        # If the response was non-JSON and non-200, surface a useful message
        if resp_json is None:
            body_preview = response.text[:200] if response.text else "(empty)"
            db.update_job(job_id, status="error",
                          message=f"API returned non-JSON (HTTP {response.status_code}): {body_preview}")
            return

        # If the API explicitly failed (and didn't provide a taskId), mark error
        if response.status_code != 200 and not resp_json.get("data", {}).get("taskId"):
            db.update_job(job_id, status="error",
                          message=resp_json.get("message", f"API request failed (HTTP {response.status_code})"))
            return

        # At this point we either have a normal SUCCESS response or a non-200
        # response that contains a taskId. Extract the task info and continue.
        task_id = resp_json.get("data", {}).get("taskId")
        api_status = resp_json.get("data", {}).get("status")
        if not task_id or not api_status:
            db.update_job(job_id, status="error", message="No task ID returned from API")
            return

        db.update_job(job_id, status="processing", task_id=task_id,
                       message=f"Task {task_id} processing...")

        # Poll for completion with retry/backoff
        results = _poll_task(job_id, task_id, generator.api_key)
        if results is None:
            return  # Error already recorded by _poll_task

        # Extract credit cost from API response
        credits_used = sum(r[3] for r in results if r[3] is not None) or None

        # Collect all successful video URLs
        video_urls = [r[2] for r in results if r[0] in SUCCESS_STATUSES and r[2]]

        if not video_urls:
            db.update_job(job_id, status="error", message="No video URL in result")
            return

        db.update_job(job_id, status="downloading", message="Downloading video...",
                       video_url=video_urls[0])

        # Download all videos (multi-video support for ref2video)
        filepath = None
        for vid_url in video_urls:
            filepath = download_video(
                vid_url, project, task_id=task_id, model=model,
                prompt=generator.prompt, metadata=generator.build_download_metadata(),
            )

        db.update_job(job_id, status="done", message="Video ready!",
                       video_path=filepath, credits_used=credits_used)

        # Invalidate caches for this project
        _invalidate_project_caches()

        # Force-regenerate project thumbnail from the newly downloaded video
        # Get slug from the job record for archive-aware thumbnail
        job_rec = db.get_job(job_id)
        project_slug = job_rec.project if job_rec else None
        _update_project_thumbnail(ASSETS_DIR / project, project_slug=project_slug, force=True)

    except Exception as e:
        db.update_job(job_id, status="error", message=str(e))


# ── Helper ──────────────────────────────────────────────────────────


def _get_assets_path(project_slug: str) -> Path | None:
    """Get the assets folder path for a project by its slug."""
    assets_folder = _get_project_assets_folder(project_slug)
    if not assets_folder:
        return None
    return ASSETS_DIR / assets_folder


def _enrich_job_result(result: dict, job, assets_path: Path | None = None) -> dict:
    """Add video_exists, update video_path if found elsewhere, and add filename.
    Modifies result dict in-place and returns it."""
    exists, found_path = _find_video_for_job(job, assets_path)
    result["video_exists"] = exists

    if exists and found_path and found_path != job.video_path:
        get_db().update_job(job.job_id, video_path=found_path)
        result["video_path"] = found_path

    video_path = result.get("video_path") or found_path
    if video_path:
        result["filename"] = Path(video_path).name

    return result


def _find_video_for_job(job, assets_path: Path | None = None) -> tuple[bool, str | None]:
    """
    Check if a video exists for a job, trying multiple methods:
    1. Check job.video_path directly
    2. Try to find video by matching filename from video_url
    3. Try to find video by task_id in filename

    Returns (exists: bool, found_path: str | None)
    """
    # Method 1: Check stored video_path
    if job.video_path and Path(job.video_path).exists():
        return True, job.video_path

    # Need assets_path for other methods
    if not assets_path:
        db = get_db()
        proj = db.get_project_by_slug(job.project)
        if not proj:
            return False, None
        assets_path = ASSETS_DIR / proj.assets_folder

    if not assets_path.exists():
        return False, None

    # Method 2: Try to find by video_url filename
    if job.video_url:
        expected_filename = get_filename_from_url(job.video_url)
        if expected_filename:
            # Check for exact match or with (1), (2) suffix
            for video_file in assets_path.glob("*.mp4"):
                name = video_file.name
                # Check exact match
                if name == expected_filename:
                    return True, str(video_file)
                # Check with suffix like filename(1).mp4
                base, ext = expected_filename.rsplit('.', 1)
                if name.startswith(base) and name.endswith(f'.{ext}'):
                    return True, str(video_file)

    # Method 3: Try to find by task_id in filename
    if job.task_id:
        for video_file in assets_path.glob("*.mp4"):
            if job.task_id in video_file.name:
                return True, str(video_file)

    return False, None


def _get_latest_video_uncached(assets_dir: Path, exclude_filenames: set[str] | None = None) -> Path | None:
    """Get the most recent video file directly from disk (no cache).
    Optionally exclude specific filenames (e.g. archived videos)."""
    if not assets_dir.exists():
        return None
    videos = list(assets_dir.glob("*.mp4"))
    if exclude_filenames:
        videos = [v for v in videos if v.name not in exclude_filenames]
    if not videos:
        return None
    videos.sort(key=lambda v: v.stat().st_mtime, reverse=True)
    return videos[0]


def _get_archived_filenames(project_slug: str) -> set[str]:
    """Get filenames of archived videos for a project."""
    db = get_db()
    jobs = db.get_jobs_by_project(project_slug)
    return {
        Path(j.video_path).name
        for j in jobs
        if j.archived and j.video_path
    }


def _update_project_thumbnail(assets_path: Path, project_slug: str | None = None, force: bool = False) -> bool:
    """Update the project thumbnail (thumb.jpg) from the latest non-archived video.
    Only updates if thumb.jpg doesn't exist or is older than the latest video.
    Set force=True to always regenerate.
    Returns True if thumbnail was created/updated."""
    # Exclude archived videos if we know the project slug
    exclude = _get_archived_filenames(project_slug) if project_slug else None
    latest_video = _get_latest_video_uncached(assets_path, exclude_filenames=exclude)
    if not latest_video:
        # No non-archived videos — remove stale thumbnail
        thumb_path = assets_path / "thumb.jpg"
        if thumb_path.exists():
            try:
                thumb_path.unlink()
            except Exception:
                pass
        return False

    thumb_path = assets_path / "thumb.jpg"

    # Check if thumbnail already exists and is up-to-date
    if not force and thumb_path.exists():
        try:
            if thumb_path.stat().st_mtime >= latest_video.stat().st_mtime:
                return True  # Already up-to-date
        except Exception:
            pass  # If stat fails, regenerate

    # Extract frame from latest video
    frame_data = _extract_first_frame_uncached(latest_video)
    if not frame_data:
        print(f"[Thumbnail] Failed to extract frame from {latest_video.name}", flush=True)
        return False

    try:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(frame_data)
        print(f"[Thumbnail] Updated {thumb_path.name} from {latest_video.name}", flush=True)
        return True
    except Exception as e:
        print(f"[Thumbnail] Failed to save: {e}", flush=True)
        return False


def _get_video_list(assets_dir: Path, sort_by_mtime: bool = False) -> list[tuple[Path, float]] | list[Path]:
    """Get video list from disk.
    When sort_by_mtime=True, returns list of (Path, mtime) tuples sorted newest-first.
    When sort_by_mtime=False, returns list of Paths sorted by name."""
    if not assets_dir.exists():
        return []

    videos = list(assets_dir.glob("*.mp4"))
    if sort_by_mtime:
        result = [(v, v.stat().st_mtime) for v in videos]
        result.sort(key=lambda x: x[1], reverse=True)
    else:
        videos.sort()
        result = videos

    return result


def _get_thumb_cache_path(video_path: Path) -> Path:
    """Get the cache path for a video thumbnail."""
    # Use hash of full path + mtime to handle file changes
    try:
        mtime = video_path.stat().st_mtime
    except OSError:
        mtime = 0
    cache_key = hashlib.md5(f"{video_path}:{mtime}".encode()).hexdigest()
    return THUMB_CACHE_DIR / f"{cache_key}.jpg"


def _cleanup_thumb_cache():
    """Remove cached video thumbnails whose source videos no longer exist.
    Iterates all project asset folders, builds a set of valid cache filenames,
    then deletes any .jpg in THUMB_CACHE_DIR that isn't in that set."""
    if not THUMB_CACHE_DIR.exists():
        return 0

    # Build the set of valid cache filenames from all existing videos
    valid_cache_names: set[str] = set()
    if ASSETS_DIR.exists():
        for project_dir in ASSETS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            for video_file in project_dir.glob("*.mp4"):
                cache_path = _get_thumb_cache_path(video_file)
                valid_cache_names.add(cache_path.name)

    # Delete orphaned cache files
    removed = 0
    for cached_file in THUMB_CACHE_DIR.glob("*.jpg"):
        if cached_file.name not in valid_cache_names:
            try:
                cached_file.unlink()
                removed += 1
            except Exception:
                pass

    if removed:
        print(f"[Thumbnail cleanup] Removed {removed} orphaned cached thumbnail(s)", flush=True)
    return removed


def _extract_first_frame_uncached(video_path: Path) -> bytes | None:
    """Extract the first frame from a video using OpenCV, returns JPEG bytes.
    No caching - always extracts fresh."""
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return None
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()
    except Exception:
        return None


def _extract_first_frame(video_path: Path) -> bytes | None:
    """Extract the first frame from a video using OpenCV, returns JPEG bytes.
    Uses disk cache to avoid repeated video file access."""

    # Check disk cache first
    cache_path = _get_thumb_cache_path(video_path)
    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except Exception:
            pass  # Fall through to extract

    # Extract from video (uncached)
    jpeg_bytes = _extract_first_frame_uncached(video_path)
    if jpeg_bytes is None:
        return None

    # Save to disk cache
    try:
        cache_path.write_bytes(jpeg_bytes)
    except Exception:
        pass  # Cache write failure is non-fatal

    return jpeg_bytes


# ═══════════════════════════════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════════════════════════════

# ── Generate ────────────────────────────────────────────────────────

@app.post("/api/generate")
def api_generate(data: GenerateRequest, _api_key: str = Depends(verify_api_key)):
    model = data.model
    if model not in GENERATORS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    prompt = (data.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    # Get or create project
    db = get_db()
    project_slug = (data.project or "").strip()

    if project_slug:
        project = db.get_project_by_slug(project_slug)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_slug}")
    else:
        # Auto-create a new project
        project = db.create_project(name=f"Generation {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        project_slug = project.slug

    # Ensure assets folder exists
    assets_path = ASSETS_DIR / project.assets_folder
    assets_path.mkdir(parents=True, exist_ok=True)

    image_url = (data.image_url or "").strip() or None
    video_url = (data.video_url or "").strip() or None
    subject_url = (data.subject_url or "").strip() or None
    audio_url = (data.audio_url or "").strip() or None

    # Handle local source image: upload to litterbox to get a public URL
    # Keep the project's stored image_url as the local reference (so the local file remains the canonical copy),
    # but pass the uploaded public URL to the generator and record both in the job params so regenerations
    # can prefer the uploaded URL while it's still valid and fall back to the local file afterwards.
    uploaded_image_url = None
    local_image_ref = None
    if image_url and image_url.startswith("local:"):
        assets_path = ASSETS_DIR / project.assets_folder
        source = _get_local_image_path(assets_path, image_url)
        if not source:
            raise HTTPException(status_code=400, detail="Source image not found — it may have been deleted")
        try:
            uploaded_image_url = _upload_to_litterbox(source)
            print(f"[Generate] Uploaded source image to litterbox: {uploaded_image_url}")
            # Keep the local ref for the project and for long-term storage
            local_image_ref = image_url
            # For the generator use the uploaded public URL
            image_url = uploaded_image_url
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to upload image: {exc}")

    # Update project with URLs if provided. Important: if we uploaded the image above, do NOT overwrite
    # the project's image_url with the temporary uploaded URL — keep the local reference as the canonical
    # project image. Otherwise use whatever URL was passed in the request.
    project_image_to_store = None
    if local_image_ref:
        project_image_to_store = local_image_ref
    else:
        project_image_to_store = image_url or project.image_url

    db.update_project(project_slug,
                      prompt=prompt,
                      image_url=project_image_to_store,
                      video_url=video_url or project.video_url,
                      subject_url=subject_url or project.subject_url,
                      audio_url=audio_url or project.audio_url)

    aspect_ratio = data.aspect_ratio
    resolution = data.resolution
    length = data.length
    generate_audio = data.generate_audio

    kwargs = {
        "api_key": os.getenv("POLLO_API_KEY"),
        "project": project.assets_folder,  # Use assets folder for file storage
        "prompt": prompt,
        "image_url": image_url,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "length": length,
        "generate_audio": generate_audio,
    }

    # Model-specific options
    model_opts = MODEL_INFO.get(model, {}).get("options", [])
    if "web_search" in model_opts:
        kwargs["web_search"] = data.web_search or False
    if "image_tail" in model_opts:
        image_tail = (data.image_tail or "").strip() or None
        if image_tail:
            kwargs["image_tail"] = image_tail
    if "seed" in model_opts and data.seed is not None:
        kwargs["seed"] = data.seed

    if MODEL_INFO.get(model, {}).get("type") == "ref":
        # ref uses refs array
        if data.refs:
            # Handle local: refs by uploading to litterbox
            assets_path = ASSETS_DIR / project.assets_folder
            resolved_refs = []
            for ref in data.refs:
                ref = dict(ref)  # shallow copy
                ref_type = ref.get("type", "image")
                if ref_type == "image":
                    url = ref.get("image") or ref.get("url") or ""
                    if url.startswith("local:"):
                        source = _get_local_image_path(assets_path, url)
                        if not source:
                            raise HTTPException(status_code=400, detail=f"Ref image not found: {url}")
                        try:
                            public_url = _upload_to_litterbox(source)
                            print(f"[Generate] Uploaded ref image to litterbox: {public_url}")
                        except ValueError as exc:
                            raise HTTPException(status_code=502, detail=f"Failed to upload ref image: {exc}")
                        # Preserve the original local reference so regenerations can fall back to it
                        ref["_local_image"] = url
                        ref["image"] = public_url
                        if "url" in ref:
                            ref["url"] = public_url
                elif ref_type == "subject":
                    images = ref.get("images", [])
                    resolved_images = []
                    for img in images:
                        img = dict(img) if isinstance(img, dict) else {"url": str(img)}
                        url = img.get("url", "")
                        if url.startswith("local:"):
                            source = _get_local_image_path(assets_path, url)
                            if not source:
                                raise HTTPException(status_code=400, detail=f"Subject ref image not found: {url}")
                            try:
                                public_url = _upload_to_litterbox(source)
                                print(f"[Generate] Uploaded subject ref image to litterbox: {public_url}")
                            except ValueError as exc:
                                raise HTTPException(status_code=502, detail=f"Failed to upload subject ref image: {exc}")
                            # Preserve local reference for regen fallback
                            img["_local_url"] = url
                            img["url"] = public_url
                        resolved_images.append(img)
                    ref["images"] = resolved_images
                resolved_refs.append(ref)
            kwargs["refs"] = resolved_refs
        else:
            # Build refs from individual URLs (backward-compatible)
            kwargs["subject_url"] = subject_url
        if data.video_num is not None:
            kwargs["video_num"] = data.video_num
        if data.image_meta is not None:
            kwargs["image_meta"] = data.image_meta

    # Create DB job record with extra params
    job_id = str(uuid.uuid4())[:8]
    extra_params = {
        "web_search": kwargs.get("web_search", False),
        "image_tail": kwargs.get("image_tail", ""),
        "seed": kwargs.get("seed", None),
        "video_num": kwargs.get("video_num", None),
        "refs": kwargs.get("refs", []) or [],
    }
    # If we uploaded a temporary public image for this generation, record both the local ref and
    # the uploaded URL + timestamp so regenerations can prefer the uploaded URL until it expires.
    if local_image_ref and uploaded_image_url:
        extra_params["source_local"] = local_image_ref
        extra_params["source_uploaded"] = uploaded_image_url
        try:
            extra_params["source_uploaded_at"] = int(time.time())
        except Exception:
            extra_params["source_uploaded_at"] = None
    db.create_job(
        job_id=job_id, project=project_slug, model=model, prompt=prompt,
        image_url=image_url, source_video_url=video_url,
        subject_url=subject_url, audio_url=audio_url,
        aspect_ratio=aspect_ratio, resolution=resolution,
        length=length, generate_audio=generate_audio,
        params=extra_params,
    )

    threading.Thread(target=run_generation, args=(job_id, model, kwargs),
                     daemon=True).start()

    return {"job_id": job_id, "project": project_slug}


# ── Job status ──────────────────────────────────────────────────────

# Track jobs currently being recovered to prevent concurrent recovery attempts
_recovering_jobs: set[str] = set()
_recovering_lock = threading.Lock()


def _recover_stale_job(job):
    """Try to recover a job stuck in a non-terminal status.

    If the job already has a video_url the generation succeeded; kick off
    a background download so the video file is available.  Otherwise fall
    back to checking the remote task API.
    """
    # Prevent concurrent recovery attempts for the same job
    with _recovering_lock:
        if job.job_id in _recovering_jobs:
            return
        _recovering_jobs.add(job.job_id)

    try:
        _recover_stale_job_inner(job)
    finally:
        with _recovering_lock:
            _recovering_jobs.discard(job.job_id)


def _recover_stale_job_inner(job):
    """Inner recovery logic (called with concurrent-recovery guard)."""
    db = get_db()

    # Re-fetch the job to get the latest status — another thread may have
    # already updated it since the caller read it.
    job = db.get_job(job.job_id)
    if not job or job.status in ("done", "error"):
        return

    print(f"[recover] Job {job.job_id} stale in status={job.status}, attempting recovery", flush=True)

    # If we already have a video URL, the generation succeeded — just
    # the download failed or was interrupted.  Trigger a background download.
    if job.video_url:
        # But if we already have the file, just mark done
        if job.video_path and os.path.isfile(job.video_path):
            db.update_job(job.job_id, status="done", message="Video ready!")
            print(f"[recover] Job {job.job_id} already has video file, marking done", flush=True)
            return
        print(f"[recover] Job {job.job_id} has video_url, triggering download", flush=True)
        db.update_job(job.job_id, status="downloading",
                      message="Downloading video (recovered)...")
        threading.Thread(
            target=_download_recovered_job,
            args=(job.job_id, job.video_url),
            daemon=True
        ).start()
        return

    # Otherwise try checking the task API
    if not job.task_id:
        db.update_job(job.job_id, status="error",
                      message="Stuck with no task ID — cannot recover")
        return

    api_key = os.getenv("POLLO_API_KEY")
    if not api_key:
        db.update_job(job.job_id, status="error",
                      message="Stuck — no API key to check task status")
        return

    try:
        results = get_task_status(job.task_id, api_key)
        if not results:
            db.update_job(job.job_id, status="error",
                          message="No status returned from API")
            return
        api_status, fail_msg, url, _credits = results[0]
        if api_status in SUCCESS_STATUSES:
            if url:
                # Trigger background download instead of marking done without file
                db.update_job(job.job_id, status="downloading", video_url=url,
                              message="Downloading video (recovered)...")
                threading.Thread(
                    target=_download_recovered_job,
                    args=(job.job_id, url),
                    daemon=True
                ).start()
            else:
                db.update_job(job.job_id, status="error",
                              message="Task succeeded but no URL returned")
        elif api_status in ERROR_STATUSES:
            db.update_job(job.job_id, status="error",
                          message=fail_msg or "Generation failed")
        else:
            # Still genuinely processing — don't touch it
            pass
    except Exception as e:
        db.update_job(job.job_id, status="error",
                      message=f"Recovery check failed: {e}")


def _download_and_complete_job(job_id: str, video_url: str, label: str = "download") -> str | None:
    """Download a video for a job, mark it done, and refresh caches.

    Shared logic used by recovery, resume, and manual re-download paths.
    Returns the local filepath on success, or None on failure (job is
    marked as error in that case).
    """
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        return None

    # If the job already has a downloaded video, just mark done
    if job.video_path and os.path.isfile(job.video_path):
        db.update_job(job_id, status="done", message="Video ready!")
        print(f"[{label}] Job {job_id} already has video, skipping download", flush=True)
        return job.video_path

    proj = db.get_project_by_slug(job.project)
    if not proj:
        db.update_job(job_id, status="error", message="Project not found")
        return None
    assets_folder = proj.assets_folder

    filepath = download_video(
        video_url, assets_folder,
        task_id=job.task_id, model=job.model,
        prompt=job.prompt, metadata={},
    )

    db.update_job(job_id, status="done", message="Video ready!",
                  video_path=filepath)

    _invalidate_project_caches()
    _update_project_thumbnail(ASSETS_DIR / assets_folder,
                              project_slug=job.project, force=True)

    print(f"[{label}] Job {job_id} download complete: {filepath}", flush=True)
    return filepath


def _download_recovered_job(job_id: str, video_url: str):
    """Download a video for a recovered job in a background thread."""
    try:
        _download_and_complete_job(job_id, video_url, label="recover")
    except Exception as e:
        get_db().update_job(job_id, status="error",
                            message=f"Recovery download failed: {e}")


@app.post("/api/jobs/bulk-move")
def api_bulk_move_jobs(body: BulkMoveRequest, _api_key: str = Depends(verify_api_key)):
    """Move a batch of jobs (and their video files) to a different project."""
    db = get_db()
    target = db.get_project_by_slug(body.target_project)
    if not target:
        raise HTTPException(status_code=404, detail=f"Project '{body.target_project}' not found")

    target_assets = ASSETS_DIR / target.assets_folder
    target_assets.mkdir(parents=True, exist_ok=True)

    moved, not_found = 0, []
    # Track source folders by physical path so we handle half-moved jobs correctly
    # (job.project may already equal target if a previous partial move updated the DB
    # but not the file — using the actual folder is always reliable)
    affected_source_folders: set[Path] = set()

    for job_id in body.job_ids:
        job = db.get_job(job_id)
        if not job:
            not_found.append(job_id)
            continue

        new_video_path = job.video_path

        if job.video_path:
            src = Path(job.video_path)
            dst = target_assets / src.name
            if src.exists() and src != dst:
                affected_source_folders.add(src.parent)
                shutil.move(str(src), str(dst))
                new_video_path = str(dst)
                db.update_download_by_local_path(
                    src.name,
                    local_path=str(dst),
                    project=body.target_project,
                )
            elif dst.exists():
                # File already in target (previous partial move)
                new_video_path = str(dst)

        if job.project != body.target_project:
            affected_source_folders.add(
                ASSETS_DIR / (db.get_project_by_slug(job.project) or target).assets_folder
            )

        db.update_job(job_id, project=body.target_project, video_path=new_video_path)
        moved += 1

    if moved:
        _invalidate_project_caches()
        for folder in affected_source_folders:
            if folder == target_assets:
                continue
            proj = db.get_project_by_assets_folder(folder.name)
            slug = proj.slug if proj else None
            _update_project_thumbnail(folder, project_slug=slug, force=True)
        _update_project_thumbnail(target_assets, project_slug=body.target_project, force=True)

    return {"moved": moved, "not_found": not_found, "target_project": body.target_project}


@app.get("/api/jobs/{job_id}")
def api_job_status(job_id: str, _api_key: str = Depends(verify_api_key)):
    job = get_db().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Auto-recover stale non-terminal jobs (e.g. stuck at "downloading")
    if job.status not in ("done", "error"):
        age = (datetime.now() - job.updated_at).total_seconds() if job.updated_at else float("inf")
        if age > STALE_JOB_SECONDS:
            _recover_stale_job(job)
            job = get_db().get_job(job_id)  # Re-fetch after recovery

    result = job.to_dict()
    _enrich_job_result(result, job)

    # Provide a preferred image_url for the UI: prefer the temporary uploaded public URL while
    # it's still valid, otherwise fall back to the local reference stored in job params.
    try:
        preferred = _choose_preferred_image_url_from_job_dict(result)
        result['image_url'] = preferred or result.get('image_url')
    except Exception:
        pass

    return result


@app.post("/api/jobs/{job_id}/check")
def api_check_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Check the status of an incomplete job and potentially resume it."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If job is already done or error, just return current status with smart video detection
    if job.status in ("done", "error"):
        result = job.to_dict()
        _enrich_job_result(result, job)
        return result

    # If we have a task_id, check its status
    if not job.task_id:
        db.update_job(job_id, status="error", message="No task ID - cannot recover job")
        return db.get_job(job_id).to_dict()

    api_key = os.getenv("POLLO_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")

    try:
        results = get_task_status(job.task_id, api_key)
        if not results:
            db.update_job(job_id, status="error", message="No status returned from API")
            return db.get_job(job_id).to_dict()

        api_status, fail_msg, url, _credits = results[0]

        if api_status in SUCCESS_STATUSES:
            if url:
                db.update_job(job_id, status="downloading", video_url=url,
                             message="Downloading video (recovered)...")
                threading.Thread(
                    target=_download_recovered_job,
                    args=(job_id, url),
                    daemon=True
                ).start()
            else:
                db.update_job(job_id, status="error", message="Task succeeded but no URL returned")
        elif api_status in ERROR_STATUSES:
            db.update_job(job_id, status="error", message=fail_msg or "Generation failed")
        else:
            # Still processing
            db.update_job(job_id, status="processing", message=f"Task {job.task_id} still processing...")

        result = db.get_job(job_id).to_dict()
        result["video_exists"] = False
        return result

    except Exception as e:
        db.update_job(job_id, status="error", message=f"Check failed: {str(e)}")
        return db.get_job(job_id).to_dict()


@app.post("/api/jobs/{job_id}/download")
def api_download_job_video(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Download the video for a completed job that doesn't have the video file."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "done":
        raise HTTPException(status_code=400, detail="Job is not complete")

    if not job.video_url:
        raise HTTPException(status_code=400, detail="No video URL available")

    # Check if video already exists using smart detection
    exists, found_path = _find_video_for_job(job)
    if exists and found_path:
        # Update job's video_path if it was found at a different location
        if found_path != job.video_path:
            db.update_job(job_id, video_path=found_path)
        return {"message": "Video already exists", "video_path": found_path}

    try:
        db.update_job(job_id, status="downloading", message="Downloading video...")

        # Get the assets folder for the project (job.project is the slug)
        proj = db.get_project_by_slug(job.project)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        assets_folder = proj.assets_folder

        # Build metadata
        meta = {}
        if job.params_json:
            try:
                meta["payload"] = json.loads(job.params_json)
            except json.JSONDecodeError:
                pass

        filepath = download_video(
            job.video_url, assets_folder,
            task_id=job.task_id, model=job.model,
            prompt=job.prompt, metadata=meta,
        )

        db.update_job(job_id, status="done", message="Video ready!",
                     video_path=filepath)

        # Invalidate caches for this project
        _invalidate_project_caches()

        # Update project thumbnail with latest video
        _update_project_thumbnail(ASSETS_DIR / assets_folder, project_slug=job.project)

        result = db.get_job(job_id).to_dict()
        result["video_exists"] = True
        result["filename"] = Path(filepath).name
        return result

    except Exception as e:
        db.update_job(job_id, status="done", message=f"Download failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
def api_jobs(status: str | None = None, project: str | None = None, active: bool | None = None, _api_key: str = Depends(verify_api_key)):
    """All jobs (optionally filter by status, project, or active state)."""
    db = get_db()
    if active:
        # Get non-terminal jobs (still running)
        jobs = db.get_active_jobs()
    elif status:
        jobs = db.get_jobs_by_status(status)
    elif project:
        jobs = db.get_jobs_by_project(project)
    else:
        jobs = db.get_all_jobs(limit=200)

    # Get assets path for the project (if filtering by project)
    assets_path = None
    if project:
        proj = db.get_project_by_slug(project)
        if proj:
            assets_path = ASSETS_DIR / proj.assets_folder

    # Include video_exists for each job with smart detection
    result = []
    for j in jobs:
        # Auto-recover stale non-terminal jobs
        if j.status not in ("done", "error"):
            age = (datetime.now() - j.updated_at).total_seconds() if j.updated_at else float("inf")
            if age > STALE_JOB_SECONDS:
                _recover_stale_job(j)
                j = db.get_job(j.job_id)  # Re-fetch after recovery

        d = j.to_dict()

        # Use cached assets_path if same project, otherwise let function look it up
        job_assets_path = assets_path if (project and j.project == project) else None
        _enrich_job_result(d, j, job_assets_path)

        # Normalize image_url for UI/regenerate preference
        try:
            preferred = _choose_preferred_image_url_from_job_dict(d)
            d['image_url'] = preferred or d.get('image_url')
        except Exception:
            pass

        result.append(d)
    return result


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Delete a job and its associated video file."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get project for cache invalidation
    proj = db.get_project_by_slug(job.project)

    # Delete associated video file if it exists
    video_deleted = False
    if job.video_path:
        video_path = Path(job.video_path)
        if video_path.exists():
            try:
                video_path.unlink()
                video_deleted = True
            except Exception:
                pass  # Continue even if file delete fails

        # Also delete download record
        filename = video_path.name
        db.delete_download_by_path(filename)

    # Delete the job record
    db.delete_job(job_id)

    # Invalidate caches and regenerate thumbnail if we deleted a video
    if video_deleted and proj:
        _invalidate_project_caches()
        _update_project_thumbnail(ASSETS_DIR / proj.assets_folder, project_slug=job.project, force=True)
        _cleanup_thumb_cache()

    return {"deleted": True, "job_id": job_id, "video_deleted": video_deleted}


def _set_job_archived(job_id: str, archived: bool) -> JobArchivedResult:
    """Toggle archive status on a job and regenerate its project thumbnail."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.update_job(job_id, archived=archived)

    # Regenerate thumbnail since the (un)archived video affects which is latest
    proj = db.get_project_by_slug(job.project)
    if proj:
        _invalidate_project_caches()
        _update_project_thumbnail(ASSETS_DIR / proj.assets_folder, project_slug=job.project, force=True)

    return {"archived": archived, "job_id": job_id}


@app.post("/api/jobs/{job_id}/archive")
def api_archive_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Archive a job (hide from gallery)."""
    return _set_job_archived(job_id, True)


@app.post("/api/jobs/{job_id}/unarchive")
def api_unarchive_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Unarchive a job (show in gallery again)."""
    return _set_job_archived(job_id, False)


# ── Projects ────────────────────────────────────────────────────────

@app.get("/api/projects")
def api_list_projects(archived: bool | None = None, _api_key: str = Depends(verify_api_key)):
    db = get_db()
    projects = db.get_all_projects(archived=archived)
    result = []

    for p in projects:
        assets_path = ASSETS_DIR / p.assets_folder
        videos = _get_video_list(assets_path) if assets_path.exists() else []

        # Check for a local image file (including thumb.jpg)
        thumb_path = assets_path / "thumb.jpg"
        has_thumb = assets_path.exists() and thumb_path.exists()
        has_local_image = assets_path.exists() and any(
            (assets_path / f"image{ext}").exists()
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")
        )
        has_image = has_thumb or has_local_image or len(videos) > 0

        # Use thumb mtime as cache-buster so frontend refetches after regeneration
        thumb_ts = ""
        if has_thumb:
            try:
                thumb_ts = str(int(thumb_path.stat().st_mtime))
            except Exception:
                pass

        result.append({
            "slug": p.slug,
            "name": p.name,
            "prompt": (p.prompt or "")[:300],
            "image_url": p.image_url or "",
            "video_url": p.video_url or "",
            "subject_url": p.subject_url or "",
            "audio_url": p.audio_url or "",
            "video_count": len(videos),
            "has_image": has_image,
            "thumb_ts": thumb_ts,
            "archived": p.archived,
            "last_modified": p.updated_at,
        })

    return result


@app.get("/api/projects/{project}")
def api_get_project(project: str, archived: bool | None = None, _api_key: str = Depends(verify_api_key)):
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    assets_path = ASSETS_DIR / proj.assets_folder

    # Use cached video list (sorted by mtime — returns (path, mtime) tuples)
    videos_with_mtime = _get_video_list(assets_path, sort_by_mtime=True)

    jobs = db.get_jobs_by_project(project)

    # Build a lookup dict for faster job matching
    job_by_filename = {}
    for j in jobs:
        if j.video_path:
            filename = Path(j.video_path).name
            job_by_filename[filename] = j

    # Fallback: for any video files on disk that didn't match a job above,
    # search all jobs whose video_path filename lands in this folder.
    # This recovers half-moved jobs (DB project updated but file not yet moved).
    unmatched_filenames = {v.name for v, _ in videos_with_mtime} - set(job_by_filename)
    if unmatched_filenames:
        for j in db.get_all_jobs_with_video_in_folder(str(assets_path)):
            filename = Path(j.video_path).name
            if filename in unmatched_filenames:
                job_by_filename[filename] = j
                # Repair: realign job.project to match where the file actually lives
                db.update_job(j.job_id, project=project, video_path=str(assets_path / filename))

    # Build video list with associated job info, filtering by archived status
    video_list = []
    for v, mtime in videos_with_mtime:
        video_info = {"filename": v.name, "mtime": mtime}

        # Find the job that created this video using lookup dict
        matched_job = job_by_filename.get(v.name)
        if matched_job:
            video_info["job"] = matched_job.to_dict()

        # Filter by archived status if specified
        if archived is not None:
            job_archived = matched_job.archived if matched_job else False
            if job_archived != archived:
                continue

        video_list.append(video_info)

    # Build job dicts and normalize image_url for UI/regenerate preference
    job_dicts = []
    for j in jobs:
        jd = j.to_dict()
        try:
            preferred = _choose_preferred_image_url_from_job_dict(jd)
            jd['image_url'] = preferred or jd.get('image_url')
        except Exception:
            pass
        job_dicts.append(jd)

    return {
        "slug": proj.slug,
        "name": proj.name,
        "assets_folder": proj.assets_folder,
        "prompt": proj.prompt or "",
        "image_url": proj.image_url or "",
        "video_url": proj.video_url or "",
        "subject_url": proj.subject_url or "",
        "audio_url": proj.audio_url or "",
        "archived": proj.archived,
        "videos": video_list,
        "jobs": job_dicts,
    }


@app.post("/api/projects")
def api_create_project(data: ProjectCreate, _api_key: str = Depends(verify_api_key)):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    db = get_db()
    project = db.create_project(
        name=name,
    )

    # Create assets folder
    assets_path = ASSETS_DIR / project.assets_folder
    assets_path.mkdir(parents=True, exist_ok=True)

    # Update with optional fields
    updates = {}
    if data.prompt:
        updates["prompt"] = data.prompt.strip()
    if data.image_url:
        updates["image_url"] = data.image_url.strip()
    if data.video_url:
        updates["video_url"] = data.video_url.strip()
    if data.subject_url:
        updates["subject_url"] = data.subject_url.strip()
    if data.audio_url:
        updates["audio_url"] = data.audio_url.strip()

    if updates:
        project = db.update_project(project.slug, **updates)

    return {"slug": project.slug, "name": project.name, "created": True}


@app.put("/api/projects/{project}")
def api_update_project(project: str, data: ProjectUpdate, _api_key: str = Depends(verify_api_key)):
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = {}
    if data.name is not None:
        updates["name"] = data.name.strip()
    if data.prompt is not None:
        updates["prompt"] = data.prompt.strip() or None
    if data.image_url is not None:
        updates["image_url"] = data.image_url.strip() or None
    if data.video_url is not None:
        updates["video_url"] = data.video_url.strip() or None
    if data.subject_url is not None:
        updates["subject_url"] = data.subject_url.strip() or None
    if data.audio_url is not None:
        updates["audio_url"] = data.audio_url.strip() or None

    if updates:
        proj = db.update_project(project, **updates)

    return {"slug": proj.slug, "name": proj.name, "updated": True}


def _set_project_archived(project: str, archived: bool) -> ProjectArchivedResult:
    """Toggle archive status on a project."""
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    db.update_project(project, archived=archived)
    _invalidate_project_caches()

    return {"archived": archived, "slug": project}


@app.post("/api/projects/{project}/archive")
def api_archive_project(project: str, _api_key: str = Depends(verify_api_key)):
    """Archive a project (hide from main listing)."""
    return _set_project_archived(project, True)


@app.post("/api/projects/{project}/unarchive")
def api_unarchive_project(project: str, _api_key: str = Depends(verify_api_key)):
    """Unarchive a project (show in main listing again)."""
    return _set_project_archived(project, False)


@app.delete("/api/projects/{project}")
def api_delete_project(project: str, _api_key: str = Depends(verify_api_key)):
    """Delete a project, all its jobs, and all its video/asset files."""
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    assets_path = ASSETS_DIR / proj.assets_folder

    # Count files before deletion for response
    files_deleted = 0
    if assets_path.exists():
        files_deleted = sum(1 for f in assets_path.iterdir() if f.is_file())
        try:
            shutil.rmtree(assets_path)
        except Exception:
            pass

    # Delete the project (cascade deletes jobs too)
    db.delete_project(project)

    # Invalidate caches
    _invalidate_project_caches()

    # Clean up orphaned thumbnail cache
    _cleanup_thumb_cache()

    return {"deleted": True, "slug": project, "files_deleted": files_deleted}


# ── Video/Image serving ─────────────────────────────────────────────

def _safe_filename(filename: str) -> str:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


@app.get("/video/{project}/{filename}")
def serve_video(project: str, filename: str):
    """Serve a video file. Project can be slug or assets_folder."""
    _safe_filename(filename)
    # Use cached lookup first
    assets_folder = _get_project_assets_folder(project)
    if not assets_folder:
        # Fall back to assuming it's already an assets folder (backward compat)
        assets_folder = project

    video_path = ASSETS_DIR / assets_folder / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Videos are immutable, cache for a long time
    return FileResponse(
        video_path, 
        media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=31536000, immutable"}
    )


@app.get("/video-thumb/{project}/{filename}")
def serve_video_thumb(project: str, filename: str):
    """Serve a thumbnail (first frame) of a specific video."""
    _safe_filename(filename)
    # Use cached lookup first
    assets_folder = _get_project_assets_folder(project)
    if not assets_folder:
        # Fall back to assuming it's already an assets folder (backward compat)
        assets_folder = project

    video_path = ASSETS_DIR / assets_folder / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    frame_data = _extract_first_frame(video_path)
    if frame_data:
        # Thumbnails are derived from immutable videos, cache for a long time
        return Response(
            content=frame_data, 
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )
    raise HTTPException(status_code=404, detail="Could not extract frame")


@app.delete("/api/videos/{project}/{filename}")
def api_delete_video(project: str, filename: str, _api_key: str = Depends(verify_api_key)):
    """Delete a video file and its associated database records."""
    _safe_filename(filename)
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    video_path = ASSETS_DIR / proj.assets_folder / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    try:
        # Delete the video file
        video_path.unlink()

        # Delete associated job record (matches by video_path)
        db.delete_job_by_video_path(filename)

        # Delete associated download record
        db.delete_download_by_path(filename)

        # Invalidate caches for this project
        _invalidate_project_caches()

        # Update project thumbnail to reflect new latest video (force since we deleted)
        _update_project_thumbnail(ASSETS_DIR / proj.assets_folder, project_slug=project, force=True)

        # Clean up orphaned thumbnail cache for the deleted video
        _cleanup_thumb_cache()

        return {"deleted": True, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/image/{project}")
def serve_image(project: str):
    """Serve the project's thumbnail image.
    Priority: thumb.jpg (latest video frame) > image.* (source image)
    """
    # Use cached lookup
    assets_folder = _get_project_assets_folder(project)
    if not assets_folder:
        raise HTTPException(status_code=404, detail="Project not found")

    # IMPORTANT: Always use ASSETS_DIR (data folder) not ROOT_DIR
    assets_path = ASSETS_DIR / assets_folder
    thumb_path = assets_path / "thumb.jpg"

    # Update thumbnail if needed (only regenerates if missing or stale)
    _update_project_thumbnail(assets_path, project_slug=project)

    # Serve the thumbnail if it exists
    if thumb_path.exists():
        return FileResponse(
            thumb_path, 
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"}  # Always revalidate
        )

    # Second, try to find an existing source image file
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        img = assets_path / f"image{ext}"
        if img.exists():
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "webp": "image/webp", "gif": "image/gif"}[ext.lstrip(".")]
            return FileResponse(
                img, 
                media_type=mime,
                headers={"Cache-Control": "public, max-age=3600"}
            )

    raise HTTPException(status_code=404, detail="Image not found")


# ── Models info ─────────────────────────────────────────────────────

@app.get("/api/models")
def api_models():
    return MODEL_INFO


# ── Usage / Credit tracking ─────────────────────────────────────────

@app.get("/api/usage/balance")
def api_usage_balance(_api_key: str = Depends(verify_api_key)):
    """Fetch current credit balance from the Pollo API."""
    api_key = os.getenv("POLLO_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")

    balance = get_credit_balance(api_key)
    if balance is None:
        raise HTTPException(status_code=502, detail="Failed to fetch credit balance from Pollo API")

    return balance


@app.get("/api/usage")
def api_usage(days: int = 30, _api_key: str = Depends(verify_api_key)):
    """Get credit usage summary.

    Uses actual credit costs from the Pollo API (stored per job).
    For older jobs without stored credits, falls back to estimation.
    Returns total credits used, breakdown by model, and daily usage.
    """
    db = get_db()
    jobs = db.get_all_jobs(limit=10000)

    # Filter to jobs within the time window
    cutoff = datetime.now().timestamp() - (days * 86400)
    recent_jobs = [
        j for j in jobs
        if j.created_at and j.created_at.timestamp() > cutoff
    ]

    total_credits = 0
    by_model: dict[str, dict] = {}
    by_day: dict[str, int] = {}
    by_project: dict[str, dict] = {}

    for j in recent_jobs:
        # Only count jobs that were actually sent (not purely errored before sending)
        if j.status == "error" and not j.task_id:
            continue

        # Use actual credits from the API (backfilled via migration)
        # Jobs without credits_used (e.g. failed) count as 0
        credits = j.credits_used or 0

        total_credits += credits

        # By model
        if j.model not in by_model:
            by_model[j.model] = {"credits": 0, "count": 0, "label": MODEL_INFO.get(j.model, {}).get("label", j.model)}
        by_model[j.model]["credits"] += credits
        by_model[j.model]["count"] += 1

        # By day
        day_key = j.created_at.strftime("%Y-%m-%d") if j.created_at else "unknown"
        by_day[day_key] = by_day.get(day_key, 0) + credits

        # By project — track credits and per-status counts
        if j.project not in by_project:
            by_project[j.project] = {"credits": 0, "total": 0, "done": 0, "error": 0}
        by_project[j.project]["credits"] += credits
        by_project[j.project]["total"] += 1
        if j.status == "done":
            by_project[j.project]["done"] += 1
        elif j.status == "error":
            by_project[j.project]["error"] += 1

    # Sort daily usage chronologically
    sorted_days = sorted(by_day.items())

    # Sort projects by usage (top spenders first)
    sorted_projects = sorted(by_project.items(), key=lambda x: x[1]["credits"], reverse=True)[:10]

    return {
        "days": days,
        "total_credits": total_credits,
        "total_generations": len(recent_jobs),
        "by_model": by_model,
        "by_day": sorted_days,
        "by_project": [
            {"project": p, "credits": info["credits"],
             "total": info["total"], "done": info["done"], "error": info["error"]}
            for p, info in sorted_projects
        ],
    }


@app.get("/api/usage/project/{project_slug}")
def api_usage_project_details(project_slug: str, days: int = 30, _api_key: str = Depends(verify_api_key)):
    """Get per-generation credit details for a project (used in usage view expansion)."""
    db = get_db()
    jobs = db.get_jobs_by_project(project_slug)

    cutoff = datetime.now().timestamp() - (days * 86400)
    recent_jobs = [
        j for j in jobs
        if j.created_at and j.created_at.timestamp() > cutoff
    ]

    proj = db.get_project_by_slug(project_slug)
    assets_path = ASSETS_DIR / proj.assets_folder if proj else None

    result = []
    for j in recent_jobs:
        # Skip jobs that were never sent
        if j.status == "error" and not j.task_id:
            continue
        credits = j.credits_used or 0
        d = {
            "job_id": j.job_id,
            "model": j.model,
            "status": j.status,
            "credits_used": credits,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "message": j.message,
            "video_path": j.video_path,
            "video_exists": False,
            "filename": None,
        }
        # Check if video exists for thumbnail
        if j.video_path and assets_path:
            vp = Path(j.video_path)
            if vp.exists():
                d["video_exists"] = True
                d["filename"] = vp.name
        result.append(d)

    return result


# ── Cache management ────────────────────────────────────────────────

@app.post("/api/cache/clear")
def api_clear_cache(_api_key: str = Depends(verify_api_key)):
    """Clear all in-memory caches. Useful after manual file changes."""
    _invalidate_project_caches()
    return {"cleared": True, "message": "All caches cleared"}


@app.post("/api/cache/cleanup-thumbnails")
def api_cleanup_thumbnails(_api_key: str = Depends(verify_api_key)):
    """Remove orphaned thumbnail cache files whose source videos no longer exist."""
    removed = _cleanup_thumb_cache()
    return {"removed": removed, "message": f"Removed {removed} orphaned thumbnail(s)"}


# ── Source image upload & litterbox relay ────────────────────────────

SOURCE_IMAGE_ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _get_local_image_path(assets_path: Path, image_url: str) -> Path | None:
    """Resolve a local:filename image_url to a file path. Returns None if not found."""
    if not image_url or not image_url.startswith("local:"):
        return None
    filename = image_url[6:]  # strip "local:"
    # Safety: no path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return None
    p = assets_path / filename
    return p if p.exists() else None


def _upload_to_litterbox(filepath: Path) -> str:
    """Upload a file to litterbox.catbox.moe and return the public URL.
    Fails fast (12 s timeout, no retry) so VPN/Cloudflare blocks surface immediately."""
    try:
        with open(filepath, "rb") as f:
            resp = _requests.post(
                LITTERBOX_URL,
                data={"reqtype": "fileupload", "time": LITTERBOX_EXPIRY},
                files={"fileToUpload": (filepath.name, f)},
                timeout=(8, 15),  # (connect, read) — read is server response time only, not upload duration
            )

        if resp.status_code != 200 or not resp.text.startswith("https://"):
            body = resp.text[:200].strip()
            reason = f"HTTP {resp.status_code}" + (f" — {body}" if body else "")
            print(f"[Litterbox] Upload failed — {reason}")
            raise ValueError(f"Litterbox upload failed — {reason}")

        return resp.text.strip()
    except _requests.exceptions.Timeout as exc:
        reason = f"timed out ({exc})"
        print(f"[Litterbox] Upload failed — {reason}")
        raise ValueError(f"Litterbox upload timed out — cycle VPN if blocked") from exc
    except (
        _requests.exceptions.SSLError,
        _requests.exceptions.ConnectionError,
    ) as exc:
        reason = f"{type(exc).__name__}: {exc}"
        print(f"[Litterbox] Upload failed — {reason}")
        raise ValueError(f"Litterbox upload failed — {reason}") from exc


def _parse_litterbox_expiry(expiry: str) -> int:
    """Parse expiry strings like '1h', '12h' into seconds. Defaults to 3600 if unknown."""
    try:
        if expiry.endswith('h'):
            hours = int(expiry[:-1])
            return hours * 3600
        return int(expiry)
    except Exception:
        return 3600


def _choose_preferred_image_url_from_job_dict(job_dict: dict) -> str | None:
    """Given a job.to_dict() result (with parsed 'params' if present), choose the
    best image URL to use for UI/regeneration. Preference order for UI input:
      1. local:... reference recorded in params (so the regenerate input shows the permanent local ref)
      2. uploaded public URL if recorded and not yet expired
      3. job.image_url (fallback)
    Returns a string or None.
    """
    params = job_dict.get('params') or {}
    public = job_dict.get('image_url')
    uploaded = params.get('source_uploaded') or None
    uploaded_at = params.get('source_uploaded_at')
    local = params.get('source_local') or None

    # Prefer local if present (so the UI's Source Image input shows the permanent local reference)
    if local:
        return local

    # If we have an uploaded URL and timestamp, check expiry and use it if still valid
    if uploaded and uploaded_at:
        try:
            expiry_secs = _parse_litterbox_expiry(LITTERBOX_EXPIRY)
            if int(time.time()) - int(uploaded_at) < expiry_secs:
                return uploaded
        except Exception:
            pass


    # Fallback to job.image_url
    # If the job.image_url looks like a litterbox/catbox temporary URL, prefer the project's
    # stored image_url if that is a local: reference (this covers older jobs where the job
    # image_url is the uploaded public URL but the project still has a local copy).
    try:
        if public and ("catbox" in public or "litterbox" in public) and job_dict.get('project'):
            proj = get_db().get_project_by_slug(job_dict.get('project'))
            if proj and proj.image_url and str(proj.image_url).startswith("local:"):
                return proj.image_url
    except Exception:
        pass

    return public


async def _save_uploaded_image(project: str, file: UploadFile, prefix: str) -> dict:
    """Shared helper: validate and save an uploaded image to a project's assets folder.

    Args:
        project: project slug
        file: the uploaded file
        prefix: filename prefix (e.g. 'src' or 'ref') to avoid collisions

    Returns:
        dict with uploaded info including the project object reference
    """
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    content_type = file.content_type or ""
    if content_type not in SOURCE_IMAGE_ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {content_type}. "
                   f"Allowed: {', '.join(SOURCE_IMAGE_ALLOWED_TYPES.keys())}",
        )

    data = await file.read()
    if len(data) > SOURCE_IMAGE_MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large ({len(data) // 1024 // 1024}MB). Max: {SOURCE_IMAGE_MAX_SIZE // 1024 // 1024}MB",
        )

    # Validate actual file content regardless of client-supplied content-type
    try:
        img = _PILImage.open(_io.BytesIO(data))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file — could not be parsed as an image")

    assets_path = ASSETS_DIR / proj.assets_folder
    assets_path.mkdir(parents=True, exist_ok=True)

    ext = SOURCE_IMAGE_ALLOWED_TYPES[content_type]
    filename = f"{prefix}-{uuid.uuid4().hex[:12]}{ext}"
    dest = assets_path / filename
    dest.write_bytes(data)

    local_ref = f"local:{filename}"

    return {
        "uploaded": True,
        "filename": filename,
        "size": len(data),
        "image_url": local_ref,
        "_proj": proj,
        "_project_slug": project,
    }


@app.post("/api/projects/{project}/source-image")
async def api_upload_source_image(project: str, file: UploadFile = File(...), _api_key: str = Depends(verify_api_key)):
    """Upload a source image for a project.

    Saved permanently with a unique name (src-{uuid}.ext) so multiple
    images can coexist.  Returns the local reference to use as image_url.
    """
    result = await _save_uploaded_image(project, file, prefix="src")

    # Update project's default image_url to this upload
    db = get_db()
    db.update_project(project, image_url=result["image_url"])
    _invalidate_project_caches()

    # Strip internal keys before returning
    result.pop("_proj", None)
    result.pop("_project_slug", None)
    return result


@app.get("/api/projects/{project}/source-image")
def api_get_source_image(project: str, f: str | None = None, _api_key: str = Depends(verify_api_key)):
    """Serve a project's uploaded source image.

    If ?f=filename is given, serve that specific file.
    Otherwise serve the project's current image_url if it's local.
    """
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    assets_path = ASSETS_DIR / proj.assets_folder

    # Determine which file to serve
    if f:
        # Serve specific file by name
        _safe_filename(f)
        source = assets_path / f
    else:
        # Serve project's current local image
        source_ref = proj.image_url or ""
        resolved = _get_local_image_path(assets_path, source_ref)
        source = resolved

    if not source or not source.exists():
        raise HTTPException(status_code=404, detail="Source image not found")

    ext = source.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return FileResponse(
        source,
        media_type=media_types.get(ext, "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.post("/api/projects/{project}/ref-image")
async def api_upload_ref_image(project: str, file: UploadFile = File(...), _api_key: str = Depends(verify_api_key)):
    """Upload a reference image for a project.

    Uses 'ref-' prefix to distinguish from source images (src-).
    Does NOT update the project's image_url.
    Returns the local reference (local:filename) to use in a ref's url field.
    """
    result = await _save_uploaded_image(project, file, prefix="ref")

    # Strip internal keys before returning
    result.pop("_proj", None)
    result.pop("_project_slug", None)
    return result


@app.delete("/api/projects/{project}/source-image")
def api_delete_source_image(project: str, f: str | None = None, _api_key: str = Depends(verify_api_key)):
    """Remove a source image.

    If ?f=filename, delete that specific file.
    Otherwise delete the project's current local image.
    """
    db = get_db()
    proj = db.get_project_by_slug(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    assets_path = ASSETS_DIR / proj.assets_folder

    if f:
        _safe_filename(f)
        target = assets_path / f
    else:
        target = _get_local_image_path(assets_path, proj.image_url or "")

    deleted = False
    if target and target.exists():
        target.unlink()
        deleted = True

    # Clear project image_url if it pointed to the deleted file
    if proj.image_url and proj.image_url.startswith("local:"):
        deleted_name = f if f else proj.image_url[6:]
        if proj.image_url == f"local:{deleted_name}":
            db.update_project(project, image_url=None)

    _invalidate_project_caches()
    return {"deleted": deleted}


# ── Startup: Resume polling for incomplete jobs ─────────────────────

def resume_polling_job(job):
    """Resume polling for a job that was interrupted (e.g., server restart)."""
    db = get_db()
    api_key = os.getenv("POLLO_API_KEY")

    if not api_key:
        db.update_job(job.job_id, status="error", message="Cannot resume: API key not configured")
        return

    print(f"[Startup] Resuming polling for job {job.job_id} (task {job.task_id})")

    # Touch updated_at so the stale-job recovery doesn't interfere
    db.update_job(job.job_id, message="Resuming after restart...")

    def _check_already_resolved():
        """Return True to abort polling if another path resolved this job."""
        current = db.get_job(job.job_id)
        if current and current.status in ("done", "error"):
            if current.status == "done" and current.video_url and not current.video_path:
                # Recovered to "done" but no file → continue to download
                return False
            print(f"[Job {job.job_id}] Already resolved (status={current.status}), stopping", flush=True)
            return True
        return False

    try:
        results = _poll_task(job.job_id, job.task_id, api_key,
                             on_poll=_check_already_resolved)

        if results is None:
            # Polling aborted — check if job was recovered to done-without-file
            current = db.get_job(job.job_id)
            if not (current and current.status == "done" and current.video_url and not current.video_path):
                return  # Error already recorded or job fully resolved by another path
            url = current.video_url
            print(f"[Job {job.job_id}] Recovered to done without video, downloading...", flush=True)
        else:
            video_urls = [r[2] for r in results if r[0] in SUCCESS_STATUSES and r[2]]
            if not video_urls:
                db.update_job(job.job_id, status="error", message="No video URL in result")
                return
            url = video_urls[0]

        db.update_job(job.job_id, status="downloading", message="Downloading video...", video_url=url)

        _download_and_complete_job(job.job_id, url, label="resume")

    except Exception as e:
        db.update_job(job.job_id, status="error", message=f"Resume failed: {str(e)}")


def startup_resume_jobs():
    """On server start, resume polling for any jobs stuck in processing."""
    db = get_db()

    # Clean up orphaned thumbnail cache files
    _cleanup_thumb_cache()

    # Find jobs that have a task_id but are still processing
    processing_jobs = [j for j in db.get_active_jobs() if j.task_id and j.status == "processing"]

    if processing_jobs:
        print(f"[Startup] Found {len(processing_jobs)} incomplete job(s) to resume")
        for job in processing_jobs:
            threading.Thread(target=resume_polling_job, args=(job,), daemon=True).start()
    else:
        print("[Startup] No incomplete jobs to resume")


# ── VPN (Gluetun) control ─────────────────────────────────────────────
# Docs: https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md
GLUETUN_API = "http://127.0.0.1:8000"
GLUETUN_API_KEY = os.getenv("GLUETUN_API_KEY", "")
_GLUETUN_HEADERS = {"X-API-Key": GLUETUN_API_KEY} if GLUETUN_API_KEY else {}

ALLOWED_VPN_COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Australia",
    "Germany", "France", "Netherlands", "Japan", "Singapore",
    "Switzerland", "Sweden", "Brazil", "India", "South Korea",
    "Italy", "Spain", "Norway", "Denmark", "Ireland",
]


def _gluetun_get(path: str, timeout: int = 3):
    return _requests.get(f"{GLUETUN_API}{path}", headers=_GLUETUN_HEADERS, timeout=timeout)


def _gluetun_put(path: str, body: dict, timeout: int = 5):
    return _requests.put(f"{GLUETUN_API}{path}", json=body, headers=_GLUETUN_HEADERS, timeout=timeout)


@app.get("/api/vpn/status")
def vpn_status(_api_key: str = Depends(verify_api_key)):
    """Get current VPN status, public IP, and settings from Gluetun."""
    out: dict[str, Any] = {}
    # VPN tunnel status
    try:
        r = _gluetun_get("/v1/vpn/status")
        out["vpn"] = r.json() if r.ok else {"status": "unknown"}
    except Exception:
        out["vpn"] = {"status": "unreachable"}
    # Public IP (also contains country/region info)
    try:
        r = _gluetun_get("/v1/publicip/ip", timeout=5)
        out["public_ip"] = r.json() if r.ok else {}
    except Exception:
        out["public_ip"] = {}
    # Current server country from settings (with public_ip country as fallback)
    try:
        r = _gluetun_get("/v1/vpn/settings")
        if r.ok:
            settings = r.json()
            out["server_countries"] = settings.get("server_countries", [])
        else:
            out["server_countries"] = []
    except Exception:
        out["server_countries"] = []
    # Fallback: if settings returned no country, use country from public IP lookup
    if not out["server_countries"] and out["public_ip"].get("country"):
        out["server_countries"] = [out["public_ip"]["country"]]
    return out


@app.post("/api/vpn/restart")
def vpn_restart(_api_key: str = Depends(verify_api_key)):
    """Restart the VPN tunnel by cycling Gluetun's status off then on."""
    try:
        _gluetun_put("/v1/vpn/status", {"status": "stopped"})
        time.sleep(2)
        r = _gluetun_put("/v1/vpn/status", {"status": "running"})
        if r.ok:
            return {"ok": True, "message": "VPN tunnel restarted — new IP in ~10s"}
        return {"ok": False, "message": f"Gluetun responded {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, detail=f"Cannot reach Gluetun control server: {e}")


@app.put("/api/vpn/country")
def vpn_change_country(data: VpnCountryRequest, _api_key: str = Depends(verify_api_key)):
    """Change VPN server country. Body: {"country": "United Kingdom"}"""
    country = data.country.strip()
    if not country:
        raise HTTPException(400, detail="Missing 'country' field")
    if country not in ALLOWED_VPN_COUNTRIES:
        raise HTTPException(
            400,
            detail=f"Invalid country: '{country}'. Allowed: {', '.join(ALLOWED_VPN_COUNTRIES)}",
        )
    try:
        # Update server selection
        r = _gluetun_put("/v1/vpn/settings", {"server_countries": [country]})
        if not r.ok:
            return {"ok": False, "message": f"Gluetun responded {r.status_code}: {r.text}"}
        return {"ok": True, "message": f"Switching to {country} — new IP in ~10s"}
    except Exception as e:
        raise HTTPException(502, detail=f"Cannot reach Gluetun control server: {e}")


@app.get("/api/vpn/countries")
def vpn_countries():
    """Return the list of allowed VPN server countries."""
    return {"countries": ALLOWED_VPN_COUNTRIES}


# ── Serve Vue frontend (production build) ────────────────────────────
STATIC_DIR = WEB_DIR / "static"
if STATIC_DIR.is_dir():
    # Serve static assets (js, css, etc.)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{path:path}")
    def serve_frontend(path: str):
        """Catch-all: serve the Vue SPA index.html for any non-API route."""
        file = STATIC_DIR / path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")


# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Starting Pollo API Server...")
    print("API: http://localhost:5000")
    print("Docs: http://localhost:5000/docs")
    uvicorn.run(app, host="127.0.0.1", port=5000)
