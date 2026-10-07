"""
Pollo Video Generator — API Backend (FastAPI)

Run:  python web/app.py   (from the pollo root directory)
"""
import os
import sys
import json
import shutil
import uuid
import threading
import hashlib
import time
from collections import Counter
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Optional, TypedDict
from contextlib import asynccontextmanager

import requests as _requests
from bs4 import BeautifulSoup as _BeautifulSoup
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Cookie, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import cv2
import uvicorn

# ── Bootstrap ───────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent.resolve()
WEB_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)
load_dotenv(override=True)

from img2vid.pollo.pollo_img2vid import get_video_generator, GENERATORS, get_image_generator, IMAGE_GENERATORS
from img2vid.pollo.generators import SUCCESS_STATUSES, ERROR_STATUSES
from img2vid.common.get_task import get_task_status, get_credit_balance
from img2vid.common.download import download_video, download_image, download_generated_image, get_filename_from_url
from img2vid.common.metadata import get_db, iso

# ── Authentication ───────────────────────────────────────────────────
from .auth import verify_api_key, is_auth_enabled, get_api_keys
from . import characters
from .chat import router as chat_router, startup_resume_chat
from .uploads import image_media_type, read_image_upload, safe_filename


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: resume polling for any jobs stuck in processing
    startup_resume_jobs()
    startup_resume_chat()
    yield
    # Shutdown: nothing to do


app = FastAPI(title="Pollo Video Generator API", lifespan=lifespan)

