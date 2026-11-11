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

from web.providers.pollo_engine._shared import ERROR_STATUSES, SUCCESS_STATUSES, closest_aspect_ratio
from web.providers.pollo_engine.audio import AUDIO_MODELS, audio_model_url, audio_payload
from web.providers.pollo_engine.image import IMAGE_MODELS, image_model_url, image_payload
from web.providers.pollo_engine.registry import (
    AUDIO_GENERATORS,
    IMAGE_GENERATORS,
    VIDEO_GENERATORS,
    ModelSpec,
    PolloGenerator,
    audio_generator,
    image_generator,
    video_generator,
)
from web.providers.pollo_engine.video import VIDEO_MODELS, video_model_url, video_payload

__all__ = [
    "AUDIO_GENERATORS",
    "AUDIO_MODELS",
    "ERROR_STATUSES",
    "IMAGE_GENERATORS",
    "IMAGE_MODELS",
    "SUCCESS_STATUSES",
    "VIDEO_GENERATORS",
    "VIDEO_MODELS",
    "ModelSpec",
    "PolloGenerator",
    "audio_generator",
    "audio_model_url",
    "audio_payload",
    "closest_aspect_ratio",
    "image_generator",
    "image_model_url",
    "image_payload",
    "video_generator",
    "video_model_url",
    "video_payload",
]
