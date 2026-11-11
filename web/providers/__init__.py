"""Model providers.

Every provider lives here as its own module — OpenRouter and Venice (text /
image / video via their chat APIs) and Pollo (image / video generation). The
goal is a single, uniform surface so callers dispatch over providers instead of
special-casing one by name. `provider_for()` is the first step of that: it maps
a model id to the module that owns it (OpenRouter is the fallback).
"""

from pathlib import Path

from web.providers import openrouter, pollo, pollo_models, venice
from web.uploads import file_to_data_url

# Dispatch order for the model catalogue (Pollo first, OpenRouter last). Each
# exposes the uniform surface: NAME, is_configured(), list_models(kind, refresh).
PROVIDERS = (pollo, venice, openrouter)


def provider_for(model_id: str | None):
    """The provider module that owns `model_id` (OpenRouter is the default)."""
    if pollo.is_pollo(model_id):
        return pollo
    if venice.is_venice(model_id):
        return venice
    return openrouter


def provider_for_job(job_id: str | None):
    """The provider module that owns an async job id — "pollo:…", "venice:…",
    else OpenRouter. Used by the background pollers, which only have the id.
    """
    if pollo.is_pollo_job(job_id):
        return pollo
    if venice.is_venice_job(job_id):
        return venice
    return openrouter


def generate_image(
    model: str,
    prompt: str,
    *,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    ref_paths: list[Path] | None = None,
    context: list[dict] | None = None,
    session_id: str | None = None,
) -> tuple[list[tuple[bytes, str]], float | None, int | None, dict]:
    """Generate images on whichever provider owns `model`, and wait for them.

    Returns ([(bytes, media type)], cost in USD, Pollo credits, the settings
    actually sent). Providers bill differently — Pollo in credits, the rest in
    dollars — so both come back and only the relevant one is set.

    An input a provider has no use for is ignored: `context` (the conversation,
    for OpenRouter's conversational image models) and `session_id` only mean
    something to OpenRouter.
    """
    owner = provider_for(model)
    refs = list(ref_paths or [])
    if owner is pollo:
        images, credits, sent = pollo.generate_image(
            model, prompt, aspect_ratio=aspect_ratio, resolution=resolution, ref_paths=refs
        )
        return images, None, credits, sent
    if owner is venice:
        images, cost, sent = venice.generate_image(
            model, prompt, aspect_ratio=aspect_ratio, resolution=resolution, ref_paths=refs
        )
        return images, cost, None, sent
    if context is not None:
        images, cost = openrouter.generate_image_chat(model, context, aspect_ratio=aspect_ratio, session_id=session_id)
        return images, cost, None, {}
    images, cost = openrouter.generate_image(
        model,
        prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        # OpenRouter's Images API takes references inline, not as URLs
        input_images=[file_to_data_url(p) for p in refs] or None,
        session_id=session_id,
    )
    return images, cost, None, {}


def submit_video(
    model: str,
    prompt: str,
    *,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    generate_audio: bool | None = None,
    first_frame: Path | None = None,
    last_frame: Path | None = None,
    source_video: Path | None = None,
    source_audio: Path | None = None,
    mode: str | None = None,
    refs: list[Path] | None = None,
    ref_items: list[dict] | None = None,
    session_id: str | None = None,
) -> dict:
    """Start a video job on whichever provider owns `model`; returns the job
    ({"id", "params"}), which the chat poller then follows by job id.

    Every provider takes the first four inputs; the rest describe sources only
    some models accept (a last frame, a source video or audio track, an
    enhancement mode, named references) and a provider ignores what it can't
    use.
    """
    owner = provider_for(model)
    shared = {
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "generate_audio": generate_audio,
    }
    if owner is pollo:
        return pollo.submit_video(
            model,
            prompt,
            **shared,
            first_frame=first_frame,
            source_video=source_video,
            source_audio=source_audio,
            mode=mode,
            ref_items=list(ref_items or []),
        )
    if owner is venice:
        return venice.submit_video(
            model,
            prompt,
            **shared,
            first_frame=first_frame,
            last_frame=last_frame,
            refs=list(refs or []),
            source_video=source_video,
        )
    return openrouter.submit_video(
        model,
        prompt,
        **shared,
        # OpenRouter takes the first frame inline, not as a path
        first_frame=file_to_data_url(first_frame) if first_frame else None,
        session_id=session_id,
    )


# Re-exported: importing the package registers these submodules' routes/providers.
__all__ = ["openrouter", "pollo", "pollo_models", "venice"]