# CORS - allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                    "https://localhost:5173", "https://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Constants ───────────────────────────────────────────────────────
# "legacy": True marks a model as living on Pollo's pre-v1 API
# (POLLO_API_BASE, no "/v1/" in the URL) — see BaseV1VideoGenerator's
# docstring in img2vid/pollo/generators.py. These are hidden from the model
# dropdown unless the frontend's "legacy mode" toggle is on (GET
# /api/models filters them out by default; see get_models() below).
# Models with no "legacy" key are on the current v1 API and always shown.
#
# "ref_mode" (v1 models only) describes the model's Reference-To-Video
# branch, which the frontend exposes as a "Ref mode" toggle (the legacy API
# used separate "type": "ref" models instead). From docs.pollo.ai/openapi.json:
# allowed ref "types", total "max" refs, optional per-type "limits", and
# optional "lengths"/"resolutions" when they differ from the image/text
# branches. "hide_options" lists options the ref branch lacks (web_search
# and image_tail never exist there). "max_length_with_video" caps duration
# when a video ref is present; "exclusive" ref types can't be combined.
MODEL_INFO = {
    "pollodance20": {
        "label": "Pollo Dance 2.0", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
        "legacy": True,
    },
    "pollodance20fast": {
        "label": "Pollo Dance 2.0 Fast", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
        "legacy": True,
    },
    "pollo20": {
        "label": "Pollo 2.0", "type": "img2vid",
        "lengths": [5, 10],
        "ratios": ["9:16", "16:9"],
        "options": ["generate_audio", "web_search"],
        "legacy": True,
    },
    "pollo25": {
        "label": "Pollo 2.5", "type": "img2vid",
        "lengths": [4, 5, 6, 7, 8, 9, 10, 11, 12, 15],
        "resolutions": ["720p", "1080p"],
        "options": ["generate_audio", "web_search"],
        "legacy": True,
    },
    "pollodanceref": {
        "label": "Pollo Dance Ref", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
        "legacy": True,
    },
    "pollodancereffast": {
        "label": "Pollo Dance Ref Fast", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
        "legacy": True,
    },
    "seedance20": {
        "label": "Seedance 2.0", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "legacy": True,
    },
    "seedance20fast": {
        "label": "Seedance 2.0 Fast", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "legacy": True,
    },
    "seedance20mini": {
        "label": "Seedance 2.0 Mini", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
        "legacy": True,
    },
    "seedance25": {
        "label": "Seedance 2.5", "type": "img2vid",
        "lengths": list(range(4, 31)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9", "adaptive"],
        "resolutions": ["480p", "720p"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "legacy": True,
    },
    "seedanceref": {
        "label": "Seedance 2.0 Ref", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "legacy": True,
    },
    "seedancereffast": {
        "label": "Seedance 2.0 Ref Fast", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "legacy": True,
    },
    "seedanceminiref": {
        "label": "Seedance 2.0 Mini Ref", "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
        "legacy": True,
    },
    "minimaxh3": {
        "label": "MiniMax H3", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480P", "768P", "2K"],
        "options": ["resolution", "image_tail", "prompt_optimizer"],
        "legacy": True,
    },
    "wan27": {
        "label": "Wan 2.7", "type": "img2vid",
        "lengths": list(range(2, 16)),
        "resolutions": ["720P", "1080P"],
        "options": ["seed", "image_tail", "negative_prompt", "audio_url"],
        "deprecated": True,
        "legacy": True,
    },
    "wan30": {
        "label": "Wan 3.0", "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480P", "720P", "1080P"],
        "options": ["generate_audio", "num_outputs"],
        "note": "numOutputs field name is unconfirmed (inferred, not yet verified against a live response).",
        "legacy": True,
    },
    "wan30prime": {
        "label": "Wan 3.0 Prime", "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480P", "720P", "1080P"],
        "options": ["generate_audio", "num_outputs"],
        "note": "numOutputs field name is unconfirmed (inferred, not yet verified against a live response).",
        "legacy": True,
    },
    "pollojourney": {
        "label": "Pollo Journey 8.2", "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["seed", "images"],
        "legacy": True,
    },
    "seedream": {
        "label": "Seedream 5.0 Lite", "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9"],
        "resolutions": ["2K", "3K", "4K"],
        "options": ["images", "max_images"],
        "legacy": True,
    },
    "nanobanana2": {
        "label": "Nano Banana 2", "type": "image",
        "ratios": ["1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"],
        "resolutions": ["1K", "2K", "4K"],
        "options": ["images", "max_images", "thinking_level"],
        "deprecated": True,
        "legacy": True,
    },
    "polloimage2": {
        "label": "Pollo Image 2.0", "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "4:5", "5:4"],
        "resolutions": ["1K", "2K", "4K"],   # 2K/4K run in Pollo's "professional" mode
        "options": ["images"],
        "legacy": True,
        "legacy_only": True,   # its v1 endpoint isn't enabled for API access — offered in both modes
    },

    # ── v1 API (current — https://docs.pollo.ai) ─────────────────────
    "pollo20v1": {
        "label": "Pollo 2.0", "type": "img2vid",
        "lengths": [5, 10],
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["16:9", "9:16", "4:3", "3:4", "1:1"],
        "options": ["generate_audio", "seed", "refs"],
        "ref_mode": {"types": ["image"], "max": 7, "lengths": list(range(1, 9)), "resolutions": ["540p", "720p", "1080p"]},
    },
    "pollo25v1": {
        "label": "Pollo 2.5", "type": "img2vid",
        "lengths": [4, 5, 6, 7, 8, 9, 10, 11, 12, 15],
        "resolutions": ["720p", "1080p"],
        "ratios": ["16:9", "9:16"],
        "options": ["generate_audio", "mode"],
    },
    "pollodance20v1": {
        "label": "Pollo Dance 2.0", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 13, "limits": {"image": 9, "video": 3, "audio": 3}, "hide_options": ["seed"]},
    },
    "pollodance20fastv1": {
        "label": "Pollo Dance 2.0 Fast", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 13, "limits": {"image": 9, "video": 3, "audio": 3}, "hide_options": ["seed"]},
    },
    "seedance20v1": {
        "label": "Seedance 2.0", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p", "1080p", "4K"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance20fastv1": {
        "label": "Seedance 2.0 Fast", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance20miniv1": {
        "label": "Seedance 2.0 Mini", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance25v1": {
        "label": "Seedance 2.5", "type": "img2vid",
        "lengths": list(range(4, 31)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 50, "limits": {"image": 30, "video": 10, "audio": 10}},
    },
    "minimaxh3v1": {
        "label": "MiniMax H3", "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "768p", "2K"],
        "ratios": ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "minimaxh3max": {
        "label": "MiniMax H3 Max", "type": "img2vid",
        "lengths": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "resolutions": ["480p", "768p", "1080p"],
        "ratios": ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 12, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "wan27v1": {
        "label": "Wan 2.7", "type": "img2vid",
        "lengths": list(range(2, 16)),
        "resolutions": ["720p", "1080p"],
        "ratios": ["16:9", "1:1", "4:3", "3:4", "9:16"],
        "options": ["seed", "image_tail", "negative_prompt", "audio_url", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 10, "limits": {"image": 5, "video": 5, "audio": 1}, "max_length_with_video": 10, "hide_options": ["audio_url"]},
        "deprecated": True,
    },
    "wan30v1": {
        "label": "Wan 3.0", "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"],
        "options": ["generate_audio", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio", "file", "link"], "max": 22, "limits": {"image": 10, "video": 5, "audio": 5, "file": 1, "link": 1}, "exclusive": ["file", "link"]},
    },
    "wan30primev1": {
        "label": "Wan 3.0 Prime", "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"],
        "options": ["generate_audio", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio", "file", "link"], "max": 22, "limits": {"image": 10, "video": 5, "audio": 5, "file": 1, "link": 1}, "exclusive": ["file", "link"]},
    },
    "klingv21v1": {
        "label": "Kling 2.1", "type": "img2vid",
        "lengths": [5, 10],
        "resolutions": ["std", "pro"],   # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": [],
        "note": "Image-to-video only — needs a source image.",
    },
    "klingv21masterv1": {
        "label": "Kling 2.1 Master", "type": "img2vid",
        "lengths": [5, 10],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": [],
    },
    "klingv25turbov1": {
        "label": "Kling 2.5 Turbo", "type": "img2vid",
        "lengths": [5, 10],
        "resolutions": ["std", "pro"],   # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["image_tail"],
    },
    "klingvideoo1v1": {
        "label": "Kling Video O1", "type": "img2vid",
        "lengths": [5, 10],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["image_tail"],
    },
    "klingv26v1": {
        "label": "Kling 2.6", "type": "img2vid",
        "lengths": [5, 10],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["generate_audio", "image_tail"],
    },
    "klingv3v1": {
        "label": "Kling 3.0", "type": "img2vid",
        "lengths": list(range(3, 16)),
        "resolutions": ["std", "pro", "4K"],   # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["generate_audio", "image_tail"],
    },
    "klingv3turbov1": {
        "label": "Kling 3.0 Turbo", "type": "img2vid",
        "lengths": list(range(3, 16)),
        "resolutions": ["720p", "1080p"],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": [],
    },
    "klingv3omniv1": {
        "label": "Kling 3.0 Omni", "type": "img2vid",
        "lengths": list(range(3, 16)),
        "resolutions": ["std", "pro", "4K"],   # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["generate_audio", "image_tail"],
    },
    "pollojourneyv1": {
        "label": "Pollo Journey 8.2", "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["seed", "images"],
    },
    "seedreamv1": {
        "label": "Seedream 5.0 Lite", "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9"],
        "resolutions": ["2K", "3K", "4K"],
        "options": ["images"],
    },
    "nanobanana2v1": {
        "label": "Nano Banana 2", "type": "image",
        "ratios": ["1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5",
                   "21:9", "1:4", "4:1", "8:1", "1:8"],
        "resolutions": ["0.5K", "1K", "2K", "4K"],
        "options": ["images"],
    },
    "klingv3imagev1": {
        "label": "Kling 3.0 Image", "type": "image",
        "ratios": ["1:1", "3:2", "2:3", "3:4", "4:3", "16:9", "9:16", "21:9"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "klingv3omniimagev1": {
        "label": "Kling 3.0 Omni Image", "type": "image",
        "ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "auto"],
        "resolutions": ["1K", "2K", "4K"],
        "options": ["images"],
    },
    "qwenimage": {
        "label": "Qwen Image", "type": "image",
        "hidden": "Not enabled for API access on this key (403)",   # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],   # text-to-image only; an edit keeps the image's shape
        "options": ["images"],
        "legacy": True,
        "legacy_only": True,   # v1 qwen/* endpoints 404 — offered in both modes
    },
    "seedreamflashv1": {
        "label": "Seedream 5.0 Flash", "type": "image",
        "hidden": "Not enabled for API access on this key (403)",   # checked with real requests 2026-10-06
        "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "resolutions": ["1K", "1.5K", "2K"],
        "options": ["images"],
    },
    "seedreamprov1": {
        "label": "Seedream 5.0 Pro", "type": "image",
        "hidden": "Not enabled for API access on this key (403)",   # checked with real requests 2026-10-06
        "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimage3v1": {
        "label": "Qwen Image 3", "type": "image",
        "hidden": "Pollo doesn't serve it to this key yet (404)",   # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimage3prov1": {
        "label": "Qwen Image 3 Pro", "type": "image",
        "hidden": "Pollo doesn't serve it to this key yet (404)",   # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimageflashv1": {
        "label": "Qwen Image Flash", "type": "image",
        "hidden": "Not enabled for API access on this key (403)",   # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "options": [],
    },
}

# Support external data directory via env var (same as metadata.py)
_data_dir_env = os.environ.get("POLLO_DATA_DIR")
print(f"📁 POLLO_DATA_DIR env var: {_data_dir_env or '(not set, using local)'}")
POLLO_ROOT = Path(_data_dir_env) if _data_dir_env else ROOT_DIR
ASSETS_DIR = POLLO_ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Thumbnail cache directory (for video frame caching)
# Stored in data directory to keep all data together
THUMB_CACHE_DIR = POLLO_ROOT / "cache" / "thumbnails"
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Polling retry constants — used by run_generation() and resume_polling_job()
MAX_POLL_ERRORS = 6          # give up after this many consecutive failures (~3 min)
POLL_BACKOFF_BASE = 10       # base sleep between polls (seconds)
POLL_BACKOFF_MAX = 60        # max backoff on transient errors
STALE_JOB_SECONDS = 180      # consider a non-terminal job stale after 3 min of no updates

# Sending retry behaviour for initial POST to API — helps when VPN/gluetun causes
# intermittent 5xx/502 responses but the remote task may still have been created.
SEND_RETRIES = 3             # number of attempts for initial send (counting first)
SEND_RETRY_BACKOFF = 2      # seconds between send retries (simple linear backoff)

# Litterbox (temporary image hosting for source uploads)
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
LITTERBOX_EXPIRY = "1h"  # 1h, 12h, 24h, 72h

print(f"📁 Pollo root: {POLLO_ROOT}")
print(f"📁 Assets directory: {ASSETS_DIR}")
print(f"📁 Data directory: {POLLO_ROOT / 'data'}")
print(f"📁 Thumbnail cache (frames): {THUMB_CACHE_DIR}")
print("📁 Project thumbnails will be saved to: ASSETS_DIR/<project>/thumb.jpg")


# ── In-Memory TTL Cache ─────────────────────────────────────────────
class TTLCache:
    """Simple in-memory cache with TTL expiration."""
    def __init__(self, default_ttl: float = 30.0):
        self._cache: dict = {}
        self._timestamps: dict = {}
        self._ttls: dict = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._cache:
                return None
            ttl = self._ttls.get(key, self._default_ttl)
            if time.time() - self._timestamps[key] > ttl:
                del self._cache[key]
                del self._timestamps[key]
                self._ttls.pop(key, None)
                return None
            return self._cache[key]

    def set(self, key: str, value: Any, ttl: float | None = None):
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            if ttl is not None:
                self._ttls[key] = ttl
            else:
                self._ttls.pop(key, None)  # use default

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._ttls.clear()


# Cache instances — ONLY for immutable lookups (slug→folder never changes once created)
_project_lookup_cache = TTLCache(default_ttl=120.0)  # Project slug -> assets_folder lookups (for file serving)


def _get_project_assets_folder(slug: str) -> str | None:
    """Get assets folder for a project slug with caching."""
    cache_key = f"project:{slug}"
    cached = _project_lookup_cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__NOT_FOUND__" else None

    db = get_db()
    proj = db.get_project_by_slug(slug)
    if proj:
        _project_lookup_cache.set(cache_key, proj.assets_folder)
        return proj.assets_folder
    else:
        _project_lookup_cache.set(cache_key, "__NOT_FOUND__")
        return None


def _invalidate_project_caches():
    """Invalidate all project-related caches."""
    _project_lookup_cache.clear()


# ── Pydantic Models ─────────────────────────────────────────────────

class JobArchivedResult(TypedDict):
    archived: bool
    job_id: str


class ProjectArchivedResult(TypedDict):
    archived: bool
    slug: str


class GenerateRequest(BaseModel):
    model: str = "pollodance20"
    project: str | None = None  # project slug
    prompt: str
    image_url: str | None = None
    video_url: str | None = None
    subject_url: str | None = None
    audio_url: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    length: int | None = None
    generate_audio: bool | None = None
    web_search: bool | None = None
    image_tail: str | None = None
    seed: int | None = None
    negative_prompt: str | None = None
    num_outputs: int | None = None
    refs: list | None = None  # ref2video: array of {type, name, image, order, avatarId?}
    video_num: int | None = None  # ref2video: 1-4
    image_meta: list | None = None  # ref2video: array of {url, order, name?, cropper?}
    character_ids: list[int] = []   # see web/characters.py
    ref_mode: bool = False          # v1 "Ref mode" is on (character images go in as refs even with no other refs)


class BulkMoveRequest(BaseModel):
    job_ids: list[str]
    target_project: str


class GenerateImageRequest(BaseModel):
    model: str = "pollojourney"
    project: str | None = None
    prompt: str
    image_url: str | None = None
    images: list[str] | None = None
    aspect_ratio: str | None = None
    seed: int | None = None
    style: str | None = None
    resolution: str | None = None
    max_images: int | None = None
    thinking_level: str | None = None
    character_ids: list[int] = []   # see web/characters.py


class ProjectCreate(BaseModel):
    name: str  # Display name
    prompt: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    subject_url: str | None = None
    audio_url: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None  # Rename display name
    prompt: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    subject_url: str | None = None
    audio_url: str | None = None


class VpnCountryRequest(BaseModel):
    country: str


class LoginRequest(BaseModel):
    key: str


# ── Auth Routes ─────────────────────────────────────────────────────

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


@app.post("/api/auth/login")
async def api_auth_login(data: LoginRequest, response: Response, request: Request):
    key = data.key.strip()
    auth_keys = get_api_keys()
    if auth_keys and key not in auth_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    is_https = request.headers.get("x-forwarded-proto", "").lower() == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=key,
        httponly=True,
        samesite="strict",
        secure=is_https,
        max_age=COOKIE_MAX_AGE,
    )
    return {"ok": True}


@app.post("/api/auth/logout")
async def api_auth_logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, samesite="strict")
    return {"ok": True}


@app.get("/api/auth/status")
async def api_auth_status(session: Optional[str] = Cookie(None)):
    enabled = is_auth_enabled()
    if not enabled:
        return {"enabled": False, "authenticated": True}
    authenticated = session is not None and session.strip() in get_api_keys()
    return {"enabled": True, "authenticated": authenticated}


# ── Background worker ──────────────────────────────────────────────

def _poll_task(job_id: str, task_id: str, api_key: str,
               on_poll: Callable[[], bool] | None = None) -> list[tuple[str, str | None, str | None, int | None]] | None:
    """Poll a task until completion, handling retries and backoff.

    *on_poll* is called before each sleep so callers can inject extra
    checks (e.g. detecting that another thread already resolved the job).
    It should return ``True`` to abort polling early.

    Returns the final *results* list on success, or ``None`` if the job
    was marked as error (the DB is updated inline).
    """
    db = get_db()
    consecutive_errors = 0

    while True:
        sleep_time = min(POLL_BACKOFF_BASE * (2 ** consecutive_errors),
                         POLL_BACKOFF_MAX)
        time.sleep(sleep_time)

        if on_poll and on_poll():
            return None  # Caller requested early abort

        # Touch updated_at each poll cycle to prevent stale-job recovery
        db.update_job(job_id, message=f"Task {task_id} processing...")

        try:
            results = get_task_status(task_id, api_key)
        except Exception as poll_exc:
            consecutive_errors += 1
            msg = (f"Poll error ({consecutive_errors}/{MAX_POLL_ERRORS}): "
                   f"{poll_exc}")
            print(f"[Job {job_id}] {msg}")
            db.update_job(job_id,
                          message=f"Task {task_id} — retrying after "
                                  f"transient error ({consecutive_errors}/"
                                  f"{MAX_POLL_ERRORS})...")
            if consecutive_errors >= MAX_POLL_ERRORS:
                db.update_job(job_id, status="error",
                              message=f"Polling failed after "
                                      f"{MAX_POLL_ERRORS} retries: "
                                      f"{poll_exc}")
                return None
            continue

        api_status, fail_msg, url, _credits = results[0]
        print(f"[Job {job_id}] Poll result: status={api_status}, url={url}")

        # Cloudflare block is transient — retry like a network error
        if api_status == "cloudflare_blocked":
            consecutive_errors += 1
            print(f"[Job {job_id}] Cloudflare blocked "
                  f"({consecutive_errors}/{MAX_POLL_ERRORS})")
            db.update_job(job_id,
                          message=f"Task {task_id} — Cloudflare block, "
                                  f"retrying ({consecutive_errors}/"
                                  f"{MAX_POLL_ERRORS})...")
            if consecutive_errors >= MAX_POLL_ERRORS:
                db.update_job(job_id, status="error",
                              message=fail_msg or "Cloudflare blocked "
                                      "after max retries")
                return None
            continue

        # Reset consecutive error counter on any successful poll
        consecutive_errors = 0

        if api_status in ERROR_STATUSES:
            db.update_job(job_id, status="error",
                          message=fail_msg or "Generation failed")
            return None

        # For multi-video (videoNum > 1), wait until all are done
        if api_status in SUCCESS_STATUSES:
            all_done = all(r[0] in SUCCESS_STATUSES for r in results)
            if all_done:
                return results


def _send_and_extract_task(generator, job_id: str, db) -> tuple[str, str] | None:
    """Send a generation request with retries, updating DB on error.

    Handles 5xx retries and accepts non-200 responses that carry a taskId.
    Returns (task_id, api_status) on success, or None if an error occurred
    (the job's DB record is already updated with status="error" in that case).
    """
    response = None
    resp_json = None
    last_exc: Exception | None = None

    for attempt in range(SEND_RETRIES):
        try:
            response = generator.send_request()
        except ConnectionError as exc:
            last_exc = exc
            db.update_job(job_id, message=f"Send attempt {attempt+1}/{SEND_RETRIES} failed: {exc}")
            if attempt < SEND_RETRIES - 1:
                time.sleep(SEND_RETRY_BACKOFF)
                continue
            db.update_job(job_id, status="error", message=str(exc))
            return None

        try:
            resp_json = response.json()
        except Exception:
            resp_json = None

        if response.status_code == 200 and resp_json and resp_json.get("code") == "SUCCESS":
            break
        if resp_json and isinstance(resp_json.get("data"), dict) and resp_json.get("data", {}).get("taskId"):
            break
        if 500 <= response.status_code < 600 and attempt < SEND_RETRIES - 1:
            db.update_job(job_id, message=f"API responded HTTP {response.status_code}, retrying ({attempt+1}/{SEND_RETRIES})...")
            time.sleep(SEND_RETRY_BACKOFF)
            continue
        break

    if response is None:
        db.update_job(job_id, status="error", message=str(last_exc or "No response from API"))
        return None
    if resp_json is None:
        body_preview = response.text[:200] if response.text else "(empty)"
        db.update_job(job_id, status="error",
                      message=f"API returned non-JSON (HTTP {response.status_code}): {body_preview}")
        return None
    if response.status_code != 200 and not resp_json.get("data", {}).get("taskId"):
        db.update_job(job_id, status="error",
                      message=resp_json.get("message", f"API request failed (HTTP {response.status_code})"))
        return None

    task_id = resp_json.get("data", {}).get("taskId")
    api_status = resp_json.get("data", {}).get("status")
    if not task_id or not api_status:
        db.update_job(job_id, status="error", message="No task ID returned from API")
        return None

    return task_id, api_status


def _submit_and_poll(generator, job_id: str, db) -> tuple[str, list] | None:
    """Send the generator's request and poll it to completion. Returns
    (task_id, results), or None once the job has been marked as failed."""
    db.update_job(job_id, status="sending", message="Sending request to API...")
    sent = _send_and_extract_task(generator, job_id, db)
    if sent is None:
        return None
    task_id, _api_status = sent
    db.update_job(job_id, status="processing", task_id=task_id,
                  message=f"Task {task_id} processing...")
    results = _poll_task(job_id, task_id, generator.api_key)
    if results is None:
        return None  # Error already recorded by _poll_task
    return task_id, results


def _result_urls(results: list) -> list[str]:
    """The media URLs of a finished task's successful outputs."""
    return [r[2] for r in results if r[0] in SUCCESS_STATUSES and r[2]]


def _credits_used(results: list) -> int | None:
    return sum(r[3] for r in results if r[3] is not None) or None


def _refresh_job_project(job_id: str, assets_folder: str) -> None:
    """After a job saved new media: refresh caches and its project's thumbnail."""
    job = get_db().get_job(job_id)
    _refresh_project_media(assets_folder, job.project if job else None)


def run_generation(job_id: str, model: str, kwargs: dict):
    """Run video generation in a background thread, updating the DB."""
    db = get_db()
    try:
        db.update_job(job_id, status="creating", message="Creating generator...")
        generator = get_video_generator(model, **kwargs)
        project = generator.project

        # Download source image for img2vid if needed
        if not generator.is_text_only and not (hasattr(generator, "is_video_edit") and generator.is_video_edit):
            if not generator.image_url:
                if not (hasattr(generator, "refs") and generator.refs):
                    db.update_job(job_id, status="error",
                                  message="image_url is required for image-to-video generation but was not provided")
                    return
            else:
                download_image(generator.image_url, project)

        polled = _submit_and_poll(generator, job_id, db)
        if polled is None:
            return
        task_id, results = polled
        video_urls = _result_urls(results)

        if not video_urls:
            db.update_job(job_id, status="error", message="No video URL in result")
            return

        db.update_job(job_id, status="downloading", message="Downloading video...",
                       video_url=video_urls[0])

        # Download all videos (multi-video support for ref2video)
        filepath = None
        for vid_url in video_urls:
            filepath = download_video(
                vid_url, project, task_id=task_id, model=model,
                prompt=generator.prompt, metadata=generator.build_download_metadata(),
            )

        db.update_job(job_id, status="done", message="Video ready!",
                       video_path=filepath, credits_used=_credits_used(results))
        _refresh_job_project(job_id, project)

    except Exception as e:
        db.update_job(job_id, status="error", message=str(e))


# ── Helper ──────────────────────────────────────────────────────────


def _get_assets_path(project_slug: str) -> Path | None:
    """Get the assets folder path for a project by its slug."""
    assets_folder = _get_project_assets_folder(project_slug)
    if not assets_folder:
        return None
    return ASSETS_DIR / assets_folder


def _require_project(slug: str):
    """The project with this slug, or 404."""
    proj = get_db().get_project_by_slug(slug)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


def _refresh_project_media(assets_folder: str, project_slug: str | None, force: bool = True) -> None:
    """After a project's media changed: drop cached lookups and rebuild its thumbnail."""
    _invalidate_project_caches()
    _update_project_thumbnail(ASSETS_DIR / assets_folder, project_slug=project_slug, force=force)


def _job_params(job) -> dict:
    """A job's stored params (empty if missing or unreadable)."""
    try:
        return json.loads(job.params_json) if job.params_json else {}
    except (TypeError, ValueError):
        return {}


def _job_media_type(job) -> str:
    return "image" if (getattr(job, "job_type", "video") or "video") == "image" else "video"


def _job_files(job) -> set[str]:
    """Every media filename a job produced (multi-image jobs have several)."""
    names = {Path(job.video_path).name} if job.video_path else set()
    return names | {Path(p).name for p in _job_params(job).get("result_paths", [])}


def _enrich_job_result(result: dict, job, assets_path: Path | None = None) -> dict:
    """Add video_exists, update video_path if found elsewhere, add filename, and add media_type.
    Modifies result dict in-place and returns it."""
    exists, found_path = _find_video_for_job(job, assets_path)
    result["video_exists"] = exists

    if exists and found_path and found_path != job.video_path:
        get_db().update_job(job.job_id, video_path=found_path)
        result["video_path"] = found_path

    video_path = result.get("video_path") or found_path
    if video_path:
        result["filename"] = Path(video_path).name

    # media_type: prefer the stored job_type column; fall back to MODEL_INFO for older rows
    stored_type = result.get("job_type") or getattr(job, "job_type", None)
    if stored_type and stored_type in ("video", "image"):
        result["media_type"] = stored_type
    else:
        model_entry = MODEL_INFO.get(result.get("model", ""), {})
        result["media_type"] = "image" if model_entry.get("type") == "image" else "video"

    return result


def _find_video_for_job(job, assets_path: Path | None = None) -> tuple[bool, str | None]:
    """
    Check if a video exists for a job, trying multiple methods:
    1. Check job.video_path directly
    2. Try to find video by matching filename from video_url
    3. Try to find video by task_id in filename

    Returns (exists: bool, found_path: str | None)
    """
    # Method 1: Check stored video_path
    if job.video_path and Path(job.video_path).exists():
        return True, job.video_path

    # Need assets_path for other methods
    if not assets_path:
        db = get_db()
        proj = db.get_project_by_slug(job.project)
        if not proj:
            return False, None
        assets_path = ASSETS_DIR / proj.assets_folder

    if not assets_path.exists():
        return False, None

    # Method 2: Try to find by video_url filename
    if job.video_url:
        expected_filename = get_filename_from_url(job.video_url)
        if expected_filename:
            # Check for exact match or with (1), (2) suffix
            for video_file in assets_path.glob("*.mp4"):
                name = video_file.name
                # Check exact match
                if name == expected_filename:
                    return True, str(video_file)
                # Check with suffix like filename(1).mp4
                base, ext = expected_filename.rsplit('.', 1)
                if name.startswith(base) and name.endswith(f'.{ext}'):
                    return True, str(video_file)

    # Method 3: Try to find by task_id in filename
    if job.task_id:
        for video_file in assets_path.glob("*.mp4"):
            if job.task_id in video_file.name:
                return True, str(video_file)

    return False, None


def _get_latest_video_uncached(assets_dir: Path, exclude_filenames: set[str] | None = None) -> Path | None:
    """Get the most recent video file directly from disk (no cache).
    Optionally exclude specific filenames (e.g. archived videos)."""
    if not assets_dir.exists():
        return None
    videos = list(assets_dir.glob("*.mp4"))
    if exclude_filenames:
        videos = [v for v in videos if v.name not in exclude_filenames]
    if not videos:
        return None
    videos.sort(key=lambda v: v.stat().st_mtime, reverse=True)
    return videos[0]


def _get_archived_filenames(project_slug: str) -> set[str]:
    """Get filenames of archived videos for a project."""
    db = get_db()
    jobs = db.get_jobs_by_project(project_slug)
    return {
        Path(j.video_path).name
        for j in jobs
        if j.archived and j.video_path
    }


def _get_latest_image_uncached(assets_dir: Path, exclude_filenames: set[str] | None = None) -> Path | None:
    """Get the most recent generated image file from disk (no cache)."""
    if not assets_dir.exists():
        return None
    IMAGE_EXTS = ('*.jpg', '*.jpeg', '*.png', '*.webp')
    images = [p for ext in IMAGE_EXTS for p in assets_dir.glob(ext)
              if p.name != 'thumb.jpg' and p.name != 'image.jpg']
    if exclude_filenames:
        images = [p for p in images if p.name not in exclude_filenames]
    if not images:
        return None
    images.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return images[0]


def _update_project_thumbnail(assets_path: Path, project_slug: str | None = None, force: bool = False) -> bool:
    """Update the project thumbnail (thumb.jpg) from the latest non-archived video or image.
    Only updates if thumb.jpg doesn't exist or is older than the latest media file.
    Set force=True to always regenerate.
    Returns True if thumbnail was created/updated."""
    exclude = _get_archived_filenames(project_slug) if project_slug else None
    latest_video = _get_latest_video_uncached(assets_path, exclude_filenames=exclude)
    latest_image = _get_latest_image_uncached(assets_path, exclude_filenames=exclude)

    # Prefer video over image; fall back to image if no video exists
    latest_media = latest_video or latest_image
    if not latest_media:
        thumb_path = assets_path / "thumb.jpg"
        if thumb_path.exists():
            try:
                thumb_path.unlink()
            except Exception:
                pass
        return False

    thumb_path = assets_path / "thumb.jpg"

    if not force and thumb_path.exists():
        try:
            if thumb_path.stat().st_mtime >= latest_media.stat().st_mtime:
                return True
        except Exception:
            pass

    try:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        if latest_media == latest_image and not latest_video:
            # For image-only projects, copy the image directly
            shutil.copy2(str(latest_media), str(thumb_path))
            print(f"[Thumbnail] Updated {thumb_path.name} from image {latest_media.name}", flush=True)
            return True

        # Extract frame from latest video
        frame_data = _extract_first_frame_uncached(latest_media)
        if not frame_data:
            print(f"[Thumbnail] Failed to extract frame from {latest_media.name}", flush=True)
            return False
        thumb_path.write_bytes(frame_data)
        print(f"[Thumbnail] Updated {thumb_path.name} from {latest_media.name}", flush=True)
        return True
    except Exception as e:
        print(f"[Thumbnail] Failed to save: {e}", flush=True)
        return False


def _get_video_list(assets_dir: Path, sort_by_mtime: bool = False) -> list[tuple[Path, float]] | list[Path]:
    """Get video list from disk.
    When sort_by_mtime=True, returns list of (Path, mtime) tuples sorted newest-first.
    When sort_by_mtime=False, returns list of Paths sorted by name."""
    if not assets_dir.exists():
        return []

    videos = list(assets_dir.glob("*.mp4"))
    if sort_by_mtime:
        result = [(v, v.stat().st_mtime) for v in videos]
        result.sort(key=lambda x: x[1], reverse=True)
    else:
        videos.sort()
        result = videos

    return result


def _get_thumb_cache_path(video_path: Path) -> Path:
    """Get the cache path for a video thumbnail."""
    # Use hash of full path + mtime to handle file changes
    try:
        mtime = video_path.stat().st_mtime
    except OSError:
        mtime = 0
    cache_key = hashlib.md5(f"{video_path}:{mtime}".encode()).hexdigest()
    return THUMB_CACHE_DIR / f"{cache_key}.jpg"


def _cleanup_thumb_cache():
    """Remove cached video thumbnails whose source videos no longer exist.
    Iterates all project asset folders, builds a set of valid cache filenames,
    then deletes any .jpg in THUMB_CACHE_DIR that isn't in that set."""
    if not THUMB_CACHE_DIR.exists():
        return 0

    # Build the set of valid cache filenames from all existing videos
    valid_cache_names: set[str] = set()
    if ASSETS_DIR.exists():
        for project_dir in ASSETS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            for video_file in project_dir.glob("*.mp4"):
                cache_path = _get_thumb_cache_path(video_file)
                valid_cache_names.add(cache_path.name)

    # Delete orphaned cache files
    removed = 0
    for cached_file in THUMB_CACHE_DIR.glob("*.jpg"):
        if cached_file.name not in valid_cache_names:
            try:
                cached_file.unlink()
                removed += 1
            except Exception:
                pass

    if removed:
        print(f"[Thumbnail cleanup] Removed {removed} orphaned cached thumbnail(s)", flush=True)
    return removed


def _extract_first_frame_uncached(video_path: Path) -> bytes | None:
    """Extract the first frame from a video using OpenCV, returns JPEG bytes.
    No caching - always extracts fresh."""
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return None
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()
    except Exception:
        return None


def _extract_first_frame(video_path: Path) -> bytes | None:
    """Extract the first frame from a video using OpenCV, returns JPEG bytes.
    Uses disk cache to avoid repeated video file access."""

    # Check disk cache first
    cache_path = _get_thumb_cache_path(video_path)
    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except Exception:
            pass  # Fall through to extract

    # Extract from video (uncached)
    jpeg_bytes = _extract_first_frame_uncached(video_path)
    if jpeg_bytes is None:
        return None

    # Save to disk cache
    try:
        cache_path.write_bytes(jpeg_bytes)
    except Exception:
        pass  # Cache write failure is non-fatal

    return jpeg_bytes


# ═══════════════════════════════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════════════════════════════

# ── Generate ────────────────────────────────────────────────────────

def _project_for_generation(project_slug: str | None):
    """The named project (404 if missing) or, with no name, a new one.
    Returns (project, assets path); the assets folder exists either way."""
    db = get_db()
    slug = (project_slug or "").strip()
    if slug:
        project = db.get_project_by_slug(slug)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project not found: {slug}")
    else:
        project = db.create_project(name=f"Generation {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    assets_path = ASSETS_DIR / project.assets_folder
    assets_path.mkdir(parents=True, exist_ok=True)
    return project, assets_path


def _publish_local_image(assets_path: Path, ref: str, what: str = "image") -> str:
    """Upload a "local:<file>" image to a temporary public host (Pollo only
    takes URLs) and return its URL. 400 if the file is gone, 502 if every host fails."""
    return _publish_file(_get_local_image_path(assets_path, ref), ref, what)


def _publish_file(source: Path | None, ref: str, what: str) -> str:
    if not source or not source.is_file():
        raise HTTPException(status_code=400, detail=f"{what[:1].upper()}{what[1:]} not found: {ref}")
    try:
        url = _upload_image(source)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to upload {what}: {exc}")
    print(f"[Generate] Uploaded {what}: {url}")
    return url


CHARACTER_REFS = 4   # character images sent per generation (spread across the characters)


def _publish_character_ref(ref: str) -> str:
    """Upload a character image ("char:<id>/<file>") and return its public URL."""
    return _publish_file(characters.ref_path(ref), ref, "character image")


def _character_ref_room(refs: list, is_ref_model: bool, ref_mode: dict | None) -> int:
    """How many character images still fit beside the user's own refs."""
    if is_ref_model:
        return min(CHARACTER_REFS, 13 - len(refs))
    image_refs = sum(1 for r in refs if r.get("type", "image") == "image")
    room = ref_mode["max"] - len(refs)
    if "image" in ref_mode.get("limits", {}):
        room = min(room, ref_mode["limits"]["image"] - image_refs)
    return max(0, min(CHARACTER_REFS, room)) if "image" in ref_mode["types"] else 0


def _source_upload_params(local_ref: str | None, uploaded_url: str | None) -> dict:
    """Job params recording a source image uploaded for this generation: the
    permanent local ref plus the temporary public URL and when it was made,
    so regenerations use the URL until it expires, then the local file."""
    if not (local_ref and uploaded_url):
        return {}
    return {"source_local": local_ref, "source_uploaded": uploaded_url, "source_uploaded_at": int(time.time())}


def _validate_v1_refs(refs: list, ref_mode: dict) -> None:
    """Reject refs that a v1 model's Reference-To-Video branch can't take
    (see "ref_mode" in MODEL_INFO), before anything is uploaded or billed."""
    counts: dict[str, int] = {}
    for ref in refs:
        ref_type = ref.get("type", "image")
        if ref_type not in ref_mode["types"]:
            raise HTTPException(status_code=400, detail=f"This model doesn't accept {ref_type} references")
        counts[ref_type] = counts.get(ref_type, 0) + 1
    if len(refs) > ref_mode["max"]:
        raise HTTPException(status_code=400, detail=f"Too many references (max {ref_mode['max']})")
    for ref_type, limit in ref_mode.get("limits", {}).items():
        if counts.get(ref_type, 0) > limit:
            raise HTTPException(status_code=400, detail=f"Too many {ref_type} references (max {limit})")
    exclusive = ref_mode.get("exclusive", [])
    if sum(1 for t in exclusive if counts.get(t)) > 1:
        raise HTTPException(status_code=400, detail=f"Can't combine {' and '.join(exclusive)} references")
    if not any(t != "audio" for t in counts):
        raise HTTPException(status_code=400, detail="At least one non-audio reference is required")


@app.post("/api/generate")
def api_generate(data: GenerateRequest, _api_key: str = Depends(verify_api_key)):
    model = data.model
    if model not in GENERATORS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    prompt = (data.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    db = get_db()
    chars = characters.require(data.character_ids, db)
    project, assets_path = _project_for_generation(data.project)
    project_slug = project.slug

    image_url = (data.image_url or "").strip() or None
    video_url = (data.video_url or "").strip() or None
    subject_url = (data.subject_url or "").strip() or None
    audio_url = (data.audio_url or "").strip() or None

    # Handle local source image: upload to litterbox to get a public URL
    # Keep the project's stored image_url as the local reference (so the local file remains the canonical copy),
    # but pass the uploaded public URL to the generator and record both in the job params so regenerations
    # can prefer the uploaded URL while it's still valid and fall back to the local file afterwards.
    uploaded_image_url = None
    local_image_ref = None
    if image_url and image_url.startswith("local:"):
        # Keep the local ref for the project and for long-term storage;
        # the generator gets the uploaded public URL
        local_image_ref = image_url
        image_url = uploaded_image_url = _publish_local_image(assets_path, image_url, "source image")

    # Update project with URLs if provided. Important: if we uploaded the image above, do NOT overwrite
    # the project's image_url with the temporary uploaded URL — keep the local reference as the canonical
    # project image. Otherwise use whatever URL was passed in the request.
    project_image_to_store = None
    if local_image_ref:
        project_image_to_store = local_image_ref
    else:
        project_image_to_store = image_url or project.image_url

    db.update_project(project_slug,
                      prompt=prompt,
                      image_url=project_image_to_store,
                      video_url=video_url or project.video_url,
                      subject_url=subject_url or project.subject_url,
                      audio_url=audio_url or project.audio_url)

    aspect_ratio = data.aspect_ratio
    resolution = data.resolution
    length = data.length
    generate_audio = data.generate_audio

    kwargs = {
        "api_key": os.getenv("POLLO_API_KEY"),
        "project": project.assets_folder,  # Use assets folder for file storage
        "prompt": characters.with_characters(prompt, chars),
        "image_url": image_url,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "length": length,
        "generate_audio": generate_audio,
    }

    # Model-specific options
    model_opts = MODEL_INFO.get(model, {}).get("options", [])
    if "web_search" in model_opts:
        kwargs["web_search"] = data.web_search or False
    if "image_tail" in model_opts:
        image_tail = (data.image_tail or "").strip() or None
        if image_tail:
            kwargs["image_tail"] = image_tail
    if "seed" in model_opts and data.seed is not None:
        kwargs["seed"] = data.seed
    if "negative_prompt" in model_opts:
        negative_prompt = (data.negative_prompt or "").strip() or None
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
    if "audio_url" in model_opts and audio_url:
        kwargs["audio_url"] = audio_url
    if "num_outputs" in model_opts and data.num_outputs is not None:
        kwargs["num_outputs"] = data.num_outputs

    is_ref_model = MODEL_INFO.get(model, {}).get("type") == "ref"
    # v1 models take refs on their regular endpoint ("Ref mode" in the UI)
    ref_mode = MODEL_INFO.get(model, {}).get("ref_mode")
    # In ref mode, characters' images go in as image refs after the user's
    # own (the description goes in the prompt either way)
    user_refs = list(data.refs or [])
    char_refs: list[dict] = []
    if chars and (is_ref_model or (ref_mode is not None and (user_refs or data.ref_mode))):
        room = _character_ref_room(user_refs, is_ref_model, ref_mode)
        char_refs = [{"type": "image", "_character": r} for r in characters.reference_refs(chars, room)]
    all_refs = user_refs + char_refs
    v1_ref_mode = bool(all_refs) and ref_mode is not None
    if v1_ref_mode:
        _validate_v1_refs(all_refs, ref_mode)
        # The ref branch has no source image or end frame
        kwargs["image_url"] = None
        kwargs.pop("image_tail", None)

    if is_ref_model or v1_ref_mode:
        # ref uses refs array
        if all_refs:
            # Handle local: refs by uploading them
            names = {c.id: c.name for c in chars}
            order = sum(1 for r in user_refs if r.get("type") != "subject")
            resolved_refs = []
            for ref in all_refs:
                ref = dict(ref)  # shallow copy
                ref_type = ref.get("type", "image")
                if ref.get("_character"):
                    # Kept on the stored ref, so a regenerate knows it came from a character
                    public_url = _publish_character_ref(ref["_character"])
                    if is_ref_model:
                        order += 1
                        cid = int(ref["_character"][len(characters.REF_PREFIX):].split("/")[0])
                        ref.update(name=names.get(cid, "character")[:20], image=public_url, order=order)
                    else:
                        ref["url"] = public_url
                elif ref_type == "image":
                    url = ref.get("image") or ref.get("url") or ""
                    if url.startswith("local:"):
                        public_url = _publish_local_image(assets_path, url, "ref image")
                        # Preserve the original local reference so regenerations can fall back to it
                        ref["_local_image"] = url
                        ref["image"] = public_url
                        if "url" in ref:
                            ref["url"] = public_url
                elif ref_type == "subject":
                    images = ref.get("images", [])
                    resolved_images = []
                    for img in images:
                        img = dict(img) if isinstance(img, dict) else {"url": str(img)}
                        url = img.get("url", "")
                        if url.startswith("local:"):
                            # Preserve local reference for regen fallback
                            img["_local_url"] = url
                            img["url"] = _publish_local_image(assets_path, url, "subject ref image")
                        resolved_images.append(img)
                    ref["images"] = resolved_images
                resolved_refs.append(ref)
            kwargs["refs"] = resolved_refs
        else:
            # Build refs from individual URLs (backward-compatible)
            kwargs["subject_url"] = subject_url
        if is_ref_model and data.video_num is not None:
            kwargs["video_num"] = data.video_num
        if is_ref_model and data.image_meta is not None:
            kwargs["image_meta"] = data.image_meta

    # Create DB job record with extra params
    job_id = str(uuid.uuid4())[:8]
    extra_params = {
        "web_search": kwargs.get("web_search", False),
        "image_tail": kwargs.get("image_tail", ""),
        "seed": kwargs.get("seed", None),
        "negative_prompt": kwargs.get("negative_prompt", ""),
        "num_outputs": kwargs.get("num_outputs", None),
        "video_num": kwargs.get("video_num", None),
        "refs": kwargs.get("refs", []) or [],
        "character_ids": [c.id for c in chars],
        **_source_upload_params(local_image_ref, uploaded_image_url),
    }
    db.create_job(
        job_id=job_id, project=project_slug, model=model, prompt=prompt,
        image_url=image_url, source_video_url=video_url,
        subject_url=subject_url, audio_url=audio_url,
        aspect_ratio=aspect_ratio, resolution=resolution,
        length=length, generate_audio=generate_audio,
        params=extra_params,
    )

    threading.Thread(target=run_generation, args=(job_id, model, kwargs),
                     daemon=True).start()

    return {"job_id": job_id, "project": project_slug}


def run_image_generation(job_id: str, model: str, kwargs: dict):
    """Run image generation in a background thread, updating the DB."""
    db = get_db()
    try:
        db.update_job(job_id, status="creating", message="Creating generator...")
        generator = get_image_generator(model, **kwargs)
        project = generator.project

        polled = _submit_and_poll(generator, job_id, db)
        if polled is None:
            return
        task_id, results = polled
        credits_used = _credits_used(results)
        image_urls = _result_urls(results)

        if not image_urls:
            db.update_job(job_id, status="error", message="No image URL in result")
            return

        db.update_job(job_id, status="downloading",
                      message=f"Downloading {len(image_urls)} image(s)...",
                      video_url=image_urls[0])

        all_filepaths: list[str] = []
        dl_metadata = generator.build_download_metadata()
        for idx, url in enumerate(image_urls):
            dl_task_id = task_id if idx == 0 else f"{task_id}_{idx}"
            try:
                fp = download_generated_image(
                    url, project,
                    task_id=dl_task_id, model=model,
                    prompt=generator.prompt, metadata=dl_metadata,
                )
                all_filepaths.append(fp)
            except Exception as exc:
                print(f"Failed to download image {idx} for job {job_id}: {exc}")

        if not all_filepaths:
            db.update_job(job_id, status="error", message="Failed to download any images")
            return

        primary_path = all_filepaths[0]
        done_msg = f"{len(all_filepaths)} images ready!" if len(all_filepaths) > 1 else "Image ready!"

        # Store all paths in params_json so the gallery can show each image separately
        if len(all_filepaths) > 1:
            job_record = db.get_job(job_id)
            current_params: dict = {}
            if job_record and job_record.params_json:
                try:
                    current_params = json.loads(job_record.params_json)
                except Exception:
                    pass
            current_params["result_paths"] = all_filepaths
            db.update_job(job_id, status="done", message=done_msg,
                          video_path=primary_path, credits_used=credits_used,
                          params_json=json.dumps(current_params))
        else:
            db.update_job(job_id, status="done", message=done_msg,
                          video_path=primary_path, credits_used=credits_used)
        _refresh_job_project(job_id, project)

    except Exception as e:
        db.update_job(job_id, status="error", message=str(e))


@app.post("/api/generate-image")
def api_generate_image(data: GenerateImageRequest, _api_key: str = Depends(verify_api_key)):
    model = data.model
    if model not in IMAGE_GENERATORS:
        raise HTTPException(status_code=400, detail=f"Unknown image model: {model}. Available: {', '.join(IMAGE_GENERATORS)}")

    prompt = (data.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    chars = characters.require(data.character_ids, get_db())
    project, assets_path = _project_for_generation(data.project)
    project_slug = project.slug

    image_url = (data.image_url or "").strip() or None

    # Handle local source image: upload it to get a public URL
    uploaded_image_url = None
    local_image_ref = None
    if image_url and image_url.startswith("local:"):
        local_image_ref = image_url
        image_url = uploaded_image_url = _publish_local_image(assets_path, image_url, "source image")

    # Resolve local: refs in images list
    images = [_publish_local_image(assets_path, u.strip()) if u.strip().startswith("local:") else u.strip()
              for u in data.images or []] or None
    # Characters' images go in as reference images after the user's own
    # (models without an "images" option get just the description)
    char_images = []
    if "images" in MODEL_INFO.get(model, {}).get("options", []):
        char_images = [_publish_character_ref(r) for r in characters.reference_refs(chars, CHARACTER_REFS)]

    kwargs = {
        "api_key": os.getenv("POLLO_API_KEY"),
        "project": project.assets_folder,
        "prompt": characters.with_characters(prompt, chars),
        "image_url": image_url,
        "aspect_ratio": data.aspect_ratio,
        "seed": data.seed,
    }
    if images or char_images:
        kwargs["images"] = (images or []) + char_images
    if data.style is not None:
        kwargs["style"] = data.style
    if data.resolution is not None:
        kwargs["resolution"] = data.resolution
    if data.max_images is not None:
        kwargs["max_images"] = data.max_images
    if data.thinking_level is not None:
        kwargs["thinking_level"] = data.thinking_level

    job_id = str(uuid.uuid4())[:8]
    extra_params: dict = {
        "seed": data.seed,
        "style": data.style or "",
        "images": images or [],
        "character_ids": [c.id for c in chars],
    }
    if data.resolution:
        extra_params["resolution"] = data.resolution
    if data.max_images:
        extra_params["max_images"] = data.max_images
    if data.thinking_level:
        extra_params["thinking_level"] = data.thinking_level
    extra_params.update(_source_upload_params(local_image_ref, uploaded_image_url))

    db = get_db()

    db.create_job(
        job_id=job_id, project=project_slug, model=model, prompt=prompt,
        image_url=local_image_ref or image_url,
        aspect_ratio=data.aspect_ratio,
        params=extra_params,
        job_type="image",
    )

    threading.Thread(target=run_image_generation, args=(job_id, model, kwargs), daemon=True).start()

    return {"job_id": job_id, "project": project_slug}


# ── Job status ──────────────────────────────────────────────────────

# Track jobs currently being recovered to prevent concurrent recovery attempts
_recovering_jobs: set[str] = set()
_recovering_lock = threading.Lock()


def _recover_stale_job(job):
    """Try to recover a job stuck in a non-terminal status.

    If the job already has a video_url the generation succeeded; kick off
    a background download so the video file is available.  Otherwise fall
    back to checking the remote task API.
    """
    # Prevent concurrent recovery attempts for the same job
    with _recovering_lock:
        if job.job_id in _recovering_jobs:
            return
        _recovering_jobs.add(job.job_id)

    try:
        _recover_stale_job_inner(job)
    finally:
        with _recovering_lock:
            _recovering_jobs.discard(job.job_id)


def _recover_stale_job_inner(job):
    """Inner recovery logic (called with concurrent-recovery guard)."""
    db = get_db()

    # Re-fetch the job to get the latest status — another thread may have
    # already updated it since the caller read it.
    job = db.get_job(job.job_id)
    if not job or job.status in ("done", "error"):
        return

    print(f"[recover] Job {job.job_id} stale in status={job.status}, attempting recovery", flush=True)

    # If we already have a video URL, the generation succeeded — just
    # the download failed or was interrupted.  Trigger a background download.
    if job.video_url:
        # But if we already have the file, just mark done
        if job.video_path and os.path.isfile(job.video_path):
            db.update_job(job.job_id, status="done", message="Video ready!")
            print(f"[recover] Job {job.job_id} already has video file, marking done", flush=True)
            return
        print(f"[recover] Job {job.job_id} has video_url, triggering download", flush=True)
        db.update_job(job.job_id, status="downloading",
                      message="Downloading video (recovered)...")
        threading.Thread(
            target=_download_recovered_job,
            args=(job.job_id, job.video_url),
            daemon=True
        ).start()
        return

    # Otherwise try checking the task API
    if not job.task_id:
        db.update_job(job.job_id, status="error",
                      message="Stuck with no task ID — cannot recover")
        return

    api_key = os.getenv("POLLO_API_KEY")
    if not api_key:
        db.update_job(job.job_id, status="error",
                      message="Stuck — no API key to check task status")
        return

    try:
        # A task that's still genuinely processing is left alone
        _apply_remote_task_status(job.job_id, job.task_id, api_key)
    except Exception as e:
        db.update_job(job.job_id, status="error",
                      message=f"Recovery check failed: {e}")


def _apply_remote_task_status(job_id: str, task_id: str, api_key: str) -> bool:
    """Check a task on the API and settle its job: a finished task starts
    a background download, a failed one marks the job as errored. Returns
    False if the task is still running (the job is left alone)."""
    db = get_db()
    results = get_task_status(task_id, api_key)
    if not results:
        db.update_job(job_id, status="error", message="No status returned from API")
        return True
    api_status, fail_msg, url, _credits = results[0]
    if api_status in SUCCESS_STATUSES:
        if url:
            # Trigger background download instead of marking done without file
            db.update_job(job_id, status="downloading", video_url=url,
                          message="Downloading video (recovered)...")
            threading.Thread(target=_download_recovered_job, args=(job_id, url), daemon=True).start()
        else:
            db.update_job(job_id, status="error", message="Task succeeded but no URL returned")
        return True
    if api_status in ERROR_STATUSES:
        db.update_job(job_id, status="error", message=fail_msg or "Generation failed")
        return True
    return False


def _recover_if_stale(job):
    """Recover a non-terminal job that hasn't updated in a while (e.g. stuck
    at "downloading"); returns the job as it stands afterwards."""
    if job.status in ("done", "error"):
        return job
    age = (datetime.now() - job.updated_at).total_seconds() if job.updated_at else float("inf")
    if age <= STALE_JOB_SECONDS:
        return job
    _recover_stale_job(job)
    return get_db().get_job(job.job_id)


def _with_preferred_image_url(job_dict: dict) -> dict:
    """Swap in the image_url the UI should show / regenerate from (see
    _choose_preferred_image_url_from_job_dict)."""
    try:
        job_dict["image_url"] = _choose_preferred_image_url_from_job_dict(job_dict) or job_dict.get("image_url")
    except Exception:
        pass
    return job_dict


def _download_and_complete_job(job_id: str, video_url: str, label: str = "download") -> str | None:
    """Download a video for a job, mark it done, and refresh caches.

    Shared logic used by recovery, resume, and manual re-download paths.
    Returns the local filepath on success, or None on failure (job is
    marked as error in that case).
    """
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        return None

    # If the job already has a downloaded video, just mark done
    if job.video_path and os.path.isfile(job.video_path):
        db.update_job(job_id, status="done", message="Video ready!")
        print(f"[{label}] Job {job_id} already has video, skipping download", flush=True)
        return job.video_path

    proj = db.get_project_by_slug(job.project)
    if not proj:
        db.update_job(job_id, status="error", message="Project not found")
        return None
    assets_folder = proj.assets_folder

    filepath = download_video(
        video_url, assets_folder,
        task_id=job.task_id, model=job.model,
        prompt=job.prompt, metadata={},
    )

    db.update_job(job_id, status="done", message="Video ready!",
                  video_path=filepath)
    _refresh_project_media(assets_folder, job.project)

    print(f"[{label}] Job {job_id} download complete: {filepath}", flush=True)
    return filepath


def _download_recovered_job(job_id: str, video_url: str):
    """Download a video for a recovered job in a background thread."""
    try:
        _download_and_complete_job(job_id, video_url, label="recover")
    except Exception as e:
        get_db().update_job(job_id, status="error",
                            message=f"Recovery download failed: {e}")


@app.post("/api/jobs/bulk-move")
def api_bulk_move_jobs(body: BulkMoveRequest, _api_key: str = Depends(verify_api_key)):
    """Move a batch of jobs (and their video files) to a different project."""
    db = get_db()
    target = db.get_project_by_slug(body.target_project)
    if not target:
        raise HTTPException(status_code=404, detail=f"Project '{body.target_project}' not found")

    target_assets = ASSETS_DIR / target.assets_folder
    target_assets.mkdir(parents=True, exist_ok=True)

    moved, not_found = 0, []
    # Track source folders by physical path so we handle half-moved jobs correctly
    # (job.project may already equal target if a previous partial move updated the DB
    # but not the file — using the actual folder is always reliable)
    affected_source_folders: set[Path] = set()

    for job_id in body.job_ids:
        job = db.get_job(job_id)
        if not job:
            not_found.append(job_id)
            continue

        new_video_path = job.video_path

        if job.video_path:
            src = Path(job.video_path)
            dst = target_assets / src.name
            if src.exists() and src != dst:
                affected_source_folders.add(src.parent)
                shutil.move(str(src), str(dst))
                new_video_path = str(dst)
                db.update_download_by_local_path(
                    src.name,
                    local_path=str(dst),
                    project=body.target_project,
                )
            elif dst.exists():
                # File already in target (previous partial move)
                new_video_path = str(dst)

        if job.project != body.target_project:
            affected_source_folders.add(
                ASSETS_DIR / (db.get_project_by_slug(job.project) or target).assets_folder
            )

        db.update_job(job_id, project=body.target_project, video_path=new_video_path)
        moved += 1

    if moved:
        _invalidate_project_caches()
        for folder in affected_source_folders:
            if folder == target_assets:
                continue
            proj = db.get_project_by_assets_folder(folder.name)
            slug = proj.slug if proj else None
            _update_project_thumbnail(folder, project_slug=slug, force=True)
        _update_project_thumbnail(target_assets, project_slug=body.target_project, force=True)

    return {"moved": moved, "not_found": not_found, "target_project": body.target_project}


@app.get("/api/jobs/{job_id}")
def api_job_status(job_id: str, _api_key: str = Depends(verify_api_key)):
    job = get_db().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _recover_if_stale(job)
    return _with_preferred_image_url(_enrich_job_result(job.to_dict(), job))


@app.post("/api/jobs/{job_id}/check")
def api_check_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Check the status of an incomplete job and potentially resume it."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If job is already done or error, just return current status with smart video detection
    if job.status in ("done", "error"):
        result = job.to_dict()
        _enrich_job_result(result, job)
        return result

    # If we have a task_id, check its status
    if not job.task_id:
        db.update_job(job_id, status="error", message="No task ID - cannot recover job")
        return db.get_job(job_id).to_dict()

    api_key = os.getenv("POLLO_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")

    try:
        if not _apply_remote_task_status(job_id, job.task_id, api_key):
            db.update_job(job_id, status="processing", message=f"Task {job.task_id} still processing...")

        result = db.get_job(job_id).to_dict()
        result["video_exists"] = False
        return result

    except Exception as e:
        db.update_job(job_id, status="error", message=f"Check failed: {str(e)}")
        return db.get_job(job_id).to_dict()


@app.post("/api/jobs/{job_id}/download")
def api_download_job_video(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Download the video for a completed job that doesn't have the video file."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "done":
        raise HTTPException(status_code=400, detail="Job is not complete")

    if not job.video_url:
        raise HTTPException(status_code=400, detail="No video URL available")

    # Check if video already exists using smart detection
    exists, found_path = _find_video_for_job(job)
    if exists and found_path:
        # Update job's video_path if it was found at a different location
        if found_path != job.video_path:
            db.update_job(job_id, video_path=found_path)
        return {"message": "Video already exists", "video_path": found_path}

    try:
        db.update_job(job_id, status="downloading", message="Downloading video...")

        # Get the assets folder for the project (job.project is the slug)
        proj = db.get_project_by_slug(job.project)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        assets_folder = proj.assets_folder

        # Build metadata
        meta = {}
        if job.params_json:
            try:
                meta["payload"] = json.loads(job.params_json)
            except json.JSONDecodeError:
                pass

        filepath = download_video(
            job.video_url, assets_folder,
            task_id=job.task_id, model=job.model,
            prompt=job.prompt, metadata=meta,
        )

        db.update_job(job_id, status="done", message="Video ready!",
                     video_path=filepath)

        _refresh_project_media(assets_folder, job.project, force=False)

        result = db.get_job(job_id).to_dict()
        result["video_exists"] = True
        result["filename"] = Path(filepath).name
        return result

    except Exception as e:
        db.update_job(job_id, status="done", message=f"Download failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
def api_jobs(status: str | None = None, project: str | None = None, active: bool | None = None, _api_key: str = Depends(verify_api_key)):
    """All jobs (optionally filter by status, project, or active state)."""
    db = get_db()
    if active:
        # Get non-terminal jobs (still running)
        jobs = db.get_active_jobs()
    elif status:
        jobs = db.get_jobs_by_status(status)
    elif project:
        jobs = db.get_jobs_by_project(project)
    else:
        jobs = db.get_all_jobs(limit=200)

    # Get assets path for the project (if filtering by project)
    assets_path = None
    if project:
        proj = db.get_project_by_slug(project)
        if proj:
            assets_path = ASSETS_DIR / proj.assets_folder

    # Include video_exists for each job with smart detection
    result = []
    for j in jobs:
        j = _recover_if_stale(j)
        # Use cached assets_path if same project, otherwise let function look it up
        job_assets_path = assets_path if (project and j.project == project) else None
        result.append(_with_preferred_image_url(_enrich_job_result(j.to_dict(), j, job_assets_path)))
    return result


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Delete a job and its associated video file."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get project for cache invalidation
    proj = db.get_project_by_slug(job.project)

    # Delete associated video file if it exists
    video_deleted = False
    if job.video_path:
        video_path = Path(job.video_path)
        if video_path.exists():
            try:
                video_path.unlink()
                video_deleted = True
            except Exception:
                pass  # Continue even if file delete fails

        # Also delete download record
        filename = video_path.name
        db.delete_download_by_path(filename)

    # Delete the job record
    db.delete_job(job_id)

    # Invalidate caches and regenerate thumbnail if we deleted a video
    if video_deleted and proj:
        _refresh_project_media(proj.assets_folder, job.project)
        _cleanup_thumb_cache()

    return {"deleted": True, "job_id": job_id, "video_deleted": video_deleted}


def _set_job_archived(job_id: str, archived: bool) -> JobArchivedResult:
    """Toggle archive status on a job and regenerate its project thumbnail."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.update_job(job_id, archived=archived)

    # Regenerate thumbnail since the (un)archived video affects which is latest
    proj = db.get_project_by_slug(job.project)
    if proj:
        _refresh_project_media(proj.assets_folder, job.project)

    return {"archived": archived, "job_id": job_id}


# ── Favourite generations ───────────────────────────────────────────

class FavouriteIn(BaseModel):
    job_id: str
    filename: str


@app.post("/api/favourites")
def api_add_favourite(data: FavouriteIn, _api_key: str = Depends(verify_api_key)):
    safe_filename(data.filename)
    db = get_db()
    job = db.get_job(data.job_id)
    if not job or data.filename not in _job_files(job):
        raise HTTPException(status_code=404, detail="Generation not found")
    db.add_favourite(data.job_id, data.filename)
    return {"favourite": True, "filename": data.filename}


@app.delete("/api/favourites/{filename}")
def api_remove_favourite(filename: str, _api_key: str = Depends(verify_api_key)):
    safe_filename(filename)
    get_db().remove_favourite(filename)
    return {"favourite": False, "filename": filename}


@app.get("/api/favourites")
def api_list_favourites(_api_key: str = Depends(verify_api_key)):
    """Starred generations from every project, newest star first, shaped like a
    project's gallery items plus the project they're in now. Stars whose job
    or file is gone (deleted another way) are left out."""
    db = get_db()
    projects = {p.slug: p for p in db.get_all_projects()}
    items = []
    for fav in db.list_favourites():
        job = db.get_job(fav.job_id)
        proj = projects.get(job.project) if job else None
        if not proj or not (ASSETS_DIR / proj.assets_folder / fav.filename).exists():
            continue
        items.append({
            "filename": fav.filename, "favourite": True, "job": job.to_dict(),
            "media_type": _job_media_type(job),
            "project": proj.slug, "project_name": proj.name, "favourited_at": iso(fav.created_at),
        })
    return {"items": items}


@app.post("/api/jobs/{job_id}/archive")
def api_archive_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Archive a job (hide from gallery)."""
    return _set_job_archived(job_id, True)


@app.post("/api/jobs/{job_id}/unarchive")
def api_unarchive_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Unarchive a job (show in gallery again)."""
    return _set_job_archived(job_id, False)


# ── Projects ────────────────────────────────────────────────────────

@app.get("/api/projects")
def api_list_projects(archived: bool | None = None, _api_key: str = Depends(verify_api_key)):
    db = get_db()
    projects = db.get_all_projects(archived=archived)
    result = []

    for p in projects:
        assets_path = ASSETS_DIR / p.assets_folder
        videos = _get_video_list(assets_path) if assets_path.exists() else []

        # Check for a local image file (including thumb.jpg)
        thumb_path = assets_path / "thumb.jpg"
        has_thumb = assets_path.exists() and thumb_path.exists()
        has_local_image = assets_path.exists() and any(
            (assets_path / f"image{ext}").exists()
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")
        )
        has_image = has_thumb or has_local_image or len(videos) > 0

        # Use thumb mtime as cache-buster so frontend refetches after regeneration
        thumb_ts = ""
        if has_thumb:
            try:
                thumb_ts = str(int(thumb_path.stat().st_mtime))
            except Exception:
                pass

        result.append({
            "slug": p.slug,
            "name": p.name,
            "prompt": (p.prompt or "")[:300],
            "image_url": p.image_url or "",
            "video_url": p.video_url or "",
            "subject_url": p.subject_url or "",
            "audio_url": p.audio_url or "",
            "video_count": len(videos),
            "has_image": has_image,
            "thumb_ts": thumb_ts,
            "archived": p.archived,
            "last_modified": p.updated_at,
        })

    return result


@app.get("/api/projects/{project}")
def api_get_project(project: str, archived: bool | None = None, _api_key: str = Depends(verify_api_key)):
    db = get_db()
    proj = _require_project(project)

    assets_path = ASSETS_DIR / proj.assets_folder

    # Video files (.mp4) from disk
    videos_with_mtime = _get_video_list(assets_path, sort_by_mtime=True)

    jobs = db.get_jobs_by_project(project)

    # Build a lookup dict for faster job matching
    job_by_filename = {}
    for j in jobs:
        if j.video_path:
            filename = Path(j.video_path).name
            job_by_filename[filename] = j
        # Also index extra result_paths from multi-image jobs
        if _job_media_type(j) == 'image':
            for extra_path in _job_params(j).get('result_paths', []):
                job_by_filename.setdefault(Path(extra_path).name, j)

    # Fallback: for any video files on disk that didn't match a job above,
    # search all jobs whose video_path filename lands in this folder.
    # This recovers half-moved jobs (DB project updated but file not yet moved).
    unmatched_filenames = {v.name for v, _ in videos_with_mtime} - set(job_by_filename)
    if unmatched_filenames:
        for j in db.get_all_jobs_with_video_in_folder(str(assets_path)):
            filename = Path(j.video_path).name
            if filename in unmatched_filenames:
                job_by_filename[filename] = j
                db.update_job(j.job_id, project=project, video_path=str(assets_path / filename))

    # Image generation results — sourced from job records (not disk glob, to avoid
    # confusing source/ref images with generated outputs)
    image_media: list[tuple[Path, float]] = []
    seen_image_filenames: set[str] = set()
    for j in jobs:
        if getattr(j, 'job_type', 'video') != 'image' or j.status != 'done':
            continue
        # Use result_paths if present (multi-image jobs), else fall back to video_path
        paths_to_add = [Path(p) for p in _job_params(j).get('result_paths', [])]
        if not paths_to_add and j.video_path:
            paths_to_add = [Path(j.video_path)]
        for p in paths_to_add:
            if p.exists() and p.name not in seen_image_filenames:
                try:
                    image_media.append((p, p.stat().st_mtime))
                    seen_image_filenames.add(p.name)
                except Exception:
                    pass

    # Merge video and image results, sorted newest-first
    all_media = list(videos_with_mtime) + image_media
    all_media.sort(key=lambda x: x[1], reverse=True)

    # Build media list with associated job info, filtering by archived status
    favourites = db.favourite_filenames()
    video_list = []
    for v, mtime in all_media:
        video_info = {"filename": v.name, "mtime": mtime, "favourite": v.name in favourites}

        matched_job = job_by_filename.get(v.name)
        if matched_job:
            video_info["job"] = matched_job.to_dict()
            video_info["media_type"] = _job_media_type(matched_job)

        # Filter by archived status if specified
        if archived is not None:
            job_archived = matched_job.archived if matched_job else False
            if job_archived != archived:
                continue

        video_list.append(video_info)

    job_dicts = [_with_preferred_image_url(j.to_dict()) for j in jobs]

    return {
        "slug": proj.slug,
        "name": proj.name,
        "assets_folder": proj.assets_folder,
        "prompt": proj.prompt or "",
        "image_url": proj.image_url or "",
        "video_url": proj.video_url or "",
        "subject_url": proj.subject_url or "",
        "audio_url": proj.audio_url or "",
        "archived": proj.archived,
        "videos": video_list,
        "jobs": job_dicts,
    }


@app.post("/api/projects")
def api_create_project(data: ProjectCreate, _api_key: str = Depends(verify_api_key)):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    db = get_db()
    project = db.create_project(
        name=name,
    )

    # Create assets folder
    assets_path = ASSETS_DIR / project.assets_folder
    assets_path.mkdir(parents=True, exist_ok=True)

    # Update with optional fields
    updates = {}
    if data.prompt:
        updates["prompt"] = data.prompt.strip()
    if data.image_url:
        updates["image_url"] = data.image_url.strip()
    if data.video_url:
        updates["video_url"] = data.video_url.strip()
    if data.subject_url:
        updates["subject_url"] = data.subject_url.strip()
    if data.audio_url:
        updates["audio_url"] = data.audio_url.strip()

    if updates:
        project = db.update_project(project.slug, **updates)

    return {"slug": project.slug, "name": project.name, "created": True}


@app.put("/api/projects/{project}")
def api_update_project(project: str, data: ProjectUpdate, _api_key: str = Depends(verify_api_key)):
    db = get_db()
    proj = _require_project(project)

    updates = {}
    if data.name is not None:
        updates["name"] = data.name.strip()
    if data.prompt is not None:
        updates["prompt"] = data.prompt.strip() or None
    if data.image_url is not None:
        updates["image_url"] = data.image_url.strip() or None
    if data.video_url is not None:
        updates["video_url"] = data.video_url.strip() or None
    if data.subject_url is not None:
        updates["subject_url"] = data.subject_url.strip() or None
    if data.audio_url is not None:
        updates["audio_url"] = data.audio_url.strip() or None

    if updates:
        proj = db.update_project(project, **updates)

    return {"slug": proj.slug, "name": proj.name, "updated": True}


def _set_project_archived(project: str, archived: bool) -> ProjectArchivedResult:
    """Toggle archive status on a project."""
    _require_project(project)
    get_db().update_project(project, archived=archived)
    _invalidate_project_caches()

    return {"archived": archived, "slug": project}


@app.post("/api/projects/{project}/archive")
def api_archive_project(project: str, _api_key: str = Depends(verify_api_key)):
    """Archive a project (hide from main listing)."""
    return _set_project_archived(project, True)


@app.post("/api/projects/{project}/unarchive")
def api_unarchive_project(project: str, _api_key: str = Depends(verify_api_key)):
    """Unarchive a project (show in main listing again)."""
    return _set_project_archived(project, False)


@app.delete("/api/projects/{project}")
def api_delete_project(project: str, _api_key: str = Depends(verify_api_key)):
    """Delete a project, all its jobs, and all its video/asset files."""
    db = get_db()
    proj = _require_project(project)

    assets_path = ASSETS_DIR / proj.assets_folder

    # Count files before deletion for response
    files_deleted = 0
    if assets_path.exists():
        files_deleted = sum(1 for f in assets_path.iterdir() if f.is_file())
        try:
            shutil.rmtree(assets_path)
        except Exception:
            pass

    # Delete the project (cascade deletes jobs too)
    db.delete_project(project)

    # Invalidate caches
    _invalidate_project_caches()

    # Clean up orphaned thumbnail cache
    _cleanup_thumb_cache()

    return {"deleted": True, "slug": project, "files_deleted": files_deleted}


# ── Video/Image serving ─────────────────────────────────────────────

IMMUTABLE_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


@app.get("/video/{project}/{filename}")
def serve_video(project: str, filename: str):
    """Serve a video or generated image file. Project can be slug or assets_folder."""
    safe_filename(filename)
    assets_folder = _get_project_assets_folder(project)
    if not assets_folder:
        assets_folder = project

    video_path = ASSETS_DIR / assets_folder / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(video_path, media_type=image_media_type(filename) or "video/mp4", headers=IMMUTABLE_CACHE)


@app.get("/video-thumb/{project}/{filename}")
def serve_video_thumb(project: str, filename: str):
    """Serve a thumbnail for a video (first frame) or image file (directly)."""
    safe_filename(filename)
    assets_folder = _get_project_assets_folder(project)
    if not assets_folder:
        assets_folder = project

    media_path = ASSETS_DIR / assets_folder / filename
    if not media_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = image_media_type(filename)
    if media_type:
        return FileResponse(media_path, media_type=media_type, headers=IMMUTABLE_CACHE)

    frame_data = _extract_first_frame(media_path)
    if frame_data:
        return Response(content=frame_data, media_type="image/jpeg", headers=IMMUTABLE_CACHE)
    raise HTTPException(status_code=404, detail="Could not extract frame")


@app.delete("/api/videos/{project}/{filename}")
def api_delete_video(project: str, filename: str, _api_key: str = Depends(verify_api_key)):
    """Delete a video file and its associated database records."""
    safe_filename(filename)
    db = get_db()
    proj = _require_project(project)

    video_path = ASSETS_DIR / proj.assets_folder / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    try:
        # Delete the video file
        video_path.unlink()

        # Delete associated job record (matches by video_path)
        db.delete_job_by_video_path(filename)

        # Delete associated download record
        db.delete_download_by_path(filename)
        db.remove_favourite(filename)

        _refresh_project_media(proj.assets_folder, project)

        # Clean up orphaned thumbnail cache for the deleted video
        _cleanup_thumb_cache()

        return {"deleted": True, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/image/{project}")
def serve_image(project: str):
    """Serve the project's thumbnail image.
    Priority: thumb.jpg (latest video frame) > image.* (source image)
    """
    # Use cached lookup
    assets_folder = _get_project_assets_folder(project)
    if not assets_folder:
        raise HTTPException(status_code=404, detail="Project not found")

    # IMPORTANT: Always use ASSETS_DIR (data folder) not ROOT_DIR
    assets_path = ASSETS_DIR / assets_folder
    thumb_path = assets_path / "thumb.jpg"

    # Update thumbnail if needed (only regenerates if missing or stale)
    _update_project_thumbnail(assets_path, project_slug=project)

    # Serve the thumbnail if it exists
    if thumb_path.exists():
        return FileResponse(
            thumb_path, 
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"}  # Always revalidate
        )

    # Second, try to find an existing source image file
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        img = assets_path / f"image{ext}"
        if img.exists():
            return FileResponse(img, media_type=image_media_type(img), headers={"Cache-Control": "public, max-age=3600"})

    raise HTTPException(status_code=404, detail="Image not found")


# ── Models info ─────────────────────────────────────────────────────

@app.get("/api/models")
def api_models(legacy: bool = False):
    """
    Model dropdown contents. `legacy=false` (default) returns the current
    v1-API models; `legacy=true` returns the pre-v1 "legacy mode" fallback
    models instead — the two sets are disjoint, not merged, matching the
    frontend's legacy-mode toggle (one list or the other, not both at once).
    The exception is `legacy_only` models (no working v1 endpoint), which
    are in both lists.
    """
    return {name: info for name, info in MODEL_INFO.items()
            if bool(info.get("legacy")) == legacy or info.get("legacy_only")}


# ── Usage / Credit tracking ─────────────────────────────────────────

@app.get("/api/usage/balance")
def api_usage_balance(_api_key: str = Depends(verify_api_key)):
    """Fetch current credit balance from the Pollo API."""
    api_key = os.getenv("POLLO_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")

    balance = get_credit_balance(api_key)
    if balance is None:
        raise HTTPException(status_code=502, detail="Failed to fetch credit balance from Pollo API")

    return balance


@app.get("/api/usage")
def api_usage(days: int = 30, _api_key: str = Depends(verify_api_key)):
    """Get credit usage summary.

    Uses actual credit costs from the Pollo API (stored per job).
    For older jobs without stored credits, falls back to estimation.
    Returns total credits used, breakdown by model, and daily usage.
    """
    db = get_db()
    jobs = db.get_all_jobs(limit=10000)

    # Filter to jobs within the time window
    cutoff = datetime.now().timestamp() - (days * 86400)
    recent_jobs = [
        j for j in jobs
        if j.created_at and j.created_at.timestamp() > cutoff
    ]

    total_credits = 0
    by_model: dict[str, dict] = {}
    by_day: dict[str, int] = {}
    by_project: dict[str, dict] = {}

    for j in recent_jobs:
        # Only count jobs that were actually sent (not purely errored before sending)
        if j.status == "error" and not j.task_id:
            continue

        # Use actual credits from the API (backfilled via migration)
        # Jobs without credits_used (e.g. failed) count as 0
        credits = j.credits_used or 0

        total_credits += credits

        # By model
        if j.model not in by_model:
            by_model[j.model] = {"credits": 0, "count": 0, "label": MODEL_INFO.get(j.model, {}).get("label", j.model)}
        by_model[j.model]["credits"] += credits
        by_model[j.model]["count"] += 1

        # By day
        day_key = j.created_at.strftime("%Y-%m-%d") if j.created_at else "unknown"
        by_day[day_key] = by_day.get(day_key, 0) + credits

        # By project — track credits and per-status counts
        if j.project not in by_project:
            by_project[j.project] = {"credits": 0, "total": 0, "done": 0, "error": 0}
        by_project[j.project]["credits"] += credits
        by_project[j.project]["total"] += 1
        if j.status == "done":
            by_project[j.project]["done"] += 1
        elif j.status == "error":
            by_project[j.project]["error"] += 1

    # Sort daily usage chronologically
    sorted_days = sorted(by_day.items())

    # Sort projects by usage (top spenders first)
    sorted_projects = sorted(by_project.items(), key=lambda x: x[1]["credits"], reverse=True)[:10]

    return {
        "days": days,
        "total_credits": total_credits,
        "total_generations": len(recent_jobs),
        "by_model": by_model,
        "by_day": sorted_days,
        "by_project": [
            {"project": p, "credits": info["credits"],
             "total": info["total"], "done": info["done"], "error": info["error"]}
            for p, info in sorted_projects
        ],
    }


@app.get("/api/usage/project/{project_slug}")
def api_usage_project_details(project_slug: str, days: int = 30, _api_key: str = Depends(verify_api_key)):
    """Get per-generation credit details for a project (used in usage view expansion)."""
    db = get_db()
    jobs = db.get_jobs_by_project(project_slug)

    cutoff = datetime.now().timestamp() - (days * 86400)
    recent_jobs = [
        j for j in jobs
        if j.created_at and j.created_at.timestamp() > cutoff
    ]

    proj = db.get_project_by_slug(project_slug)
    assets_path = ASSETS_DIR / proj.assets_folder if proj else None

    result = []
    for j in recent_jobs:
        # Skip jobs that were never sent
        if j.status == "error" and not j.task_id:
            continue
        credits = j.credits_used or 0
        d = {
            "job_id": j.job_id,
            "model": j.model,
            "status": j.status,
            "credits_used": credits,
            "created_at": iso(j.created_at),
            "message": j.message,
            "video_path": j.video_path,
            "video_exists": False,
            "filename": None,
        }
        # Check if video exists for thumbnail
        if j.video_path and assets_path:
            vp = Path(j.video_path)
            if vp.exists():
                d["video_exists"] = True
                d["filename"] = vp.name
        result.append(d)

    return result


@app.get("/api/usage/estimate")
def api_usage_estimate(
    model: str,
    resolution: Optional[str] = None,
    length: Optional[int] = None,
    generate_audio: Optional[bool] = None,
    _api_key: str = Depends(verify_api_key),
):
    """Estimate the credit cost for a generation from past jobs with identical settings.

    Pollo's API only reports credit cost after a task is submitted (no pre-flight
    pricing endpoint exists), so this looks up prior jobs that used the exact same
    model/resolution/length/generate_audio and reports the most common cost seen.
    Returns credits=None when there's no matching history yet.
    """
    db = get_db()
    matches = [
        j for j in db.get_all_jobs(limit=10000)
        if j.model == model
        and j.credits_used is not None
        and j.resolution == resolution
        and j.length == length
        and j.generate_audio == generate_audio
    ]
    if not matches:
        return {"credits": None, "samples": 0}

    credits, _count = Counter(j.credits_used for j in matches).most_common(1)[0]
    return {"credits": credits, "samples": len(matches)}


# ── Cache management ────────────────────────────────────────────────

@app.post("/api/cache/clear")
def api_clear_cache(_api_key: str = Depends(verify_api_key)):
    """Clear all in-memory caches. Useful after manual file changes."""
    _invalidate_project_caches()
    return {"cleared": True, "message": "All caches cleared"}


@app.post("/api/cache/cleanup-thumbnails")
def api_cleanup_thumbnails(_api_key: str = Depends(verify_api_key)):
    """Remove orphaned thumbnail cache files whose source videos no longer exist."""
    removed = _cleanup_thumb_cache()
    return {"removed": removed, "message": f"Removed {removed} orphaned thumbnail(s)"}


# ── Source image upload (tmpfiles.org primary, litterbox fallback) ────

def _get_local_image_path(assets_path: Path, image_url: str) -> Path | None:
    """Resolve a local:filename image_url to a file path. Returns None if not found."""
    if not image_url or not image_url.startswith("local:"):
        return None
    filename = image_url[6:]  # strip "local:"
    # Safety: no path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return None
    p = assets_path / filename
    return p if p.exists() else None


def _upload_to_litterbox(filepath: Path) -> str:
    """Upload a file to litterbox.catbox.moe and return the public URL.
    Fails fast (12 s timeout, no retry) so VPN/Cloudflare blocks surface immediately."""
    try:
        with open(filepath, "rb") as f:
            resp = _requests.post(
                LITTERBOX_URL,
                data={"reqtype": "fileupload", "time": LITTERBOX_EXPIRY},
                files={"fileToUpload": (filepath.name, f)},
                timeout=(8, 15),  # (connect, read) — read is server response time only, not upload duration
            )

        if resp.status_code != 200 or not resp.text.startswith("https://"):
            body = resp.text[:200].strip()
            reason = f"HTTP {resp.status_code}" + (f" — {body}" if body else "")
            print(f"[Litterbox] Upload failed — {reason}")
            raise ValueError(f"Litterbox upload failed — {reason}")

        return resp.text.strip()
    except _requests.exceptions.Timeout as exc:
        reason = f"timed out ({exc})"
        print(f"[Litterbox] Upload failed — {reason}")
        raise ValueError("Litterbox upload timed out — cycle VPN if blocked") from exc
    except (
        _requests.exceptions.SSLError,
        _requests.exceptions.ConnectionError,
    ) as exc:
        reason = f"{type(exc).__name__}: {exc}"
        print(f"[Litterbox] Upload failed — {reason}")
        raise ValueError(f"Litterbox upload failed — {reason}") from exc


def _upload_to_tmpfiles(filepath: Path) -> str:
    """Upload a file to tmpfiles.org and return the public URL."""
    try:
        expiry_secs = _parse_litterbox_expiry(LITTERBOX_EXPIRY)
        with open(filepath, "rb") as f:
            resp = _requests.post(
                "https://tmpfiles.org/api/v1/upload",
                data={"expire": expiry_secs},
                files={"file": (filepath.name, f)},
                timeout=(8, 30),
            )

        if resp.status_code != 200:
            body = resp.text[:200].strip()
            raise ValueError(f"tmpfiles.org upload failed — HTTP {resp.status_code}" + (f" — {body}" if body else ""))

        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(f"tmpfiles.org upload failed — {data}")

        page_url = data["data"]["url"]
        # tmpfiles.org's dl/ URLs now require a {timestamp}.{hash} segment that
        # isn't returned by the upload API — scrape it from the file's HTML page.
        page_resp = _requests.get(page_url, timeout=(8, 30))
        page_resp.raise_for_status()
        soup = _BeautifulSoup(page_resp.text, "html.parser")
        link = soup.find("a", class_="download") or soup.find("img", id="img_preview")
        direct_url = link.get("href") or link.get("src") if link else None
        if not direct_url:
            raise ValueError(f"tmpfiles.org upload succeeded but no direct download link found on {page_url}")
        return direct_url
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"tmpfiles.org upload failed — {exc}") from exc


def _upload_image(filepath: Path) -> str:
    """Upload a file to tmpfiles.org, falling back to litterbox if that fails."""
    try:
        url = _upload_to_tmpfiles(filepath)
        print(f"[Upload] tmpfiles.org succeeded: {url}")
        return url
    except ValueError as primary_exc:
        print(f"[Upload] tmpfiles.org failed ({primary_exc}), trying litterbox…")
        try:
            return _upload_to_litterbox(filepath)
        except ValueError as fallback_exc:
            raise ValueError(f"All upload hosts failed — tmpfiles: {primary_exc}; litterbox: {fallback_exc}") from fallback_exc


def _parse_litterbox_expiry(expiry: str) -> int:
    """Parse expiry strings like '1h', '12h' into seconds. Defaults to 3600 if unknown."""
    try:
        if expiry.endswith('h'):
            hours = int(expiry[:-1])
            return hours * 3600
        return int(expiry)
    except Exception:
        return 3600


def _choose_preferred_image_url_from_job_dict(job_dict: dict) -> str | None:
    """Given a job.to_dict() result (with parsed 'params' if present), choose the
    best image URL to use for UI/regeneration. Preference order for UI input:
      1. local:... reference recorded in params (so the regenerate input shows the permanent local ref)
      2. uploaded public URL if recorded and not yet expired
      3. job.image_url (fallback)
    Returns a string or None.
    """
    params = job_dict.get('params') or {}
    public = job_dict.get('image_url')
    uploaded = params.get('source_uploaded') or None
    uploaded_at = params.get('source_uploaded_at')
    local = params.get('source_local') or None

    # Prefer local if present (so the UI's Source Image input shows the permanent local reference)
    if local:
        return local

    # If we have an uploaded URL and timestamp, check expiry and use it if still valid
    if uploaded and uploaded_at:
        try:
            expiry_secs = _parse_litterbox_expiry(LITTERBOX_EXPIRY)
            if int(time.time()) - int(uploaded_at) < expiry_secs:
                return uploaded
        except Exception:
            pass

    # Fallback to job.image_url
    # If the job.image_url looks like a litterbox/catbox temporary URL, prefer the project's
    # stored image_url if that is a local: reference (this covers older jobs where the job
    # image_url is the uploaded public URL but the project still has a local copy).
    try:
        if public and ("catbox" in public or "litterbox" in public) and job_dict.get('project'):
            proj = get_db().get_project_by_slug(job_dict.get('project'))
            if proj and proj.image_url and str(proj.image_url).startswith("local:"):
                return proj.image_url
    except Exception:
        pass

    return public


async def _save_uploaded_image(project: str, file: UploadFile, prefix: str) -> dict:
    """Shared helper: validate and save an uploaded image to a project's assets folder.

    Args:
        project: project slug
        file: the uploaded file
        prefix: filename prefix (e.g. 'src' or 'ref') to avoid collisions

    Returns:
        dict with uploaded info including the project object reference
    """
    proj = _require_project(project)
    data, ext = await read_image_upload(file)

    assets_path = ASSETS_DIR / proj.assets_folder
    assets_path.mkdir(parents=True, exist_ok=True)

    filename = f"{prefix}-{uuid.uuid4().hex[:12]}{ext}"
    dest = assets_path / filename
    dest.write_bytes(data)

    local_ref = f"local:{filename}"

    return {
        "uploaded": True,
        "filename": filename,
        "size": len(data),
        "image_url": local_ref,
    }


@app.post("/api/projects/{project}/source-image")
async def api_upload_source_image(project: str, file: UploadFile = File(...), _api_key: str = Depends(verify_api_key)):
    """Upload a source image for a project.

    Saved permanently with a unique name (src-{uuid}.ext) so multiple
    images can coexist.  Returns the local reference to use as image_url.
    """
    result = await _save_uploaded_image(project, file, prefix="src")

    # Update project's default image_url to this upload
    db = get_db()
    db.update_project(project, image_url=result["image_url"])
    _invalidate_project_caches()

    return result


@app.get("/api/projects/{project}/source-image")
def api_get_source_image(project: str, f: str | None = None, _api_key: str = Depends(verify_api_key)):
    """Serve a project's uploaded source image.

    If ?f=filename is given, serve that specific file.
    Otherwise serve the project's current image_url if it's local.
    """
    proj = _require_project(project)
    assets_path = ASSETS_DIR / proj.assets_folder

    # Determine which file to serve
    if f:
        # Serve specific file by name
        safe_filename(f)
        source = assets_path / f
    else:
        # Serve project's current local image
        source_ref = proj.image_url or ""
        resolved = _get_local_image_path(assets_path, source_ref)
        source = resolved

    if not source or not source.exists():
        raise HTTPException(status_code=404, detail="Source image not found")

    return FileResponse(source, media_type=image_media_type(source) or "application/octet-stream",
                        headers=IMMUTABLE_CACHE)


@app.post("/api/projects/{project}/ref-image")
async def api_upload_ref_image(project: str, file: UploadFile = File(...), _api_key: str = Depends(verify_api_key)):
    """Upload a reference image for a project.

    Uses 'ref-' prefix to distinguish from source images (src-).
    Does NOT update the project's image_url.
    Returns the local reference (local:filename) to use in a ref's url field.
    """
    return await _save_uploaded_image(project, file, prefix="ref")


@app.delete("/api/projects/{project}/source-image")
def api_delete_source_image(project: str, f: str | None = None, _api_key: str = Depends(verify_api_key)):
    """Remove a source image.

    If ?f=filename, delete that specific file.
    Otherwise delete the project's current local image.
    """
    db = get_db()
    proj = _require_project(project)

    assets_path = ASSETS_DIR / proj.assets_folder

    if f:
        safe_filename(f)
        target = assets_path / f
    else:
        target = _get_local_image_path(assets_path, proj.image_url or "")

    deleted = False
    if target and target.exists():
        target.unlink()
        deleted = True

    # Clear project image_url if it pointed to the deleted file
    if proj.image_url and proj.image_url.startswith("local:"):
        deleted_name = f if f else proj.image_url[6:]
        if proj.image_url == f"local:{deleted_name}":
            db.update_project(project, image_url=None)

    _invalidate_project_caches()
    return {"deleted": deleted}


# ── Startup: Resume polling for incomplete jobs ─────────────────────

def resume_polling_job(job):
    """Resume polling for a job that was interrupted (e.g., server restart)."""
    db = get_db()
    api_key = os.getenv("POLLO_API_KEY")

    if not api_key:
        db.update_job(job.job_id, status="error", message="Cannot resume: API key not configured")
        return

    print(f"[Startup] Resuming polling for job {job.job_id} (task {job.task_id})")

    # Touch updated_at so the stale-job recovery doesn't interfere
    db.update_job(job.job_id, message="Resuming after restart...")

    def _check_already_resolved():
        """Return True to abort polling if another path resolved this job."""
        current = db.get_job(job.job_id)
        if current and current.status in ("done", "error"):
            if current.status == "done" and current.video_url and not current.video_path:
                # Recovered to "done" but no file → continue to download
                return False
            print(f"[Job {job.job_id}] Already resolved (status={current.status}), stopping", flush=True)
            return True
        return False

    try:
        results = _poll_task(job.job_id, job.task_id, api_key,
                             on_poll=_check_already_resolved)

        if results is None:
            # Polling aborted — check if job was recovered to done-without-file
            current = db.get_job(job.job_id)
            if not (current and current.status == "done" and current.video_url and not current.video_path):
                return  # Error already recorded or job fully resolved by another path
            url = current.video_url
            print(f"[Job {job.job_id}] Recovered to done without video, downloading...", flush=True)
        else:
            video_urls = _result_urls(results)
            if not video_urls:
                db.update_job(job.job_id, status="error", message="No video URL in result")
                return
            url = video_urls[0]

        db.update_job(job.job_id, status="downloading", message="Downloading video...", video_url=url)

        _download_and_complete_job(job.job_id, url, label="resume")

    except Exception as e:
        db.update_job(job.job_id, status="error", message=f"Resume failed: {str(e)}")


def startup_resume_jobs():
    """On server start, resume polling for any jobs stuck in processing."""
    db = get_db()

    # Clean up orphaned thumbnail cache files
    _cleanup_thumb_cache()

    # Find jobs that have a task_id but are still processing
    processing_jobs = [j for j in db.get_active_jobs() if j.task_id and j.status == "processing"]

    if processing_jobs:
        print(f"[Startup] Found {len(processing_jobs)} incomplete job(s) to resume")
        for job in processing_jobs:
            threading.Thread(target=resume_polling_job, args=(job,), daemon=True).start()
    else:
        print("[Startup] No incomplete jobs to resume")


# ── VPN (Gluetun) control ─────────────────────────────────────────────
# Docs: https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md
GLUETUN_API = "http://127.0.0.1:8000"
GLUETUN_API_KEY = os.getenv("GLUETUN_API_KEY", "")
_GLUETUN_HEADERS = {"X-API-Key": GLUETUN_API_KEY} if GLUETUN_API_KEY else {}

ALLOWED_VPN_COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Australia",
    "Germany", "France", "Netherlands", "Japan", "Singapore",
    "Switzerland", "Sweden", "Brazil", "India", "South Korea",
    "Italy", "Spain", "Norway", "Denmark", "Ireland",
]


def _gluetun_get(path: str, timeout: int = 3):
    return _requests.get(f"{GLUETUN_API}{path}", headers=_GLUETUN_HEADERS, timeout=timeout)


def _gluetun_put(path: str, body: dict, timeout: int = 5):
    return _requests.put(f"{GLUETUN_API}{path}", json=body, headers=_GLUETUN_HEADERS, timeout=timeout)


@app.get("/api/vpn/status")
def vpn_status(_api_key: str = Depends(verify_api_key)):
    """Get current VPN status, public IP, and settings from Gluetun."""
    out: dict[str, Any] = {}
    # VPN tunnel status
    try:
        r = _gluetun_get("/v1/vpn/status")
        out["vpn"] = r.json() if r.ok else {"status": "unknown"}
    except Exception:
        out["vpn"] = {"status": "unreachable"}
    # Public IP (also contains country/region info)
    try:
        r = _gluetun_get("/v1/publicip/ip", timeout=5)
        out["public_ip"] = r.json() if r.ok else {}
    except Exception:
        out["public_ip"] = {}
    # Current server country from settings (with public_ip country as fallback)
    try:
        r = _gluetun_get("/v1/vpn/settings")
        if r.ok:
            settings = r.json()
            out["server_countries"] = settings.get("server_countries", [])
        else:
            out["server_countries"] = []
    except Exception:
        out["server_countries"] = []
    # Fallback: if settings returned no country, use country from public IP lookup
    if not out["server_countries"] and out["public_ip"].get("country"):
        out["server_countries"] = [out["public_ip"]["country"]]
    return out


@app.post("/api/vpn/restart")
def vpn_restart(_api_key: str = Depends(verify_api_key)):
    """Restart the VPN tunnel by cycling Gluetun's status off then on."""
    try:
        _gluetun_put("/v1/vpn/status", {"status": "stopped"})
        time.sleep(2)
        r = _gluetun_put("/v1/vpn/status", {"status": "running"})
        if r.ok:
            return {"ok": True, "message": "VPN tunnel restarted — new IP in ~10s"}
        return {"ok": False, "message": f"Gluetun responded {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, detail=f"Cannot reach Gluetun control server: {e}")


@app.put("/api/vpn/country")
def vpn_change_country(data: VpnCountryRequest, _api_key: str = Depends(verify_api_key)):
    """Change VPN server country. Body: {"country": "United Kingdom"}"""
    country = data.country.strip()
    if not country:
        raise HTTPException(400, detail="Missing 'country' field")
    if country not in ALLOWED_VPN_COUNTRIES:
        raise HTTPException(
            400,
            detail=f"Invalid country: '{country}'. Allowed: {', '.join(ALLOWED_VPN_COUNTRIES)}",
        )
    try:
        # Update server selection
        r = _gluetun_put("/v1/vpn/settings", {"server_countries": [country]})
        if not r.ok:
            return {"ok": False, "message": f"Gluetun responded {r.status_code}: {r.text}"}
        return {"ok": True, "message": f"Switching to {country} — new IP in ~10s"}
    except Exception as e:
        raise HTTPException(502, detail=f"Cannot reach Gluetun control server: {e}")


@app.get("/api/vpn/countries")
def vpn_countries():
    """Return the list of allowed VPN server countries."""
    return {"countries": ALLOWED_VPN_COUNTRIES}


# ── Chat mode (OpenRouter) — see web/chat.py ─────────────────────────
# Must be registered before the SPA catch-all below.
app.include_router(chat_router)
app.include_router(characters.router)


# ── Serve Vue frontend (production build) ────────────────────────────
STATIC_DIR = WEB_DIR / "static"


def _static_file(path: str, static_dir: Path = STATIC_DIR) -> Path:
    """Map a request path to a file in the SPA build, falling back to index.html.

    Resolved and confined to static_dir: encoded "../" (e.g. /..%2F.env)
    reaches us un-normalised and would otherwise escape the directory.
    """
    file = (static_dir / path).resolve()
    if file.is_relative_to(static_dir.resolve()) and file.is_file():
        return file
    return static_dir / "index.html"


if STATIC_DIR.is_dir():
    # Serve static assets (js, css, etc.)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{path:path}")
    def serve_frontend(path: str):
        """Catch-all: serve the Vue SPA index.html for any non-API route."""
        return FileResponse(_static_file(path))


# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Starting Pollo API Server...")
    print("API: http://localhost:5000")
    print("Docs: http://localhost:5000/docs")
    uvicorn.run(app, host="127.0.0.1", port=5000)
