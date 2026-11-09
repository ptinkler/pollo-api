"""Audio generation (speech / music): submit a Pollo job; the video poller
finishes it (audio rides the same job + download path, saved as .mp3)."""

from typing import Any

from .. import request_log
from ..providers import openrouter, pollo
from .models import AudioOptions

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


def audio_params(opts: AudioOptions) -> dict[str, Any]:
    """The options the user set (unset ones are left to the model's defaults)."""
    return {k: v for k in _OPTION_FIELDS if (v := getattr(opts, k)) not in (None, "")}


def submit_audio_generation(model: str, prompt: str, params: dict[str, Any]) -> dict:
    """Start the job. Returns the job plus "log": what was sent and answered."""
    if not pollo.is_pollo(model):
        raise openrouter.OpenRouterError("Audio generation needs a Pollo model")
    request_log.forget_last()
    job = pollo.submit_audio(model, prompt, **{k: params[k] for k in _OPTION_FIELDS if k in params})
    return {**job, "log": request_log.take_last()}
