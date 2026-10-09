import uuid
from time import sleep

from ..common.download import download_image, download_video
from ..common.get_task import get_task_status
from ..common.metadata import get_db
from ..common.spinner import Spinner
from .generators import (
    ERROR_STATUSES,
    SUCCESS_STATUSES,
    KlingV3ImageGeneratorV1,
    KlingV3OmniImageGeneratorV1,
    KlingV3OmniVideoGeneratorV1,
    KlingV3TurboVideoGeneratorV1,
    KlingV3VideoGeneratorV1,
    KlingV21MasterVideoGeneratorV1,
    KlingV21VideoGeneratorV1,
    KlingV25TurboVideoGeneratorV1,
    KlingV26VideoGeneratorV1,
    KlingVideoO1VideoGeneratorV1,
    MinimaxH3MaxVideoGenerator,
    MinimaxH3VideoGenerator,
    MinimaxH3VideoGeneratorV1,
    NanoBanana2ImageGenerator,
    NanoBanana2ImageGeneratorV1,
    Pollo20VideoGenerator,
    Pollo20VideoGeneratorV1,
    Pollo25VideoGenerator,
    Pollo25VideoGeneratorV1,
    Pollo30FastVideoGeneratorV1,
    Pollo30VideoGeneratorV1,
    PolloDance20FastVideoGenerator,
    PolloDance20FastVideoGeneratorV1,
    PolloDance20VideoGenerator,
    PolloDance20VideoGeneratorV1,
    PolloDanceRefFastVideoGenerator,
    PolloDanceRefVideoGenerator,
    PolloImage2ImageGenerator,
    PolloJourneyImageGenerator,
    PolloJourneyImageGeneratorV1,
    QwenImage3ImageGeneratorV1,
    QwenImage3ProImageGeneratorV1,
    QwenImageFlashImageGeneratorV1,
    QwenImageImageGenerator,
    Seedance20FastVideoGenerator,
    Seedance20FastVideoGeneratorV1,
    Seedance20MiniVideoGenerator,
    Seedance20MiniVideoGeneratorV1,
    Seedance20VideoGenerator,
    Seedance20VideoGeneratorV1,
    Seedance25VideoGenerator,
    Seedance25VideoGeneratorV1,
    SeedanceMiniRefVideoGenerator,
    SeedanceRefFastVideoGenerator,
    SeedanceRefVideoGenerator,
    SeedreamFlashImageGeneratorV1,
    SeedreamImageGenerator,
    SeedreamImageGeneratorV1,
    SeedreamProImageGeneratorV1,
    Wan27VideoGenerator,
    Wan27VideoGeneratorV1,
    Wan30PrimeVideoGenerator,
    Wan30PrimeVideoGeneratorV1,
    Wan30VideoGenerator,
    Wan30VideoGeneratorV1,
)

# Legacy (pre-v1) endpoints — kept as a fallback, only shown in the web UI
# behind the "legacy mode" toggle. See BaseV1VideoGenerator's docstring in
# generators.py for why v1 exists and how it differs.
GENERATORS_LEGACY = {
    "pollo20": Pollo20VideoGenerator,
    "pollo25": Pollo25VideoGenerator,
    "pollodance20": PolloDance20VideoGenerator,
    "pollodance20fast": PolloDance20FastVideoGenerator,
    "pollodanceref": PolloDanceRefVideoGenerator,
    "pollodancereffast": PolloDanceRefFastVideoGenerator,
    "seedance20": Seedance20VideoGenerator,
    "seedance20fast": Seedance20FastVideoGenerator,
    "seedance20mini": Seedance20MiniVideoGenerator,
    "seedance25": Seedance25VideoGenerator,
    "seedanceref": SeedanceRefVideoGenerator,
    "seedancereffast": SeedanceRefFastVideoGenerator,
    "seedanceminiref": SeedanceMiniRefVideoGenerator,
    "minimaxh3": MinimaxH3VideoGenerator,
    "wan27": Wan27VideoGenerator,
    "wan30": Wan30VideoGenerator,
    "wan30prime": Wan30PrimeVideoGenerator,
}

