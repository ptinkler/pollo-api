"""Data-driven Pollo generation engine (replaces the old generator-class hierarchy).

Each model is a row in a family table (V1_VIDEO, V1_IMAGE, LEGACY_VIDEO,
LEGACY_IMAGE, LEGACY_REF); a small set of family builders turn a row + the
request inputs into the Pollo API body. ModelSpec exposes a model's static data
(the VALID_* the catalogue/validation read) and is a factory for PolloGenerator,
the single runtime object that resolves inputs, builds the payload, and
submits/prices a request — replacing the 44 former generator classes.

The builders were verified byte-identical to those classes (the oracle) before
the classes were removed; tests/test_pollo_engine.py now pins that proven output
as a golden snapshot. The engine is split by model family:

    _shared        statuses, input-parsing + aspect-ratio helpers
    v1_video       V1_VIDEO table + generic/kling/extend/recast builders
    v1_image       V1_IMAGE table + builder
    legacy_video   LEGACY_VIDEO table + builders
    legacy_image   LEGACY_IMAGE table + builders
    legacy_ref     LEGACY_REF table + ref2video builder
    registry       ModelSpec, PolloGenerator, the GENERATORS* registries
"""

from __future__ import annotations

from ._shared import ERROR_STATUSES, SUCCESS_STATUSES, closest_aspect_ratio
from .legacy_image import LEGACY_IMAGE, legacy_image_model_url, legacy_image_payload
from .legacy_ref import LEGACY_REF, legacy_ref_model_url, legacy_ref_payload
from .legacy_video import LEGACY_VIDEO, legacy_video_model_url, legacy_video_payload
from .registry import (
    AUDIO_GENERATORS,
    GENERATORS,
    GENERATORS_LEGACY,
    GENERATORS_V1,
    IMAGE_GENERATORS,
    IMAGE_GENERATORS_LEGACY,
    IMAGE_GENERATORS_V1,
    ModelSpec,
    PolloGenerator,
    audio_generator,
    image_generator,
    video_generator,
)
from .v1_audio import V1_AUDIO, v1_audio_model_url, v1_audio_payload
from .v1_image import V1_IMAGE, v1_image_model_url, v1_image_payload
from .v1_video import V1_VIDEO, v1_video_model_url, v1_video_payload

__all__ = [
    "ERROR_STATUSES",
    "SUCCESS_STATUSES",
    "closest_aspect_ratio",
    "AUDIO_GENERATORS",
    "GENERATORS",
    "GENERATORS_LEGACY",
    "GENERATORS_V1",
    "IMAGE_GENERATORS",
    "IMAGE_GENERATORS_LEGACY",
    "IMAGE_GENERATORS_V1",
    "ModelSpec",
    "PolloGenerator",
    "audio_generator",
    "image_generator",
    "video_generator",
    "V1_AUDIO",
    "V1_VIDEO",
    "V1_IMAGE",
    "LEGACY_VIDEO",
    "LEGACY_IMAGE",
    "LEGACY_REF",
    "v1_audio_model_url",
    "v1_audio_payload",
    "v1_video_model_url",
    "v1_video_payload",
    "v1_image_model_url",
    "v1_image_payload",
    "legacy_video_model_url",
    "legacy_video_payload",
    "legacy_image_model_url",
    "legacy_image_payload",
    "legacy_ref_model_url",
    "legacy_ref_payload",
]
