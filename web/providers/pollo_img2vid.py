import uuid
from time import sleep

from web.core.download import download_image, download_video
from web.core.get_task import get_task_status
from web.core.metadata import get_db
from web.core.spinner import Spinner

from .pollo_engine import (
    ERROR_STATUSES,
    GENERATORS,
    GENERATORS_LEGACY,
    GENERATORS_V1,
    IMAGE_GENERATORS,
    IMAGE_GENERATORS_LEGACY,
    IMAGE_GENERATORS_V1,
    SUCCESS_STATUSES,
)
from .pollo_engine import image_generator as get_image_generator
from .pollo_engine import video_generator as get_video_generator

__all__ = [
    "ERROR_STATUSES",
    "GENERATORS",
    "GENERATORS_LEGACY",
    "GENERATORS_V1",
    "IMAGE_GENERATORS",
    "IMAGE_GENERATORS_LEGACY",
    "IMAGE_GENERATORS_V1",
    "SUCCESS_STATUSES",
    "create_video",
    "get_image_generator",
    "get_video_generator",
]

DEFAULT_MODEL = "seedance20fastv1"


def _check_choice(gen_cls, attr: str, value, what: str, model: str, default: tuple = ()) -> None:
    """ValueError if `value` is set and not among the generator's `attr`
    choices (or `default` when it lists none; no choices = anything goes)."""
    choices = getattr(gen_cls, attr, None) or default
    if value is not None and value != "" and choices and value not in choices:
        raise ValueError(f"Invalid {what} {value} for {model}. Valid: {', '.join(str(c) for c in choices)}")


CF_MAX_RETRIES = 6  # consecutive Cloudflare-blocked polls (~3 minutes) before giving up
POLL_SECONDS = 10


def create_video(
    model: str | None = None,
    project: str | None = None,
    aspect_ratio: str | None = None,
    length: int | None = None,
    resolution: str | None = None,
    generate_audio: bool | None = None,
    image_url: str | None = None,
    subject_url: str | None = None,
    seed: int | None = None,
    image_tail: str | None = None,
    negative_prompt: str | None = None,
    audio_url: str | None = None,
    refs: list | None = None,
    video_num: int | None = None,
    image_meta: list | None = None,
    num_outputs: int | None = None,
    api_key: str | None = None,
) -> None:
    """Generate a video from the command line: send the task, poll it and
    download the result, recording a job like the web interface does."""
    model = model or DEFAULT_MODEL
    # Validate against the generator spec before spending credits
    gen_cls = GENERATORS.get(model)
    if gen_cls is None:
        raise ValueError(f"Unknown model: {model}. Available: {', '.join(GENERATORS)}")
    _check_choice(gen_cls, "VALID_LENGTHS", length, "length", model)
    _check_choice(gen_cls, "VALID_RATIOS", aspect_ratio, "ratio", model)
    _check_choice(gen_cls, "VALID_RESOLUTIONS", resolution, "resolution", model, default=("480p", "720p", "1080p"))

    # Only what was given, so the generator falls back to the project's files and env defaults
    given = {"project": project, "aspect_ratio": aspect_ratio, "resolution": resolution}
    optional = {
        "length": length,
        "generate_audio": generate_audio,
        "image_url": image_url,
        "subject_url": subject_url,
        "seed": seed,
        "image_tail": image_tail,
        "negative_prompt": negative_prompt,
        "audio_url": audio_url,
        "num_outputs": num_outputs,
        "refs": refs,
        "video_num": video_num,
        "image_meta": image_meta,
        "api_key": api_key,
    }
    kwargs = {k: v for k, v in given.items() if v} | {k: v for k, v in optional.items() if v is not None}
    generator = get_video_generator(model, **kwargs)
    print(f"Using model: {model}")

    db = get_db()
    job_id = _record_job(db, generator, model)
    _prepare_inputs(generator)
    task_id = _send_task(db, job_id, generator)
    if not task_id:
        return
    url = _poll_task(db, job_id, generator, task_id)
    if url:
        _download(db, job_id, generator, model, task_id, url)


def _record_job(db, generator, model: str) -> str:
    """A job record for the generation (the same as the web interface makes)."""
    job_id = str(uuid.uuid4())[:8]
    db.create_job(
        job_id=job_id,
        project=generator.project,
        model=model,
        prompt=generator.prompt or "",
        image_url=getattr(generator, "image_url", None),
        aspect_ratio=getattr(generator, "aspect_ratio", None),
        resolution=getattr(generator, "resolution", None),
        length=getattr(generator, "length", None) or getattr(generator, "duration", None),
        generate_audio=getattr(generator, "generate_audio", None),
    )
    return job_id


