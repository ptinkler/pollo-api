"""Tunables and small constant tables shared across the chat package."""

from web.media_types import IMAGE_EXTS  # noqa: F401 — re-exported for the chat package

MAX_TOOL_ROUNDS = 4
CONSISTENCY_REFS = 2  # recent images passed to the image model to keep characters consistent
# Chat images per request unless the composer's slider says otherwise: the most
# recent images sent to the chat model as pixels, and the cap on chat images sent
# as references (edit source + recent + pins + attachments). Character images
# come on top, uncapped (each model trims to its own maximum).
DEFAULT_IMAGE_LIMIT = 6
MODELS_CACHE_TTL = 30 * 60
CHAT_ROUND_SECONDS = 300  # cap on one LLM call (long stories stream for a while)
VIDEO_POLL_INTERVAL = 10
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
# The turn settings remembered on the conversation (so a reopen restores them)
REMEMBERED_SETTINGS = {
    "mode",
    "history_limit",
    "image_limit",
    "image_options",
    "video_options",
    "audio_model",
    "audio_options",
    "ref_choices",
}
