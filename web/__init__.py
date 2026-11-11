"""Pollo Studio backend.

Python runs this before any `web.*` module, so it is where the process gets
prepared: importing web.core.config loads .env (by absolute path), and logging
is configured once. That guarantee is what lets every module below use plain
top-level imports in any order — no bootstrap wedged into an import block, no
"import this first" comments, no E402.
"""

from web.core import config
from web.core.logs import setup as _setup_logging

_setup_logging()

__all__ = ["config"]