def _prepare_inputs(generator) -> None:
    """Say which kind of generation this is; image-to-video downloads its source image."""
    project = generator.project
    if getattr(generator, "is_video_edit", False):
        print(f"Creating video edit from project: {project}...")
        print(f"Source video: {generator.video_url}")
    elif getattr(generator, "refs", None):
        # Ref2video: refs are URLs, nothing to download. Truthy rather than
        # hasattr: v1 generators always define `refs`, None when not given.
        print(f"Creating ref2video from project: {project}...")
        print(f"  {len(generator.refs)} reference(s)")
    elif generator.is_text_only:
        print(f"Creating text-to-video from project: {project}...")
    else:
        print(f"Creating image-to-video from project: {project}...")
        if not generator.image_url:
            raise ValueError("image_url is required for image-to-video generation but was not provided")
        download_image(generator.image_url, project)


def _fail(db, job_id: str, message: str, *notes: str) -> None:
    db.update_job(job_id, status="error", message=message)
    for note in notes:
        print(note)


def _send_task(db, job_id: str, generator) -> str | None:
    """Send the generation request; the task id, or None (job marked failed)."""
    try:
        response = generator.send_request()
    except ConnectionError as exc:
        return _fail(db, job_id, str(exc), f"Error: {exc}")
    try:
        resp_json = response.json()
    except Exception:  # noqa: BLE001 — any unparseable body
        preview = response.text[:200] if response.text else "(empty)"
        return _fail(
            db,
            job_id,
            f"API returned non-JSON (HTTP {response.status_code}): {preview}",
            f"Error: API returned non-JSON response (HTTP {response.status_code})",
            f"Body: {preview}",
        )
    if response.status_code != 200 or resp_json.get("code") != "SUCCESS":
        error_msg = resp_json.get("message", f"API request failed (HTTP {response.status_code})")
        return _fail(db, job_id, error_msg, "Error creating task.", error_msg)

    data = resp_json.get("data", {})
    task_id, status = data.get("taskId"), data.get("status")
    if not task_id or not status:
        return _fail(db, job_id, "Task ID or status not found", "Task ID or status not found in the response.")
    db.update_job(job_id, status="processing", task_id=task_id, message=f"Task {task_id} processing...")
    print(f"Task created successfully: {task_id} status: {status}")
    return task_id


def _poll_task(db, job_id: str, generator, task_id: str) -> str | None:
    """Poll until the task finishes; the video URL, or None (job marked failed)."""
    spinner = Spinner(message="Processing")
    spinner.start()
    try:
        return _wait_for_url(db, job_id, generator, task_id)
    finally:
        spinner.stop()


def _wait_for_url(db, job_id: str, generator, task_id: str) -> str | None:
    cf_retries = 0
    while True:
        sleep(POLL_SECONDS)
        status, message, url = get_task_status(task_id, generator.api_key)[0][:3]
        if status == "cloudflare_blocked":
            cf_retries += 1
            if cf_retries >= CF_MAX_RETRIES:
                return _fail(
                    db,
                    job_id,
                    f"Cloudflare blocked polling {CF_MAX_RETRIES} times — task {task_id} may have succeeded "
                    "on the backend but we can't reach the API to confirm. Check VPN/region.",
                    f"Cloudflare blocked polling {CF_MAX_RETRIES} consecutive times. Giving up.",
                    f"Task {task_id} may still have succeeded — check manually if possible.",
                )
            backoff = min(30, 10 * cf_retries)  # 10s, 20s, 30s, 30s, ...
            print(f"\nCloudflare blocked poll attempt ({cf_retries}/{CF_MAX_RETRIES}), retrying in {backoff}s...")
            sleep(backoff)
            continue
        cf_retries = 0  # any successful poll resets it, even while still processing
        if status in ERROR_STATUSES:
            return _fail(db, job_id, message or "Generation failed", f"Video failed: {message}")
        if status in SUCCESS_STATUSES:
            if url is None:
                return _fail(db, job_id, "No video URL in result", "No video URL found in the response.")
            return url


def _download(db, job_id: str, generator, model: str, task_id: str, url: str) -> None:
    db.update_job(job_id, status="downloading", message="Downloading video...", video_url=url)
    try:
        filepath = download_video(
            url,
            generator.project,
            task_id=task_id,
            model=model,
            prompt=generator.prompt,
            metadata=generator.build_download_metadata(),
        )
    except ValueError as exc:
        return _fail(db, job_id, str(exc), f"Download validation failed: {exc}")
    db.update_job(job_id, status="done", message="Video ready!", video_path=filepath)
