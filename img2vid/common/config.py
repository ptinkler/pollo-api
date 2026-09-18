"""
Shared configuration — single source of truth for data paths and API settings.

All modules that need ROOT_DIR, ASSETS_DIR, DB_PATH, or API constants should
import from here instead of computing them independently.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project root (the pollo-api directory)
_PROJECT_ROOT = Path(__file__).parent.parent.parent

# Support external data directory via POLLO_DATA_DIR env var
ROOT_DIR = Path(os.environ.get("POLLO_DATA_DIR", _PROJECT_ROOT))
ASSETS_DIR = ROOT_DIR / "assets"
DB_PATH = ROOT_DIR / "data" / "metadata.db"

# Pollo API settings
POLLO_API_BASE = "https://pollo.ai/api/platform/generation"
# Newer "v1" API surface (https://docs.pollo.ai) — same account/key, but a
# different URL shape (/v1/generation/{provider}/{model}/video|image) and,
# per model, a different provider slug (e.g. "wanx" -> "alibaba",
# "seedream" -> "bytedance") and payload schema than the pre-v1 endpoints
# under POLLO_API_BASE, which Pollo now calls the "legacy" API.
POLLO_API_V1_BASE = "https://pollo.ai/api/platform/v1/generation"
POLLO_API_TIMEOUT = 30  # per-request timeout in seconds for individual HTTP calls

