"""Video API bodies: the generic family plus Kling, extend, edit, upscale, lipsync and motion."""

from __future__ import annotations

from typing import Any

from web.core.config import POLLO_GENERATION_BASE
from web.providers.pollo_engine._shared import parse_aspect_ratio, valid_length

# Config rows (introspected from the generator classes). Fields omitted here
# take the base defaults below.
_V1_VIDEO_DEFAULTS: dict[str, Any] = {
    "VALID_LENGTHS": (),
    "VALID_RESOLUTIONS": (),
    "VALID_RATIOS": (),
    "DEFAULT_RESOLUTION": "",
    "DEFAULT_LENGTH": 5,
    "HAS_GENERATE_AUDIO": False,
    "HAS_WEB_SEARCH": False,
    "HAS_SEED": False,
    "HAS_IMAGE_TAIL": False,
    "HAS_REFS": False,
    "HAS_MODE": False,
    "HAS_NEGATIVE_PROMPT_AUDIO": False,
    "HAS_ASPECT_RATIO_ON_IMAGE": False,
    "REF_TYPES": ("image", "video", "audio"),
    "MAX_REFS": 0,
    "REF_HAS_SEED": True,
    "REF_VALID_LENGTHS": (),
    "REF_VALID_RESOLUTIONS": (),
    # dispatch + endpoint
    "builder": "generic",
    "endpoint": "video",
    # Kling post-processing flags (ignored by the generic builder)
    "RESOLUTION_IS_MODE": False,
    "MODE_ON_TEXT": True,
    "TEXT_TO_VIDEO": True,
    "IMAGE_TAIL_NEEDS_PRO": False,
    "NO_AUDIO_WITH_IMAGE_TAIL": False,
}

# Kling models share these base values (layered under each Kling row).
_KLING_BASE: dict[str, Any] = {
    "PROVIDER": "kling-ai",
    "VALID_LENGTHS": (5, 10),
    "VALID_RATIOS": ("16:9", "9:16", "1:1"),
    "DEFAULT_RESOLUTION": "",
}

_UPSCALE_SCALES = ("original", "2x", "4x", "hd", "4K")
_UPSCALE_MODES = ("standard", "face", "denoise", "sharpen", "anime")

