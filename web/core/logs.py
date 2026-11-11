"""Application logging.

One place to configure it, so every module can simply do:

    import logging
    log = logging.getLogger(__name__)

The level comes from LOG_LEVEL (default INFO). Under uvicorn these go to the
same stream as its own logs; uvicorn's loggers keep their own handlers and
don't propagate, so configuring the root logger here doesn't disturb them.

Command-line output (web/provision_admin.py, `python -m web.api`) stays on
print(): it is talking to the person who ran it, not recording what the
server did.
"""

import logging
import os
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup() -> None:
    """Configure logging once, at startup."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format=_FORMAT,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
