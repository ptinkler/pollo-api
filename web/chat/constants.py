"""Tunables and small constant tables shared across the chat package."""

MAX_TOOL_ROUNDS = 4
CONSISTENCY_REFS = 2  # recent images passed to the image model to keep characters consistent
# Chat images per request unless the composer's slider says otherwise: the most
# recent images sent to the chat model as pixels, and the cap on chat images sent
# as references (edit source + recent + pins + attachments). Character images
# come on top, uncapped (each model trims to its own maximum).
DEFAULT_IMAGE_LIMIT = 6
MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024  # larger images are downscaled before sending
MODELS_CACHE_TTL = 30 * 60
CHAT_ROUND_SECONDS = 300  # cap on one LLM call (long stories stream for a while)
VIDEO_POLL_INTERVAL = 10
VIDEO_POLL_TIMEOUT = 45 * 60
VIDEO_MAX_POLL_ERRORS = 10
DEFAULT_TITLE = "New chat"
TITLE_SECONDS = 20  # cap on the title request, which runs alongside the first reply
TITLE_WAIT_SECONDS = 8  # how long a finished first reply waits for it before using the prompt

IMAGE_EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/svg+xml": ".svg"}
# px on the shorter side: sharp in the chat, a fraction of a full-size image
CHAT_PREVIEW_SIZE = 768

CONVERSATION_LIST_LIMIT = 200
SNIPPET_CHARS = 120
THREAD_KINDS = ("chat", "gallery")
_KINDS = ("character", "instruction", "instruction_group")
_PAUSE_KINDS = ("instruction", "instruction_group")
_PARAM_FILES = ("first_frame", "last_frame", "source_video")  # media params naming one reference file
# The turn settings remembered on the conversation (so a reopen restores them)
_REMEMBERED_SETTINGS = {
    "mode",
    "history_limit",
    "image_limit",
    "image_options",
    "video_options",
    "audio_model",
    "audio_options",
    "ref_choices",
}
