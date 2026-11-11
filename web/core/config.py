"""Shared configuration — single source of truth for data paths and API settings.

All modules that need ROOT_DIR, ASSETS_DIR, DB_PATH, or API constants should
import from here instead of computing them independently.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root (the pollo-api directory)
_PROJECT_ROOT = Path(__file__).parent.parent.parent

# The one .env load for the whole app, by absolute path (so it doesn't depend
# on the working directory) and WITHOUT override: a variable already in the
# environment — docker-compose's env_file, the Dockerfile's ENV, a shell
# export — beats the file. Overriding hid POLLO_DATA_DIR in containers.
load_dotenv(_PROJECT_ROOT / ".env")

# Support external data directory via POLLO_DATA_DIR env var
ROOT_DIR = Path(os.environ.get("POLLO_DATA_DIR", _PROJECT_ROOT))
ASSETS_DIR = ROOT_DIR / "assets"
DB_PATH = ROOT_DIR / "data" / "metadata.db"

# Pollo API settings. Three bases, because Pollo splits them that way:
# the account/config endpoints sit at the platform root, task status under
# /generation, and the generation endpoints under /v1/generation.
POLLO_PLATFORM_BASE = "https://pollo.ai/api/platform"
POLLO_TASK_BASE = f"{POLLO_PLATFORM_BASE}/generation"
# Generation endpoints (https://docs.pollo.ai): /{provider}/{model}/video|image
# |audio, where the provider is a slug per model ("wanx" -> "alibaba",
# "seedream" -> "bytedance"). Each has a free ".../estimate" price-check twin.
POLLO_GENERATION_BASE = f"{POLLO_PLATFORM_BASE}/v1/generation"
# Pollo bills in credits; its API converts them to USD at this fixed rate (costUsd in a task's status)
POLLO_USD_PER_CREDIT = 0.06
POLLO_API_TIMEOUT = 30  # per-request timeout in seconds for individual HTTP calls
