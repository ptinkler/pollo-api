"""
Chat mode — a Gemini/Grok-style multimodal chat backed by OpenRouter.

A conversation has three model slots: a text model that drives the chat, an
image model and a video model. In "auto" mode the text model is given
generate_image / generate_video tools and decides itself when to use them;
the tools run on whichever image/video model is selected. "text", "image"
and "video" modes bypass that decision and hit one model directly.

Media item shape (stored in ChatMessage.media_json, sent to the frontend):
    {
      "id": "a1b2c3d4",              # stable per item; the UI upserts by it
      "kind": "image" | "video",
      "source": "upload" | "generated",
      "status": "pending" | "done" | "error",
      "file": "img_….png" | None,    # under <data>/chat/<conversation_id>/
      "pinned": optional bool,        # user pinned this image: sent as a reference with every new image
      "prompt", "model", "job_id", "error", "cost": optional,
      "credits": optional,            # Pollo images bill in credits, not dollars
      "request", "response": optional # what was sent to the provider and what it answered (web/request_log.py)
    }

This package is pure wiring. The pieces live in their own modules:
    deps          the shared APIRouter
    constants / models / tools        tunables, request bodies, tool schemas
    helpers       path/branch/validation/default-inheritance helpers
    catalogue     the cached model catalogue
    workers       background-thread + owner-key helpers
    generation    request building + image/video generation primitives
    turn          the Turn class (one streamed turn in a worker thread)
    polling       background video polling + startup resume
    routes        the CRUD + catalogue/media/messages routes
    routes_turns  the SSE turn routes + pin/favourite/regenerate media routes
"""

import threading as threading  # tests patch web.chat.threading.Thread (the stdlib module)

# Importing the route modules registers their endpoints on the shared router;
# the rest are re-exports used by other modules and the tests (web.chat.<name>).
from ..providers import openrouter as openrouter  # tests patch web.chat.openrouter.*
from ..providers import pollo as pollo  # tests patch web.chat.pollo.*
from . import routes as routes  # noqa: F401 — CRUD + catalogue/media/messages routes
from . import routes_turns as routes_turns  # noqa: F401 — SSE turn + media-gen routes
from .catalogue import _models_cache as _models_cache  # tests mutate web.chat._models_cache
from .catalogue import get_models as get_models
from .constants import CHAT_PREVIEW_SIZE as CHAT_PREVIEW_SIZE  # chatgpt_import
from .constants import IMAGE_EXTS as IMAGE_EXTS  # chatgpt_import
from .deps import router as router  # web.api mounts this
from .helpers import _conv_dir as _conv_dir  # chatgpt_import
from .helpers import _inherited as _inherited  # tests call web.chat._inherited
from .models import ConversationCreate as ConversationCreate  # chatgpt_import
from .polling import startup_resume_chat as startup_resume_chat  # web.api lifespan
from .routes import api_create_conversation as api_create_conversation  # chatgpt_import
