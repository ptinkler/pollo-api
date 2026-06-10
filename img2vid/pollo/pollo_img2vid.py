import uuid
from time import sleep

from ..common.get_task import get_task_status
from ..common.download import download_video, download_image
from ..common.spinner import Spinner
from ..common.metadata import get_db
from .generators import (
    Pollo20VideoGenerator,
    PolloDance20VideoGenerator,
    PolloDance20FastVideoGenerator,
    PolloDanceRefVideoGenerator,
    PolloDanceRefFastVideoGenerator,
    Seedance20VideoGenerator,
    Seedance20FastVideoGenerator,
    SeedanceRefVideoGenerator,
    SeedanceRefFastVideoGenerator,
    NanoBanana2ImageGenerator,
    PolloJourneyImageGenerator,
    SeedreamImageGenerator,
    SUCCESS_STATUSES,
    ERROR_STATUSES,
)


GENERATORS = {
    "pollo20": Pollo20VideoGenerator,
    "pollodance20": PolloDance20VideoGenerator,
    "pollodance20fast": PolloDance20FastVideoGenerator,
    "pollodanceref": PolloDanceRefVideoGenerator,
    "pollodancereffast": PolloDanceRefFastVideoGenerator,
    "seedance20": Seedance20VideoGenerator,
    "seedance20fast": Seedance20FastVideoGenerator,
    "seedanceref": SeedanceRefVideoGenerator,
    "seedancereffast": SeedanceRefFastVideoGenerator,
}

DEFAULT_MODEL = "seedance20fast"

IMAGE_GENERATORS = {
    "pollojourney": PolloJourneyImageGenerator,
    "seedream": SeedreamImageGenerator,
    "nanobanana2": NanoBanana2ImageGenerator,
}