# Current (v1) endpoints — shown by default in the web UI.
GENERATORS_V1 = {
    "pollo20v1": Pollo20VideoGeneratorV1,
    "pollo25v1": Pollo25VideoGeneratorV1,
    "pollodance20v1": PolloDance20VideoGeneratorV1,
    "pollodance20fastv1": PolloDance20FastVideoGeneratorV1,
    "pollo30v1": Pollo30VideoGeneratorV1,
    "pollo30fastv1": Pollo30FastVideoGeneratorV1,
    "seedance20v1": Seedance20VideoGeneratorV1,
    "seedance20fastv1": Seedance20FastVideoGeneratorV1,
    "seedance20miniv1": Seedance20MiniVideoGeneratorV1,
    "seedance25v1": Seedance25VideoGeneratorV1,
    "minimaxh3v1": MinimaxH3VideoGeneratorV1,
    "minimaxh3max": MinimaxH3MaxVideoGenerator,  # v1-API-only; no legacy counterpart
    "wan27v1": Wan27VideoGeneratorV1,
    "wan30v1": Wan30VideoGeneratorV1,
    "wan30primev1": Wan30PrimeVideoGeneratorV1,
    "klingv21v1": KlingV21VideoGeneratorV1,
    "klingv21masterv1": KlingV21MasterVideoGeneratorV1,
    "klingv25turbov1": KlingV25TurboVideoGeneratorV1,
    "klingvideoo1v1": KlingVideoO1VideoGeneratorV1,
    "klingv26v1": KlingV26VideoGeneratorV1,
    "klingv3v1": KlingV3VideoGeneratorV1,
    "klingv3turbov1": KlingV3TurboVideoGeneratorV1,
    "klingv3omniv1": KlingV3OmniVideoGeneratorV1,
}

GENERATORS = {**GENERATORS_LEGACY, **GENERATORS_V1}

DEFAULT_MODEL = "seedance20fastv1"

IMAGE_GENERATORS_LEGACY = {
    "pollojourney": PolloJourneyImageGenerator,
    "seedream": SeedreamImageGenerator,
    "nanobanana2": NanoBanana2ImageGenerator,
    "polloimage2": PolloImage2ImageGenerator,
    "qwenimage": QwenImageImageGenerator,
}

IMAGE_GENERATORS_V1 = {
    "pollojourneyv1": PolloJourneyImageGeneratorV1,
    "seedreamv1": SeedreamImageGeneratorV1,
    "nanobanana2v1": NanoBanana2ImageGeneratorV1,
    "klingv3imagev1": KlingV3ImageGeneratorV1,
    "klingv3omniimagev1": KlingV3OmniImageGeneratorV1,
    "seedreamprov1": SeedreamProImageGeneratorV1,
    "seedreamflashv1": SeedreamFlashImageGeneratorV1,
    "qwenimage3v1": QwenImage3ImageGeneratorV1,
    "qwenimage3prov1": QwenImage3ProImageGeneratorV1,
    "qwenimageflashv1": QwenImageFlashImageGeneratorV1,
}

IMAGE_GENERATORS = {**IMAGE_GENERATORS_LEGACY, **IMAGE_GENERATORS_V1}


def get_video_generator(model: str, **kwargs):
    try:
        return GENERATORS[model](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported model: {model}. Available: {', '.join(GENERATORS)}") from None


def get_image_generator(model: str, **kwargs):
    try:
        return IMAGE_GENERATORS[model](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported image model: {model}. Available: {', '.join(IMAGE_GENERATORS)}") from None


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
) -> None:
    """Generate a video from the command line: send the task, poll it and
    download the result, recording a job like the web interface does."""
    model = model or DEFAULT_MODEL
    # Validate against the generator class before spending credits
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
