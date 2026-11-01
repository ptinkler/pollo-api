"""Model providers.

Every provider lives here as its own module — OpenRouter and Venice (text /
image / video via their chat APIs) and Pollo (image / video generation). The
goal is a single, uniform surface so callers dispatch over providers instead of
special-casing one by name. `provider_for()` is the first step of that: it maps
a model id to the module that owns it (OpenRouter is the fallback).
"""

from . import openrouter, pollo, pollo_estimate, pollo_models, venice  # noqa: F401

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
