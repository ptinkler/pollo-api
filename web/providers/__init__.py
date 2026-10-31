"""Model providers.

Every provider lives here as its own module — OpenRouter and Venice (text /
image / video via their chat APIs) and Pollo (image / video generation). The
goal is a single, uniform surface so callers dispatch over providers instead of
special-casing one by name. `provider_for()` is the first step of that: it maps
a model id to the module that owns it (OpenRouter is the fallback).
"""

from . import openrouter, pollo_chat, pollo_estimate, pollo_models, venice_chat  # noqa: F401


def provider_for(model_id: str | None):
    """The provider module that owns `model_id` (OpenRouter is the default)."""
    if pollo_chat.is_pollo(model_id):
        return pollo_chat
    if venice_chat.is_venice(model_id):
        return venice_chat
    return openrouter