def get_video_generator(model: str, **kwargs):
    try:
        return GENERATORS[model](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported model: {model}. Available: {', '.join(GENERATORS)}")


def get_image_generator(model: str, **kwargs):
    try:
        return IMAGE_GENERATORS[model](**kwargs)
    except KeyError:
        raise ValueError(f"Unsupported image model: {model}. Available: {', '.join(IMAGE_GENERATORS)}")


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
    refs: list | None = None,
    video_num: int | None = None,
    image_meta: list | None = None,
) -> None:
    model = model or DEFAULT_MODEL

    # Validate against the generator class before spending credits
    gen_cls = GENERATORS.get(model)
    if gen_cls is None:
        raise ValueError(f"Unknown model: {model}. Available: {', '.join(GENERATORS)}")

    if length is not None and hasattr(gen_cls, "VALID_LENGTHS") and gen_cls.VALID_LENGTHS:
        if length not in gen_cls.VALID_LENGTHS:
            raise ValueError(f"Invalid length {length}s for {model}. Valid: {', '.join(str(v) for v in gen_cls.VALID_LENGTHS)}")

    if aspect_ratio and hasattr(gen_cls, "VALID_RATIOS") and gen_cls.VALID_RATIOS:
        if aspect_ratio not in gen_cls.VALID_RATIOS:
            raise ValueError(f"Invalid ratio {aspect_ratio} for {model}. Valid: {', '.join(gen_cls.VALID_RATIOS)}")

    if resolution and resolution not in ("480p", "720p", "1080p"):
        raise ValueError(f"Invalid resolution {resolution}. Valid: 480p, 720p, 1080p")

    # Build kwargs from whatever was explicitly provided
    kwargs = {}
    if project:
        kwargs["project"] = project
    if aspect_ratio:
        kwargs["aspect_ratio"] = aspect_ratio
    if length is not None:
        kwargs["length"] = length
    if resolution:
        kwargs["resolution"] = resolution
    if generate_audio is not None:
        kwargs["generate_audio"] = generate_audio
    if image_url is not None:
        kwargs["image_url"] = image_url
    if subject_url is not None:
        kwargs["subject_url"] = subject_url
    if seed is not None:
        kwargs["seed"] = seed
    if image_tail is not None:
        kwargs["image_tail"] = image_tail
    if refs is not None:
        kwargs["refs"] = refs
    if video_num is not None:
        kwargs["video_num"] = video_num
    if image_meta is not None:
        kwargs["image_meta"] = image_meta

    generator = get_video_generator(model, **kwargs)
    print(f'Using model: {model}')

    # Create a job record (same as web interface)
    db = get_db()
    job_id = str(uuid.uuid4())[:8]
    db.create_job(
        job_id=job_id,
        project=generator.project,
        model=model,
        prompt=generator.prompt or "",
        image_url=getattr(generator, 'image_url', None),
        aspect_ratio=getattr(generator, 'aspect_ratio', None),
        resolution=getattr(generator, 'resolution', None),
        length=getattr(generator, 'length', None) or getattr(generator, 'duration', None),
        generate_audio=getattr(generator, 'generate_audio', None),
    )

    # Handle ref/video-edit mode
    if hasattr(generator, 'is_video_edit') and generator.is_video_edit:
        print(f'Creating video edit from project: {generator.project}...')
        print(f'Source video: {generator.video_url}')
    elif hasattr(generator, 'refs'):
        # Ref2video mode — refs are URLs, no local image download needed
        print(f'Creating ref2video from project: {generator.project}...')
        print(f'  {len(generator.refs)} reference(s)')
    elif generator.is_text_only:
        print(f'Creating text-to-video from project: {generator.project}...')
    else:
        print(f'Creating image-to-video from project: {generator.project}...')
        if not generator.image_url:
            raise ValueError("image_url is required for image-to-video generation but was not provided")
        download_image(generator.image_url, generator.project)

    try:
        response = generator.send_request()
    except ConnectionError as exc:
        db.update_job(job_id, status="error", message=str(exc))
        print(f"Error: {exc}")
        return

    try:
        resp_json = response.json()
    except Exception:
        body_preview = response.text[:200] if response.text else "(empty)"
        db.update_job(job_id, status="error",
                      message=f"API returned non-JSON (HTTP {response.status_code}): {body_preview}")
        print(f"Error: API returned non-JSON response (HTTP {response.status_code})")
        print(f"Body: {body_preview}")
        return

    if response.status_code != 200 or resp_json.get("code") != "SUCCESS":
        error_msg = resp_json.get("message", f"API request failed (HTTP {response.status_code})")
        db.update_job(job_id, status="error", message=error_msg)
        print("Error creating task.")
        print(error_msg)
        return

    task_id = resp_json.get('data', {}).get("taskId")
    status = resp_json.get('data', {}).get("status")
    url: str | None = None

    if not task_id or not status:
        db.update_job(job_id, status="error", message="Task ID or status not found")
        print("Task ID or status not found in the response.")
        return
    
    db.update_job(job_id, status="processing", task_id=task_id, message=f"Task {task_id} processing...")
    print(f"Task created successfully: {task_id} status: {status}")

    spinner = Spinner(message="Processing")
    spinner.start()

    # Polling for task status
    cf_retries = 0
    max_cf_retries = 6  # Up to ~3 minutes of CF blocks before giving up
    while status not in SUCCESS_STATUSES:
        sleep(10)
        status, message, url = get_task_status(task_id, generator.api_key)[0]

        if status == "cloudflare_blocked":
            cf_retries += 1
            if cf_retries >= max_cf_retries:
                spinner.stop()
                db.update_job(job_id, status="error",
                              message=f"Cloudflare blocked polling {max_cf_retries} times — task {task_id} may have succeeded on the backend but we can't reach the API to confirm. Check VPN/region.")
                print(f"Cloudflare blocked polling {max_cf_retries} consecutive times. Giving up.")
                print(f"Task {task_id} may still have succeeded — check manually if possible.")
                return
            backoff = min(30, 10 * cf_retries)  # 10s, 20s, 30s, 30s, ...
            print(f"\nCloudflare blocked poll attempt ({cf_retries}/{max_cf_retries}), retrying in {backoff}s...")
            sleep(backoff)
            continue

        # Reset CF counter on any successful poll (even if task is still processing)
        cf_retries = 0

        if status in ERROR_STATUSES:
            spinner.stop()
            db.update_job(job_id, status="error", message=message or "Generation failed")
            print(f"Video failed: {message}")
            return

    spinner.stop()
    if url is None:
        db.update_job(job_id, status="error", message="No video URL in result")
        print("No video URL found in the response.")
        return
    
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
        db.update_job(job_id, status="error", message=str(exc))
        print(f"Download validation failed: {exc}")
        return

    # Update job with completed status and video path
    db.update_job(job_id, status="done", message="Video ready!", video_path=filepath)

