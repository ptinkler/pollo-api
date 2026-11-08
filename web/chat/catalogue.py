"""The chat model catalogue, cached: every provider's text/image/video models,
and the per-model lookups used to validate and auto-fit media params."""

import threading
import time
from typing import Any

from ..providers import PROVIDERS, venice
from ..providers.model_tags import tags_for
from .constants import MODELS_CACHE_TTL

_models_cache: dict[str, Any] = {"at": 0.0, "data": None}
_models_lock = threading.Lock()


def get_models(refresh: bool = False) -> dict[str, Any]:
    with _models_lock:
        if not refresh and _models_cache["data"] and time.time() - _models_cache["at"] < MODELS_CACHE_TTL:
            return _models_cache["data"]
        data: dict[str, Any] = {"errors": {}}
        # Uniform dispatch: each provider lists its own models per kind (in
        # PROVIDERS order), so no provider is special-cased here.
        for kind in ("text", "image", "video"):
            models: list = []
            for prov in PROVIDERS:
                try:
                    models += prov.list_models(kind, refresh)
                except Exception as e:  # noqa: BLE001 — surface any failure per provider/kind
                    data["errors"][f"{prov.NAME}_{kind}"] = str(e)
            # Capability tags, derived uniformly so every provider is consistent;
            # the picker filters on these. Set once here rather than in each
            # provider's list_models (see web/providers/model_tags.py).
            for m in models:
                m["tags"] = tags_for(kind, m)
            data[kind] = models
        # Only cache a complete result, so a transient failure isn't sticky
        if not data["errors"]:
            _models_cache.update(at=time.time(), data=data)
        return data


def _model_info(kind: str, model_id: str | None) -> dict | None:
    """Look up cached catalogue info without fetching every provider's list.
    That cache is empty after a restart or when any list failed to load;
    Venice models then come from Venice's own catalogue, so a model without
    vision isn't sent images (Venice rejects those requests)."""
    if not model_id:
        return None
    data = _models_cache["data"]
    info = next((m for m in data.get(kind, []) if m["id"] == model_id), None) if data else None
    if info is None and venice.is_venice(model_id) and venice.is_configured():
        try:
            return venice.model_info(kind, model_id)
        except Exception:  # noqa: BLE001 — unknown model or Venice unreachable: treat as unknown
            return None
    return info


# Values a model exposes that mean "you decide" — mapped to from an unset ratio
# so the "Ratio: auto" placeholder really is automatic, not the provider's
# missing-field default (Seedream, for one, treats a missing ratio as 16:9).
_AUTO_RATIOS = ("auto", "adaptive")


def _auto_ratio(kind: str, model_id: str | None) -> str | None:
    """The model's own 'auto' aspect-ratio value, if it offers one."""
    ratios = (_model_info(kind, model_id) or {}).get("aspect_ratios") or []
    return next((v for v in _AUTO_RATIOS if v in ratios), None)


def _fit_video_params(
    model_id: str, duration: int | None, aspect_ratio: str | None, resolution: str | None
) -> tuple[int | None, str | None, str | None]:
    """Snap requested params onto what the video model supports (when known),
    so a model-chosen "7 seconds" doesn't fail on a 5/10-only model."""
    info = _model_info("video", model_id)
    if not info:
        return duration, aspect_ratio, resolution
    durations = info.get("durations") or []
    if duration and durations and duration not in durations:
        duration = min(durations, key=lambda d: abs(d - duration))
    if aspect_ratio and info.get("aspect_ratios") and aspect_ratio not in info["aspect_ratios"]:
        aspect_ratio = None
    if resolution and info.get("resolutions") and resolution not in info["resolutions"]:
        resolution = None
    return duration, aspect_ratio, resolution
