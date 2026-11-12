"""Audio generation (speech / music): submit a Pollo job; the video poller.

finishes it (audio rides the same job + download path, saved as .mp3).
"""

from collections.abc import Mapping
from typing import NotRequired, TypedDict, cast

from web import request_log
from web.chat.helpers import conversation_dir
from web.chat.models import AudioOptions
from web.providers import openrouter, pollo
from web.types import JsonValue

# AudioOptions fields that go to the model as-is
_OPTION_FIELDS = (
    "voice",
    "speed",
    "volume",
    "pitch",
    "instrumental",
    "vocal_gender",
    "style",
    "title",
    "negative_prompt",
    "duration",
)


class _AudioJob(TypedDict):
    id: str
    params: dict[str, JsonValue]
    log: NotRequired[dict[str, JsonValue] | None]


def audio_params(opts: AudioOptions) -> dict[str, JsonValue]:
    """The options the user set (unset ones are left to the model's defaults)."""
    values = cast("dict[str, JsonValue]", opts.model_dump())
    return {key: value for key in _OPTION_FIELDS if (value := values.get(key)) not in (None, "")}


def submit_audio_generation(conv_id: str, model: str, prompt: str, params: dict[str, JsonValue]) -> _AudioJob:
    """Start the job. Returns the job plus "log": what was sent and answered."""
    if not pollo.is_pollo(model):
        raise openrouter.OpenRouterError("Audio generation needs a Pollo model")  # noqa: TRY003
    request_log.forget_last()
    source_audio = params.get("source_audio")
    clip = conversation_dir(conv_id) / source_audio if isinstance(source_audio, str) else None
    job = pollo.submit_audio(model, prompt, clip, **{k: params[k] for k in _OPTION_FIELDS if k in params})
    job_id = job.get("id")
    job_params = job.get("params")
    if not isinstance(job_id, str) or not isinstance(job_params, Mapping):
        raise TypeError("Pollo returned an invalid audio job")  # noqa: TRY003
    return {"id": job_id, "params": dict(job_params), "log": request_log.take_last()}
