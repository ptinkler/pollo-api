"""Tunables and small constant tables shared across the chat package."""

from web.core.env import number_env
from web.media.kinds import IMAGE_EXTS

__all__ = ["IMAGE_EXTS"]  # re-exported for the chat package

MAX_TOOL_ROUNDS = 4
# Chat images per request unless the composer's slider says otherwise: the most
# recent images sent to the chat model as pixels, and the cap on chat images sent
# as references (edit source + recent + pins + attachments). Character images
# come on top, uncapped (each model trims to its own maximum).
DEFAULT_IMAGE_LIMIT = 6
MODELS_CACHE_TTL = 30 * 60
CHAT_ROUND_SECONDS = 300  # cap on one LLM call (long stories stream for a while)
# Seconds between video status checks (the end-to-end tests poll faster); a floor so a typo can't hammer a provider
VIDEO_POLL_INTERVAL = number_env("CYNO_VIDEO_POLL_SECONDS", 10, minimum=0.1)
VIDEO_POLL_TIMEOUT = 45 * 60
VIDEO_MAX_POLL_ERRORS = 10
DEFAULT_TITLE = "New chat"
TITLE_SECONDS = 20  # cap on the title request, which runs alongside the first reply
TITLE_WAIT_SECONDS = 8  # how long a finished first reply waits for it before using the prompt

# px on the shorter side: sharp in the chat, a fraction of a full-size image
CHAT_PREVIEW_SIZE = 768

CONVERSATION_LIST_LIMIT = 200
SNIPPET_CHARS = 120
THREAD_KINDS = ("chat", "gallery")
KINDS = ("character", "instruction", "instruction_group")
PAUSE_KINDS = ("instruction", "instruction_group")
PARAM_FILES = ("first_frame", "last_frame", "source_video")  # media params naming one reference file