# model_id -> overrides of the defaults above (plus PROVIDER/MODEL)
VIDEO_MODELS: dict[str, dict[str, Any]] = {
    "pollo20": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollo-v2",
        "VALID_LENGTHS": (5, 10),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("16:9", "9:16", "4:3", "3:4", "1:1"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_REFS": True,
        "REF_TYPES": ("image",),
        "MAX_REFS": 7,
        "REF_VALID_LENGTHS": (1, 2, 3, 4, 5, 6, 7, 8),
        "REF_VALID_RESOLUTIONS": ("540p", "720p", "1080p"),
    },
    "pollo25": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollo-v2-5",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 15),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "VALID_RATIOS": ("16:9", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_MODE": True,
        "MODE_DEFAULT": "basic",
    },
    "pollo30": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollo-v3-0",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p", "4K"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_MODE": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 13,
        "MODE_PRO_RESOLUTIONS": ("1080p", "4K"),
    },
    "pollo30fast": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollo-v3-0-fast",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 13,
        "REF_HAS_SEED": False,
    },
    "seedance20": {
        "PROVIDER": "bytedance",
        "MODEL": "seedance-2-0",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p", "4K"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 15,
    },
    "seedance20fast": {
        "PROVIDER": "bytedance",
        "MODEL": "seedance-2-0-fast",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 15,
    },
    "seedance20mini": {
        "PROVIDER": "bytedance",
        "MODEL": "seedance-2-0-mini",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_ASPECT_RATIO_ON_IMAGE": True,
        "MAX_REFS": 15,
    },
    "seedance25": {
        "PROVIDER": "bytedance",
        "MODEL": "seedance-2-5",
        "VALID_LENGTHS": tuple(range(4, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 50,
        "DEFAULT_RATIO": "adaptive",
    },
    "seedance25draft": {
        "PROVIDER": "bytedance",
        "MODEL": "seedance-2-5-draft",
        "VALID_LENGTHS": tuple(range(4, 31)),
        "VALID_RESOLUTIONS": ("480p",),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 50,
        "DEFAULT_RATIO": "adaptive",
        "FORCE_RESOLUTION": "480p",
    },
    "minimaxh3": {
        "PROVIDER": "minimax",
        "MODEL": "minimax-h3",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "768p", "2K"),
        "VALID_RATIOS": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 15,
    },
    "minimaxh3max": {
        "PROVIDER": "minimax",
        "MODEL": "minimax-h3-max",
        "VALID_LENGTHS": (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
        "VALID_RESOLUTIONS": ("480p", "768p", "1080p"),
        "VALID_RATIOS": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "MAX_REFS": 12,
    },
    "wan27": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v2-7",
        "VALID_LENGTHS": tuple(range(2, 16)),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "VALID_RATIOS": ("16:9", "1:1", "4:3", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "HAS_NEGATIVE_PROMPT_AUDIO": True,
        "MAX_REFS": 10,
    },
    "wan30": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v3-0",
        "VALID_LENGTHS": tuple(range(2, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "REF_TYPES": ("image", "video", "audio", "file", "link"),
        "MAX_REFS": 22,
        "DEFAULT_RATIO": "adaptive",
    },
    "wan30prime": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v3-0-prime",
        "VALID_LENGTHS": tuple(range(2, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "REF_TYPES": ("image", "video", "audio", "file", "link"),
        "MAX_REFS": 22,
        "DEFAULT_RATIO": "adaptive",
    },
    # --- Newer frontier models (added 2026-11) ---
    "sora2": {
        "PROVIDER": "openai",
        "MODEL": "sora-2",
        "VALID_LENGTHS": (4, 8, 12, 16, 20),
        "VALID_RESOLUTIONS": (),
        "VALID_RATIOS": ("16:9", "9:16"),
        "DEFAULT_LENGTH": 8,
    },
    "sora2pro": {
        "PROVIDER": "openai",
        "MODEL": "sora-2-pro",
        "VALID_LENGTHS": (4, 8, 12, 16, 20),
        "VALID_RESOLUTIONS": ("720p", "1024p", "1080p"),
        "VALID_RATIOS": ("16:9", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "DEFAULT_LENGTH": 8,
    },
    "veo31": {
        "PROVIDER": "google",
        "MODEL": "veo-3-1",
        "VALID_LENGTHS": (8,),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "VALID_RATIOS": ("16:9", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "DEFAULT_LENGTH": 8,
        "HAS_GENERATE_AUDIO": True,
        "HAS_IMAGE_TAIL": True,
    },
    "veo31fast": {
        "PROVIDER": "google",
        "MODEL": "veo-3-1-fast",
        "VALID_LENGTHS": (4, 6, 8),
        "VALID_RESOLUTIONS": ("720p", "1080p", "4K"),
        "VALID_RATIOS": ("16:9", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "DEFAULT_LENGTH": 8,
        "HAS_GENERATE_AUDIO": True,
        "HAS_IMAGE_TAIL": True,
    },
    "veo31lite": {
        "PROVIDER": "google",
        "MODEL": "veo3-1-lite",
        "VALID_LENGTHS": (4, 6, 8),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "VALID_RATIOS": ("16:9", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "DEFAULT_LENGTH": 8,
        "HAS_IMAGE_TAIL": True,
    },
    "hailuo23": {
        "PROVIDER": "minimax",
        "MODEL": "hailuo-2-3",
        "VALID_LENGTHS": (6, 10),
        "VALID_RESOLUTIONS": ("768p", "1080p"),
        "VALID_RATIOS": (),
        "DEFAULT_RESOLUTION": "768p",
        "DEFAULT_LENGTH": 6,
    },
    "hailuo03": {
        "PROVIDER": "minimax",
        "MODEL": "hailuo-03",
        "VALID_LENGTHS": tuple(range(4, 16)),
        "VALID_RESOLUTIONS": ("480p", "768p", "2K"),
        "VALID_RATIOS": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "768p",
        "HAS_IMAGE_TAIL": True,
    },
    "pollo26": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollo-v2-6",
        "VALID_LENGTHS": tuple(range(4, 16)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p", "4K"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
    },
    "pollo26fast": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollo-v2-6-fast",
        "VALID_LENGTHS": tuple(range(4, 16)),
        "VALID_RESOLUTIONS": ("480p", "720p"),
        "VALID_RATIOS": ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_WEB_SEARCH": True,
        "HAS_SEED": True,
        "HAS_IMAGE_TAIL": True,
    },
    "wan25": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v2-5",
        "VALID_LENGTHS": (5, 10),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": ("16:9", "1:1", "4:3", "3:4", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
    },
    "wan26": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v2-6",
        "VALID_LENGTHS": (5, 10),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "VALID_RATIOS": ("1:1", "4:3", "3:4", "16:9", "9:16"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_GENERATE_AUDIO": True,
        "HAS_SEED": True,
    },
    "grokvideo15": {
        "PROVIDER": "xai",
        "MODEL": "grok-imagine-video-1-5",
        "VALID_LENGTHS": tuple(range(1, 16)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "VALID_RATIOS": (),
        "DEFAULT_RESOLUTION": "720p",
    },
    # Kling video: reuses the generic payload, then remaps the resolution
    # tier to a mode and applies end-frame rules
    "klingv21": {
        "MODEL": "kling-v2-1",
        "VALID_RESOLUTIONS": ("std", "pro"),
        "RESOLUTION_IS_MODE": True,
        "TEXT_TO_VIDEO": False,
        "builder": "kling",
    },
    "klingv21master": {"MODEL": "kling-v2-1-master", "builder": "kling"},
    "klingv25turbo": {
        "MODEL": "kling-v2-5-turbo",
        "VALID_RESOLUTIONS": ("std", "pro"),
        "HAS_IMAGE_TAIL": True,
        "RESOLUTION_IS_MODE": True,
        "MODE_ON_TEXT": False,
        "IMAGE_TAIL_NEEDS_PRO": True,
        "builder": "kling",
    },
    "klingvideoo1": {"MODEL": "kling-video-o1", "HAS_IMAGE_TAIL": True, "builder": "kling"},
    "klingv26": {
        "MODEL": "kling-v2-6",
        "HAS_IMAGE_TAIL": True,
        "HAS_GENERATE_AUDIO": True,
        "NO_AUDIO_WITH_IMAGE_TAIL": True,
        "builder": "kling",
    },
    "klingv3": {
        "MODEL": "kling-v3",
        "VALID_LENGTHS": tuple(range(3, 16)),
        "VALID_RESOLUTIONS": ("std", "pro", "4K"),
        "HAS_IMAGE_TAIL": True,
        "HAS_GENERATE_AUDIO": True,
        "RESOLUTION_IS_MODE": True,
        "builder": "kling",
    },
    "klingv3turbo": {
        "MODEL": "kling-v3-turbo",
        "VALID_LENGTHS": tuple(range(3, 16)),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "builder": "kling",
    },
    "klingv3omni": {
        "MODEL": "kling-v3-omni",
        "VALID_LENGTHS": tuple(range(3, 16)),
        "VALID_RESOLUTIONS": ("std", "pro", "4K"),
        "HAS_IMAGE_TAIL": True,
        "HAS_GENERATE_AUDIO": True,
        "RESOLUTION_IS_MODE": True,
        "HAS_REFS": True,  # reference-to-video: image/video refs, [@name] mentions
        "REF_TYPES": ("image", "video"),  # no audio voice ref on Omni (docs 2026-11)
        "MAX_REFS": 7,
        "builder": "kling",
    },
    "klingv4": {
        "MODEL": "kling-v4",
        "VALID_LENGTHS": tuple(range(3, 31)),
        "VALID_RESOLUTIONS": ("720p", "1080p"),  # real resolutions, not std/pro tiers
        "VALID_RATIOS": ("21:9", "16:9", "9:16", "1:1", "adaptive"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,  # reference-to-video: image/video/audio refs, [@name] mentions
        "MAX_REFS": 15,
        "builder": "kling",
    },
    "klingv4flash": {
        "MODEL": "kling-v4-flash",
        "VALID_LENGTHS": tuple(range(3, 21)),
        "VALID_RESOLUTIONS": ("720p",),
        "VALID_RATIOS": ("21:9", "16:9", "9:16", "1:1", "adaptive"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_IMAGE_TAIL": True,
        "HAS_REFS": True,
        "REF_TYPES": ("image", "video"),  # audio voice refs unsupported by Flash (docs 2026-11)
        "MAX_REFS": 15,
        "builder": "kling",
    },
    "seedance25extend": {
        "PROVIDER": "bytedance",
        "MODEL": "seedance-2-5",
        "endpoint": "video-extend",
        "VALID_LENGTHS": tuple(range(4, 31)),
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "480p",
        "HAS_SEED": True,
        "HAS_GENERATE_AUDIO": True,
        "builder": "extend",
    },
    # Video-extend models (added 2026-11): continue a source video instead of
    # animating an image. All take the `_extend_payload` shape (video + prompt +
    # duration + resolution, plus generateAudio/seed where offered). Sora 2's and
    # Runway's extend endpoints use a different request shape and are left out.
    "pollov2extender": {
        "PROVIDER": "pollo-ai",
        "MODEL": "pollo-v2-extender",
        "endpoint": "video-extend",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10),
        "VALID_RESOLUTIONS": ("540p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "extend",
    },
    "geminiomniextend": {
        "PROVIDER": "google",
        "MODEL": "gemini-omni-1-1-flash",
        "endpoint": "video-extend",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10),
        "VALID_RESOLUTIONS": ("360p", "720p", "1080p", "4K"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "extend",
    },
    "flux3extend": {
        "PROVIDER": "flux",
        "MODEL": "flux-3",
        "endpoint": "video-extend",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10),
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "HAS_GENERATE_AUDIO": True,
        "builder": "extend",
    },
    "viduq2proextend": {
        "PROVIDER": "vidu",
        "MODEL": "viduq2-pro",
        "endpoint": "video-extend",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10),
        "VALID_RESOLUTIONS": ("540p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "extend",
    },
    "viduq2turboextend": {
        "PROVIDER": "vidu",
        "MODEL": "viduq2-turbo",
        "endpoint": "video-extend",
        "VALID_LENGTHS": (4, 5, 6, 7, 8, 9, 10),
        "VALID_RESOLUTIONS": ("540p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "extend",
    },
    # Video-edit models (added 2026-11): edit a source video from a text
    # instruction (`video` and `prompt` are both required). Minimal shape —
    # {video, prompt} plus a resolution where the model offers one; images/seed/
    # audio refinements are left for a later pass.
    "wanedit27": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v2-7",
        "endpoint": "video-edit",
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "edit",
    },
    "wanedit30": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v3-0",
        "endpoint": "video-edit",
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "edit",
    },
    "wanedit30prime": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-v3-0-prime",
        "endpoint": "video-edit",
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "edit",
    },
    "geminiomniedit": {
        "PROVIDER": "google",
        "MODEL": "gemini-omni-1-1-flash",
        "endpoint": "video-edit",
        "VALID_RESOLUTIONS": ("360p", "720p", "1080p", "4K"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "edit",
    },
    "happyhorse10": {
        "PROVIDER": "alibaba",
        "MODEL": "happyhorse-1-0",
        "endpoint": "video-edit",
        "VALID_RESOLUTIONS": ("720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "edit",
    },
    "viduq2proedit": {
        "PROVIDER": "vidu",
        "MODEL": "viduq2-pro",
        "endpoint": "video-edit",
        "VALID_RESOLUTIONS": ("540p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "builder": "edit",
    },
    "runwayalephedit": {
        "PROVIDER": "runway",
        "MODEL": "runway-gen-4-aleph",
        "endpoint": "video-edit",
        "builder": "edit",
    },
    "wananimatemix": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-2-2-animate-mix",
        "endpoint": "motion",
        "HAS_MODE": True,
        "DEFAULT_MODE": "std",
        "builder": "motion",
    },
    # Motion / act (added 2026-11): a reference image animated by the motion of a
    # source video. Wan 2.2 Animate Mix is one of them;
    # the MODEL_INFO "type": "motion" sets the tag and submit routing.
    "wananimatemove": {
        "PROVIDER": "alibaba",
        "MODEL": "wan-2-2-animate-move",
        "endpoint": "motion",
        "HAS_MODE": True,
        "DEFAULT_MODE": "std",
        "builder": "motion",
    },
    "klingmotion26": {
        "PROVIDER": "kling-ai",
        "MODEL": "kling-v2-6",
        "endpoint": "motion",
        "HAS_MODE": True,
        "DEFAULT_MODE": "std",
        "builder": "motion",
    },
    "klingmotion3": {
        "PROVIDER": "kling-ai",
        "MODEL": "kling-v3",
        "endpoint": "motion",
        "HAS_MODE": True,
        "DEFAULT_MODE": "std",
        "builder": "motion",
    },
    "actionimitation": {
        "PROVIDER": "pollo-ai",
        "MODEL": "action-imitation",
        "endpoint": "motion",
        "builder": "motion",
    },
    "actionimitationv2": {
        "PROVIDER": "pollo-ai",
        "MODEL": "action-imitation-v2",
        "endpoint": "motion",
        "builder": "motion",
    },
    "runwayacttwo": {
        "PROVIDER": "runway",
        "MODEL": "runway-act-two",
        "endpoint": "motion",
        "builder": "motion",
    },
    # Video upscale (added 2026-11): {video, scale (+mode)}. The resolution
    # picker carries Pollo's `scale`; Pollo's own endpoint has no provider/model
    # segment, so it sets V1_URL.
    "pollovideoupscale": {
        "V1_URL": f"{POLLO_GENERATION_BASE}/upscale",
        "VALID_RESOLUTIONS": _UPSCALE_SCALES,
        "DEFAULT_RESOLUTION": "2x",
        "MODES": _UPSCALE_MODES,
        "builder": "upscale",
    },
    "topazvideoupscale": {
        "PROVIDER": "topaz",
        "MODEL": "topaz-video-upscale",
        "endpoint": "upscale",
        "VALID_RESOLUTIONS": _UPSCALE_SCALES,
        "DEFAULT_RESOLUTION": "2x",
        "MODES": _UPSCALE_MODES,
        "builder": "upscale",
    },
    # Video tools (added 2026-11): source video in, video out. Like upscale, the
    # resolution picker carries the one choice (output format / subtitle language).
    "videobgremove": {
        "V1_URL": f"{POLLO_GENERATION_BASE}/video-background-remove",
        "VALID_RESOLUTIONS": ("webm", "mov"),
        "DEFAULT_RESOLUTION": "webm",
        "builder": "bgremove",
    },
    "videosubtitleremove": {
        "V1_URL": f"{POLLO_GENERATION_BASE}/video-subtitle-remove",
        "VALID_RESOLUTIONS": ("en", "zh", "all", "ja", "ko", "ar"),
        "DEFAULT_RESOLUTION": "en",
        "MODES": ("standard", "advanced"),
        "builder": "subtitle",
    },
    # Face swap: the source video plus one face image (first_frame).
    "faceswap": {
        "V1_URL": f"{POLLO_GENERATION_BASE}/face-swap",
        "builder": "faceswap",
    },
    # Lip-sync (added 2026-11): drive a reference image (a portrait) with an
    # audio track. Shape {image, audio} (+prompt, +resolution where offered).
    "omnihuman": {
        "PROVIDER": "bytedance",
        "MODEL": "omnihuman",
        "endpoint": "lipsync",
        "builder": "lipsync",
    },
    "omnihuman15": {
        "PROVIDER": "bytedance",
        "MODEL": "omnihuman-v1-5",
        "endpoint": "lipsync",
        "builder": "lipsync",
    },
    "hedracharv3": {
        "PROVIDER": "hedra",
        "MODEL": "hedra-character-v3",
        "endpoint": "lipsync",
        "VALID_RESOLUTIONS": ("540p", "720p"),
        "DEFAULT_RESOLUTION": "540p",
        "builder": "lipsync",
    },
    "h3lipsync": {
        "PROVIDER": "pollo-ai",
        "MODEL": "h3-lipsync",
        "endpoint": "lipsync",
        "VALID_RESOLUTIONS": ("480p", "720p", "1080p"),
        "DEFAULT_RESOLUTION": "720p",
        "NEEDS_PROMPT": True,
        "builder": "lipsync",
    },
}


def cfg(model_id: str) -> dict[str, Any]:
    """Return default and model-specific settings for a video model."""
    row = VIDEO_MODELS[model_id]
    base = {**_V1_VIDEO_DEFAULTS}
    if row.get("builder") == "kling":
        base.update(_KLING_BASE)
    return {**base, **row}


def video_model_url(model_id: str) -> str:
    """Return the generation endpoint for a video model."""
    c = cfg(model_id)
    if c.get("V1_URL"):
        return c["V1_URL"]
    return f"{POLLO_GENERATION_BASE}/{c['PROVIDER']}/{c['MODEL']}/{c['endpoint']}"


def _normalize_refs(refs: list[dict[str, object]] | None) -> list[dict[str, Any]] | None:
    if not refs:
        return None
    out: list[dict[str, Any]] = []
    for ref in refs:
        url = str(ref.get("url") or ref.get("image") or ref.get("video") or ref.get("audio") or "").strip()
        if not url:
            continue
        item: dict[str, Any] = {"url": url}
        if ref.get("type"):
            item["type"] = ref["type"]
        # The handle the prompt mentions as [@name] (Kling 4.0 / Omni, MiniMax
        # H3…). Pollo defaults it to ref1, ref2… by position when omitted.
        if ref.get("name"):
            item["name"] = ref["name"]
        out.append(item)
    return out or None


def _resolve_resolution(c: dict[str, object], **kw: object) -> str:
    if c.get("FORCE_RESOLUTION"):
        return c["FORCE_RESOLUTION"]
    return kw.get("resolution") or c["DEFAULT_RESOLUTION"]


def _resolve_length(c: dict[str, object], **kw: object) -> int:
    length_str = str(kw.get("length") or c["DEFAULT_LENGTH"])
    if kw.get("refs") and c["REF_VALID_LENGTHS"]:
        length = int(length_str) if length_str.isdigit() else c["DEFAULT_LENGTH"]
        return min(c["REF_VALID_LENGTHS"], key=lambda v: abs(v - length))
    return valid_length(length_str, c["VALID_LENGTHS"], c["DEFAULT_LENGTH"])


def _resolve_aspect_ratio(c: dict[str, object], **kw: object) -> str:
    # the explicit kwarg, then a model default ("adaptive" on a few), else the
    # base "portrait" → 9:16.
    return kw.get("aspect_ratio") or c.get("DEFAULT_RATIO") or parse_aspect_ratio("portrait")


def _resolve_mode(c: dict[str, object], resolution: str, mode: str | None) -> str | None:
    if not c["HAS_MODE"]:
        return None
    if c.get("MODE_PRO_RESOLUTIONS"):
        return "pro" if resolution.upper() in {r.upper() for r in c["MODE_PRO_RESOLUTIONS"]} else "basic"
    return mode or c.get("MODE_DEFAULT")


def _process_inputs(c: dict[str, object], image_url: str | None, **kw: object) -> dict[str, Any]:
    """Resolve request inputs against a model's configuration.

    Use the caller's value or the model default; unsupported fields stay None.
    """
    refs = _normalize_refs(kw.get("refs")) if c["HAS_REFS"] else None
    resolution = _resolve_resolution(c, **kw)
    return {
        "refs": refs,
        "is_text_only": image_url is None,
        "resolution": resolution,
        "length": _resolve_length(c, **kw),
        "aspect_ratio": _resolve_aspect_ratio(c, **kw),
        "image_tail": kw.get("image_tail") if c["HAS_IMAGE_TAIL"] else None,
        "seed": kw.get("seed") if c["HAS_SEED"] else None,
        "generate_audio": (
            (True if kw.get("generate_audio") is None else kw["generate_audio"]) if c["HAS_GENERATE_AUDIO"] else None
        ),
        "web_search": ((False if kw.get("web_search") is None else kw["web_search"]) if c["HAS_WEB_SEARCH"] else None),
        "mode": _resolve_mode(c, resolution, kw.get("mode")),
        "negative_prompt": kw.get("negative_prompt") if c["HAS_NEGATIVE_PROMPT_AUDIO"] else None,
        "audio_url": kw.get("audio_url") if c["HAS_NEGATIVE_PROMPT_AUDIO"] else None,
    }


def _generic_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **_: object,
) -> dict[str, Any]:
    refs, is_text_only = s["refs"], s["is_text_only"]
    attrs: dict[str, Any] = {"prompt": prompt}
    if refs:
        attrs["refs"] = refs
    elif not is_text_only:
        attrs["image"] = image_url
    attrs["duration"] = s["length"]
    if s["resolution"]:  # some models (Sora 2) have no resolution field
        attrs["resolution"] = s["resolution"]
    # Only send aspectRatio when the model actually offers one (a few, e.g.
    # Hailuo 2.3, take none and derive it from the image).
    if (refs or is_text_only or c["HAS_ASPECT_RATIO_ON_IMAGE"]) and c["VALID_RATIOS"]:
        attrs["aspectRatio"] = s["aspect_ratio"]

    has_refs = bool(refs)
    image_branch = not has_refs and not is_text_only
    candidates = {
        "imageTail": ((s["image_tail"] or None) if c["HAS_IMAGE_TAIL"] else None, image_branch),
        "generateAudio": (s["generate_audio"], True),
        "webSearch": (s["web_search"], not has_refs),
        "seed": (s["seed"], c["REF_HAS_SEED"] or not has_refs),
        "mode": (s["mode"] or None, True),
        "negativePrompt": (s["negative_prompt"] or None, True),
        "audio": (s["audio_url"] or None, not has_refs),
    }
    attrs.update({k: v for k, (v, allowed) in candidates.items() if v is not None and allowed})
    return {"input": attrs}


def _kling_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **_: object,
) -> dict[str, Any]:
    if s["is_text_only"] and not c["TEXT_TO_VIDEO"]:
        raise ValueError(f"{c['MODEL']} needs a source image (it has no text-to-video mode)")
    payload = _generic_payload(c, prompt, image_url, s)
    attrs = payload["input"]
    tier = attrs.pop("resolution", None)
    if tier in c["VALID_RESOLUTIONS"]:
        if not c["RESOLUTION_IS_MODE"]:
            attrs["resolution"] = tier
        elif c["MODE_ON_TEXT"] or not s["is_text_only"]:
            attrs["mode"] = tier
    if "imageTail" in attrs:
        if c["IMAGE_TAIL_NEEDS_PRO"]:
            attrs["mode"] = "pro"
        if c["NO_AUDIO_WITH_IMAGE_TAIL"]:
            attrs.pop("generateAudio", None)
    return payload


def _extend_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    video_url = kw.get("video_url")
    if not video_url:
        raise ValueError("Extending needs the source video's URL")
    attrs: dict[str, Any] = {"video": video_url}
    if prompt:
        attrs["prompt"] = prompt
    attrs["duration"] = s["length"]
    attrs["resolution"] = s["resolution"]
    if s["generate_audio"] is not None:
        attrs["generateAudio"] = s["generate_audio"]
    if s["seed"] is not None:
        attrs["seed"] = s["seed"]
    return {"input": attrs}


def _edit_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    video_url = kw.get("video_url")
    if not video_url:
        raise ValueError("Editing needs the source video's URL")
    if not prompt:
        raise ValueError("Editing needs an instruction prompt")
    attrs: dict[str, Any] = {"video": video_url, "prompt": prompt}
    if c["VALID_RESOLUTIONS"] and s["resolution"]:
        attrs["resolution"] = s["resolution"]
    return {"input": attrs}


def _upscale_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    """Build a video-upscale body containing the source, scale, and mode.

    Unknown scale or mode values fall back to the model defaults.
    """
    video_url = kw.get("video_url")
    if not video_url:
        raise ValueError("Upscaling needs the source video's URL")
    scales = {v.lower(): v for v in c["VALID_RESOLUTIONS"]}
    scale = scales.get(str(s["resolution"]).lower(), c["DEFAULT_RESOLUTION"])
    mode = kw.get("mode") if kw.get("mode") in c["MODES"] else c["MODES"][0]
    return {"input": {"video": video_url, "scale": scale, "mode": mode}}


def _bgremove_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    """Video background removal: {video, outputFormat} (webm / mov, both transparent)."""
    if not kw.get("video_url"):
        raise ValueError("Background removal needs the source video's URL")
    fmt = s["resolution"] if s["resolution"] in c["VALID_RESOLUTIONS"] else c["DEFAULT_RESOLUTION"]
    return {"input": {"video": kw["video_url"], "outputFormat": fmt}}


def _subtitle_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    """Subtitle removal: {video, language, tier}; unknown values fall back to the defaults."""
    if not kw.get("video_url"):
        raise ValueError("Subtitle removal needs the source video's URL")
    lang = s["resolution"] if s["resolution"] in c["VALID_RESOLUTIONS"] else c["DEFAULT_RESOLUTION"]
    tier = kw.get("mode") if kw.get("mode") in c["MODES"] else c["MODES"][0]
    return {"input": {"video": kw["video_url"], "language": lang, "tier": tier}}


def _faceswap_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    """Face swap: the source video plus a face image."""
    if not kw.get("video_url"):
        raise ValueError("Face swap needs the source video's URL")
    if not image_url:
        raise ValueError("Face swap needs a face image URL")
    return {"input": {"video": kw["video_url"], "faceImage": image_url}}


def _lipsync_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    """Build a lip-sync body from a reference image and audio track.

    Include a prompt when supplied or required, and resolution when supported.
    """
    audio_url = kw.get("audio_url")
    if not image_url:
        raise ValueError("Lip sync needs a reference image URL")
    if not audio_url:
        raise ValueError("Lip sync needs an audio URL")
    if c.get("NEEDS_PROMPT") and not prompt:
        raise ValueError("Lip sync needs a prompt")
    attrs: dict[str, Any] = {"image": image_url, "audio": audio_url}
    if prompt:
        attrs["prompt"] = prompt
    if c["VALID_RESOLUTIONS"] and s["resolution"]:
        attrs["resolution"] = s["resolution"]
    return {"input": attrs}


def _motion_payload(
    c: dict[str, object],
    prompt: str,
    image_url: str | None,
    s: dict[str, object],
    **kw: object,
) -> dict[str, Any]:
    """Build a motion-transfer body from a reference image and source video.

    ``mode`` is sent only when the model supports it.
    """
    video_url = kw.get("video_url")
    if not video_url:
        raise ValueError("This model needs the source video's URL")
    if not image_url:
        raise ValueError("This model needs a reference image URL")
    attrs: dict[str, Any] = {"image": image_url, "video": video_url}
    if c["HAS_MODE"]:
        attrs["mode"] = s["mode"] or c["DEFAULT_MODE"]
    return {"input": attrs}


_BUILDERS = {
    "generic": _generic_payload,
    "kling": _kling_payload,
    "extend": _extend_payload,
    "edit": _edit_payload,
    "upscale": _upscale_payload,
    "bgremove": _bgremove_payload,
    "subtitle": _subtitle_payload,
    "faceswap": _faceswap_payload,
    "lipsync": _lipsync_payload,
    "motion": _motion_payload,
}


def video_payload(model_id: str, *, prompt: str, image_url: str | None, **kw: object) -> dict[str, Any]:
    """Build the video API body for any model, dispatching on its family."""
    c = cfg(model_id)
    build = _BUILDERS.get(c["builder"])
    if build is None:
        raise ValueError(f"unknown builder {c['builder']!r} for {model_id}")
    return build(c, prompt, image_url, _process_inputs(c, image_url, **kw), **kw)
