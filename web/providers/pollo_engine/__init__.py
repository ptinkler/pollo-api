"""Data-driven Pollo generation engine.

Each model is a row in its kind's table (VIDEO_MODELS, IMAGE_MODELS,
AUDIO_MODELS); a small set of family builders turn a row + the request inputs
into the Pollo API body. ModelSpec exposes a model's static data (the VALID_*
the catalogue and validation read) and is a factory for PolloGenerator, the
single runtime object that resolves inputs, builds the payload, and submits or
prices a request.

The builders were verified byte-identical to the generator classes they
replaced; tests/test_pollo_engine.py pins that proven output as a golden
snapshot. Regenerate it only on a deliberate, reviewed change.

    _shared     statuses, input-parsing + aspect-ratio helpers
    video       VIDEO_MODELS + the generic/kling/extend/motion/… builders
    image       IMAGE_MODELS + its builder
    audio       AUDIO_MODELS + its builders
    registry    ModelSpec, PolloGenerator, the *_GENERATORS registries
"""

from __future__ import annotations

from ._shared import ERROR_STATUSES, SUCCESS_STATUSES, closest_aspect_ratio
from .audio import AUDIO_MODELS, audio_model_url, audio_payload
from .image import IMAGE_MODELS, image_model_url, image_payload
from .registry import (
    AUDIO_GENERATORS,
    IMAGE_GENERATORS,
    VIDEO_GENERATORS,
    ModelSpec,
    PolloGenerator,
    audio_generator,
    image_generator,
    video_generator,
)
from .video import VIDEO_MODELS, video_model_url, video_payload

__all__ = [
    "ERROR_STATUSES",
    "SUCCESS_STATUSES",
    "closest_aspect_ratio",
    "AUDIO_GENERATORS",
    "IMAGE_GENERATORS",
    "VIDEO_GENERATORS",
    "ModelSpec",
    "PolloGenerator",
    "audio_generator",
    "image_generator",
    "video_generator",
    "AUDIO_MODELS",
    "IMAGE_MODELS",
    "VIDEO_MODELS",
    "audio_model_url",
    "audio_payload",
    "image_model_url",
    "image_payload",
    "video_model_url",
    "video_payload",
]
