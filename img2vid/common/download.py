import requests
import os
import uuid
import re
import struct
import threading
from typing import Any
from urllib.parse import urlparse, unquote

from .config import ASSETS_DIR
from .metadata import record_download, get_db


# Per-task lock to prevent concurrent downloads of the same task
_download_locks: dict[str, threading.Lock] = {}
_download_locks_guard = threading.Lock()


def get_filename() -> str:
    """Generate a UUID for the file name."""
    return f"{uuid.uuid4()}.mp4"


def get_filename_from_url(url: str) -> str | None:
    """Extract a clean filename from the download URL.

    Returns the filename from the URL path, or None if it can't be extracted.
    Uses the original filename from the URL.
    """
    try:
        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = os.path.basename(path)

        # Make sure it's a valid video filename
        if not filename or not filename.endswith('.mp4'):
            return None

        # Clean up the filename - remove any query params that might have snuck in
        filename = filename.split('?')[0]

        # Sanitize: only allow alphanumeric, dash, underscore, dot
        filename = re.sub(r'[^a-zA-Z0-9_\-.]', '_', filename)

        return filename
    except Exception:
        return None


def get_unique_filepath(folder_path: str, filename: str) -> str:
    """Get a unique filepath, adding (1), (2), etc. if collision exists."""
    filepath = f"{folder_path}/{filename}"
    if not os.path.exists(filepath):
        return filepath

    # Split into name and extension
    name_part, ext = os.path.splitext(filename)

    counter = 1
    while True:
        new_filename = f"{name_part}({counter}){ext}"
        filepath = f"{folder_path}/{new_filename}"
        if not os.path.exists(filepath):
            return filepath
        counter += 1


def download_image(image_url: str, project: str, record: bool = True) -> str:
    folder_path = ASSETS_DIR / project
    folder_path.mkdir(parents=True, exist_ok=True)

    filepath = folder_path / "image.jpg"

    if filepath.exists():
        return str(filepath)  # Image already downloaded

    download_file(image_url, str(filepath))

    # Record in metadata database
    if record:
        record_download(
            url=image_url,
            local_path=str(filepath),
            file_type="image",
            project=project,
        )

    print(f"Image downloaded: {filepath}")
    return str(filepath)


def download_video(
    url: str,
    dest_path: str,
    task_id: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    metadata: dict[str, Any] | None = None,
    record: bool = True,
) -> str:
    # Acquire a per-task lock so concurrent callers for the same task
    # serialise and the second one hits the dedup check properly.
    task_lock = None
    if task_id:
        with _download_locks_guard:
            if task_id not in _download_locks:
                _download_locks[task_id] = threading.Lock()
            task_lock = _download_locks[task_id]

    if task_lock:
        task_lock.acquire()
    try:
        return _download_video_inner(
            url, dest_path, task_id=task_id, model=model,
            prompt=prompt, metadata=metadata, record=record,
        )
    finally:
        if task_lock:
            task_lock.release()
        # Clean up the lock entry to avoid unbounded growth
        if task_id:
            with _download_locks_guard:
                _download_locks.pop(task_id, None)


def _download_video_inner(
    url: str,
    dest_path: str,
    task_id: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    metadata: dict[str, Any] | None = None,
    record: bool = True,
) -> str:
    # Deduplication: if this task was already downloaded, return existing path
    if task_id and record:
        existing = get_db().get_downloads_by_task_id(task_id)
        if existing:
            path = existing[0].local_path
            if os.path.isfile(path):
                print(f"Video already downloaded for task {task_id}: {path}")
                return path

    folder_path = ASSETS_DIR / dest_path
    folder_path.mkdir(parents=True, exist_ok=True)

    # Try to get filename from URL first, fall back to UUID
    filename = get_filename_from_url(url)
    if not filename:
        filename = get_filename()

    # Get unique filepath with (1), (2) etc. for collisions
    filepath = get_unique_filepath(str(folder_path), filename)

    download_file(url, filepath)

    # Validate the downloaded video is not corrupt / truncated
    try:
        validate_video(filepath)
    except ValueError as exc:
        # Clean up the broken file so it doesn't linger
        try:
            os.remove(filepath)
        except OSError:
            pass
        raise ValueError(str(exc)) from None

    # Record in metadata database
    if record:
        record_download(
            url=url,
            local_path=filepath,
            file_type="video",
            project=dest_path,
            task_id=task_id,
            model=model,
            prompt=prompt,
            metadata=metadata,
        )

    print(f"File downloaded: {filepath}")
    return filepath


def _has_moov_atom(filepath: str) -> bool:
    """Check that an MP4 file contains a moov atom (required metadata box).

    Walks the top-level ISO-BMFF boxes looking for 'moov'.  Returns False if
    the file is too small, truncated, or the moov box is simply missing.
    """
    try:
        size = os.path.getsize(filepath)
        if size < 8:
            return False
        with open(filepath, 'rb') as f:
            pos = 0
            while pos < size:
                f.seek(pos)
                header = f.read(8)
                if len(header) < 8:
                    break
                box_size, box_type = struct.unpack('>I4s', header)
                box_type = box_type.decode('ascii', errors='replace')
                if box_size == 0:
                    # box extends to end of file
                    box_size = size - pos
                elif box_size == 1:
                    # 64-bit extended size
                    ext = f.read(8)
                    if len(ext) < 8:
                        break
                    box_size = struct.unpack('>Q', ext)[0]
                if box_size < 8:
                    break
                if box_type == 'moov':
                    return True
                pos += box_size
    except Exception:
        return False
    return False


def validate_video(filepath: str) -> None:
    """Validate that a downloaded video file is usable.

    Raises ``ValueError`` with a descriptive message when the file is
    corrupt, truncated, or missing the required moov atom.
    """
    fsize = os.path.getsize(filepath)
    if fsize < 1024:
        raise ValueError(
            f"Downloaded video is too small ({fsize} bytes), likely corrupt: {filepath}"
        )
    if filepath.endswith('.mp4') and not _has_moov_atom(filepath):
        raise ValueError(
            f"Downloaded video is missing moov atom (corrupt/truncated): {filepath}"
        )


def download_file(url: str, file_dest: str) -> None:
    response = requests.get(url, stream=True, timeout=(15, 120))
    if response.status_code == 403:
        raise requests.exceptions.HTTPError(
            f"403 Forbidden — download blocked (possible VPN/geo restriction): {url}",
            response=response,
        )
    response.raise_for_status()

    with open(file_dest, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
