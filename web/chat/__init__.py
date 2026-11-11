"""Chat mode — a Gemini/Grok-style multimodal chat backed by OpenRouter.

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

# Importing the route modules registers their endpoints on the shared router.
from web.chat import routes, routes_turns
from web.chat.constants import CHAT_PREVIEW_SIZE, IMAGE_EXTS
from web.chat.deps import router
from web.chat.helpers import conversation_dir
from web.chat.models import ConversationCreate
from web.chat.polling import startup_resume_chat
from web.chat.routes import api_create_conversation

# The package's public surface (used by web.api and web.chatgpt_import).
__all__ = [
    "CHAT_PREVIEW_SIZE",
    "IMAGE_EXTS",
    "ConversationCreate",
    "api_create_conversation",
    "conversation_dir",
    "router",
    # imported for their route-registration side effect
    "routes",
    "routes_turns",
    "startup_resume_chat",
]
